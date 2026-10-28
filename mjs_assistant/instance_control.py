"""Small per-data-directory local channel to reopen an already running app."""
import hashlib
from pathlib import Path
from PySide6.QtCore import QTimer,QEventLoop
from PySide6.QtNetwork import QLocalServer,QLocalSocket


def endpoint(folder):
    return 'MjsSettings-'+hashlib.sha256(str(Path(folder).resolve()).casefold().encode()).hexdigest()[:24]


def request_settings(folder,owner_pid=None):
    socket=QLocalSocket();socket.connectToServer(endpoint(folder))
    if not socket.waitForConnected(500):return False
    if owner_pid:
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(int(owner_pid))
        except Exception:pass
    loop=QEventLoop();timeout=QTimer();timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit);socket.readyRead.connect(loop.quit)
    socket.write(b'show-settings\n');socket.flush();timeout.start(500)
    if not socket.bytesAvailable():loop.exec()
    timeout.stop();sent=bytes(socket.readAll())==b'ok\n';socket.disconnectFromServer()
    return sent


class SettingsServer(QLocalServer):
    def __init__(self,folder,show,parent=None):
        super().__init__(parent);self.show=show
        self.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        # Caller must already own assistant.lock before cleaning a stale endpoint.
        self.removeServer(endpoint(folder))
        if not self.listen(endpoint(folder)):raise RuntimeError(self.errorString())
        self.newConnection.connect(self.accept_requests)

    def accept_requests(self):
        while self.hasPendingConnections():
            client=self.nextPendingConnection();buffer=bytearray()
            def read(client=client,buffer=buffer):
                buffer.extend(bytes(client.readAll()))
                if len(buffer)>64:client.abort();return
                if b'\n' in buffer:
                    if buffer==b'show-settings\n':
                        self.show();client.write(b'ok\n');client.flush()
                    client.disconnectFromServer()
            client.readyRead.connect(read)
            client.disconnected.connect(client.deleteLater)
            timeout=QTimer(client);timeout.setSingleShot(True);timeout.timeout.connect(client.abort);timeout.start(1000)
            read()
