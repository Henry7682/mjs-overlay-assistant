# Windows 10／11 兼容审查与测试（1.0.2）

1.0.2 是 **Win10 兼容测试包**。目标为 Windows 10 22H2 x64（19045），也保留 Windows 11 的现有行为。最低启动边界为 Windows 10 2004（19041）；更旧 Win10、32位、ARM和精简系统不在本次支持承诺内。维护者当前只有 Win11 实机，因此尚不能宣称 Win10 全功能验收通过。

## 功能保持一致

继续使用同一套四模式统计、官方榜单、OCR／两帧确认、自动模式识别、校准、强势武将、傀儡候选、2v2小程序查询与可拖动战斗攻略。普通楚汉统计仍来自巅峰楚汉；查询预算仍为15／40秒，快捷键与用户配置不改。没有新增游戏输入，也没有为Win10改成截取整个桌面。

Win10可能出现系统自带的捕获边框；它是系统提示，不是错误，不需要关闭安全设置。截图仍绑定游戏HWND，配阵切窗后仍可读取该窗口。

## 审查结果与修复

| 范围 | 文档／代码结论 | 本版处理 |
| --- | --- | --- |
| WGC边框 IsBorderRequired | 20348才引入，19045显式设置会失败 | 旧系统传None，保留系统默认；新系统保持False |
| WGC MinUpdateInterval | 文档支持26100起，Win10和早期Win11不可用 | 旧系统传None，回调复制图像最多约5次/秒；识别循环仍约2次/秒 |
| WGC IsCursorCaptureEnabled | 19041起 | 支持时保持False；更旧能力策略为None，实际程序拒绝低于最低系统 |
| 属性判断与异常 | 构建号初筛不代替依赖内部能力检测 | 仅明确“可选接口不支持”时同HWND用系统默认重试一次；权限／设备／窗口错误不掩盖 |
| DPI／坐标 | SetProcessDpiAwarenessContext需1703；GetDpiForWindow需1607 | 19045均支持，保留每显示器DPI与物理坐标逻辑 |
| 统计／攻略浮窗 | SetWindowDisplayAffinity的0x11需2004，分层、透明、置顶及无激活窗口API更早可用 | 19045支持，保留排除捕获、鼠标穿透及局部可拖动面板 |
| 托盘／热键／单实例 | Qt托盘、RegisterHotKey、QLockFile/QLocalServer及AllowSetForegroundWindow无Win11专用要求 | 保留原流程；热键冲突仍提示，不拦截用户输入 |
| 微信UIA／MSAA／Win32文件框 | Windows UIA COM、oleacc与现有窗口操作可用于Win10 | 保留公开界面查询；不将UIA延迟当成已解决的系统兼容问题 |
| 切窗 | SetForegroundWindow仍受Windows前台规则限制 | 保留现有桥接与前台核验，不能保证每次切窗必定成功 |
| 更新／下载 | Windows PowerShell5.1、.NET、TLS1.2、RSA3072、ZIP路径及哈希校验 | 沿用现有签名协议；本测试版不进入稳定自动更新通道 |
| 系统组件 | Qt使用icuuc.dll；实际cv2.pyd静态依赖MF/MFPlat/MFReadWrite | GUI/OCR导入前检测，缺少时给出系统组件修复提示；不下载不明DLL |

硬件驱动、WGC不可用、远程桌面、黑屏、最小化和被系统限制的捕获仍按原行为显示错误／暂停；不以桌面截屏兜底。

## 依赖审查

保留原哈希锁定依赖与模型：CPython3.11.9、Qt/PySide6 Essentials6.12.0、RapidOCR3.10.0、ONNX Runtime CPU1.31.0、OpenCV5.0.0.93、NumPy2.4.6、windows-capture2.0.1、pywinauto0.6.9、pywin32 312、comtypes1.4.17。未为兼容性盲目降级模型或替换算法。

- Python3.11支持Windows8.1及以上；Qt6.12列明Win10 1809及以上；ONNX Runtime官方列明Win10运行目标及VC++运行库要求。实际包仍需在Win10运行验证，文档支持不等于这份包已验证。
- 检查现有发行包156个EXE/DLL/PYD的导入表：WGC依赖CoreMessaging的CreateDispatcherQueueController（1709），Qt的ICU为1703起系统组件，主程序使用的DPI接口均早于19045。
- 静态导入审查不能发现所有动态加载、驱动及COM差异；没有逐项对照真实19045系统DLL导出表，不能宣称完成二进制兼容证明。纯Python依赖和图像算法仍通过锁定依赖、导入自检及回归测试核对。
- Windows 10 N若缺少媒体功能，请在“设置→应用→可选功能”安装微软Media Feature Pack，按微软要求重启。精简系统应恢复系统组件；不得从DLL站补文件。VC++运行库仍使用项目依赖表中的微软官方x64安装器。

## 使用与验证

1. 从 **v1.0.2预发行页面**下载完整win64 ZIP，解压到新目录；不要用稳定下载器获取测试包。
2. 如需沿用配置，先退出旧助手，将其最外层data复制到新目录；保留旧目录，不覆盖。
3. 双击最外层launch.cmd。旧稳定清单版本较低时不会降级本包；本轮不推送1.0.2到稳定更新通道。
4. 双击compat-check.cmd：依次检测模型、Qt、OCR、UIA、设置初始化，再打开短暂的助手测试窗口验证WGC连续帧与客户区尺寸。它不连接游戏、不操作小程序、不保存图像，使用独立临时配置。
5. 检查报告位于本包compatibility-checks下。自检成功也不是完整实战成功。反馈时附该报告以及设置中导出的诊断包；原始游戏画面仅私聊发送。

源码也可运行：`python main.py --capture-check capture-report.json`。这只测当前真实系统的截图；开发者在Win11注入19045策略的结果必须标为模拟策略，不得当作Win10实机证据。

待验收：19045首次启动与首帧、持续选将/战斗、四模式与两客户端、125%/150%DPI、移动/最小化/还原、切到小程序后后台截图、相册/填名/结果返回、热键/托盘/拖动、关闭攻略不影响统计、配置迁移与反馈导出。按TODO T38持续维护。

## 官方依据（2026-10-31核对）

- [IsBorderRequired](https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.graphicscapturesession.isborderrequired)、[MinUpdateInterval](https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.graphicscapturesession.minupdateinterval)、[IsCursorCaptureEnabled](https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.graphicscapturesession.iscursorcaptureenabled)
- [DPI上下文](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext)、[窗口DPI](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow)、[浮窗排除捕获](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity)
- [UIA](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview)、[前台窗口限制](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)、[DispatcherQueue](https://learn.microsoft.com/en-us/windows/win32/api/dispatcherqueue/nf-dispatcherqueue-createdispatcherqueuecontroller)
- [Qt6.12 Windows支持](https://doc.qt.io/qt-6.12/windows.html)、[Python3.11 Windows支持](https://docs.python.org/3.11/using/windows.html)、[ONNX Runtime兼容](https://onnxruntime.ai/docs/reference/compatibility.html)、[ONNX Runtime安装](https://onnxruntime.ai/docs/install/)
- [系统ICU](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-)、[Media Feature Pack](https://support.microsoft.com/en-us/windows/experience/platform-variants/media-feature-pack-list-for-windows-n-editions)、[VC++运行库](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)
