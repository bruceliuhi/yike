# 五门禁发布证据清单

发布证据必须绑定同一个最终提交，不能用旧版本的截图、测试输出或部署记录替代当前版本。`scripts/release_candidate_check.py --evidence <manifest.json>` 会校验以下内容：

- 清单 schema、当前 40 位提交 SHA、带时区时间和记录人；
- 五个门禁全部存在且为 `PASS`；
- 每个门禁有责任人、环境、说明和带 SHA-256 摘要的证据引用；本机 `path` 证据必须是仓库外的普通文件，远程 `uri` 必须是不带凭据、查询串或片段的 HTTPS 地址；
- 证据种类覆盖授权来源能力/重开/保存重试、`SEARCH → READ → candidate → evidence`、真实样本批次/指标、迁移/数据库 ACL 或 RLS/备份恢复/回滚、运行版本/HTTPS 探针/客户验收。

清单的最小形状如下。`path` 必须是本机存在的绝对路径，脚本会重新计算摘要；目标环境保存的证据可使用不含账号、密码、查询串或片段的 `uri`，摘要仍必须由采集证据时计算。

```json
{
  "schema": "yike.release-evidence/v1",
  "revision": "<当前提交的 40 位 SHA>",
  "recorded_at": "2026-09-23T10:00:00Z",
  "operator": "姓名或团队",
  "gates": {
    "authorized_source_proof": {
      "status": "PASS",
      "verified_at": "2026-09-23T10:00:00Z",
      "verified_by": "姓名或团队",
      "environment": "目标环境",
      "notes": "授权来源 capability 回执及原文重开/保存/重试证据",
      "artifacts": [
        {"kind": "capability_receipt", "uri": "https://evidence.example/capability", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "source_reopen", "uri": "https://evidence.example/reopen", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "source_save_retry", "uri": "https://evidence.example/save-retry", "sha256": "<64 位小写 SHA-256>"}
      ]
    },
    "autonomous_research_run": {
      "status": "PASS",
      "verified_at": "2026-09-23T10:00:00Z",
      "verified_by": "姓名或团队",
      "environment": "目标环境",
      "notes": "未预置 URL/作者的 SEARCH → READ → candidate → evidence 运行",
      "artifacts": [
        {"kind": "search_read_run", "uri": "https://evidence.example/run", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "candidate_evidence", "uri": "https://evidence.example/candidates", "sha256": "<64 位小写 SHA-256>"}
      ]
    },
    "real_sample_calibration": {
      "status": "PASS",
      "verified_at": "2026-09-23T10:00:00Z",
      "verified_by": "姓名或团队",
      "environment": "目标环境",
      "notes": "真实候选人工校准、误报漏报和重开指标",
      "artifacts": [
        {"kind": "calibration_batch", "uri": "https://evidence.example/calibration", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "calibration_metrics", "uri": "https://evidence.example/calibration-metrics", "sha256": "<64 位小写 SHA-256>"}
      ]
    },
    "production_database_and_recovery": {
      "status": "PASS",
      "verified_at": "2026-09-23T10:00:00Z",
      "verified_by": "姓名或团队",
      "environment": "目标环境",
      "notes": "迁移、最小权限/RLS、备份恢复和回滚",
      "artifacts": [
        {"kind": "migration", "uri": "https://evidence.example/migration", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "database_acl", "uri": "https://evidence.example/database-acl", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "backup_restore", "uri": "https://evidence.example/restore", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "rollback", "uri": "https://evidence.example/rollback", "sha256": "<64 位小写 SHA-256>"}
      ]
    },
    "production_https_and_customer_uat": {
      "status": "PASS",
      "verified_at": "2026-09-23T10:00:00Z",
      "verified_by": "姓名或团队",
      "environment": "目标环境",
      "notes": "最终版本 HTTPS、运行时和客户验收",
      "artifacts": [
        {"kind": "runtime_revision", "uri": "https://evidence.example/runtime-revision", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "https_probe", "uri": "https://evidence.example/https", "sha256": "<64 位小写 SHA-256>"},
        {"kind": "customer_uat", "uri": "https://evidence.example/uat", "sha256": "<64 位小写 SHA-256>"}
      ]
    }
  }
}
```

没有清单时发布候选检查继续将五门禁标为 `NOT_VERIFIED`。清单通过后，机器结果为 `RECORDED`，表示格式、摘要和版本绑定已检查；这仍不替代责任人核对原始证据，也不会把 `overall=HOLD` 改成上线通过。清单和证据文件不应放入仓库，也不得包含 Cookie、Token、手机号或客户原文。
