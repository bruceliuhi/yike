# 隔离视觉验收入口

此目录仅用于以测试状态运行真实 React 页面。入口复用生产 `App`、`AppProvider`、页面组件和 `YikeService` 类型，不改生产 main / renderer 入口。

P12 的待确认、待回复、需处理三个队列提供 TEST 内存状态供点击核对；沿用 populated/empty/error/loading 切换。新发送方法仍拦截，原请求核对只返回 UNKNOWN，不模拟渠道投递成功。

**TEST 数据不是客户、商机业绩、真实账号或真实运行结果。** 内存中出现的“运行中”“已回复”等状态仅用于检查布局和交互。该工具不能证明真实采集、平台登录、发送或客户数据库接入已经完成。

## 启动与入口

在 `desktop` 目录使用 Node 24：

```sh
npx vite --config vite.visual.config.ts
```

仅监听 `127.0.0.1:18794`，端口被占用时退出，不自动换端口。不配置 API proxy，不读取业务服务地址或凭据。

- [P09 监控详情](http://127.0.0.1:18794/?scenario=P09)
- [P05 采集任务](http://127.0.0.1:18794/?scenario=P05)
- [P08 监控列表](http://127.0.0.1:18794/?scenario=P08)
- [P14 跟进记录](http://127.0.0.1:18794/?scenario=P14)
- [P15 添加跟进](http://127.0.0.1:18794/?scenario=P15)

可将 `scenario` 替换为 `P01` 至 `P20`。也支持首次打开 `http://127.0.0.1:18794/#P09` 或 `#/P09`，会转换成对应语义路由；页面内跳转继续使用真实路由。左下角 TEST 场景选择器切换页面时重新加载并重置内存。

`state=populated|empty|error|loading` 控制数据读取状态，默认 `populated`；详情在 `empty` 时呈现记录不存在。会话默认使用 TEST 身份，`session=guest` 或 P01 使用访客。启动确认仍缺真实账号和执行设备，不能启动；P13 仍禁止发送。

20 个入口已映射，不表示 20 页所有状态已做视觉验收。当前仅完成 P09 浏览器打开与执行记录切换，以及任务 / 监控 / 跟进的组件回归；完整截图比较留待后续功能分支。

## 数据与外部动作边界

- [fixtures.ts](fixtures.ts) 全部使用 TEST 标记。任务关键词、排除词和两次监控时刻沿用已批准的展台场景；不存在真实采购联系人、预算或成交数据。合成询价对象使用 `.invalid` 来源地址；产品自带公开研究样例仍按原页面的只读规则展示。
- [service.ts](service.ts) 数据每个实例独立深拷贝，画像 / 跟进 / 任务动作只影响该实例内存。候选入库、真实任务启动和消息发送始终拒绝；登录、短信、生成草稿等测试响应不调用外部服务。
- [isolation.ts](isolation.ts) 将 localStorage 与 sessionStorage 替换为内存对象，禁用 native bridge、业务 fetch / XHR / beacon、剪贴板写入、外链打开和 CSV 下载（包括脱离 DOM 的下载链接）。刷新后测试存储重置，不接触产品端口的存储。
- 页面固定显示 TEST 标识。外部动作只记录在 `window.__YIKE_VISUAL__.events` 的内存事件数组中；复制只记录字符数，登录不记录输入凭证。
- Vite 仅加载本机模块与 HMR，CSP 限制连接到本机入口；不应输入任何真实客户资料或凭据。

## 回归与生产排除检查

在 `desktop` 目录执行：

```sh
npx vitest run tests/visual
npm run typecheck
node tests/visual/verify-production-exclusion.mjs
```

排除脚本使用真实生产入口与 `vite.renderer.config.ts`，仅将输出改到 `desktop/out/visual-production-check`，检查构建模块图、产物文本和 Vite manifest 无 harness 引用。它同时检查当前磁盘存在的 Mac ASAR 的文件路径与内容标记；未找到包时输出 `existingAsarChecked: false`，不能据此宣称包检查通过。也可传入明确的 ASAR 路径作为第一个参数。

独立视觉构建若需要使用 `npx vite build --config vite.visual.config.ts`，输出到 `desktop/out/visual-harness`，不覆盖生产 `.vite/renderer`，且不是 Forge 的 renderer 入口。所有 `out` 产物不提交 Git。

当前记录见 [VALIDATION.json](VALIDATION.json)。后续修改生产打包配置或新建安装包时重新执行排除脚本；本轮对既有 ASAR 的检查不替代未来安装包检查。
