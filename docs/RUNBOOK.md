# 意客 AI DISCOVERY MVP 本地运行手册

本手册覆盖 B 站＋抖音授权数据的本地采集、AI 评分、人工复核、草稿、人工联系事实登记和导出。二维码、验证码和风控提示只在可见浏览器中由操作人处理；系统不自动发送，也不绕过平台限流或风控。

## 1. 代码门禁

```bash
cd "/Users/xingheimac/Developer/Work/意客AI-MVP"
./scripts/check.sh
```

门禁执行 frozen 依赖同步、全量 pytest、Python compileall、JavaScript 语法检查和 `git diff --check`。它只证明代码候选，不证明真实采集或 14 天业务结果。

## 2. 本机配置

在仓库根目录创建被 Git 忽略的 `.env.local`，只在本机填写真实值：

```bash
cd "/Users/xingheimac/Developer/Work/意客AI-MVP"
cat > .env.local <<'ENV'
YIKE_RUNTIME_ROOT=/Users/xingheimac/Developer/Runtime/yike-discovery
YIKE_MVP_ROOT=/Users/xingheimac/Developer/Runtime/yike-discovery/app
YIKE_MEDIACRAWLER_PATH=/Users/xingheimac/Developer/Runtime/yike-discovery/mediacrawler-43950978
DISCOVERY_MODEL_BASE_URL=https://your-openai-compatible-endpoint.example/v1
DISCOVERY_MODEL_API_KEY=replace-in-local-file-only
DISCOVERY_MODEL_NAME=replace-with-model-name
ENV
chmod 600 .env.local
set -a
source .env.local
set +a
mkdir -p "$YIKE_RUNTIME_ROOT"
```

`.env.local`、Cookie、Profile、二维码、Token 和 API Key 不得写入 Git、SQLite、普通日志或导出。

## 3. 获取固定 MediaCrawler runtime

目标路径必须尚不存在。脚本会检出固定 commit、应用受控补丁、校验摘要并安装 Chromium：

```bash
./scripts/fetch_mediacrawler.sh "$YIKE_MEDIACRAWLER_PATH"
```

不要覆盖或手改已有 runtime；需要重建时使用新的空路径，并更新 `.env.local`。

## 4. 初始化并启动

```bash
uv sync --frozen --extra dev
uv run --frozen python -c 'from app.config import Settings; from app.repository import Repository; r=Repository.from_settings(Settings.from_env()); r.connection.close(); print("SQLite migration: OK")'
uv run --frozen yike-web
```

