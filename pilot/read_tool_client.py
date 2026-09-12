"""Strict MCP-to-host client for the literal-loopback public-read route."""
import json
import threading
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from pilot.open_web_reader import PublicReadError, normalize_public_url, valid_page_evidence

_MAX_RESPONSE_BYTES=300_000
_ALLOWED={"invalid_url","unavailable","unsupported_content","too_large","timeout"}


class ReadToolClient:
    def __init__(self, *, url, token):
        try:
            parts=urlsplit(url)
            if (type(url) is not str or parts.scheme!="http" or parts.hostname!="127.0.0.1"
                or parts.port is None or not 1<=parts.port<=65535 or parts.netloc!=f"127.0.0.1:{parts.port}"
                or parts.path!="/v1/public-read" or parts.query or parts.fragment
                or type(token) is not str or not 1<=len(token)<=256 or any(c.isspace() for c in token)):
                raise ValueError
        except (ValueError,TypeError,AttributeError):
            raise ValueError("invalid_read_configuration") from None
        self._url,self._token=url,token

    def read(self,url,*,deadline):
        try:
            normalized=normalize_public_url(url)
            if not isinstance(deadline,datetime) or deadline.tzinfo is None or deadline.utcoffset() is None:
                raise PublicReadError("invalid_url")
            remaining=(deadline.astimezone(timezone.utc)-datetime.now(timezone.utc)).total_seconds()
            if remaining<=0: raise PublicReadError("timeout")
            timeout=min(21.0,remaining)
            expires_at = min(
                deadline.astimezone(timezone.utc),
                datetime.now(timezone.utc) + timedelta(seconds=timeout),
            )

            def reject_if_expired():
                if datetime.now(timezone.utc) >= expires_at:
                    raise PublicReadError("timeout")

            with httpx.Client(timeout=timeout,trust_env=False,follow_redirects=False) as client:
                timer=threading.Timer(timeout,client.close); timer.daemon=True; timer.start()
                try:
                    with client.stream("POST",self._url,headers={"Authorization":"Bearer "+self._token},json={"url":normalized}) as response:
                        if response.status_code!=200: raise PublicReadError("unavailable")
                        chunks=[]; size=0
                        for chunk in response.iter_bytes():
                            reject_if_expired()
                            size+=len(chunk)
                            if size>_MAX_RESPONSE_BYTES: raise PublicReadError("unavailable")
                            chunks.append(chunk)
                    reject_if_expired()
                    value=json.loads(b"".join(chunks))
                    reject_if_expired()
                finally: timer.cancel()
            if type(value) is not dict:
                raise PublicReadError("unavailable")
            if set(value)=={"status","code","replayed"} and value["status"]=="FAILED" and type(value["replayed"]) is bool:
                raise PublicReadError(value["code"] if value["code"] in _ALLOWED else "unavailable")
            if set(value)!={"status","evidence","review_status","replayed"} or value["status"]!="READ" or value["review_status"]!="UNREVIEWED" or type(value["replayed"]) is not bool or not valid_page_evidence(value["evidence"],normalized):
                raise PublicReadError("unavailable")
            reject_if_expired()
            return value["evidence"]
        except PublicReadError: raise
        except Exception: raise PublicReadError("unavailable") from None
