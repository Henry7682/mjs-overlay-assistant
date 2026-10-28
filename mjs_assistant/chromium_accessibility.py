"""Request the bound window's public MSAA client object before a UIA read."""
import ctypes as C
from ctypes import wintypes as W


def wake_accessibility(hwnd):
    import comtypes
    import comtypes.client
    module=comtypes.client.GetModule('oleacc.dll')
    accessible=C.POINTER(module.IAccessible)()
    oleacc=C.OleDLL('oleacc')
    get=oleacc.AccessibleObjectFromWindow
    get.argtypes=[W.HWND,W.DWORD,C.POINTER(comtypes.GUID),C.POINTER(C.POINTER(module.IAccessible))]
    get.restype=C.c_long
    hr=get(hwnd,0xfffffffc,C.byref(module.IAccessible._iid_),C.byref(accessible))
    if hr<0 or not accessible:return {'ok':False,'hr':hr}
    # Asking for child count prompts lazy renderers to expose web contents.
    count=accessible.accChildCount
    return {'ok':True,'children':count}