服务只监听 [http://127.0.0.1:8766/runs](http://127.0.0.1:8766/runs)。在“运行”页创建双平台实验，然后在另一个已加载 `.env.local` 的终端取得 ACTIVE run：

```bash
export MVP_RUN_ID="$(uv run --frozen python -c "from app.config import Settings; from app.repository import Repository; r=Repository.from_settings(Settings.from_env()); row=r.connection.execute(\"SELECT mvp_run_id FROM mvp_runs WHERE state='ACTIVE'\").fetchone(); r.connection.close(); print(row[0] if row else '')")"
test -n "$MVP_RUN_ID"
printf 'ACTIVE mvp_run_id=%s\n' "$MVP_RUN_ID"
```

## 5. 双平台三关键词采集

每条命令创建一个新 attempt；进度只写 stderr，stdout 只写一行终态 JSON。

B 站：

```bash
uv run --frozen yike-collector collect --platform bili --mvp-run-id "$MVP_RUN_ID" --query-cluster acquisition --query-text "B2B 销售获客" --max-contents 5 --max-comments-per-content 20 --started-by operator
uv run --frozen yike-collector collect --platform bili --mvp-run-id "$MVP_RUN_ID" --query-cluster qualification --query-text "销售线索筛选" --max-contents 5 --max-comments-per-content 20 --started-by operator
uv run --frozen yike-collector collect --platform bili --mvp-run-id "$MVP_RUN_ID" --query-cluster follow-up --query-text "CRM 跟进自动化" --max-contents 5 --max-comments-per-content 20 --started-by operator
```

抖音：

```bash
uv run --frozen yike-collector collect --platform dy --mvp-run-id "$MVP_RUN_ID" --query-cluster acquisition --query-text "B2B 销售获客" --max-contents 5 --max-comments-per-content 20 --started-by operator
uv run --frozen yike-collector collect --platform dy --mvp-run-id "$MVP_RUN_ID" --query-cluster qualification --query-text "销售线索筛选" --max-contents 5 --max-comments-per-content 20 --started-by operator
uv run --frozen yike-collector collect --platform dy --mvp-run-id "$MVP_RUN_ID" --query-cluster follow-up --query-text "CRM 跟进自动化" --max-contents 5 --max-comments-per-content 20 --started-by operator
```

在可见浏览器中人工扫码。出现验证码或风控时停止并人工处理，不使用自动求解、代理池、账号池或隐藏浏览器。B 站与抖音分别验收：每批至少 5 条可重开真实 Signal；重跑一个关键词后 Signal 数不增加、observation 数增加。

重跑前后分别记录：

```bash
uv run --frozen python -c 'import os; from app.config import Settings; from app.repository import Repository; r=Repository.from_settings(Settings.from_env()); run_id=os.environ["MVP_RUN_ID"]; print({"signals":r.count_signals(run_id),"observations":r.count_observations(run_id)}); r.connection.close()'
```

缺少账号、扫码、浏览器或平台响应时，按平台分别记录精确 `BLOCKED_INPUT`；fixture 和另一平台的结果不能替代。

## 6. 严格 AI 评分

加载三个 `DISCOVERY_MODEL_*` 变量后，对尚无成功评分的 Signal 执行：

```bash
uv run --frozen python - <<'PY'
import json
import os
from app.config import Settings
from app.model_client import model_client_from_env
from app.repository import Repository
from app.scorer import Scorer

client = model_client_from_env()
if client is None:
    raise SystemExit("BLOCKED_INPUT: MODEL_NOT_CONFIGURED")
repository = Repository.from_settings(Settings.from_env())
try:
    run_id = os.environ["MVP_RUN_ID"]
    rows = repository.connection.execute(
        """SELECT member.signal_id FROM mvp_run_signals AS member
           WHERE member.mvp_run_id = ?
             AND NOT EXISTS (
               SELECT 1 FROM score_runs AS score
               WHERE score.mvp_run_id = member.mvp_run_id
                 AND score.signal_id = member.signal_id
                 AND score.status = 'SUCCEEDED')
           ORDER BY member.added_at, member.signal_id""",
        (run_id,),
    ).fetchall()
    scorer = Scorer(repository, client)
    for row in rows:
        result = scorer.score(run_id, row["signal_id"])
        print(json.dumps({"signal_id": row["signal_id"],
                          "score_run_id": result.score_run_id,
                          "status": result.status,
                          "error_code": result.error_code},
                         ensure_ascii=False, separators=(",", ":")))
finally:
    repository.connection.close()
PY
```

模型输出不满足严格 Schema 时记录失败事实，不降级生成 A/B。

## 7. 人工复核、草稿和联系登记

```bash
open "http://127.0.0.1:8766/signals?run_id=$MVP_RUN_ID"
```

对每条候选依次操作：

1. 打开详情页和原评论链接，人工核对正文、父评论与来源。
2. 选择人工标签，填写原因、备注与有效处理时间并保存复核。
3. 编辑不超过 180 字的个性化草稿并保存。
4. 操作人在平台或明确公开的商务入口逐条发送；工作台不代发。
5. 回到详情页，填写实际文本、时间、主体键和来源 URL，确认已打开来源后登记 `SENT_VERIFIED`。
6. 在“跟进”页只登记真实发生且已人工核验的回复、访谈和报价机会。

草稿、fixture、模拟回复或仅打开链接都不能登记为已联系。

## 8. 指标与导出

```bash
open "http://127.0.0.1:8766/metrics?run_id=$MVP_RUN_ID"
mkdir -p "$YIKE_RUNTIME_ROOT/exports"
curl --fail --silent --show-error \
  --output "$YIKE_RUNTIME_ROOT/exports/$MVP_RUN_ID-signals.csv" \
  "http://127.0.0.1:8766/exports/signals.csv?run_id=$MVP_RUN_ID"
shasum -a 256 "$YIKE_RUNTIME_ROOT/exports/$MVP_RUN_ID-signals.csv"
```

指标只从 SQLite 事实计算。CSV 不含登录态或模型密钥，但含公开作者标识和原文，只用于本轮授权实验。

## 9. 暂停与重试

| 结果 | 操作 |
|---|---|
| `SUCCEEDED` | 核对数量和可重开链接；它本身不等于真实验收 PASS。 |
| `SUCCEEDED_NO_DATA` | 保留空结果；需要时由操作人发起新 attempt。 |
| `PLATFORM_AUTH_REQUIRED` | 可见浏览器人工登录/扫码后，手工发起新 attempt。 |
| `PLATFORM_VERIFICATION_REQUIRED` | 停止并人工处理验证，不自动求解。 |
| `PLATFORM_RATE_LIMITED` | 按平台提示等待，不并发、不切换代理或账号绕过。 |
| `PLATFORM_PERMISSION_DENIED` | 核对授权与权限；未解决时保持 `BLOCKED_INPUT`。 |
| `COLLECTION_RUNTIME_MISSING` / `COLLECTION_RUNTIME_MISMATCH` | 按第 3 节在新路径重建 runtime。 |
| `COLLECTION_NETWORK_FAILED` | 人工核对网络后显式发起新 attempt，不自动重试。 |
| `PLATFORM_RESPONSE_CHANGED` / `COLLECTION_PARSE_FAILED` | 停止对应批次；修复并通过代码门禁前不重试。 |
| `COLLECTION_CANCELLED` | 保留取消事实；需要继续时显式创建新 attempt。 |
| `MODEL_NOT_CONFIGURED` / `MODEL_UNAVAILABLE` | 单独记录模型 `BLOCKED_INPUT`，不用规则或 fixture 伪造分数。 |

所有重试都是新的只追加 attempt，不覆盖旧事实。自动门禁、空库页面、fixture 和单平台证据都不得升级为 `REAL_COLLECTION_*` 或 14 天结论。
