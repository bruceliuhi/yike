"""Read-only customer management; no device binding, backup or update authority."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException, Request


MAX_EXPORT_BYTES = 2 * 1024 * 1024
MAX_EXPORT_ROWS = 1000
CSV_HEADERS = ('商机标题', '需求方', '来源平台', '意向状态', '来源状态',
               '来源页面（不含参数）', '来源时间', '更新时间')


def _error(status, code, message):
    return HTTPException(status, {'code': code, 'message': message})


def _too_large():
    return _error(413, 'management_export_too_large',
                  '导出超过1000条或2 MiB上限，未生成部分文件。请在商机库筛选、勾选记录，使用“导出所选客户商机”。')


def _cell(value):
    text = value.isoformat() if hasattr(value, 'isoformat') else str(value or '')
    if '\0' in text:
        raise _error(409, 'management_export_invalid', '商机数据包含无法导出的字符，请联系支持核对。')
    return "'" + text if re.match(r'^\s*[=+\-@\t\r]', text) else text


def _public_page(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return ''
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
    except (ValueError, TypeError):
        return ''


def register_management_read_api(router, store, identity, require_session_https):
    def current(request, allowed_query):
        require_session_https(request)
        owner = identity(request)
        if owner.claims is None:
            raise _error(401, 'invalid_session', '请重新登录。')
        if list(request.query_params.multi_items()) != allowed_query:
            raise _error(422, 'invalid_request', '请求字段无效。')
        return owner.claims

    @router.get('/management/account')
    def account(request: Request):
        claims = current(request, [])
        with store.database.connect() as connection, connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            tenant = store.sessions.require_active(cursor, claims)
            # Existing trial column grants only: never read phone/code/ciphertext.
            cursor.execute('SELECT activated_at,expires_at,revoked_at FROM pilot_trial_accounts WHERE user_id=%s',
                           (claims.user_id,))
            trial = cursor.fetchone()
            license_state = {'status': 'UNKNOWN', 'expiresAt': None}
            if trial is not None:
                activated, expires, revoked = trial
                # require_active already rejected expired, revoked or inactive trials.
                if activated is not None and expires is not None and revoked is None:
                    license_state = {'status': 'ACTIVE', 'expiresAt': expires.isoformat()}
            store.sessions.require_active(cursor, claims)
        result = {'userId': claims.user_id, 'accountScope': {'id': tenant, 'version': 1},
                  'spaceId': tenant, 'spaceName': '当前客户空间', 'license': license_state, 'device': None}
        revision = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return {**result, 'revision': revision}

    @router.get('/management/export')
    def export(request: Request):
        kind = request.query_params.get('kind')
        claims = current(request, [('kind', kind)] if kind is not None else [])
        if kind == 'backup-json':
            raise _error(501, 'management_unavailable', '客户备份恢复尚未接通，没有执行更改。')
        if kind != 'csv':
            raise _error(422, 'invalid_request', '仅支持商机CSV导出。')
        with store.database.connect() as connection, connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION READ ONLY')
            tenant = store.sessions.require_active(cursor, claims)
            # Match the research library: captured raw opportunities remain owner
            # private, while legacy imported opportunities are tenant shared.
            # Select only business columns; never serialize an entire DB row.
            cursor.execute('''SELECT o.title,o.buyer,s.platform,o.intent_status,o.source_status,
                    s.public_url,s.published_at,o.updated_at
                FROM pilot_opportunities o JOIN pilot_sources s USING(tenant_id,source_id)
                LEFT JOIN pilot_opportunity_evidence e USING(tenant_id,opportunity_id)
                WHERE o.tenant_id=%s AND (e.opportunity_id IS NULL OR e.included_by_user_id=%s)
                ORDER BY o.created_at DESC,o.opportunity_id LIMIT %s''',
                (tenant, claims.user_id, MAX_EXPORT_ROWS + 1))
            rows = cursor.fetchall()
            if len(rows) > MAX_EXPORT_ROWS:
                raise _too_large()
            output = io.StringIO(newline='')
            output.write('\ufeff')
            writer = csv.writer(output, lineterminator='\r\n')
            writer.writerow(CSV_HEADERS)
            byte_count = len(output.getvalue().encode('utf-8'))
            for row in rows:
                values = list(row)
                values[5] = _public_page(values[5])
                line = io.StringIO(newline='')
                csv.writer(line, lineterminator='\r\n').writerow([_cell(value) for value in values])
                text = line.getvalue()
                byte_count += len(text.encode('utf-8'))
                if byte_count > MAX_EXPORT_BYTES:
                    raise _too_large()
                output.write(text)
            result = {'userId': claims.user_id, 'accountScope': {'id': tenant, 'version': 1},
                      'spaceId': tenant, 'name': '意客AI-客户商机.csv', 'content': output.getvalue()}
            # JSON escaping can be larger than the CSV and must fit the same IPC limit.
            if len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode()) > MAX_EXPORT_BYTES:
                raise _too_large()
            store.sessions.require_active(cursor, claims)
            return result
