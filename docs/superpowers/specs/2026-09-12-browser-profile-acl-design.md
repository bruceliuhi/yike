# Windows 浏览器档案核验兼容修复

范围：已授权 V0.2 内的实机登录阻断修复；不改变平台授权、设备执行许可或发送批准。用户要求独立处理并压缩重复材料，本批仅记录变化和新增证据。

实测 Chromium 149.0.7827.55 正常退出后产生重复用户/SYSTEM/Administrators FullControl ACE、文件 Everyone deny execute，以及网络 LPAC 的 Modify 和继承 RWX/DELETE ACE。精确三条 ACE 的通用私有目录校验因此拒绝档案。拒绝被翻译成 SOURCE_HOST_FAILED，又触发全局停止未确认。

采用独立 profile 验证入口、复用句柄安全遍历。根仍必须满足既有严格策略；后代允许同一可信主体重复授权、文件上固定 deny execute；仅 Default 下 Cache、Network、Safe Browsing Network、Shared Dictionary 子树允许固定 lpacChromeNetworkSandbox SID 和实际有限掩码/继承形式。每节点仍须具备用户/SYSTEM/Administrators 的完整基础权限。未知主体、root capability、额外权限、重解析点、多硬链接、非法路径一律拒绝。运行环境/output 的 verify_private_tree 不变。

未采用：全树忽略 ACL 会失去隐私边界；只外置 Cache 无法解决 Network/Cookies 和原子写入；原地修复 DACL 会修改用户缓存并破坏浏览器沙箱。此策略明确承认同渠道 Chromium 网络沙箱是档案信任主体，不代表跨 Windows 用户开放权限。

参考固定上游版本：[网络目录授权](https://raw.githubusercontent.com/chromium/chromium/149.0.7827.55/content/browser/network_sandbox.cc)、[渠道 capability 名](https://raw.githubusercontent.com/chromium/chromium/149.0.7827.55/chrome/browser/chrome_content_browser_client.cc)、[SID 派生](https://raw.githubusercontent.com/chromium/chromium/149.0.7827.55/base/win/sid.cc)。UNKNOWN 渠道 lpacChromeNetworkSandbox 的大写 UTF16LE SHA256 按 8 个小端 DWORD 派生 SID，已与实机 ACL 匹配。

验收：原生 NTFS 测试先红后绿；安全反例仍拒绝；真实已停止档案仅只读核验，不读取 Cookie 内容。三个 profile 调用方统一切换，runtime/output 不切换。实际登录/取消/换平台须在后续固定候选上复测；测试通过不等于客户登录授权完成。
