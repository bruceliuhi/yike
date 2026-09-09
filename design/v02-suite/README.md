# 意客AI · 全页面设计评审 R1

2026-09-09 · **20 张核心页面及操作状态 · 全部待用户确认**

这是一套延续蓝白科技风、Y Logo 和八入口导航的完整核心页面设计。先一起确认，再按设计开发。图册仅展示静态设计，图片中的产品按钮尚不能操作，平台列表是规划范围而非已支持声明。

## 查看方式

- 本地打开 [index.html](index.html) 对应图册服务：在本目录运行 `python3 -m http.server 18789 --bind 127.0.0.1`，浏览器打开 `http://127.0.0.1:18789/`。目录可复制到其他机器，图册无外部依赖。
- 点击缩略图或左侧 P01–P20 查看原尺寸比例的大图；左右方向键翻页，Esc 返回总览。图册的浏览按钮可用，图片里的产品操作不可用。
- 不启动服务也可以直接查看下方 PNG、[页面与状态清单](PAGE_STATE_MATRIX.md)和[组件规范及勘误](DESIGN_SYSTEM.md)。

## 这次确认什么

确认页面布局、信息密度、导航与跳转、关键操作和复用状态，以及统一组件规则。20 张图覆盖核心页面和关键操作；加载、校验、取消与恢复等复用状态有文字定义，不声称每一种状态都有独立画稿。

建议按“P06 表单再紧凑一些”“P12 证据栏加宽”等页面编号反馈。认可整体方向不自动等于批准所有页面；收到明确的整套确认后才更新 [manifest.json](manifest.json) 和 [确认记录](APPROVAL.md)。本轮没有启动新版业务页面实现。

## 页面图册

| 页面 | 页面 |
|---|---|
| **P01 · 登录与试用**<br>[![P01 登录与试用](screens/P01.png)](screens/P01.png) | **P02 · 商机工作台**<br>[![P02 商机工作台](screens/P02.png)](screens/P02.png) |
| **P03 · 业务画像**<br>[![P03 业务画像](screens/P03.png)](screens/P03.png) | **P04 · 资料与案例**<br>[![P04 资料与案例](screens/P04.png)](screens/P04.png) |
| **P05 · 线索采集任务**<br>[![P05 线索采集任务](screens/P05.png)](screens/P05.png) | **P06 · 新建获客任务**<br>[![P06 新建获客任务](screens/P06.png)](screens/P06.png) |
| **P07 · 原始线索复核**<br>[![P07 原始线索复核](screens/P07.png)](screens/P07.png) | **P08 · 监控任务**<br>[![P08 监控任务](screens/P08.png)](screens/P08.png) |
| **P09 · 监控运行详情**<br>[![P09 监控运行详情](screens/P09.png)](screens/P09.png) | **P10 · 商机库**<br>[![P10 商机库](screens/P10.png)](screens/P10.png) |
| **P11 · 机会证据详情**<br>[![P11 机会证据详情](screens/P11.png)](screens/P11.png) | **P12 · 触达中心**<br>[![P12 触达中心](screens/P12.png)](screens/P12.png) |
| **P13 · 发送确认**<br>[![P13 发送确认](screens/P13.png)](screens/P13.png) | **P14 · 回复与跟进**<br>[![P14 回复与跟进](screens/P14.png)](screens/P14.png) |
| **P15 · 添加跟进**<br>[![P15 添加跟进](screens/P15.png)](screens/P15.png) | **P16 · 账号与平台连接**<br>[![P16 账号与平台连接](screens/P16.png)](screens/P16.png) |
| **P17 · 连接平台**<br>[![P17 连接平台](screens/P17.png)](screens/P17.png) | **P18 · 设备与使用授权**<br>[![P18 设备与使用授权](screens/P18.png)](screens/P18.png) |
| **P19 · 确认启动**<br>[![P19 确认启动](screens/P19.png)](screens/P19.png) | **P20 · 持续监控设置**<br>[![P20 持续监控设置](screens/P20.png)](screens/P20.png) |

## 来源与开发交接

17 张首轮新图、复用的 P11 和补充的 P19/P20 共 20 张；精修不增加页面数量。图中公开研究样例独立于客户数据，空态和故障示意不代表真实运行。图片使用内置 image_gen，原样复制，未对输出做程序绘图或重采样。

- [完整页面清单](manifest.json)：图片、尺寸、SHA-256 和逐页待确认状态。图片修改后须同步摘要，确认必须指向确定版本。
- [页面流程与关键状态](PAGE_STATE_MATRIX.md)：每页操作、跳转、缺项、失败及恢复。
- [组件与验收规范](DESIGN_SYSTEM.md)：统一视觉、按图实现、必要的文字勘误。
- 生成记录：[A 登录/资料/连接/启动](GENERATION_A.md)、[B 采集/监控](GENERATION_B.md)、[C 触达/跟进/授权](GENERATION_C.md)、[工作台/商机库/证据复用](GENERATION_ROOT.md)。`generated_images/…` 为生成环境缓存溯源标识，仓库内稳定资产以 `screens/` 为准。
- [开发任务书](../../docs/V02_IMPLEMENTATION_TASKBOOK.md)：真实业务实现进度，不以图册完成替代功能完成。

整套确认后，先校准公共壳和基础组件，再按同一套规范逐页实现；用相同视口、相同数据状态的运行截图对照。涉及实质布局或业务流程变化时先改设计再确认。
