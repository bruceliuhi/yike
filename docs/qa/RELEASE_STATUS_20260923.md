# 当前发布状态（2026-09-23）

本记录绑定当前 `main`，用于把本机候选、线上服务和真实上线门禁分开核对。

## 当前主线与本机候选

- 主线提交：`7328c6c087f3655f22c4b9b3e62443b652b622b5`
- Gitee `origin/main` 与 GitHub `github/main` 均为同一提交
- 本机发布候选检查：`local=PASS / external=NOT_VERIFIED / overall=HOLD`
- Lead Radar 定向测试：`56 passed`
- macOS arm64 安装包结构检查和包内冒烟：均 `PASS`
- 当前包为 ad hoc 签名；Developer ID 与公证尚未完成。包哈希和完整检查见 [`latest-main-package-61ec69c.json`](ui-candidate-mac/latest-main-package-61ec69c.json)。

## 公网版本核对

2026-09-23 对 `https://yike.tuokexing.net` 执行 CP-06 版本探针：

```text
expected: 7328c6c087f3655f22c4b9b3e62443b652b622b5
actual:   5330c81046b636b6cad65589581374e321a277c5
result:   revision mismatch
```

公网 `/healthz` 返回 200 只证明旧服务存活，不证明当前主线已部署。当前能力回读仍显示：

- 已返回：登录会话、画像、商机、人工跟进、短信登录、搜索建议
- 未验证可用：平台连接、任务执行、触达、回复

## 正式上线仍需的外部证据

以下项目不能由本机测试、健康检查或历史部署记录代替：

1. 已授权搜索提供商的能力回执，以及一次不预置 URL/作者的 `SEARCH → READ → 候选 → 原文证据` 运行
2. 真实样本校准：准确率、误触率、重新打开率和客户复核记录
3. 目标 PostgreSQL 的迁移、最小权限/RLS、备份恢复和回滚演练
4. 将最终主线部署到 HTTPS，并在同一版本完成客户 UAT
5. 对外分发 macOS 时完成 Developer ID 签名、公证和实际安装验收

目标主机 `101.200.137.138` 当前 SSH 端口不可达，因此本机无法代替服务器管理员完成发布。不得把这份状态记录改写成上线证明；完成部署后应重新运行 `scripts/cp06_probe.sh`，并将目标环境的原始输出、时间、责任人和回滚结果放入仓外证据清单。
