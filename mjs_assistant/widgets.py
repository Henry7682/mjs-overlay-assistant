from __future__ import annotations

import copy
import ctypes as C
from ctypes import wintypes as W

import cv2
from PySide6.QtCore import Qt, QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QImage, QPixmap, QFont
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QSpinBox,QDialogButtonBox,
                              QTableWidget,QTableWidgetItem,QHeaderView,QLineEdit,QMessageBox,QSplitter,QScrollArea,QCheckBox)

from .boards import MODE,validate_board
from .recognition import place_labels,profile_key
from .modes import MODES,MINGDAO,PEAK_SHUANGLONG
from .stats_source import source_label,is_strong
from .overlay_scale import logical_scale


def pixmap(frame):
    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
    h,w=rgb.shape[:2]
    return QPixmap.fromImage(QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy())


class Overlay(QWidget):
    def __init__(self,store):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool|Qt.WindowType.WindowTransparentForInput|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.store=store;self.game_mode=None;self.items=[];self.frame_size=(1,1);self.offset=(0,0);self.anchors={}
        self.recommendation=None;self.recommendation_status='';self.detail=False;self.rec_anchor=(.015,.40);self.status_lines=[]
        self.setWindowTitle('名将统计悬浮层')
        self.hwnd=int(self.winId())
        u=C.windll.user32
        u.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];u.GetWindowLongPtrW.restype=C.c_ssize_t
        u.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t]
        u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
        u.SetWindowLongPtrW(self.hwnd,-20,u.GetWindowLongPtrW(self.hwnd,-20)|0x80000|0x20|0x8000000|0x80)
        # Prevent the overlay entering diagnostic desktop capture paths.
        u.SetWindowDisplayAffinity.argtypes=[W.HWND,W.DWORD]
        u.SetWindowDisplayAffinity(self.hwnd,0x11)

    def present(self,rect,size,items,profile):
        self.frame_size=size;self.items=items;self.offset=tuple(profile.get('offset',[0,0]));self.anchors=profile.get('anchors',{})
        self.show()
        C.windll.user32.SetWindowPos(self.hwnd,W.HWND(-1),*map(int,rect),0x10|0x40)
        self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fw,fh=self.frame_size
        scale=logical_scale(self.width(),self.height())
        p.scale(scale,scale)
        width,height=self.width()/scale,self.height()/scale
        sx,sy=width/fw,height/fh
        # Draw in a common design space. One painter transform scales fonts,
        # boxes, borders and gaps together; screenshot positions stay aligned.
        from dataclasses import replace
        converted=[replace(d,box=(d.box[0]*sx,d.box[1]*sy,d.box[2]*sx,d.box[3]*sy)) for d in self.items if d.confirmed]
        normal_font=QFont('Microsoft YaHei UI');normal_font.setPixelSize(12)
        name_font=QFont('Microsoft YaHei UI');name_font.setPixelSize(13);name_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(normal_font)
        board=self.store.board
        period=f'{board["period_start"]} — {board["period_end"]}' if board.get('heroes') else '该模式暂无已复核榜单'
        title=f'{source_label(self.game_mode) if self.game_mode else board["mode"]}  ·  官方统计 {period}'
        text='\n'.join(self.status_lines) if self.status_lines else title
        banner_width=min(width-16,840)
        flags=Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignLeft
        banner_height=max(27,p.boundingRect(QRectF(0,0,banner_width-20,300),flags,text).height()+12)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(15,23,35,215));p.drawRoundedRect(QRectF(8,4,banner_width,banner_height),6,6)
        p.setPen(QColor('#e7c77a'));p.drawText(QRectF(18,10,banner_width-20,banner_height-12),flags,text)
        anchors={slot:(a*width,b*height) for slot,(a,b) in self.anchors.items()}
        for d,rect in place_labels(converted,width,height,286,46,(self.offset[0]*width,self.offset[1]*height),anchors):
            x,y,x2,y2=rect
            box=QRectF(x,y,x2-x,y2-y)
            record=self.store.lookup(d.name)
            strong=is_strong(record)
            p.setPen(QPen(QColor('#eac76b' if strong else '#567783'),2 if strong else 1))
            p.setBrush(QColor(58,44,21,240) if strong else QColor(13,24,35,225));p.drawRoundedRect(box,7,7)
            p.setPen(QColor('#f8e6b5'));p.setFont(name_font)
            p.drawText(QRectF(x+9,y+3,268,20),Qt.AlignmentFlag.AlignVCenter,(d.name or d.raw)+('  · 强势' if strong else ''))
            p.setFont(normal_font);p.setPen(QColor('#d5e4e8'))
            text=f'{record["win_rate"]:.2f}%  ·  胜率 #{record["win_rank"]}  ·  出场 #{record["pick_rank"]}' if record else ('本期未收录' if board.get('heroes') else '该模式暂无榜单')
            p.drawText(QRectF(x+9,y+23,268,18),Qt.AlignmentFlag.AlignVCenter,text)
            # Leader line preserves correspondence when labels move to avoid overlap.
            p.setPen(QPen(QColor(119,181,182,140),1))
            p.drawLine(QPointF((d.box[0]+d.box[2])/2,d.box[3]),QPointF(x+10,y))
        # Guides use a separate small interactive window; this layer stays click-through.

    def paint_recommendation(self,p):
        result=self.recommendation
        if not result and not self.recommendation_status:return
        lines=['配阵参考 · 来源：名将小助手' if result else '配阵状态']
        if result:
            if result.no_match:lines.append('未找到匹配的组合搭配')
            elif not result.recommendations:lines.append('已读取组合中无适用搭配')
            for i,r in enumerate(result.recommendations,1):
                if result.reference_only:
                    lines.append(f'{i}. 组合参考：{r.own_hero} ＋ {r.ally_hero}')
                    lines.append(f'原始座次：{r.own_hero} {r.own_seat or "?"}、{r.ally_hero} {r.ally_seat or "?"}'+(f' ｜ 评级：{r.rating}' if r.rating else ''))
                else:
                    lines.append(f'{i}. 你：{r.own_hero} ｜ 队友：{r.ally_hero}')
                    lines.append(f'座次：你 {r.own_seat or "?"}、队友 {r.ally_seat or "?"}'+(f' ｜ 评级：{r.rating}' if r.rating else ''))
                reason=r.reason if self.detail else r.reason[:44]+('…' if len(r.reason)>44 else '')
                if reason:lines.append('理由：'+reason)
            lines.extend(result.limits)
        else:lines.append(self.recommendation_status)
        text='\n'.join(lines);width=min(390,self.width()-24)
        p.setFont(QFont('Microsoft YaHei UI',9))
        flags=Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignLeft
        bounds=p.boundingRect(QRectF(0,0,width-24,1000),flags,text)
        height=min(bounds.height()+24,self.height()-42)
        x=max(8,min(self.width()-width-8,self.rec_anchor[0]*self.width()))
        y=max(36,min(self.height()-height-8,self.rec_anchor[1]*self.height()))
        p.setPen(QPen(QColor('#66999b'),1));p.setBrush(QColor(13,24,35,238))
        p.drawRoundedRect(QRectF(x,y,width,height),8,8)
        p.setPen(QColor('#e3e9de'));p.drawText(QRectF(x+12,y+12,width-24,height-24),flags,text)


