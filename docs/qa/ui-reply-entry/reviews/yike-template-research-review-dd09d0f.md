# 模板研究配置独立代码复核

候选：`dd09d0fbd4e900b020e41a8486f0343ff9f33c56`；2026-09-10。

结论：限定两文件增量 PASS，未发现新增 P0/P1。

非作者审查范围为 `desktop/src/renderer/pages/tasks/localTemplates.ts` 与新增 `desktop/tests/ui/task-template-research.test.tsx`。模板现在保留人工需求类型、搜贝上限、停止条件、证据顺序与执行上限；使用可编辑草稿 schema，有限但尚未填完的数字不会被默认值替换，最终估算和启动仍有独立严格校验。

模板存入及从模板新建均经过白名单解析，剥离旧报价、授权、请求和两类来源 provenance；新副本重置任务身份且保留祖先源草稿链。旧无研究字段模板兼容，原 pending 祖先检查未改变。该功能不复用旧报价或取得启动授权，也不代表后台研究服务已接通。

独立执行新旧模板两套：20 passed（不与作者 86 项重复累加）。日志 `/tmp/yike-template-research-independent-dd09d0f.log`。本次未运行 Windows 原生、构包或外部业务请求，未修改产品源码。
