# 意客AI Logo 与设计稿生成记录

使用内置 imagegen 工具；未使用 CLI/API 回退。当前为设计图阶段，未修改运行页面。

## 交付文件

- `yike-logo-blue-v1.png`：独立蓝色 Y 形标志，纯白背景 PNG。交付不宣称具有透明通道。
- `../previews/workbench-blue-logo-v1.png`：在已选蓝白左导航设计稿上替换左上角图标，保留业务内容与状态。

后续实现引用本目录资产，不依赖 Codex 默认生成目录。导航中建议实际图形宽约 34–36px，品牌区域约 40–44px，与文字间隔 10–12px。

## 初始标志提示词

```text
Use case: logo-brand
Asset type: standalone square app logo mark for 意客AI, to replace the temporary “意” tile in the top-left of a light blue-and-white desktop business app.
Input image: reference for the app's palette and visual weight only; do not redraw the interface.
Primary request: create one original, refined, compact abstract brand symbol suggesting the meeting of a business intent and a customer. Two simple geometric blue strokes converge into an elegant stylized Y, with an open diagonal cut that gives a subtle sense of direction. Strong distinct silhouette, balanced negative space, gently softened corners, visually recognizable at 24–40px.
Style/medium: exceptionally clean flat vector-like raster logo, friendly modern technology brand, crisp optical geometry, minimal and restrained.
Composition: one centered symbol on a 1024x1024 square canvas; symbol occupies about 76% of the canvas with even clear space. No wordmark, no text, no additional variants.
Color palette: primary clear blue #1677FF with at most one supporting lighter blue #55B4FF. Flat fills, no gradients.
Scene/backdrop: genuinely transparent background with alpha, clean edges; no checkerboard pattern painted into the image.
Constraints: standalone usable asset, no shadow, bevel, metallic material, 3D, presentation board, frame, slogan or watermark. Do not imitate the Alipay glyph, Feishu bird, or another company's logo. Do not use a generic robot, brain, magic sparkle or chat bubble. Keep the symbol simple enough for a real navigation logo.
```

初次输出没有真实 alpha，棋盘格已绘入 RGB 背景，因此不作为最终独立资产。

## 最终白底标志提示词

```text
Use case: precise-object-edit
Asset type: clean standalone logo PNG.
Input image: edit target, the blue two-piece Y logo.
Primary request: Replace ONLY the grey checkerboard background with perfectly uniform pure white #FFFFFF. Preserve the two blue shapes, exact silhouette, angle, proportions, placement and clear space. Remove all checkerboard pattern, texture, ripples, outlines and shadows from outside the blue mark.
Composition: same square canvas and centered mark, whole symbol visible, even margins.
Color: keep dark blue #1677FF and light blue #55B4FF as clean flat fills.
Constraints: do not redesign the symbol, do not add text or a rounded-square tile. No wordmark, no extra variant, no grey checkerboard, no transparency simulation. This is a flat logo asset on SOLID WHITE. Keep the edges crisp and the white backdrop completely plain.
```

## 设计稿合成提示词

```text
Use case: compositing
Asset type: desktop UI design preview with new brand logo.
Input images:
Image 1 is the EDIT TARGET: the latest light grey, white and blue 意客AI workbench screen.
Image 2 is the SUPPORTING INSERT: the new two-piece blue geometric Y logo. Its grey checkerboard is a faulty backdrop, NOT part of the mark. Extract only the two blue shapes.
Primary request: Replace ONLY the temporary blue rounded-square “意” icon in the TOP LEFT of Image 1 with the precise two-piece blue Y mark from Image 2. Insert the mark directly on the existing very light sidebar background, with no square backdrop, no grey checkerboard, no white box and no shadow. Keep the Chinese wordmark “意客AI” exactly as is to the right of the new symbol.
Placement: fit the complete logo into approximately the same 40x40px visible icon area as the old icon, optically aligned to the center of the wordmark, with roughly12px spacing. Preserve the mark's aspect ratio, silhouette, negative-space cut and dark/light blue colors. Do not enlarge it into a decoration.
INVARIANTS: Everything outside that small upper-left icon area stays unchanged: canvas dimensions/aspect ratio, all page geometry, sidebar width, white and pale-grey surfaces, blue selections/buttons, brand text, navigation labels, toolbar, search, status selector, table, exact source data, pending-review/未入客户库 labels, title, metadata, excerpt, source link, inquiry text, copy button and empty follow-up state. Do not rewrite Chinese, move panels, add features, crop, recolor the UI, or change fonts. Keep the existing “意客AI” text; only replace the icon before it.
Output one complete desktop UI image with the logo naturally installed, not a comparison, collage, logo presentation board or zoom-in. Preserve the input's entire screen.
```