class CalibrationCanvas(QWidget):
    def __init__(self,frame,regions,items,anchors):
        super().__init__();self.pm=pixmap(frame);self.regions=copy.deepcopy(regions);self.items=items;self.anchors=copy.deepcopy(anchors)
        self.begin=None;self.end=None;self.moving=None;self.mode='region'
        self.setMinimumSize(800,420);self.setMouseTracking(True)

    def image_rect(self):
        size=self.pm.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())

    def norm(self,point):
        r=self.image_rect();return (max(0,min(1,(point.x()-r.x())/r.width())),max(0,min(1,(point.y()-r.y())/r.height())))

    def paintEvent(self,event):
        p=QPainter(self);r=self.image_rect();p.drawPixmap(r.toRect(),self.pm)
        p.setBrush(QColor(25,170,165,35));p.setPen(QPen(QColor('#39dfca'),2))
        for i,(a,b,c,d) in enumerate(self.regions):
            rr=QRectF(r.x()+a*r.width(),r.y()+b*r.height(),(c-a)*r.width(),(d-b)*r.height())
            p.drawRect(rr);p.drawText(rr.topLeft()+QPointF(3,16),str(i+1))
        if self.begin and self.end and self.mode=='region':p.drawRect(QRectF(self.begin,self.end).normalized())
        if self.mode=='anchor':
            for item in self.items:
                anchor=self.anchors.get(item.slot,[(item.box[0])/self.pm.width(),item.box[3]/self.pm.height()])
                x,y=r.x()+anchor[0]*r.width(),r.y()+anchor[1]*r.height()
                p.fillRect(QRectF(x,y,150,25),QColor('#152b39'));p.drawText(QRectF(x+4,y,145,25),Qt.AlignmentFlag.AlignVCenter,item.name or item.raw)

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.begin=event.position();self.end=self.begin
        if self.mode=='anchor':
            r=self.image_rect()
            for item in self.items:
                a=self.anchors.get(item.slot,[item.box[0]/self.pm.width(),item.box[3]/self.pm.height()])
                if QRectF(r.x()+a[0]*r.width(),r.y()+a[1]*r.height(),150,25).contains(self.begin):self.moving=item.slot;break

    def mouseMoveEvent(self,event):
        if self.begin:
            self.end=event.position()
            if self.moving:self.anchors[self.moving]=list(self.norm(self.end))
            self.update()

    def mouseReleaseEvent(self,event):
        if self.begin and self.mode=='region':
            a,b=self.norm(self.begin);c,d=self.norm(event.position())
            if abs(a-c)>.005 and abs(b-d)>.01:self.regions.append([min(a,c),min(b,d),max(a,c),max(b,d)])
        self.begin=self.end=self.moving=None;self.update()


