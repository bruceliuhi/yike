# 小红书登录顺序 Implementation Plan

**Goal:** 匿名用户能到达原生登录等待，完成本人操作后才查询严格账号状态。
**Architecture:** 只改 `app/platform_login_worker.py::login_xhs` 的预登录顺序，原后置pong/self导航和清理门禁保留。
**Tech Stack:** Python asyncio、现有受控Playwright runtime、pytest。

单一紧耦合修复由主任务串行执行；独立Agent集中审核设计/差量，按用户要求不重复全仓或构包。

- [x] 在 `tests/test_platform_login_worker.py` 补匿名等待先于pong/创建client，已登录不等待、错误域/歧义及后置失败回归；执行单文件验证RED。
- [x] 修改login_xhs：官方域→导航计数（>1拒绝，0/不可见等待本人）→重核官方域→同上下文client/pong→既有self链接/账号核对→物理关闭。无错误吞掉、不改其他平台。
- [x] 定向worker/Windows host/原xhs runtime测试，复用未改vendor字节；匿名实机探针确认顺序和进程停止（档案瞬态核验见下）。
- [x] 独立差量审核，记录失败与实际范围，纳入本批main提交。
- [ ] 停止后档案瞬态核验根因、同候选构包及实际安装版登录复验。与前一登录状态UI修复合为一次下一候选，当前2a85dbc不追认。

## Evidence

基线5166cc6。首轮worker **6 failed /19 passed**；补强后置门禁测试确保确实经过本人等待后 **4 failed**，均为预期RED。实现后 **25 passed /0 skipped**，含实际加载受控runtime但阻断外网/真实浏览器的接口夹具。XML `.runtime/xhs-login-order-red.xml`、`xhs-login-order-postcheck-red.xml`、`xhs-login-order-green.xml` 保留。

扩展 Windows host/多平台/runtime三模块 **109 passed /3 failed**，`.runtime/xhs-login-order-regression.xml`。两个host测试只替换旧private校验、遗漏主线新增browser profile校验；另一个runtime测试仍引用已更名的_has_comment_output。仅修旧夹具边界/函数名，产品门禁不变；失败3项补测 **3 passed**，`xhs-login-order-fixtures.xml`。去重总范围137项已有最终通过证据，不相加重复样本。初次pytest回收历史受限目录的权限警告保留；后续使用新的独立basetemp，未删除或改ACL。

实机诊断只用新建匿名档案，未读取用户档案/Cookie、未输入认证或改安装runtime：同2a85 runtime早期探针首页200官方域→pong→client.request第81行拒绝信封；另次pong false→USER_LOGIN_WAIT。数字错误码未取得，不将其猜成未登录/限流，也不修改严格响应分类。

修复后一次实际探针：首页200官方域→**USER_LOGIN_WAIT，无PONG_ENTER**；35秒由原Windows Job supervisor停止，随后进程盘点无该runtime平台进程。匿名档案 `C:/ykt2a85/xhs-init-_z3jua70/anonymous-profile` 立即只读核验拒绝、稍后原样复核PASS，未改ACL；另一个修复前匿名探针也出现过此情况。尚未区分瞬态文件占用/权限/其他OS状态，不能标完整取消恢复通过。脚本 `.runtime/probe-xhs-login-stage.py` 与只读 `.runtime/diagnose-anonymous-profile.py`、各匿名档案保留；只输出阶段、固定错误码/代码位置，无认证或原始响应内容。

独立 `login_status_review` 设计与代码差量 GO，无阻断；worker blob `ca69459855fe1663d178de9a6e8980a6906b3d27`，worker测试 `403cdaefd1ab15c79791382a476f1f51f644b2c5`，host夹具 `49b4518a1dea5d805ebd64d0b31acc923ec3fb7e`，runtime夹具 `02ac114fde1b4d393232652725e4fa1036d7032e`。未构包/部署或实际用户认证，仍有已登录后接口拒绝可能性；待同候选和真实用户验收，Goal ACTIVE。
