"""Local strategy editor; no network or game automation."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,
    QTextEdit,QTableWidget,QTableWidgetItem,QPushButton,QMessageBox,QDialogButtonBox,
    QLabel,QCheckBox)
from .custom_guides import CustomGuides
from .jiangce import preferred


class CardEditor(QDialog):
    def __init__(self, card=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑个人组合');self.resize(650,560)
        self.original = dict(card or {})
        layout=QVBoxLayout(self);form=QFormLayout()
        heroes=self.original.get('heroes',['',''])
        self.first=QLineEdit(heroes[0]);self.second=QLineEdit(heroes[1])
        form.addRow('武将一（完整姓名）',self.first);form.addRow('武将二（完整姓名）',self.second)
        layout.addLayout(form)
        self.reason=QTextEdit();self.reason.setPlainText(self.original.get('reason',''))
        layout.addWidget(QLabel('攻略说明（个人修改，不代表小程序作者意见）'));layout.addWidget(self.reason)
        hint=QLabel('每行一个站位：座次填1—4；两侧都留空表示未知。评分填0/5—5/5或留空。')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['武将一座次','武将二座次','个人评分'])
        layout.addWidget(self.table)
        for v in self.original.get('variants',[{'group':'未知'}]):
            seats=dict(v.get('seats',[]));self.add_row([str(seats.get(h,'')) for h in heroes]+[v.get('rating','')])
        row=QHBoxLayout();add=QPushButton('增加站位');remove=QPushButton('删除所选站位')
        add.clicked.connect(lambda:self.add_row(['','','']));remove.clicked.connect(lambda:self.table.removeRow(self.table.currentRow()))
        row.addWidget(add);row.addWidget(remove);layout.addLayout(row)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.submit);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def add_row(self,values):
        row=self.table.rowCount();self.table.insertRow(row)
        for col,value in enumerate(values):self.table.setItem(row,col,QTableWidgetItem(value))

    def submit(self):
        try:
            heroes=[self.first.text().strip(),self.second.text().strip()];variants=[]
            for row in range(self.table.rowCount()):
                values=[self.table.item(row,c).text().strip() if self.table.item(row,c) else '' for c in range(3)]
                a,b,rating=values
                if bool(a)!=bool(b):raise ValueError('未知站位时两侧都应留空')
                v={'group':f'{a}/{b}' if a else '未知'}
                if a:v['seats']=[[heroes[0],int(a)],[heroes[1],int(b)]]
                if rating:v['rating']=rating
                variants.append(v)
            self.result_card=dict(self.original,heroes=heroes,reason=self.reason.toPlainText().strip(),variants=variants)
            from .custom_guides import validate_card
            validate_card(self.result_card)
        except (ValueError,TypeError) as exc:
            QMessageBox.warning(self,'无法保存',str(exc));return
        self.accept()


class GuideEditor(QDialog):
    def __init__(self,folder,parent=None):
        super().__init__(parent);self.folder=folder;self.setWindowTitle('本地组合库 · 个人编辑');self.resize(850,600)
        self.custom=CustomGuides(folder);self.base=preferred(folder,custom=False).cards
        layout=QVBoxLayout(self)
        note=QLabel('个人新增、修改及隐藏独立保存，自动更新不会覆盖。当前对局保留原缓存，下一局生效。恢复原版会移除个人修改；个人新增则被移除。')
        note.setWordWrap(True);layout.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索武将或攻略内容');layout.addWidget(self.search)
        self.hidden=QCheckBox('显示已隐藏条目（可恢复）');layout.addWidget(self.hidden)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['组合','状态','说明'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);layout.addWidget(self.table)
        buttons=QHBoxLayout()
        for title,action in [('新增组合',self.add),('编辑所选',self.edit),('删除／隐藏',self.hide_card),('恢复原版',self.restore)]:
            button=QPushButton(title);button.clicked.connect(action);buttons.addWidget(button)
        layout.addLayout(buttons)
        self.search.textChanged.connect(self.refresh);self.hidden.toggled.connect(self.refresh);self.refresh()

    def refresh(self):
        query=self.search.text().strip()
        self.rows=[c for c in self.custom.merge(self.base,include_hidden=self.hidden.isChecked())
                   if not query or query in ' '.join(c['heroes'])+' '+c['reason']]
        self.table.setRowCount(len(self.rows))
        for row,c in enumerate(self.rows):
            for col,value in enumerate([' ＋ '.join(c['heroes']), '已隐藏' if c['hidden'] else '个人编辑' if c.get('custom') else '来源攻略',c['reason'][:100]]):
                self.table.setItem(row,col,QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def selected(self):
        row=self.table.currentRow();return self.rows[row] if 0<=row<len(self.rows) else None

    def save_action(self,action):
        try:action();self.refresh()
        except Exception as exc:
            # Reload committed state after an I/O failure, never silently replace a corrupt file.
            self.custom=CustomGuides(self.folder)
            QMessageBox.warning(self,'保存失败',str(exc))

    def add(self):self.open_card(None)
    def edit(self):
        card=self.selected()
        if card:self.open_card(card)

    def open_card(self,card):
        dialog=CardEditor(card,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.save_action(lambda:self.custom.put(dialog.result_card,card['id'] if card else None))

    def hide_card(self):
        card=self.selected()
        if card and QMessageBox.question(self,'隐藏组合','隐藏此组合？可勾选“显示已隐藏条目”后恢复。')==QMessageBox.StandardButton.Yes:
            self.save_action(lambda:self.custom.hide(card['id']))

    def restore(self):
        card=self.selected()
        if card and QMessageBox.question(self,'恢复原版','移除此条目的个人修改及隐藏状态？个人新增条目将被移除。')==QMessageBox.StandardButton.Yes:
            self.save_action(lambda:self.custom.restore(card['id']))
