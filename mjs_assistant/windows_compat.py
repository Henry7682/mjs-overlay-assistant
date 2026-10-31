"""Windows feature policy; no game, desktop or input access.

Target: Windows 10 22H2 x64 (19045) and Windows 11. Older builds are
handled conservatively, not advertised as fully validated platforms.
"""
import sys
import ctypes


def windows_build():
    # Actual kernel version, unaffected by an old executable manifest.
    return sys.getwindowsversion().platform_version[2]


def capture_options(build):
    return {
        'cursor_capture': False if build >= 19041 else None,
        'draw_border': False if build >= 20348 else None,
        'minimum_update_interval': 200 if build >= 26100 else None,
    }


def optional_capture_error(error):
    # Only retry explicit unsupported-option errors, never access/device/ HWND
    # errors. The library already performs property-availability checks.
    text = str(error).lower()
    return any(message in text for message in (
        'toggling cursor capture is not supported',
        'toggling the capture border is not supported',
        'setting a minimum update interval is not supported',
    ))


def runtime_issue(build=None, load=None):
    """Check hard prerequisites before Qt/OpenCV imports can raise DLL errors."""
    if build is None: build = windows_build()
    if build < 19041:
        return '此兼容包要求 Windows 10 2004（19041）或更高的 x64 系统，建议 22H2（19045）。'
    if load is None:
        load = lambda name: ctypes.WinDLL(name, winmode=0x800)  # System32 only
    missing = []
    for name in ('icuuc.dll', 'mfplat.dll', 'mf.dll', 'mfreadwrite.dll'):
        try: load(name)
        except OSError: missing.append(name)
    if missing:
        return ('缺少或无法加载 Windows 系统组件：' + '、'.join(missing) +
                '。Windows 10 N 请在“设置 → 应用 → 可选功能”安装微软 Media Feature Pack；'
                '其他系统请使用 Windows 更新或系统修复恢复组件。不要从第三方网站下载单个 DLL。'
                '详细说明见 docs/WINDOWS-COMPATIBILITY.md。')
    return None
