# CP-06 目标环境验收记录模板

状态：`NOT_STARTED`  
说明：模板不是上线证明。只有填入目标环境的实际命令输出、地址、时间和责任人后，才可将状态改为 `PASSED`。

## 环境与版本

- 服务器/区域：`待填写`
- 域名：`待填写`
- 部署提交 SHA：`待填写`
- 应用镜像 SHA：`待填写`
- PostgreSQL 主机（仅私网）：`待填写`
- 应用数据库角色：`待填写`（确认非超级用户、非 owner）
- 验收时间/责任人：`待填写`

## 必验项

| 项目 | 实际证据 | 结果 |
| --- | --- | --- |
| 空库迁移与重复迁移 | `待填写命令和输出` | `PENDING` |
| `/healthz` | `待填写 HTTPS 响应` | `PENDING` |
| `/readyz` | `待填写 HTTPS 响应` | `PENDING` |
| HTTPS 证书与强制跳转 | `待填写 curl/浏览器证据` | `PENDING` |
| 四页真实手机流程 | `待填写设备、时间、截图路径` | `PENDING` |
| 两租户隔离 | `待填写非超级用户验证` | `PENDING` |
| 日志脱敏 | `待填写访问日志抽查` | `PENDING` |
| 加密备份 | `待填写 backup_pilot.sh 输出和存储位置` | `PENDING` |
| 隔离恢复 | `待填写 restore_pilot.sh 输出和恢复库` | `PENDING` |
| 回滚 | `待填写旧镜像 SHA 与恢复结果` | `PENDING` |
| 生产关闭开发桥接 | `待填写 YIKE_PILOT_DEV_LOGIN 未启用证据` | `PENDING` |

## 放行条件

所有项目为 `PASS`，且没有公网数据库、明文密钥、未脱敏 query token、跨租户读取或无法回滚项；否则保持 `NOT_STARTED`/`BLOCKED`，不得对外宣称已上线。