class CalibrationDialog(QDialog):
    def __init__(self,frame,scene,profiles,items,parent=None,layout_name='default'):
        super().__init__(parent);self.setWindowTitle('校准识别区域与标注位置');self.resize(1100,760)
        self.frame=frame;self.profiles=profiles;self.result_profile=None
        self.layout_name=layout_name
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('拖动框选姓名区域；每位武将的完整姓名各框一处，避免包含国籍和技能文字。空区域列表表示自动定位。'))
        row=QHBoxLayout();self.scene=QComboBox();self.scene.addItems(['selection','battle']);self.scene.setCurrentText(scene if scene in ('selection','battle') else 'battle')
        row.addWidget(QLabel('场景：selection 选将 / battle 战斗'));row.addWidget(self.scene)
        self.mode=QComboBox();self.mode.addItems(['框选识别区域','拖动标注位置']);row.addWidget(self.mode)
        undo=QPushButton('撤销最后区域');clear=QPushButton('恢复自动定位');row.addWidget(undo);row.addWidget(clear);layout.addLayout(row)
        h,w=frame.shape[:2];key=self.key(self.scene.currentText(),w,h);profile=profiles.get(key,{})
        self.canvas=CalibrationCanvas(frame,profile.get('regions',[]),items,profile.get('anchors',{}));layout.addWidget(self.canvas,1)
        undo.clicked.connect(lambda:(self.canvas.regions.pop() if self.canvas.regions else None,self.canvas.update()))
        clear.clicked.connect(lambda:(self.canvas.regions.clear(),self.canvas.anchors.clear(),self.canvas.update()))
        self.mode.currentIndexChanged.connect(lambda i:(setattr(self.canvas,'mode','region' if i==0 else 'anchor'),self.canvas.update()))
        self.scene.currentTextChanged.connect(self.load_profile)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def load_profile(self):
        h,w=self.frame.shape[:2];p=self.profiles.get(self.key(self.scene.currentText(),w,h),{})
        self.canvas.regions=copy.deepcopy(p.get('regions',[]));self.canvas.anchors=copy.deepcopy(p.get('anchors',{}));self.canvas.update()

    def save(self):
        h,w=self.frame.shape[:2]
        self.result_profile=(self.key(self.scene.currentText(),w,h),{'regions':self.canvas.regions,'anchors':self.canvas.anchors})
        self.accept()

    def key(self,scene,w,h):
        return profile_key(scene,w,h)+(':'+self.layout_name if self.layout_name!='default' and scene=='selection' else '')


