# 服务镜像启动缺陷与限定验证

- 源码：`2d6b79b8392cb35782a1ea73c96e2860c45a4181`，非作者审核GO，无阻断。修复当前pilot导入app.model_contract而镜像排除app的问题，只带入`__init__.py`及`model_contract.py`；不带入采集器。
- COPY布局检查先复现`app.model_contract missing from image`，修后部署合同4 passed（0.67s）。前期测试解析Dockerfile续行、macOS临时路径规范化的脚本错误已纠正，不作为产品故障。
- 一次真实构建：`docker build --platform linux/amd64 --build-arg VCS_REF=2d6b79b -t yike-service-candidate:2d6b79b -f deploy/Dockerfile .`，退出0。镜像ID：`sha256:c72ebe8b37532b93b35fd3a8aecd28adcd5a66a8ce6c6e88308f365b152f8868`；尚未推镜像仓库或部署服务器，目标机器架构须登录后确认。
- 原CMD启动、无源目录挂载、network=none、只读根文件系统、cap-drop ALL、no-new-privileges：uid10001，合同从镜像`/app/app/model_contract.py`加载，healthz=200。使用明确隔离的非生产配置，未连接任何数据库，readyz=503；不能宣称业务就绪或生产成功。
- 首次HTTP探测早于服务监听，返回Connection refused；确认同一容器仍运行且日志显示startup complete后，仅复测该探测成功。没有重启/重建。临时容器`yike-image-smoke-2d6b79b`已停止并自动移除，镜像保留供后续复用。
- 下一步仍是恢复已授权101.200.137.138的合法SSH访问、只读盘点后独立部署/数据库/HTTPS，再以同版本Windows包做真实业务验收。服务尚未部署、域名未定；不改现有业务或历史禁用服务器。
