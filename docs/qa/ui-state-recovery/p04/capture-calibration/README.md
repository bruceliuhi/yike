# 截图校准，不能作为视觉通过证据

首次 capture 在浏览器既有125%缩放下得到1187×848 CSS视口，且 clip 参数与底层设备坐标不一致，出现缩小/白边；这些图只保留排查记录。并行Vite热更新还重置了TEST内存，先前抽屉状态丢失，不能将其解释为用户操作成功或产品数据丢失。

后续使用实际 DOM innerWidth/innerHeight 校准指定 CSS 视口；以无clip的 Page.captureScreenshot(fromSurface=true,captureBeyondViewport=false)保存整视口。冻结TEST静态构建后重新执行完整流程，单独记录有效截图。浏览器缩放/模拟不等同Windows实机缩放验收。
