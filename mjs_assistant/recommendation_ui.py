from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QCheckBox,QLineEdit,
    QComboBox,QDialogButtonBox,QTableWidget,QTableWidgetItem,QMessageBox,QSpinBox)

from .hotkeys import parse_hotkey


class RecommendationSettings(QDialog):
    def __init__(self,settings,parent=None,bound_hwnd=None):
        super().__init__(parent);self.original_settings=dict(settings);self.setWindowTitle('小程序配阵设置');self.resize(620,460)
        layout=QVBoxLayout(self)
        text=QLabel('普通排位将完整原始游戏 PNG 临时保存并交给“名将小助手”，可能包含昵称，小程序可能上传并保留副本。巅峰楚汉只通过公开选将页输入已确认姓名。助手不操作微信登录或游戏选将。')
        text.setWordWrap(True);layout.addWidget(text)
        self.enabled=QCheckBox('启用以上小程序配阵方式');self.enabled.setChecked(settings.get('enabled',True));layout.addWidget(self.enabled)
        self.guides=QCheckBox('开启攻略浮窗（关闭时停止查询；本地武将统计不受影响）')
        self.guides.setChecked(settings.get('guides_enabled',True));layout.addWidget(self.guides)
        self.auto=QCheckBox('自动查询：选将一次；普通排位战斗另查敌方一次');self.auto.setChecked(settings.get('automatic',True));layout.addWidget(self.auto)
        note=QLabel('数据统计直接查询本地官方榜单，无需小程序。攻略需打开“名将小助手 → 一键配阵”，选择“按强度／位置不限”。普通排位传原始 PNG，最多15秒；巅峰提交已确认姓名，最多40秒。未读完会保留部分攻略并注明；战斗自动收起。普通战斗只补查敌方一次，巅峰只用缓存。键鼠操作不直接取消；输入阶段离开小程序等待恢复，提交后可以只读结果。')
        note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();self.keys={}
        from .mini_windows import mini_windows
        self.connection=QComboBox();self.connection.addItem('自动连接唯一窗口',None)
        candidates=mini_windows()
        for hwnd in candidates:self.connection.addItem(f'名将小助手 · HWND {hwnd}',hwnd)
        self.connection.setCurrentIndex(max(0,self.connection.findData(bound_hwnd)))
        form.addRow(f'小程序窗口（检测到 {len(candidates)} 个）',self.connection)
        for key,label,default in [('request','重新配阵','Ctrl+Alt+P'),('details','显示详情','Ctrl+Alt+D'),('cancel','取消','Ctrl+Alt+X')]:
            edit=QLineEdit(settings.get('hotkeys',{}).get(key,default));self.keys[key]=edit;form.addRow(label,edit)
        self.x=QSpinBox();self.x.setRange(0,90);self.x.setValue(round(settings.get('panel_anchor',settings.get('anchor',[.015,.40]))[0]*100))
        self.y=QSpinBox();self.y.setRange(0,90);self.y.setValue(round(settings.get('panel_anchor',settings.get('anchor',[.015,.40]))[1]*100))
        form.addRow('推荐面板横向位置 %',self.x);form.addRow('推荐面板纵向位置 %',self.y);layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def save(self):
        try:
            values={k:v.text().strip() for k,v in self.keys.items()}
            parsed=[parse_hotkey(v) for v in values.values()]
            if len(set(parsed))!=3:raise ValueError('三个快捷键不能相同')
            self.result_settings=dict(self.original_settings,enabled=self.enabled.isChecked(),guides_enabled=self.guides.isChecked(),automatic=self.auto.isChecked(),
                hotkeys=values,panel_anchor=[self.x.value()/100,self.y.value()/100],privacy_notice_version=1)
            self.selected_hwnd=self.connection.currentData()
            self.accept()
        except ValueError as error:QMessageBox.warning(self,'快捷键无效',str(error))


class CandidateDialog(QDialog):
    def __init__(self,snapshot,parent=None):
        super().__init__(parent);self.snapshot=snapshot;self.setWindowTitle('确认本轮候选范围和锁将');self.resize(610,580)
        layout=QVBoxLayout(self)
        label=QLabel('只勾选当前仍可选择的武将。已被敌方选择或禁用的武将需取消；队友已锁定时在下方指定。候选图像或姓名变化后，这份确认立即失效。')
        label.setWordWrap(True);layout.addWidget(label)
        if snapshot.shared_pool_assumed:
            label=QLabel('普通排位暂按双方共享 8 张候选处理（用户提供的规则尚待确认，可在此修改）。');label.setWordWrap(True);layout.addWidget(label)
        names=list(dict.fromkeys(snapshot.own_pool+snapshot.ally_pool));self.names=names
        self.table=QTableWidget(len(names),3);self.table.setHorizontalHeaderLabels(['武将','自己可选','队友可选'])
        for i,name in enumerate(names):
            item=QTableWidgetItem(name);item.setFlags(Qt.ItemFlag.ItemIsEnabled);self.table.setItem(i,0,item)
            for j,pool in ((1,snapshot.own_pool),(2,snapshot.ally_pool)):
                item=QTableWidgetItem();item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if name in pool else Qt.CheckState.Unchecked);self.table.setItem(i,j,item)
        layout.addWidget(self.table)
        form=QFormLayout();self.own_seat=QComboBox();self.ally_seat=QComboBox()
        for field,seat,label in ((self.own_seat,snapshot.own_seat,'自己座次'),(self.ally_seat,snapshot.ally_seat,'队友座次')):
            field.addItem('未知',None)
            for number in range(1,5):field.addItem(str(number),number)
            field.setCurrentIndex(max(0,field.findData(seat)));form.addRow(label,field)
        self.locked=QComboBox();self.locked.addItem('尚未锁定',None)
        for name in names:self.locked.addItem(name,name)
        form.addRow('队友已锁定',self.locked)
        self.self_locked=QCheckBox('我已锁定（停止推荐）');form.addRow(self.self_locked);layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def save(self):
        own=tuple(n for i,n in enumerate(self.names) if self.table.item(i,1).checkState()==Qt.CheckState.Checked)
        ally=tuple(n for i,n in enumerate(self.names) if self.table.item(i,2).checkState()==Qt.CheckState.Checked)
        sa,sb=self.own_seat.currentData(),self.ally_seat.currentData()
        if sa and sa==sb:QMessageBox.warning(self,'座次冲突','自己与队友不能使用相同座次。');return
        self.result_snapshot=replace(self.snapshot,own_pool=own,ally_pool=ally,ally_locked=self.locked.currentData(),
            own_locked='已锁定' if self.self_locked.isChecked() else None,own_seat=sa,ally_seat=sb,pools_confirmed=True,reference_only=False,image_only=False)
        self.accept()
