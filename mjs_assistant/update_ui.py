"""Read-only status view; retry actions delegate to isolated updater workers."""
from datetime import datetime
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from .storage import read_json, ASSETS
from .build_identity import get_build_identity


def timestamp(value):
    if not value:return '尚无成功记录'
    try:return datetime.fromtimestamp(float(value)).strftime('%Y-%m-%d %H:%M')
    except (ValueError,TypeError,OverflowError,OSError):return str(value)


class UpdateDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner);self.owner=owner
        self.setWindowTitle('更新与数据');self.resize(680,460)
        layout=QVBoxLayout(self);self.label=QLabel();self.label.setWordWrap(True);layout.addWidget(self.label)
        row=QHBoxLayout()
        for name,callback in [('检查软件版本',self.software),('重试官方榜单',lambda:owner.start_data(force=True)),
                              ('重试组合库',lambda:owner.jiangce_check.check(force=True))]:
            button=QPushButton(name);button.clicked.connect(callback);row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(QLabel('便携版重启最外层 launch.cmd 后自动升级；源码目录仅提示。'))
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(1500);self.refresh()

    def software(self):
        from .software_update import SourceUpdateCheck
        owner=self.owner
        if getattr(owner,'software_check',None) and owner.software_check.isRunning():return
        owner.software_check=SourceUpdateCheck(owner)
        owner.software_check.message.connect(lambda text:owner.tray.showMessage('助手更新',text))
        owner.software_check.start()

    def refresh(self):
        folder=self.owner.folder
        rows=['软件：'+get_build_identity().display]
        for name,path in [('软件检查','software-check.json'),('官方榜单','update_state.json'),('组合库','jiangce-check.json')]:
            state=read_json(folder/path,{})
            rows.extend(['',name+'：'+str(state.get('message',state.get('status','等待检查'))),
                         '上次尝试：'+timestamp(state.get('last_attempt'))+'；上次成功：'+timestamp(state.get('last_success'))])
        seed=read_json(ASSETS/'jiangce/channel.json',{})
        book=getattr(self.owner,'local_book',None)
        rows.append('当前局组合库：'+str(getattr(book,'date',seed.get('date','未知'))))
        for board in self.owner.store.all_current().values():
            rows.append(board['mode']+'：'+board.get('period_start','')+'—'+board.get('period_end','')+'（'+str(len(board['heroes']))+'名）')
        channel=read_json(folder/'board-channel-state.json',{})
        rows.append('签名榜单来源：'+('、'.join(channel.get('sources',[])) or '尚未连接成功；沿用本地数据'))
        rows.append('组合库检查来源：'+self.owner.jiangce_check.last.get('source','尚未连接成功'))
        self.label.setText('\n'.join(rows))
