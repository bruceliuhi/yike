# 阿里云验证码接入

当前目标是正式短信验证，不启用手机号后四位或体验码替代身份认证。用户已提供控制台截图：模板 `SMS_512095645` 审核通过、状态正常，签名“北京星河卓越科技有限公司”，单一数字变量 `code`。

模板内容：“验证码为：${code}，您正在注册成为平台会员，感谢您的支持！”如后续另需登录文案，应申请对应正式模板；本实现不修改阿里云控制台模板。

## 配置

在**客户服务**的私有环境文件配置以下名称，不放入 Git、客户端、日志、命令参数或聊天。此处只有公开配置值，故意不提供密钥样例值：

```dotenv
YIKE_SMS_PROVIDER=aliyun
YIKE_SMS_SIGN_NAME=北京星河卓越科技有限公司
YIKE_SMS_TEMPLATE_CODE=SMS_512095645
YIKE_SMS_CODE_PARAMETER=code
```

同一私有文件还需 `ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET` 和独立的 `YIKE_PILOT_PHONE_AUTH_SECRET`（32～4096 bytes），如使用 STS 则另配 `ALIBABA_CLOUD_SECURITY_TOKEN`。使用专用 RAM 身份和最小短信发送权限；不要使用阿里云主账号密钥。长效AccessKey需要由部署者安全配置、轮换；本片不提供动态RAM角色凭据自动刷新。

运营服务的 `YIKE_OPS_DATABASE_URL`、手机号解密密钥和管理员密码不能传给客户runtime；其开通、签发权益码、停用流程见 [OPS_ADMIN](OPS_ADMIN.md)。已开通手机号才可能请求验证码，未知号码统一受理形状但不向供应商发信。

无 `YIKE_SMS_PROVIDER` 时不会发送短信；显式启用却缺配置或格式错误时拒绝启动。仅模板审核通过不代表已配置凭据、已获短信发送权限或手机可以收码。SDK启动不调用短信接口，也不打印配置值。

禁止设置 `DEBUG=sdk`（大小写不敏感）：官方SDK该模式会打印敏感请求。适配器在配置、构造和每次发送前均拒绝此模式，不自动改环境；运行时不应启用任何记录完整短信请求/响应的调试或代理日志。

## 发送与失败语义

- 官方SDK固定HTTPS、国内短信endpoint、单个号码与6位验证码；模板参数绑定已确认的 `code`。
- 单次请求关闭自动重试，连接5秒、读取10秒超时。供应商明确受理记ACCEPTED，明确拒绝记REJECTED，超时/异常/不可信响应记UNKNOWN，不自动重发。
- ACCEPTED不等于手机送达。原持久冷却、发送额度、验证码5分钟过期、猜测上限和一次性消费保持不变。
- 客户端仍使用手机号＋真实6位验证码；首次trial还需运营发放的权益码。后续短信登录不延长已激活的试用期限。

## 上线顺序与验收

1. 先按现有维护流程执行含136的迁移和受限runtime授权，部署绑定本批代码及锁文件的服务镜像；不能只改env便声称旧镜像已有adapter。
2. 在服务器私有文件配置完整发送参数与密钥，通过既有进程/容器环境机制加载，不把秘密置于shell argv。检查HTTPS与 `/api/ui/capabilities` 中 `sms_login.available`。
3. 在运营后台预开通一个经用户批准的真实测试手机号。由其本人请求验证码并在客户端输入；不将OTP复制到聊天或保存截图。
4. 记录供应商受理、实际收到、输入成功、首次权益激活、后续登录、退出/过期拒绝的结果，绑定服务器SHA、客户端版本与时间；不记录完整号码、码或Cookie。
5. 撤销测试trial时核对旧会话失效。若需关闭短信，移除provider启用项并按原部署流程重启；不切换为假验证码。

2026-09-11：本批源码056e258与正式SMS配置已部署到既有HTTPS服务，36项迁移/授权和候选、正式受限DB检查通过，公网能力为available；[唯一部署事实与未验项](../docs/qa/SERVER_137138_DEPLOYMENT.md#当前部署056e258正式短信配置已装配2026-09-11)。未完成真实短信发送/手机收码或客户验收；ops尚未部署，Web `/session` 仍为token入口，不表示任意手机号已可自助开通。

依据：[SendSms官方接口](https://help.aliyun.com/zh/sms/developer-reference/api-dysmsapi-2017-05-25-sendsms)、[官方SDK接入](https://help.aliyun.com/zh/sms/developer-reference/how-to-use-api-quickly)。
