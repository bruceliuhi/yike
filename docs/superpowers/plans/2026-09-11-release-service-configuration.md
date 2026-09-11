# 客户服务分发配置与部署准备

> For agentic workers: executing-plans、定向TDD及一次非作者审核。服务端/Windows客户端架构已批准，不新增UI。

**Goal:** 正式构包必须绑定HTTPS服务，客户双击无需环境变量；保留明确开发路径，不写入服务密钥。
**Architecture:** build/releaseService.ts复用configuredService校验公开origin；Forge make缺配置即拒绝，Vite把origin编译进main；新main/clientServiceConfiguration.ts在正式包只用内置origin，开发版继续旧环境配置。源/运行payload仍按原同SHA规则，不重复构包。
**Tech Stack:** 现有Node24/Forge/Vite/serviceClient，无新依赖或数据迁移。

- [ ] tests/releaseService.test.ts：正式缺配置失败，HTTP/凭据/路径/查询拒绝；合法HTTPS规范化；正式包忽略外部重定向配置，开发loopback仍需显式允许。
- [ ] 实现desktop/build/releaseService.ts、src/main/clientServiceConfiguration.ts；接forge.config.ts、vite.main.config.ts、main.ts，不添加任何真实域名占位值；YIKE_RELEASE_SERVICE_URL只包含公开HTTPS地址。
- [ ] 定向测试/类型检查与必要审核，更新desktop/docs/PACKAGING.md；服务未部署时不make空配置包，不凭配置存在宣称服务可用。
- [ ] 用户侧任务已授权部署101.200.137.138；当前root认证Permission denied(publickey)，不重复无凭据重试。已一次询问恢复本机公钥授权及意客域名。获访问后只读盘点，独立目录/数据库/配置，保护现有业务；不触碰101.200.223.4。真实部署/备份回滚/Windows/平台UAT继续待完成。

## 实施与验证

源码`5f54d4a5ed2e1fecedd498ff931d030b0f298921`非作者整批GO，无阻断P1/P2；配置输入、运行时绑定与原serviceClient共9 passed（0.39s）及TypeScript通过，不重复构包/平台测试。正式make须提供公开HTTPS origin并编译入main；运行环境不能覆盖正式包地址。开发loopback规则不变。

用户已授权目标服务器101.200.137.138，确认域名未定。本机默认SSH密钥存在但服务器拒绝，agent没有其它identity；尚无可用服务、实际部署或Windows候选。本批解除“普通双击必须继承终端环境”的代码缺口，不解除真实服务器访问/HTTPS/部署验收缺口，完整Goal继续。
