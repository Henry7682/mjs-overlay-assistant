import pytest
from mjs_assistant.capture import client_kind

STEAM = r'D:\SteamLibrary\steamapps\common\名将杀\mjs.exe'
PC = r'D:\Games\MJS_official\mjs.exe'


def test_official_pc_not_excluded_when_steam_is_installed():
    assert client_kind(PC,'名将杀','UnityWndClass',{STEAM}) == 'PC 客户端'
    assert client_kind(STEAM,'名将杀','UnityWndClass',{STEAM}) == 'Steam'


def test_no_steam_install_required():
    assert client_kind(PC,'名将杀','UnityWndClass',set()) == 'PC 客户端'


def test_steam_path_is_case_insensitive():
    assert client_kind(STEAM.upper(),'名将杀','UnityWndClass',{STEAM}) == 'Steam'


@pytest.mark.parametrize('path,title,kind',[
    (r'D:\Games\launcher.exe','名将杀','UnityWndClass'),
    (PC,'名将杀','Chrome_WidgetWin_1'),
    (PC,'登录器','UnityWndClass'),
    (PC,'','UnityWndClass'),
    (r'D:\Games\other.exe','名将杀','UnityWndClass'),
])
def test_unrelated_windows_not_bound(path,title,kind):
    assert client_kind(path,title,kind,{STEAM}) is None