class ReviewDialog(QDialog):
    def __init__(self,draft,names,parent=None):
        super().__init__(parent);self.setWindowTitle('官方榜单复核 — 有疑点的数据不会自动启用');self.resize(1250,850)
        self.draft=copy.deepcopy(draft);self.names=names;self.result_board=None
        layout=QVBoxLayout(self);meta=QHBoxLayout()
        self.board_mode=QComboBox()
        self.board_mode.addItem('请选择并核对榜单模式',None)
        for key,title in MODES.items():self.board_mode.addItem(title,key)
        self.board_mode.setCurrentIndex(max(0,self.board_mode.findData(draft.get('mode_id',MINGDAO if draft.get('mode')==MODE else None))))
        meta.addWidget(self.board_mode)
        self.start=QLineEdit(draft.get('period_start',''));self.end=QLineEdit(draft.get('period_end',''));self.source=QLineEdit(draft.get('source_url',''))
        for label,field in [('开始',self.start),('结束',self.end),('来源',self.source)]:meta.addWidget(QLabel(label));meta.addWidget(field)
        layout.addLayout(meta)
        self.issue=QLabel('；'.join(validate_board(draft)[:8]) or '结构校验通过，请对照原图核对模式、周期、姓名和两份排名。');self.issue.setWordWrap(True);layout.addWidget(self.issue)
        splitter=QSplitter()
        # Editable independent tables prevent an OCR name mismatch from losing pick ranks.
        self.wins=QTableWidget(0,3);self.wins.setHorizontalHeaderLabels(['胜率排名','武将','胜率 %'])
        self.picks=QTableWidget(0,2);self.picks.setHorizontalHeaderLabels(['出场排名','武将'])
        left=QWidget();lv=QVBoxLayout(left);lv.addWidget(self.wins);lv.addWidget(self.picks);splitter.addWidget(left)
        wr=draft.get('raw_win_rows') or draft.get('heroes',[])
        pr=draft.get('raw_pick_rows') or sorted(draft.get('heroes',[]),key=lambda x:x.get('pick_rank') or 999)
        for table,rows,fields in [(self.wins,wr,('win_rank','name','win_rate')),(self.picks,pr,('pick_rank','name'))]:
            table.setRowCount(len(rows));table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for i,row in enumerate(rows):
                for j,k in enumerate(fields):table.setItem(i,j,QTableWidgetItem(str(row.get(k,''))))
        from pathlib import Path
        from .storage import ROOT
        source_path=Path(draft.get('image_path',''))
        if not source_path.is_absolute():source_path=ROOT/source_path
        img=QLabel();pm=QPixmap(str(source_path));img.setPixmap(pm);img.resize(pm.size())
        scroll=QScrollArea();scroll.setWidget(img);splitter.addWidget(scroll);splitter.setSizes([470,700]);layout.addWidget(splitter,1)
        controls=QHBoxLayout()
        for title,table in [('胜率表',self.wins),('出场表',self.picks)]:
            add=QPushButton(title+'加行');delete=QPushButton(title+'删选中行')
            add.clicked.connect(lambda checked=False,t=table:t.insertRow(t.rowCount()))
            delete.clicked.connect(lambda checked=False,t=table:t.removeRow(t.currentRow()) if t.currentRow()>=0 else None)
            controls.addWidget(add);controls.addWidget(delete)
        layout.addLayout(controls)
        self.confirm=QCheckBox('已对照原图确认所选模式、统计周期及全部数据行；巅峰身份与双龙争鼎的对应仅对此周期有效');layout.addWidget(self.confirm)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def save(self):
        if not self.confirm.isChecked():QMessageBox.warning(self,'需要复核','请先对照原图完成复核并勾选确认。');return
        try:
            def text(t,r,c):return t.item(r,c).text().strip() if t.item(r,c) else ''
            wins=[{'win_rank':int(text(self.wins,r,0)),'name':text(self.wins,r,1),'win_rate':float(text(self.wins,r,2))} for r in range(self.wins.rowCount())]
            picks=[{'pick_rank':int(text(self.picks,r,0)),'name':text(self.picks,r,1)} for r in range(self.picks.rowCount())]
            if len(picks)!=len(wins) or len({p['name'] for p in picks})!=len(picks):raise ValueError('出场表条数或武将唯一性不正确')
            mapping={p['name']:p['pick_rank'] for p in picks}
            if set(mapping)!={p['name'] for p in wins}:raise ValueError('两表的武将名单不同，请逐一修正')
            board=copy.deepcopy(self.draft)
            mode=self.board_mode.currentData()
            if not mode:raise ValueError('必须确认榜单模式')
            board.update(schema_version=2,mode_id=mode,mode=MODES[mode],period_start=self.start.text(),period_end=self.end.text(),source_url=self.source.text(),heroes=[r|{'pick_rank':mapping.get(r['name'])} for r in wins],expected_count=max((x['win_rank'] for x in wins),default=0),issues=[],review_status='user-reviewed',raw_win_rows=wins,raw_pick_rows=picks)
            if mode==PEAK_SHUANGLONG:board['mode_evidence']={'status':'user-reviewed','period_start':board['period_start'],'period_end':board['period_end'],'source_url':board['source_url']}
            problems=validate_board(board)
            if problems:raise ValueError('；'.join(problems))
            self.result_board=board;self.accept()
        except Exception as e:QMessageBox.warning(self,'未启用榜单',str(e))
