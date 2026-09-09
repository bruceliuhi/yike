# P02 098ce6b 限定非作者复核

绑定 `098ce6b` 的 `TodoQueue.tsx` 两项依赖及 `workbench-queue-scope.test.tsx`。结论 **PASS**，本次范围无剩余 P0/P1。

读取源码确认 accountScope.id/version 进入 useResource 身份；useResource 在 render 时即隐藏旧身份数据并禁止旧异步请求发布，未依赖下一轮 effect 才清除。现有 AppProvider 会话刷新使用同一个 service 实例，四项回归通过真实 Provider 分别验证换空间、同空间换版本、已读取旧行隐藏和旧请求迟到丢弃；新行目标仍经过真实 hash 路由跳转。

独立命令：Node 24.19，`node node_modules/vitest/vitest.mjs run tests/ui/workbench-queue-scope.test.tsx`，结果 1 文件 / **4 passed**；原日志 `/tmp/yike-workbench-scope-independent.log`。未重跑全量、操作浏览器或验证真实后台租户鉴权；这不是整个工作台或 Goal 完成结论。
