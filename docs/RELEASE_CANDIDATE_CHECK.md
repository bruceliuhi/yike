# 发布候选自检

`scripts/release_candidate_check.py` 是一个失败关闭的发布候选自检。它把“本机代码候选已经通过”与“真实环境已经上线”分开，避免用单元测试、静态页面、健康检查、fixture 或环境变量存在来代替真实平台和客户证据。

## 使用

在仓库根目录执行：

```bash
python3 scripts/release_candidate_check.py --run-tests
```

它会检查当前提交、已跟踪工作树、差异空白、发布合同文件、脚本权限和静态凭据扫描，并执行 Lead Radar 合同测试。默认返回码为：

- `0`：本机检查和测试通过，且显式使用了 `--local-only`
- `1`：本机检查失败
- `3`：本机检查通过，但真实上线门禁仍未验证

只验证源码候选时可使用：

```bash
python3 scripts/release_candidate_check.py --local-only --run-tests
```

机器读取用 `--json`。输出不会打印数据库 URL、认证密钥、备份口令或其它环境变量值。

## 为什么默认仍是 HOLD

脚本固定将以下项目标为 `NOT_VERIFIED`，不会从源码或旧记录推断通过：

1. 真实授权平台来源的 capability 回执、原文重开、发布时间、保存边界和重试幂等证明
2. 一次不预置 URL 或作者的 `SEARCH → READ → candidate → evidence` 真实研究运行
3. 目标 PostgreSQL 迁移、最小权限/RLS、备份恢复和回滚
4. 最终版本的 HTTPS 部署和客户环境验收

这些证据要在目标环境按 [CP-06 验收模板](DEPLOYMENT_ACCEPTANCE_CP06_TEMPLATE.md) 和 [部署手册](../deploy/README.md) 记录。拿到证据后仍需人工复核版本 SHA、时间、环境和责任人，再更新验收记录；本脚本不会把用户提供的 JSON、配置开关或历史页面变成生产证明。

## 适用范围

当前检查范围是 macOS 客户端及服务端发布候选；Windows 按当前工作目标排除。排除 Windows 不会豁免真实来源、生产数据库、恢复、HTTPS 或客户验收门禁。
