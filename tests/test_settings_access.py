import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace as NS
from unittest.mock import Mock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QWidget,QDialog,QSystemTrayIcon
from PySide6.QtTest import QTest
from PySide6.QtNetwork import QLocalSocket
from mjs_assistant.app import MainWindow
from mjs_assistant.settings_window import show_settings_window
from mjs_assistant.instance_control import SettingsServer,request_settings,endpoint


def test_single_and_double_click_open_settings_but_context_click_does_not():
    host=NS(open_settings=Mock())
    for reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick,
                   QSystemTrayIcon.ActivationReason.Context):MainWindow.tray_activated(host,reason)
    assert host.open_settings.call_count==2


def test_settings_action_is_queued_and_coalesced():
    app=QApplication.instance() or QApplication([])
    host=NS(_show_settings=Mock())
    MainWindow.open_settings(host);MainWindow.open_settings(host)
    host._show_settings.assert_not_called()
    app.processEvents();host._show_settings.assert_called_once()


def test_hidden_offscreen_settings_and_active_modal_can_be_restored(monkeypatch):
    import win32gui
    for name in ('ShowWindow','SetForegroundWindow'):monkeypatch.setattr(win32gui,name,Mock())
    monkeypatch.setattr(win32gui,'IsWindowVisible',lambda _:True)
    app=QApplication.instance() or QApplication([])
    window=QWidget();window.resize(500,400);window.move(-20000,-20000)
    assert show_settings_window(window) is window and window.isVisible()
    assert any(s.availableGeometry().intersects(window.frameGeometry()) for s in app.screens())
    modal=QDialog(window);modal.setWindowModality(Qt.WindowModality.ApplicationModal);modal.show();app.processEvents()
    assert show_settings_window(window) is modal
    modal.close();window.close()


def test_second_launch_forwards_only_settings_command(tmp_path):
    app=QApplication.instance() or QApplication([]);show=Mock()
    server=SettingsServer(tmp_path,show)
    try:
        assert request_settings(tmp_path)
        QTest.qWait(50);show.assert_called_once()
        bad=QLocalSocket();bad.connectToServer(endpoint(tmp_path));assert bad.waitForConnected(200)
        bad.write(b'run-command\n');bad.waitForBytesWritten(200);QTest.qWait(50)
        show.assert_called_once();bad.abort()
        assert not request_settings(tmp_path/'other-profile')
    finally:server.close()
