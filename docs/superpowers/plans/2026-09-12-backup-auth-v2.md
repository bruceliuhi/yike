# CP-06备份认证缺陷修复

Base42ebce8；代码核实旧OpenSSL `-macopt key:file:<path>`把路径字符串当HMAC密钥。沿已有部署备份恢复范围修复，不操作任何真实数据库/旧备份。使用review-reception/TDD，定向测试和整批独立审核，不全测/构包。

## 约束与实现

- 新侧车格式固定`YIKE-BACKUP-MAC-V2\n`加32字节HMAC。拒绝旧32字节MAC、缺失、超长或未知版本；不迁移/删除/自动重签旧备份。
- Python标准库helper读仓库外私有secret文件第一行，与现OpenSSL `-pass file:`匹配；非空、无NUL/CR、上限64KiB，不输出秘密或把秘密传进argv。独立认证key使用PBKDF2-HMAC-SHA256(passphrase, domain+密文头16字节, 200000, 32)，HMAC-SHA256覆盖domain+完整密文。加密仍OpenSSL AES256CBC/PBKDF2 200000，认证与加密派生隔离。
- helper流式处理密文、恒时比较MAC；校验Salted__头与最小密文长度。创建和验证严格sidecar格式。新备份私有临时目录生成密文和MAC后不覆盖发布；失败只清理本次拥有文件，不删旧备份。
- 每次备份/恢复先验证并固定一个私有secret快照，加密/MAC或验证/解密使用同一快照，避免原secret轮换产生不可恢复备份。原秘密与快照不得位于仓库内；仅在私有临时目录以600创建并精确清理。
- 恢复先复制密文到私有快照，在快照上验证，再解密同一快照，防止验后原文件被替换。认证失败不能调用pg_restore。发布必须精确no-clobber目标（os.link），不能使用ln的“目标是目录时复制到内部”语义。显式CONFIRM_RESTORE要求不变，任何真实恢复仍需另行明确指定隔离目标。
- 定向证据：真实OpenSSL加解密/fixture pg_dump与pg_restore；新版本往返、同一secret不同路径、路径不变但secret改变、旧路径MAC伪造、密文篡改、旧侧车拒绝、既有文件不覆盖。测试不冒充真实PG恢复。
- 修复后更新deploy/README、CUSTOMER_PILOT_RUNBOOK与CP06模板，保留历史失败来源并明确旧备份不可自动信任；正式环境恢复演练仍未完成。

## 工作项

1. 写RED回归复现旧MAC路径错误和版本缺失。
2. 新helper与脚本最小接线，私有临时输出/恢复快照。
3. 只跑backup脚本相关测试；整批一次非作者独立审核，修复按增量。
4. 更新文档，推送main；V0.2/CP06不因源码修复标已上线。

## 本批验证

最终独立增量审核GO绑定`e389ee9dbd80d53b1b867fb8f38190d90a4ece44`，原两个P2关闭，无新P1/P2；审核报告提交`432ea33`。本计划四项工程工作完成，目标环境演练仍未完成。

源码`2342d01`。真实OpenSSL加解密配fixture pg_dump/pg_restore：新回归先3 failed，明确复现旧版格式缺失、换秘密仍通过MAC、伪造路径MAC被接受；修复后相关文件6 passed/3.62s。新增验后替换原密文的私有快照测试单项1 passed/1.72s，其余6未重跑，不累加重复覆盖。bash -n与git diff --check exit0。未读取/恢复/删除任何用户备份或真实数据库；临时测试文件由pytestfixture拥有。

完整V0.2下一业务重点：资料服务目前缺客户可用后端闭环（renderer的MaterialService接口未装配）；五项画像字段已有`profileDescription/mapProfile`序列化保存与版本确认，不能误报为完全未实现。下一片应复用既有画像路径接资料保存/真实提取/人工确认与引用授权，不重写画像。其次多平台原生发现和周期监控。此安全修复完成后直接推进客户主链，不继续扩备份管理功能。

首轮独立审核`2342d01`为NO-GO，两项P2：secret双次打开可遇轮换、ln目录竞态可误报成功。原报告保留于[backup-auth-v2-review.md](backup-auth-v2-review.md)；只按这两项增量修复，不用初轮6项通过覆盖审核结论。

增量源码`e389ee9`：新增helper `snapshot SOURCE DEST`固定同一秘密、`publish SOURCE DEST`使用精确os.link；拒绝仓库内快照写入，EXIT只清理本次文件。新反例RED后，最终相关单文件12 passed/9.36s；bash -n、py_compile、diffcheck exit0。最终独立增量结论见上方审核报告。不累加旧测试数，不声称真实PG恢复或CP-06已通过。
