# 默认服务可选依赖隔离

Goal：修复79427c0默认服务在未启用研究时也导入MCP的启动阻断，不改生产配置或扩大依赖。

Architecture：worker需要的`_valid_page`已是中性模块`open_web_reader.valid_page_evidence`的别名。直接从中性模块导入同一函数，行为和校验不变。相比延迟整个动态runtime装配，这是更窄的依赖方向修正；不采用把research extra加入默认镜像的方案。MCP进程仍独立加载其传输。

按用户自主修复、压缩重复验证要求，主任务串行修复，复用当前部署审核Agent做一次差量复核。

- [x] 在独立Python进程阻止MCP导入，实际装配默认runtime并GET healthz，先RED。初次测试编码/Windows环境大小写问题修正后复现真实MCP导入阻断，不将夹具失败当产品RED。
- [x] 仅修改worker的校验函数导入，保持严格函数同一性。
- [x] 默认启动、原文校验定向通过；独立差量GO，随XHS误拒绝修复提交main。Windows下64项POSIX worker用例跳过，未冒称通过。唯一批次证据见[Windows记录](../../qa/WINDOWS_SYNC_20260912.md)。
- [ ] 后续真实镜像、39→43迁移及旧客户端/回退检查仍须执行，不将本地启动写成部署成功。
