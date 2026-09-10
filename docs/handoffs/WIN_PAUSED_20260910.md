# Win 阶段暂停交接（2026-09-10）

用户因额度要求阶段性收尾、提交 Gitee，停止继续开发/实验/构包。Mac 已停止，后续仍由 Win 按精简可验收版接续；本次不把 Goal 标为完成。

## main 小差量

基线 `3ad329a`；五个 Python/桌面启动命令显式增加 `-B`，以兼容离线 Python 的 `_pth` 隔离，避免运行后写入缓存。其余执行、授权与 packaged 门禁不变。先取得缺失参数 RED，修复后 Python 两文件 **55 passed / 1 skipped**（旧安装路径预检未配置）；桌面三文件 **60 passed**、类型检查通过。非作者限定规格/代码审核 Approved，仅覆盖这十个产品/测试文件，不包含 WIP。没有重跑全量或重新构包。

## 现有开发分支保留 WIP

`codex/win-collection-flow` 保留以下全部源码及测试，尚未合入 main：

- `app/windows_portable_bundle.py`、`app/windows_portable_inventory.py`、两个 portable 测试与分支内 `docs/superpowers/plans/2026-09-10-win-portable-runtime.md`：最近一版轻量测试 16 passed，随后新增 **2 个失败用例尚未实现**。crawler 的 `fonttools ../../share/man/man1/ttx.1`、`greenlet ../../include/site/python3.11/greenlet/greenlet.h` 是合法 wheel 外部文件，当前安全规则拒绝；接续应做固定白名单映射，不能放宽任意路径越界。没有生成真实 payload、执行搬迁 Chromium 探针或完成客户 bootstrap。
- `pilot/reply_store.py`、`tests/test_reply_store_postgres.py`：修复首次登记 42501、平台更正 revision 23505、跨归属更正、并发去重与已读限制。实现者实际 **66 passed，其中 32 项受限 PostgreSQL**；独立审核及真实平台验证未完成，不将其视为已交付回复能力。旧诊断证据保留。

本机构建准备：`.runtime/portable-build-host-20260910-01` 为新建 copy-mode host 环境，六个依赖与项目锁定版本相同，未改旧环境；离线安装因缓存不全失败后，联网固定版本安装成功。新环境尚待生成器只读复核，路径不应进入客户配置。实际运行时仍是 `.runtime/windows-installed-xhs-20260910-02`，未修改。账号 profile、Cookie、数据库秘密与运行产物均不提交 Git。

## 恢复顺序

用户明确恢复后，先从 WIP 提交接续两项已知失败及独立审核，真实生成离线 payload，再接 Electron 首次安装/现有连接页。随后交付单一 Windows 候选并验证真实 XHS、辅助渠道、多找类似、短句、批准发送/跟进。三渠道真实批次、客户安装验收及 100/30 真实案例均未完成；不自动发送、部署或继续耗额度。
