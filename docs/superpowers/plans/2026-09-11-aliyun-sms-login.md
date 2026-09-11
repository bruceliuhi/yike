# Aliyun SMS login implementation plan

> **For agentic workers:** Use subagent-driven-development/TDD; root alone stages and pushes. One whole-batch independent review and targeted tests, no repeated full builds.

**Goal:** 已开通客户与新trial可经真实阿里云验证码登录；不再等待不存在的短信适配器，不实现后四位替代认证。

**Architecture:** 实现既有 `SmsSender.send_code(phone,code)->bool`，复用 OTP 预留/冷却/消费、手机号绑定、trial权益和原会话。正式runtime只在显式完整配置后装配；发送未知不自动重试，不宣称供应商受理就是手机送达。

**Tech Stack:** 官方 `alibabacloud-dysmsapi20170525==4.6.0`（本日PyPI已核验）、当前Python服务，无前端新增依赖。

## 需求与约束

- 用户截图确认模板 `SMS_512095645` 审核通过且状态正常、签名“北京星河卓越科技有限公司”，内容为“验证码为：${code}，您正在注册成为平台会员，感谢您的支持！”。唯一变量 `code` 为数字，部署时明确配置 `YIKE_SMS_CODE_PARAMETER=code`；仍未实际发送或完成手机收码验收。模板为注册措辞，后续若要单独登录文案应使用另一个正式获批模板，不自行修改供应商模板。
- 固定 HTTPS `dysmsapi.aliyuncs.com`，固定 SendSms，单个国内号码/单个6位ASCII验证码；不用外部输入控制endpoint、模板或签名。不批量发送。
- `YIKE_SMS_PROVIDER=aliyun` 显式启用，完整配置 `YIKE_SMS_SIGN_NAME`、`YIKE_SMS_TEMPLATE_CODE`、`YIKE_SMS_CODE_PARAMETER`、`ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`，可选 `ALIBABA_CLOUD_SECURITY_TOKEN`；另需既有 `YIKE_PILOT_PHONE_AUTH_SECRET`。只通过服务端私有env配置，不把ops专用凭据带到runtime。
- 无provider默认不装配；未知provider或已启用但缺字段拒绝启动。仅提供模板/签名不启动网络调用。模板参数仅支持本次OTP单变量；若实际模板要求额外参数，先按真实模板扩展，不吞缺项。
- 官方SDK显式关闭自动重试，连接5000ms、读取10000ms，固定协议HTTPS和域名；SDK异常/未知/结构错误只抛固定脱敏异常交给原phone_api记录UNKNOWN。只识别明确 `Code=OK` 为受理；明确正常业务拒绝为false。任何错误不回显SDK正文、号码、OTP或AccessKey。
- 官方依赖及uv.lock一并固定；测试用精确SDK模型/受控传输，不以替身声称短信真正送达。

### Task 1: 官方SMS适配器及正式runtime接线

**Files:** 新增 `pilot/aliyun_sms.py`、`tests/test_aliyun_sms.py`、`deploy/ALIYUN_SMS.md`；修改 `pyproject.toml`、`uv.lock`、`pilot/runtime.py`、`tests/test_runtime_composition.py`（按实际已有命名定位）、`deploy` 当前示例配置与任务书。先只新增adapter独立文件，等ops候选精确审核/合入后接runtime，不碰其未提交clone。

**Interfaces:**

```python
class AliyunSmsSender:
    # configuration fields validated once; secret repr/log suppression
    def send_code(self, phone: str, code: str) -> bool: ...

def configured_sms_sender(environment: Mapping[str,str]) -> AliyunSmsSender | None: ...
```

- [ ] RED严格配置/单号码与6位OTP、无provider静默关闭/启用缺项固定失败；SDK调用固定endpoint/模板/签名/单变量，禁重试与超时；OK/业务拒绝/未知与异常脱敏、恰好一次调用。
- [ ] 最小adapter实现并用安装的真实SDK接口核验配置和请求（网络替身）；修依赖并生成锁，避免自己实现阿里云签名。
- [ ] ops136基础独立审核/合入后，真实build_runtime_app从显式env装配；无provider仍关闭，可信手动sender注入与provider配置不能悄悄冲突。测试正式capabilities/SMS请求到adapter，不用直接测试helper冒充CLI已接通。
- [ ] 检查SMS/试用相关定向回归、一次独立整批审核；写精确证据与部署说明，串行push main。
- [ ] 实际服务器配置由用户/授权部署流程提供签名、变量与私有凭据；真实手机收码、首次trial激活及后续登录须另验。没有真实授权目标号码不主动发送短信，不将源码接线称作上线。

## 官方依据

[官方SDK接入](https://help.aliyun.com/zh/sms/developer-reference/how-to-use-api-quickly)、[SendSms接口](https://help.aliyun.com/zh/sms/developer-reference/api-dysmsapi-2017-05-25-sendsms)、[SDK超时](https://help.aliyun.com/en/sdk/developer-reference/configure-a-timeout-period)。模板与签名分别传入，API受理与送达分开。

## Evidence

实施中，尚无生产发送或收码证据。
