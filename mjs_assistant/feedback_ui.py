"""Explicit preview/export; never submits diagnostics to any service."""
from pathlib import Path
from PySide6.QtCore import Qt,QRect,QByteArray,QBuffer,QIODevice
from PySide6.QtGui import QPixmap,QPainter,QColor,QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,
    QListWidget,QListWidgetItem,QFileDialog,QMessageBox,QSplitter,QPlainTextEdit)
from .version import ISSUES_URL,VERSION
from .build_identity import get_build_identity

class Preview(QLabel):
    def __init__(self):
        super().__init__();self.original=None;self.edited=None;self.start=None;self.setMinimumSize(400,240)
        self.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
    def load(self,path):
        self.original=QPixmap(str(path));self.edited=self.original.copy();self.refresh()
    def refresh(self):
        if self.edited:self.setPixmap(self.edited.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def resizeEvent(self,event):super().resizeEvent(event);self.refresh()
    def mousePressEvent(self,event):self.start=event.position().toPoint()
    def mouseReleaseEvent(self,event):
        if self.start is None or not self.edited or not self.pixmap():return
        scale=self.edited.width()/self.pixmap().width();r=QRect(self.start,event.position().toPoint()).normalized()
        painter=QPainter(self.edited);painter.fillRect(QRect(int(r.x()*scale),int(r.y()*scale),int(r.width()*scale),int(r.height()*scale)),QColor('black'));painter.end()
        self.start=None;self.refresh()
    def png(self):
        data=QByteArray();buffer=QBuffer(data);buffer.open(QIODevice.OpenModeFlag.WriteOnly);self.edited.save(buffer,'PNG');return bytes(data)

class FeedbackDialog(QDialog):
    def __init__(self,recorder,parent=None):
        super().__init__(parent);self.recorder=recorder;self.edits={};self.current=None
        self.setWindowTitle('反馈问题与本地诊断');self.resize(980,700)
        layout=QVBoxLayout(self)
        note=QLabel('默认导出脱敏日志，不含图片。GitHub Issue附件公开；含原图的包请加入QQ群104720192，联系群主／管理员后私聊发送。不会自动上传。选中图片可预览，拖动鼠标画黑块遮挡昵称等内容，再勾选导出。')
        note.setWordWrap(True);layout.addWidget(note)
        self.enabled=QCheckBox('开启本地故障画面（前30秒／后10秒，最多500MB，7天自动清理）');self.enabled.setChecked(recorder.enabled)
        self.enabled.toggled.connect(self.toggle);layout.addWidget(self.enabled)
        split=QSplitter();self.list=QListWidget();self.preview=Preview();split.addWidget(self.list);split.addWidget(self.preview);layout.addWidget(split)
        for path in sorted(recorder.root.glob('*/*.png')):
            item=QListWidgetItem(path.parent.name+'/'+path.name);item.setData(Qt.ItemDataRole.UserRole,str(path));item.setCheckState(Qt.CheckState.Unchecked);self.list.addItem(item)
        self.list.currentItemChanged.connect(self.show_image)
        self.summary=QPlainTextEdit(f'版本：{get_build_identity().display}\n事件编号：{recorder.session}\n模式／阶段：\n复现步骤：\n预期行为：\n实际行为：\n附件：导出的feedback ZIP（公开提交前核对是否包含图片）')
        self.summary.setMaximumHeight(145);layout.addWidget(self.summary)
        row=QHBoxLayout();layout.addLayout(row)
        for title,callback in [('记录当前问题',self.record),('导出反馈包',self.export),('打开GitHub反馈',self.open_issue),('清除本地故障包',self.clear)]:
            b=QPushButton(title);b.clicked.connect(callback);row.addWidget(b)
    def toggle(self,enabled):
        self.recorder.set_enabled(enabled)
        owner=self.parent()
        if owner and hasattr(owner,'config'):
            from .storage import write_json
            owner.config.setdefault('diagnostics',{})['capture_enabled']=enabled;write_json(owner.folder/'settings.json',owner.config)
    def show_image(self,item,previous):
        if self.current and self.preview.edited:self.edits[self.current]=self.preview.png()
        self.current=item.data(Qt.ItemDataRole.UserRole) if item else None
        if self.current:
            self.preview.load(self.current)
            if self.current in self.edits:self.preview.edited.loadFromData(self.edits[self.current]);self.preview.refresh()
    def record(self):
        ident=self.recorder.trigger('用户记录问题');QMessageBox.information(self,'已记录',f'事件：{ident}\n约10秒后完成保存；重新打开此页面可查看新增画面。')
    def export(self):
        self.show_image(self.list.currentItem(),None)
        selected={}
        for i in range(self.list.count()):
            item=self.list.item(i)
            if item.checkState()==Qt.CheckState.Checked:
                path=item.data(Qt.ItemDataRole.UserRole)
                if path not in self.edits:
                    QMessageBox.information(self,'请先预览','请逐张点击并预览勾选图片后再导出。');return
                selected[path]=self.edits[path]
        if selected and QMessageBox.question(self,'确认图片内容',f'将包含{len(selected)}张图片。请确认已检查昵称和无关信息；原始画面应私聊发送。')!=QMessageBox.StandardButton.Yes:return
        folder=QFileDialog.getExistingDirectory(self,'选择反馈包保存目录')
        if not folder:return
        try:
            paths=self.recorder.export(folder,selected)
            (Path(folder)/(paths[0].stem+'-说明.txt')).write_text(self.summary.toPlainText(),'utf8')
            QMessageBox.information(self,'已导出','\n'.join(p.name for p in paths)+'\n请自行提交；没有自动上传。')
        except Exception as e:QMessageBox.warning(self,'导出失败',str(e))
    def open_issue(self):QDesktopServices.openUrl(QUrl(ISSUES_URL))
    def clear(self):
        if QMessageBox.question(self,'清理本地故障包','仅删除助手登记的故障图片和事件包，已导出的包不受影响。')!=QMessageBox.StandardButton.Yes:return
        self.recorder.clear_incidents()
        self.current=None;self.preview.edited=None;self.preview.original=None
        self.list.clear();self.edits.clear();self.preview.clear()
