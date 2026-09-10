# CP-06备份认证缺陷修复

Base42ebce8；代码核实旧OpenSSL `-macopt key:file:<path>`把路径字符串当HMAC密钥。沿已有部署备份恢复范围修复，不操作任何真实数据库/旧备份。使用review-reception/TDD，定向测试和整批独立审核，不全测/构包。

## 约束与实现

- 新侧车格式固定`YIKE-BACKUP-MAC-V2\n`加32字节HMAC。拒绝旧32字节MAC、缺失、超长或未知版本；不迁移/删除/自动重签旧备份。
- Python标准库helper读仓库外私有secret文件第一行，与现OpenSSL `-pass file:`匹配；非空、无NUL/CR、上限64KiB，不输出秘密或把秘密传进argv。独立认证key使用PBKDF2-HMAC-SHA256(passphrase, domain+密文头16字节, 200000, 32)，HMAC-SHA256覆盖domain+完整密文。加密仍OpenSSL AES256CBC/PBKDF2 200000，认证与加密派生隔离。
- helper流式处理密文、恒时比较MAC；校验Salted__头与最小密文长度。创建和验证严格sidecar格式。新备份私有临时目录生成密文和MAC后不覆盖发布；失败只清理本次拥有文件，不删旧备份。
- 恢复先复制密文到私有快照，在快照上验证，再解密同一快照，防止验后原文件被替换。认证失败不能调用pg_restore。显式CONFIRM_RESTORE要求不变，任何真实恢复仍需另行明确指定隔离目标。
- 定向证据：真实OpenSSL加解密/fixture pg_dump与pg_restore；新版本往返、同一secret不同路径、路径不变但secret改变、旧路径MAC伪造、密文篡改、旧侧车拒绝、既有文件不覆盖。测试不冒充真实PG恢复。
- 修复后更新deploy/README、CUSTOMER_PILOT_RUNBOOK与CP06模板，保留历史失败来源并明确旧备份不可自动信任；正式环境恢复演练仍未完成。

## 工作项

1. 写RED回归复现旧MAC路径错误和版本缺失。
2. 新helper与脚本最小接线，私有临时输出/恢复快照。
3. 只跑backup脚本相关测试；整批一次非作者独立审核，修复按增量。
4. 更新文档，推送main；V0.2/CP06不因源码修复标已上线。
