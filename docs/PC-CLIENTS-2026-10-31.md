# 巨人 PC 客户端适配与 Windows 10 截图诊断（2026-10-31）

本轮仅源码适配及诊断，不修改 Release、安装版或用户配置，不操作游戏。

## 巨人 PC 窗口发现

原 windows() 在找到 Steam 安装清单后排除其他目录的 mjs.exe，导致已安装 Steam 的机器无法选中巨人官方独立 PC 游戏。实机确认官方客户端同样使用 mjs.exe、名将杀标题和 UnityWndClass。

改为：Steam 清单用于标明渠道，不再排斥独立客户端。非 Steam 路径要求同时满足 mjs.exe、完整游戏标题和 UnityWndClass；不按标题直接接入浏览器或登录器。窗口列表显示 Steam／PC 客户端，多窗口仍由用户选择；悬停可核对实际路径。榜单、模式识别、小程序操作及用户配置不改变。

本机 Windows 11 上，修复前 windows() 返回空，修复后唯一官方PC窗口可见。WGC按HWND实测读到2560×1334客户区，入口识别为ranked_chuhan_2v2。画面仅在内存分析，未保存游戏截图；私人元数据位于 .research/giant-pc-20261031/probe.json。新增8项窗口渠道判定测试通过；完整回归结果见TESTING。

待实战：巨人端四模式选将与战斗布局、统计位置、小程序往返、与Steam双开选择；入口截图成功不等于全部适配已验收。不自动启动、重启或控制游戏。

## Windows 10 用户反馈：单独问题，本轮先诊断

反馈包为1.0.0，系统Windows-10-10.0.19045-SP0、AMD64、Python3.11.9、windows-capture 2.0.1，无图片。18:42:11至19:18:50（北京时间）的33条限频fault均为：

`Capture session threw an exception: Graphics capture error: Toggling the capture border is not supported by the Graphics Capture API on this platform.`

代码Capture构造固定传draw_border=False。Microsoft文档标明IsBorderRequired从build20348引入，用户19045缺少该可选接口；依赖源码在显式配置边框而接口不可用时抛出此错误。因此本次阻点是截图会话初始化，不是OCR字库、武将置信度或巨人路径过滤；不需要截图也足以定位这一个错误。

修复方向（尚未实施）：不支持时用draw_border=None保留系统默认捕获边框，检查minimum_update_interval=200等可选能力也是否可用，默认参数回退而非要求用户关闭系统保护或反复管理员运行。库源码显示更新间隔也有独立“不支持”错误；当前日志只证实边框，不能声称其他错误已经发生。降级时应保留应用层识别节流并提示兼容状态。需Windows10 19045实机回传首帧、持续识别及负载数据；不能以本机Win11成功宣称Win10通过。

依据：
- https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.graphicscapturesession.isborderrequired
- https://docs.rs/windows-capture/latest/src/windows_capture/graphics_capture_api.rs.html
- 本地已锁定windows_capture 2.0.1构造参数draw_border及minimum_update_interval默认均为None。

反馈原包包含诊断上下文，仅本地读取；不上传或打包。公开记录只保留脱敏错误、版本和结论。
