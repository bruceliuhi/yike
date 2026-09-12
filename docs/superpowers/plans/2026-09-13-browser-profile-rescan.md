# 浏览器档案重扫实施计划

Goal：消除已枚举后代消失导致的误拒绝，同时保留严格安全边界。

Architecture：app/windows_private_directory.py 区分原生 FILE_NOT_FOUND；仅浏览器后代打开缺失触发有界完整重扫。公共异常始终固定文本。

Tech Stack：Python ctypes、Windows NTFS、pytest。

按用户压缩重复流程要求，本批主实现串行，独立 Agent 集中审核设计与实际差量。

- [x] tests/test_windows_private_directory.py：真实私有目录，枚举快照后删除文件，先见 RED；验证全树重扫发现新增坏 ACL、持续变化拒绝、严格策略/根缺失/其他错误不恢复。
- [x] app/windows_private_directory.py：仅 native error 2 分类，三次上限完整遍历，不跳过任何剩余节点；运行定向原生测试。
- [x] 匿名真实 runtime 单次复验退出后的即时核验；不是用户登录成功证据。
- [x] 独立差量审核；提交 main。
- [x] 与此前 STATUS / XHS 登录顺序修复合为一次候选0d9500b构包并实际升级；[唯一新包证据及尚待本人核验的边界](../../qa/WINDOWS_SYNC_20260912.md#固定候选0d9500b已构建并覆盖升级2026-09-13)。

## 证据

基线916df9c。原生 RED 3失败/2通过；模块52通过/1跳过，补充边界6通过，最终去重58通过/1跳过。跳过为本机文件symlink权限不足，不冒充已验。XML：.runtime/profile-rescan-{red,green,boundary}.xml。全部在私有测试目录内，未修改用户档案。

独立 profile_rescan_review GO，绑定 app blob `44bde96a592e310d4b25c5f4f17a1f86bbfae8cd` 与 tests blob `8234744a4db868ab2ec0f1aa8c723fba374e762b`。覆盖原生打开根/祖先2及后代3/5/32只失败一次，坏ACL即使残留last_error2也不重试。git diff --check通过。

真实匿名复验使用固定2a85dbc runtime与当前worker：官方首页200→USER_LOGIN_WAIT，无提前PONG；35秒Job超时停止后即时档案核验通过，探针退出0。隔离目录 C:/ykt2a85/xhs-init-xh1vfl_p 保留，无登录或外发。此轮未记录内部重扫次数，不能宣称该次实网必然触发竞态；精确竞态恢复由上面原生受控测试证明。安装包仍2a85dbc，新源码不追认旧包；正式认证/真实业务闭环/签名/客户验收仍待完成。
