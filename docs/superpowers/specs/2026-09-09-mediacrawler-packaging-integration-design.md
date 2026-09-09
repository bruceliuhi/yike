# MediaCrawler 打包集成设计

> 状态：`APPROVED_FOR_IMPLEMENTATION`
> 日期：2026-09-09
> 适用范围：意客 AI DISCOVERY MVP 的授权 B 站＋抖音采集链路

## 1. 目标与假设

用户已确认拥有 MediaCrawler 在本产品中的商业使用、修改和再分发授权。本设计据此把固定版本 MediaCrawler 纳入实现仓，授权原件和账号运行资料仍只保存在仓外。

本次只解决“运行时可复现、减少手工安装和版本漂移”，不扩大平台范围，不恢复云端多租户，不提供自动发送或风控绕过。

## 2. 方案

- 以固定 commit 的 MediaCrawler 源码作为 vendor subtree，保留上游 LICENSE/NOTICE。
- 通过 `vendor/mediacrawler.lock` 固定 commit、补丁集、依赖文件和运行时摘要。
- `app/collector.py` 只通过受控 supervisor 启动 vendor runtime；平台输出先落在仓外私有目录。
- 现有 B 站/抖音 normalizer、SQLite 事实链和人工复核流程保持不变。
- MediaCrawler 修改集中在 `vendor/patches/mediacrawler/`，不把意客业务逻辑塞进上游目录。

## 3. 数据与安全边界

vendor runtime 不直接写意客 SQLite。采集结果必须经过现有标准化、双层去重和 `mvp_run_id` 事实事务。Profile、Cookie、二维码、模型密钥和授权文件不进入 Git、日志或导出；运行目录继续按 0700/0600 约束。

实际登录、验证码、限流和平台风控仍由操作人在可见浏览器中处理。任何真实采集结论仍需真实账号和可重开来源证据，fixture 只能证明代码契约。

## 4. 兼容与回滚

启动前校验 vendor commit、patchset 和依赖摘要；不一致时 fail closed。保留仓外 runtime 路径作为开发回滚方式，但产品默认使用仓内 vendor runtime。若上游升级，只允许新 commit＋新锁文件＋新补丁集的独立变更，不覆盖历史事实。

## 5. 验收

1. 空库启动和 fixture 采集测试继续通过。
2. vendor lock 校验、补丁重放、依赖安装和 secret scan 通过。
3. 不产生 Cookie/Profile/Token 入仓证据。
4. 真实授权账号的小批次仍需另行标记 `REAL_COLLECTION_BILI` / `REAL_COLLECTION_DY`，本次代码提交不宣称真实平台成功。
