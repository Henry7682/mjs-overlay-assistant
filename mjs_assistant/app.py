from __future__ import annotations

import copy
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path

import cv2
from PySide6.QtCore import Qt,QThread,Signal,QTimer,Slot
from PySide6.QtGui import QAction,QIcon,QColor,QPixmap,QPainter,QFont
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
                              QTableWidget,QTableWidgetItem,QHeaderView,QSystemTrayIcon,QMenu,QFileDialog,QMessageBox,QInputDialog,QDialog,QCheckBox)

from .storage import BoardStore,user_dir,read_json,write_json,ASSETS,migrate_settings
from .modes import MODES,MINGDAO,board_mode
from .stats_source import statistics_mode,source_label
from .guide_controller import GuideController
from .ocr import Names,Ocr
from .capture import Capture,windows,client_rect,foreground
from .recognition import Recognizer,Stabilizer,profile_key
from .widgets import Overlay,CalibrationDialog,ReviewDialog
from .boards import import_image,validate_board
from .updater import Updater
from .recommendations import ModeContext,SelectionSnapshot,RECOMMENDATION_MODES,RANKED_SHARED_POOL_ASSUMPTION,refresh_image_result,retain_previous_selection
from .selection_state import SelectionGuard
from .provider import WeChatMiniProgramProvider,input_idle_seconds
from .hotkeys import Hotkeys
from .frame_timing import frame_fresh,query_state_alive
from .recommendation_ui import RecommendationSettings,CandidateDialog
from . import diagnostics
from .version import APP_NAME,VERSION


def save_selection_diagnostic(data,event,reason=''):
    # Explicit local test opt-in only; normal distributions never persist frames.
    destination=os.environ.get('MJS_SELECTION_DIAGNOSTIC_DIR')
    if not destination or not data or data.get('frame') is None:return
    try:
        if time.time()>float(os.environ.get('MJS_SELECTION_DIAGNOSTIC_UNTIL','0')):return
        folder=Path(destination);folder.mkdir(parents=True,exist_ok=True)
        if len(list(folder.glob('*.png')))>=2:return
        label=time.strftime('%Y%m%d-%H%M%S')+'-'+event+'-'+uuid.uuid4().hex[:6]
        cv2.imencode('.png',data['frame'])[1].tofile(str(folder/(label+'.png')))
        write_json(folder/(label+'.json'),dict(event=event,reason=reason,mode=data.get('mode_id'),
            scene=data.get('scene'),phase=data.get('phase'),seats=data.get('seats'),
            self_locked=data.get('self_locked'),empty_panels=data.get('empty_panels'),
            items=[dict(name=d.name,raw=d.raw,slot=d.slot,box=d.box,confirmed=d.confirmed) for d in data.get('items',[])]))
    except Exception:logging.exception('explicit selection diagnostic failed')


class RecognitionThread(QThread):
    result=Signal(object)
    status=Signal(str)
    def __init__(self):
        super().__init__();self.lock=threading.Lock();self.hwnd=0;self.enabled=True;self.scene='auto';self.profiles={};self.extra=[];self.generation=0
        self.stabilizer=Stabilizer();self.correction=None;self.mode_id=None;self.allow_background=False
        self.progress=None;self.models_ready=False

    def configure(self,hwnd,enabled,scene,profiles,extra,mode_id=None):
        with self.lock:
            self.hwnd=hwnd;self.enabled=enabled;self.scene=scene;self.profiles=copy.deepcopy(profiles);self.extra=list(extra);self.mode_id=mode_id;self.generation+=1

    def run(self):
        cap=None;bound=0;lastgen=-1;laststatus=''
        def status(s):
            nonlocal laststatus
            if s!=laststatus:
                if s.split(' · ')[0]!=laststatus.split(' · ')[0]:logging.info('recognition: %s',s)
                self.status.emit(s);laststatus=s
        try:
            status('正在加载本地 OCR 模型…');ocr=Ocr();recognizer=Recognizer(ocr,Names())
            self.models_ready=True
            while not self.isInterruptionRequested():
                began=time.monotonic()
                with self.lock:
                    hwnd,enabled,scene,profiles,extra,gen=self.hwnd,self.enabled,self.scene,self.profiles,self.extra,self.generation
                    correction=self.correction;self.correction=None
                    mode=self.mode_id;allow_background=self.allow_background
                if gen!=lastgen:
                    self.stabilizer.clear();recognizer.names=Names(extra);lastgen=gen
                if correction:self.stabilizer.overrides[(correction[0],correction[1])]=correction[2]
                if not enabled or not hwnd:
                    if cap:cap.stop();cap=None;bound=0
                    status('已暂停' if not enabled else '等待名将杀窗口…');self.msleep(400);continue
                try:
                    if bound!=hwnd:
                        if cap:cap.stop()
                        cap=Capture(hwnd);bound=hwnd;self.msleep(400)
                    frame,rect,stamp=cap.read()
                    if not foreground(hwnd) and not allow_background:
                        self.stabilizer.previous.clear();self.stabilizer.last_time=time.monotonic()
                        status('游戏不在前台，悬浮已隐藏')
                        self.result.emit({'frame':frame,'rect':rect,'scene':'unknown','items':[],'generation':gen,'stamp':time.monotonic(),'seconds':0,'background':True})
                        self.msleep(600);continue
                    self.progress=dict(active=True,generation=gen,stamp=stamp,began=time.monotonic())
                    found,items,words=recognizer.analyze(frame,scene,profiles,mode)
                    items=self.stabilizer.update(found,items,max_gap=4.5 if mode=='peak_chuhan_2v2' and found=='selection' else 3)
                    # Fourteen-card cold/repair passes measured up to 3.5s in
                    # the authorized sequence; do not discard every slow ban frame.
                    freshness=4 if mode=='peak_chuhan_2v2' and found=='selection' else 2
                    if time.monotonic()-stamp>freshness:
                        items=[];self.stabilizer.clear()
                    elapsed=time.monotonic()-began
                    self.progress=dict(self.progress,active=False,finished_at=time.monotonic())
                    self.result.emit({'frame':frame,'rect':rect,'scene':found,'items':items,'generation':gen,'stamp':stamp,'seconds':elapsed,'processed_at':time.monotonic(),
                                      'mode_id':mode,'layout':recognizer.layout,'phase':recognizer.phase,
                                      'seats':recognizer.seats,'self_locked':recognizer.self_locked,'remaining':recognizer.remaining,
                                      'empty_panels':recognizer.empty_panels,'battle_badges':recognizer.battle_badges,'locked_names':recognizer.locked_names,
                                      'entry_mode':recognizer.entry_mode,'in_entry':recognizer.in_entry,'round_end':recognizer.round_end})
                    label=('模式入口识别' if found=='entry' else '傀儡三选一识别' if recognizer.phase=='puppet' else
                           '等待选将／战斗界面' if found=='unknown' else ('选将识别' if found=='selection' else '战场识别'))
                    if found=='selection' and not any(item.name for item in items):
                        label='选将未识别到姓名，请核对排位／巅峰模式或校准区域'
                    status(label+f' · {elapsed:.2f}s')
                except Exception as e:
                    self.stabilizer.clear();status(str(e));self.result.emit({'error':str(e),'generation':gen})
                    if cap and '关闭' in str(e):cap.stop();cap=None;bound=0
                finally:
                    if self.progress and self.progress.get('active'):self.progress=None
                self.msleep(max(10,int((.5-(time.monotonic()-began))*1000)))
        except Exception as e:
            logging.exception('recognition startup');self.status.emit(f'OCR 启动失败：{e}')
        finally:
            self.models_ready=False
            if cap:cap.stop()


class DataThread(QThread):
    done=Signal(object,str)
    progress=Signal(str)
    def __init__(self,folder,board,path=None,force=False,busy=None):
        super().__init__();self.folder=folder;self.board=copy.deepcopy(board);self.path=path;self.force=force
        self.busy=busy or threading.Event()

    def run(self):
        try:
            values=self.board.values() if 'heroes' not in self.board else [self.board]
            names=Names(x['name'] for b in values for x in b.get('heroes',[]))
            # Construct OCR lazily: a check finding the same post needs no model load.
            class LazyOcr:
                obj=None
                def __getattr__(self,key):
                    def idle():
                        while owner.busy.is_set():
                            if owner.isInterruptionRequested():raise RuntimeError('已取消榜单OCR')
                            owner.msleep(250)
                        if owner.isInterruptionRequested():raise RuntimeError('已取消榜单OCR')
                    def call(*args,**kwargs):
                        idle()
                        if self.obj is None:self.obj=Ocr()
                        if key=='document':kwargs['before_read']=idle
                        return getattr(self.obj,key)(*args,**kwargs)
                    return call
            owner=self
            engine=LazyOcr()
            if self.path:
                self.progress.emit('正在识别导入的官方图片…')
                board=import_image(self.path,engine,names);message='导入完成，请复核'
            else:
                board,message=Updater(self.folder,engine,names,self.isInterruptionRequested,self.busy.is_set).check(self.board,self.force,self.progress.emit)
            self.done.emit(board,message)
        except Exception as e:
            logging.exception('data update');self.done.emit(None,'更新失败，保留原榜单：'+str(e))


def app_icon():
    pm=QPixmap(64,64);pm.fill(QColor('#172a36'));p=QPainter(pm);p.setPen(QColor('#edcc83'));p.setFont(QFont('Microsoft YaHei UI',29,QFont.Weight.Bold));p.drawText(pm.rect(),Qt.AlignmentFlag.AlignCenter,'将');p.end();return QIcon(pm)


class MainWindow(GuideController,QMainWindow):
    def __init__(self):
        super().__init__();self.folder=user_dir();self.config=migrate_settings(self.folder)
        self.store=BoardStore(self.folder);self.overlay=Overlay(self.store);self.worker=RecognitionThread();self.data_worker=None
        self.enabled=True;self.visible_overlay=True;self.latest=None;self.pending=read_json(self.folder/'boards/pending.json');self.quitting=False
        self.provider=WeChatMiniProgramProvider(self.folder,self);self.selection_guard=SelectionGuard()
        self.snapshot=None;self.confirmed_snapshot=None;self.request_id=None;self.game_id=uuid.uuid4().hex
        self.auto_attempted=False;self.stable_since=0;self.hotkeys=None;self.previous_scene='unknown'
        self.mode_evidence='unknown';self.auto_mode=None;self.entry_candidate=None;self.entry_hits=0
        self.observed_seats=(None,None)
        self.init_guides()
        self.setWindowTitle(APP_NAME+' '+VERSION+' · 公开测试版');self.setWindowIcon(app_icon());self.resize(920,660)
        widget=QWidget();self.setCentralWidget(widget);layout=QVBoxLayout(widget);layout.setSpacing(12);layout.setContentsMargins(24,20,24,20)
        title=QLabel('名将浮窗助手');title.setObjectName('title');layout.addWidget(title)
        layout.addWidget(QLabel('多模式本地识别 · 官方榜单；模式未确认时不显示统计'))
        self.mode_box=QComboBox();self.mode_box.addItem('自动识别模式（持续跟随入口）',None)
        for key,label in MODES.items():self.mode_box.addItem(label,key)
        layout.addWidget(self.mode_box)
        self.mode_status=QLabel();self.mode_status.setWordWrap(True);layout.addWidget(self.mode_status)
        self.board_label=QLabel();self.board_label.setObjectName('board');layout.addWidget(self.board_label)
        row=QHBoxLayout();self.window_box=QComboBox();self.window_box.setMinimumWidth(300);row.addWidget(self.window_box,1)
        refresh=QPushButton('刷新窗口');refresh.clicked.connect(self.refresh_windows);row.addWidget(refresh)
        self.scene_box=QComboBox()
        for title,code in [('自动判断场景','auto'),('手动：选将','selection'),('手动：战斗','battle')]:self.scene_box.addItem(title,code)
        row.addWidget(self.scene_box);layout.addLayout(row)
        row=QHBoxLayout();self.pause_btn=QPushButton('暂停识别');self.pause_btn.clicked.connect(self.toggle_pause);row.addWidget(self.pause_btn)
        self.show_btn=QPushButton('隐藏悬浮');self.show_btn.clicked.connect(self.toggle_overlay);row.addWidget(self.show_btn)
        for label,callback in [('校准区域／位置',self.calibrate),('纠正选中姓名',self.correct),('保存诊断样本',self.save_sample)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        layout.addLayout(row)
        self.guide_check=QCheckBox('开启攻略浮窗（需配合名将小助手；关闭不影响本地武将统计）')
        self.guide_check.setChecked(self.guides_enabled());self.guide_check.toggled.connect(self.set_guides_enabled)
        layout.addWidget(self.guide_check)
        rec_row=QHBoxLayout()
        for label,callback in [('小程序配阵设置',self.recommendation_settings),('确认禁将后名单',self.confirm_peak_roster),('重新配阵',self.request_recommendation),('取消配阵',self.cancel_recommendation)]:
            button=QPushButton(label);button.clicked.connect(callback);rec_row.addWidget(button)
        layout.addLayout(rec_row)
        self.rec_status=QLabel('小程序配阵未启用');self.rec_status.setWordWrap(True);layout.addWidget(self.rec_status)
        self.provider.status.connect(lambda text:self.safe_guide_call(self.recommendation_status,text))
        self.provider.finished.connect(lambda result:self.safe_guide_call(self.recommendation_finished,result))
        self.status=QLabel('准备连接…');self.status.setObjectName('status');layout.addWidget(self.status)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['识别武将','胜率','胜率排名','出场排名','状态','OCR 原文'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        row=QHBoxLayout()
        self.check_btn=QPushButton('检查新榜单');self.check_btn.clicked.connect(lambda:self.start_data(force=True));row.addWidget(self.check_btn)
        self.import_btn=QPushButton('导入官方图片');self.import_btn.clicked.connect(self.import_board);row.addWidget(self.import_btn)
        self.review_btn=QPushButton('复核待确认榜单');self.review_btn.clicked.connect(self.review);row.addWidget(self.review_btn)
        self.rollback_btn=QPushButton('回退上一期');self.rollback_btn.clicked.connect(self.rollback);row.addWidget(self.rollback_btn);layout.addLayout(row)
        self.data_status=QLabel('官方统计在本地查询；小程序配阵的数据传递方式请见配阵设置。');self.data_status.setWordWrap(True);layout.addWidget(self.data_status)
        footer=QLabel('关闭窗口后留在托盘。使用窗口化／无边框模式；切出游戏时自动隐藏标注。');footer.setObjectName('muted');layout.addWidget(footer)
        self.tray=QSystemTrayIcon(app_icon(),self);self.tray_menu=QMenu(self);menu=self.tray_menu
        for label,callback in [('打开设置',self.open_settings),('检查榜单',lambda:self.start_data(force=True)),('退出',self.quit)]:
            a=menu.addAction(label);a.triggered.connect(callback)
        self.pause_action=menu.addAction('');self.pause_action.triggered.connect(self.toggle_pause)
        self.overlay_action=menu.addAction('');self.overlay_action.triggered.connect(self.toggle_overlay)
        self.guides_action=menu.addAction('攻略浮窗已开启');self.guides_action.setCheckable(True)
        self.guides_action.toggled.connect(self.set_guides_enabled)
        self.tray.setContextMenu(menu);self.tray.setToolTip('名将浮窗助手');self.tray.activated.connect(self.tray_activated);self.tray.show()
        self.sync_controls()
        self.window_box.currentIndexChanged.connect(self.configure);self.scene_box.currentIndexChanged.connect(self.configure)
        self.mode_box.currentIndexChanged.connect(self.change_mode)
        self.worker.result.connect(self.receive);self.worker.status.connect(self.status.setText)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(120)
        self.scan_timer=QTimer(self);self.scan_timer.timeout.connect(self.refresh_windows);self.scan_timer.start(3000)
        self.update_timer=QTimer(self);self.update_timer.timeout.connect(lambda:self.start_data());self.update_timer.start(86400000)
        self.install_hotkeys();self.update_board_label();self.refresh_windows();self.worker.start();QTimer.singleShot(1500,lambda:self.start_data(force=True))
        feedback=QPushButton('反馈问题／本地诊断');feedback.clicked.connect(self.open_feedback);layout.addWidget(feedback)
        migrate=QPushButton('导入旧版 data 配置');migrate.clicked.connect(self.import_previous);layout.addWidget(migrate)
        if not self.config.get('diagnostic_notice_v1'):
            QTimer.singleShot(700,self.diagnostic_notice)
        if '--mode' in sys.argv:
            index=sys.argv.index('--mode')
            if index+1<len(sys.argv) and sys.argv[index+1] in MODES:
                self.mode_box.setCurrentIndex(self.mode_box.findData(sys.argv[index+1]))

    def update_board_label(self):
        b=self.store.board
        self.mode_status.setText('手动固定模式；入口不一致时仅提醒，不自动改选。'
            if self.mode_box.currentData() else
            '自动识别持续开启；当前：'+MODES.get(self.current_mode(),'等待明确入口')+'。进入对局后沿用本局模式。')
        self.board_label.setText('模式待确认' if not self.current_mode() else
            (f'{source_label(self.current_mode())}  ·  {b["period_start"]} — {b["period_end"]}  ·  {len(b["heroes"])} 名武将' if b.get('heroes') else f'{source_label(self.current_mode())}：暂无已复核榜单'))
        self.review_btn.setEnabled(bool(self.pending) or any(read_json(self.folder/'boards'/mode/'pending.json') for mode in [*MODES,'unassigned']))
        self.review_btn.setText('复核榜单（楚汉共用巅峰）' if self.current_mode()=='ranked_chuhan_2v2' else '复核待确认榜单')
        self.rollback_btn.setText('回退巅峰来源（两楚汉共用）' if self.current_mode()=='ranked_chuhan_2v2' else '回退上一期')

    def profiles(self):
        return self.config.get('mode_profiles',{}).get(self.current_mode(),{})

    def change_mode(self):
        mode=self.mode_box.currentData()
        if mode is None:self.auto_mode=None
        self.mode_evidence='manual' if mode else 'unknown'
        self.entry_hits=0;self.entry_candidate=None
        if mode:
            self.store.select(statistics_mode(mode));self.overlay.game_mode=mode;self.pending=read_json(self.store.pending_path)
        self.update_board_label();self.configure()

    def configure(self,*args):
        hwnd=self.window_box.currentData() or 0
        self.reset_round('游戏窗口／模式／识别设置变化')
        self.observed_seats=(None,None)
        self.latest=None;self.overlay.hide();self.table.setRowCount(0)
        self.configure_worker()

    def configure_worker(self):
        self.worker.configure(self.window_box.currentData() or 0,self.enabled,self.scene_box.currentData(),self.profiles(),
            [x['name'] for x in self.store.board['heroes']],self.current_mode())

    def refresh_windows(self):
        old=self.window_box.currentData();wins=windows()
        current=[self.window_box.itemData(i) for i in range(self.window_box.count())]
        target=([0] if len(wins)>1 else [])+[w.hwnd for w in wins] if wins else [0]
        if current==target:return
        self.window_box.blockSignals(True);self.window_box.clear()
        if not wins:self.window_box.addItem('未检测到名将杀，请启动 Steam 游戏',0)
        else:
            if len(wins)>1:self.window_box.addItem('请选择游戏窗口',0)
            for w in wins:self.window_box.addItem(f'{w.title} · HWND {w.hwnd}',w.hwnd)
            index=self.window_box.findData(old)
            if index>=0:self.window_box.setCurrentIndex(index)
        self.window_box.blockSignals(False)
        if old and old!=self.window_box.currentData():
            self.auto_mode=None;self.entry_hits=0;self.entry_candidate=None
            self.mode_evidence='unknown'
            self.mode_box.setCurrentIndex(0)
            self.update_board_label()
        self.configure()

    def receive(self,data):
        if hasattr(self,'data_busy'):
            if data.get('scene')=='selection' or self.provider.busy:self.data_busy.set()
            else:self.data_busy.clear()
        metadata={k:data.get(k) for k in ('scene','phase','layout','seconds','rect')}
        metadata['mode']=data.get('mode_id')
        metadata['round_id']=self.game_id
        metadata['items']=[{k:getattr(x,k,None) for k in ('name','raw','box','confidence','confirmed','slot','method')} for x in data.get('items',[])]
        diagnostics.event('recognition',**metadata)
        if data.get('scene') in ('selection','battle'):diagnostics.frame('game',data.get('frame'),**metadata)
        if data.get('error'):diagnostics.fault('识别异常：'+str(data['error']))
        if data.get('scene')=='selection' and not any(x.name for x in data.get('items',[])):
            self._empty_since=getattr(self,'_empty_since',time.monotonic())
            if time.monotonic()-self._empty_since>4:diagnostics.fault('选将持续没有姓名')
        else:self._empty_since=time.monotonic()
        if data.get('generation')!=self.worker.generation:return
        if 'error' in data:
            self.safe_guide_call(self.invalidate_recommendation,'游戏截图不可用')
            self.latest=None;self.overlay.hide();self.guide_panel.hide();self.table.setRowCount(0);return
        if data.get('background') and self.latest:
            self.overlay.hide();self.guide_panel.hide();return
        if data.get('round_end'):
            self.end_hits=getattr(self,'end_hits',0)+1
            if self.end_hits>=2 and self.previous_scene in ('selection','battle'):self.reset_round('已确认结算／返回大厅')
        else:self.end_hits=0
        if data.get('in_entry'):
            hint=data.get('entry_mode')
            self.entry_hits=self.entry_hits+1 if self.entry_candidate==hint else 1;self.entry_candidate=hint
            if self.entry_hits>=2 and hint and self.mode_box.currentData() and hint!=self.current_mode():
                diagnostics.fault('入口与手动模式不一致')
            if self.entry_hits>=2:
                if self.previous_scene in ('selection','battle'):self.reset_round('已确认返回模式入口')
                self.previous_scene='entry'
                if self.mode_box.currentData() is None and self.auto_mode!=hint:
                    self.auto_mode=hint;self.mode_evidence='visible_entry' if hint else 'unknown'
                    if hint:
                        self.store.select(statistics_mode(hint));self.overlay.game_mode=hint
                        self.pending=read_json(self.store.pending_path)
                    self.update_board_label();self.configure();return
        else:self.entry_hits=0;self.entry_candidate=None
        self.latest=data;items=data['items'];self.table.setRowCount(len(items))
        for i,d in enumerate(items):
            record=self.store.lookup(d.name) if d.name else None
            values=[d.name or '待确认',f'{record["win_rate"]:.2f}%' if record else '—',str(record['win_rank']) if record else '—',str(record['pick_rank']) if record else '—',('已确认' if record else '本期未收录') if d.confirmed else '等待确认',d.raw]
            for j,v in enumerate(values):self.table.setItem(i,j,QTableWidgetItem(v))
        if not data.get('in_entry'):self.safe_guide_call(self.update_selection,data)
        self.tick()

    def status_lines(self,data):
        mode=self.current_mode();b=self.store.board
        choice='自动识别' if self.mode_box.currentData() is None else '手动模式'
        mode_text=source_label(mode) if mode else '模式待确认，请进入玩法入口或手动选择'
        period=(f'{b["period_start"]} — {b["period_end"]}' if b.get('heroes') else '暂无已复核榜单') if mode else '暂无对应统计'
        lines=[f'{choice} · {mode_text} · {period}']
        if not self.guides_enabled():guide='已关闭'
        elif not self.config.get('recommendation',{}).get('enabled',True):guide='已开启，小程序查询未启用'
        elif self.provider.busy:guide='正在查询'
        elif mode not in RECOMMENDATION_MODES:guide='当前模式不支持配阵'
        else:guide='已开启，需名将小助手'
        lines.append(('运行中' if self.enabled else '已暂停识别')+f' · 数据：本地官方榜单 · 攻略：{guide}')
        hint=data.get('entry_mode')
        if data.get('in_entry') and self.entry_hits>=2:
            if self.mode_box.currentData() and hint and mode!=hint:
                lines.append('⚠ 入口是'+MODES[hint]+'；当前固定'+MODES[mode]+'，请核对模式')
            elif not hint:lines.append('入口标签待确认；暂不按模糊画面切换模式')
        return lines

    def tick(self):
        d=self.latest;hwnd=self.window_box.currentData()
        fresh=frame_fresh(d,self.current_mode()=='peak_chuhan_2v2')
        if self.provider.busy:
            from .capture import user32
            if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
                self.safe_guide_call(self.invalidate_recommendation,'游戏窗口已关闭或最小化，本次配阵已取消')
            elif not query_state_alive(d,getattr(self.worker,'progress',None),self.current_mode()=='peak_chuhan_2v2'):
                self.safe_guide_call(self.invalidate_recommendation,'游戏状态未及时确认，本次配阵已取消')
        entry=bool(d and d.get('in_entry'))
        if ((not self.enabled and not entry) or not self.visible_overlay or not d or d['scene']=='unknown'
            or not hwnd or not foreground(hwnd) or (self.enabled and not fresh)):
            self.overlay.hide();self.guide_panel.hide();return
        try:
            rect=client_rect(hwnd);frame=d['frame'];h,w=frame.shape[:2]
            if abs(rect[2]-w)>2 or abs(rect[3]-h)>2:self.overlay.hide();self.guide_panel.hide();return
            key=profile_key(d['scene'],w,h);layout=d.get('layout','default')
            profile=self.profiles().get(key+':'+layout,{} if layout=='puppet3' else self.profiles().get(key,{}))
            self.overlay.status_lines=self.status_lines(d)
            self.overlay.present(rect,(w,h),d['items'],profile)
        except Exception:
            logging.exception('statistics overlay presentation');self.overlay.hide();self.guide_panel.hide();return
        if not self.safe_guide_call(self.present_guides,rect,d):self.guide_panel.hide()

    def present_guides(self,rect,data):
        if self.guides_enabled() and self.current_mode() in RECOMMENDATION_MODES and data['scene'] in ('selection','battle'):
            self.guide_panel.set_content(data['scene'],self.guide_html(data['scene']),data['scene']=='battle' and self.current_mode()=='ranked_chuhan_2v2')
            self.guide_panel.present(rect)
        else:self.guide_panel.hide()
        return True

    def toggle_pause(self):
        self.enabled=not self.enabled
        if not self.enabled:self.safe_guide_call(self.invalidate_recommendation,'识别已暂停，保留已读攻略')
        self.configure_worker();self.sync_controls();self.tick()

    def toggle_overlay(self):
        self.visible_overlay=not self.visible_overlay;self.sync_controls();self.tick()

    def set_guides_enabled(self,enabled):
        self.config.setdefault('recommendation',{})['guides_enabled']=bool(enabled)
        write_json(self.folder/'settings.json',self.config)
        if not enabled:
            self.safe_guide_call(self.invalidate_recommendation,'攻略浮窗已关闭；本地统计继续，已读攻略保留')
            self.guide_panel.hide()
            with self.worker.lock:self.worker.allow_background=False
        self.sync_controls();self.tick()

    def sync_controls(self):
        self.pause_btn.setText('暂停识别' if self.enabled else '开始识别')
        self.show_btn.setText('隐藏悬浮' if self.visible_overlay else '显示悬浮')
        self.pause_action.setText('识别：运行中 — 点击暂停' if self.enabled else '识别：已暂停 — 点击开始')
        self.overlay_action.setText('悬浮显示：已开启 — 点击隐藏' if self.visible_overlay else '悬浮显示：已关闭 — 点击显示')
        for control in (self.guide_check,self.guides_action):
            control.blockSignals(True);control.setChecked(self.guides_enabled());control.blockSignals(False)
        self.guides_action.setText('攻略浮窗：已开启' if self.guides_enabled() else '攻略浮窗：已关闭')
        self.tray.setToolTip('名将浮窗助手 · '+('运行中' if self.enabled else '已暂停')+' · '+('悬浮显示开启' if self.visible_overlay else '悬浮显示关闭'))

    def tray_activated(self,reason):
        logging.info('tray activated: %s',reason)
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_settings()

    @Slot()
    def open_settings(self):
        logging.info('settings requested')
        # Let the native tray popup finish closing before restoring the window.
        if getattr(self,'_settings_pending',False):return
        self._settings_pending=True;QTimer.singleShot(0,self._show_settings)

    @Slot()
    def _show_settings(self):
        self._settings_pending=False
        from .settings_window import show_settings_window
        try:show_settings_window(self)
        except Exception:logging.exception('settings restore failed')

    def calibrate(self):
        if not self.latest:QMessageBox.information(self,'等待画面','请先启动游戏并等待收到截图。');return
        d=self.latest;scene=self.scene_box.currentData()
        if d.get('in_entry'):QMessageBox.information(self,'等待选将／战斗','入口无需校准武将区域，请进入选将或战斗后再校准。');return
        if not self.current_mode():QMessageBox.information(self,'模式待确认','请先选择本局模式。');return
        dialog=CalibrationDialog(d['frame'],scene if scene!='auto' else d['scene'],self.profiles(),d['items'],self,layout_name=d.get('layout','default'))
        if dialog.exec()==QDialog.DialogCode.Accepted:
            key,profile=dialog.result_profile;self.config.setdefault('mode_profiles',{}).setdefault(self.current_mode(),{})[key]=profile;write_json(self.folder/'settings.json',self.config);self.configure()

    def correct(self):
        row=self.table.currentRow()
        if not self.latest or row<0 or row>=len(self.latest['items']):return
        d=self.latest['items'][row]
        names=Names(x['name'] for x in self.store.board['heroes']);options=names.candidates(d.raw)+sorted(names.names)
        chosen,ok=QInputDialog.getItem(self,'纠正姓名','只对当前槽位的当前识别文本有效：',list(dict.fromkeys(options)),0,False)
        if ok:
            if self.current_mode()=='ranked_chuhan_2v2' and self.latest['scene']=='selection':
                self.retain_ranked_recommendation()
            else:self.invalidate_recommendation('姓名已纠正，请重新配阵')
            with self.worker.lock:self.worker.correction=(d.slot,d.raw,chosen)






    def recommendation_settings(self):
        dialog=RecommendationSettings(self.config.get('recommendation',{}),self,bound_hwnd=self.provider.bound_hwnd)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.config['recommendation']=dialog.result_settings;write_json(self.folder/'settings.json',self.config)
            self.provider.bound_hwnd=dialog.selected_hwnd
            self.safe_guide_call(self.invalidate_recommendation,'配阵设置已更新');self.install_hotkeys();self.sync_controls();self.tick()

    def install_hotkeys(self):
        if self.hotkeys:self.hotkeys.close()
        settings=self.config.get('recommendation',{});keys=settings.get('hotkeys',{})
        self.overlay.rec_anchor=tuple(settings.get('anchor',[.015,.4]))
        self.guide_panel.anchor=tuple(settings.get('panel_anchor',settings.get('anchor',[.015,.4])))
        self.hotkeys=Hotkeys(QApplication.instance(),[(keys.get('request','Ctrl+Alt+P'),self.request_recommendation),
            (keys.get('details','Ctrl+Alt+D'),self.toggle_details),(keys.get('cancel','Ctrl+Alt+X'),self.cancel_recommendation)])
        self.rec_status.setText('攻略浮窗已关闭；本地统计继续' if not self.guides_enabled() else '；'.join(self.hotkeys.errors) if self.hotkeys.errors else
            (('配阵已启用；排位确认选将即传图，巅峰确认姓名后查询' if settings.get('automatic',True) else
              '配阵已启用；按 '+keys.get('request','Ctrl+Alt+P')+' 查询') if settings.get('enabled',True) else '小程序配阵未启用'))

    def confirm_candidates(self):
        if not self.snapshot or self.snapshot.phase!='selection':
            QMessageBox.information(self,'等待选将','请先进入楚汉选将并确认本局模式。');return
        if not self.snapshot.own_pool:
            QMessageBox.information(self,'等待姓名','请先纠正待确认的姓名。');return
        initial=self.snapshot
        with self.worker.lock:self.worker.allow_background=True
        dialog=CandidateDialog(initial,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            if self.snapshot and initial.visual_revision==self.snapshot.visual_revision:
                self.confirmed_snapshot=dialog.result_snapshot;self.snapshot=dialog.result_snapshot
                self.rec_status.setText('候选已确认；返回游戏按配阵热键')
            else:self.rec_status.setText('确认期间画面已变化，请重新核对')
        with self.worker.lock:self.worker.allow_background=False





    def save_sample(self):
        if not self.latest:return
        path,_=QFileDialog.getSaveFileName(self,'保存本地诊断画面',str(self.folder/'sample.png'),'PNG (*.png)')
        if path:cv2.imencode('.png',self.latest['frame'])[1].tofile(path)

    def open_feedback(self):
        from .feedback_ui import FeedbackDialog
        if diagnostics._recorder:FeedbackDialog(diagnostics._recorder,self).exec()
        else:QMessageBox.information(self,'诊断不可用','诊断文件暂时无法写入，本地统计继续运行。请检查数据目录权限或剩余空间。')

    def diagnostic_notice(self):
        QMessageBox.information(self,'公开测试版与本地诊断',
            '本版用于招募测试，部分配阵可能超时。默认开启本地故障画面：仅游戏及配阵时的小程序窗口，最多500MB、保留7天，不自动上传。\n'
            '可在“反馈问题／本地诊断”关闭、预览及删除图片。普通配阵会把完整游戏PNG交给小程序，可能含昵称；可在配阵设置关闭。')
        self.config['diagnostic_notice_v1']=True;write_json(self.folder/'settings.json',self.config)

    def import_previous(self):
        from .migration import import_data
        folder=QFileDialog.getExistingDirectory(self,'选择旧版 data 文件夹')
        if not folder:return
        try:
            backup=import_data(Path(folder),self.folder)
            QMessageBox.information(self,'配置已导入','原配置备份已保存。退出后重新启动生效。\n'+str(backup))
        except Exception as error:QMessageBox.warning(self,'导入失败',str(error))

    def start_data(self,force=False,path=None):
        if self.data_worker and self.data_worker.isRunning():return
        self.check_btn.setEnabled(False);self.import_btn.setEnabled(False)
        if not hasattr(self,'data_busy'):self.data_busy=threading.Event()
        if self.provider.busy or (self.latest and self.latest.get('scene')=='selection'):self.data_busy.set()
        self.data_worker=DataThread(self.folder,self.store.all_current(),path,force,self.data_busy);self.data_worker.progress.connect(self.data_status.setText);self.data_worker.done.connect(self.data_done);self.data_worker.start()

    def data_done(self,board,message):
        self.check_btn.setEnabled(True);self.import_btn.setEnabled(True);self.data_status.setText(message)
        if board:
            for draft in (board if isinstance(board,list) else [board]):
                if not validate_board(draft) and self.data_worker.path is None:
                    self.store.install(draft)
                else:
                    mode=board_mode(draft)
                    path=BoardStore(self.folder,mode).pending_path if mode else self.folder/'boards/unassigned/pending.json'
                    write_json(path,draft)
                    if mode==statistics_mode(self.current_mode()) or mode is None:self.pending=draft
                    self.tray.showMessage('榜单需要复核','对应模式的新榜单已暂存，当前数据继续有效。')
            self.store.select(statistics_mode(self.current_mode()) or MINGDAO)
            self.update_board_label();self.configure()

    def import_board(self):
        path,_=QFileDialog.getOpenFileName(self,'导入官方榜单','','图片 (*.png *.jpg *.jpeg *.webp)')
        if path:self.start_data(path=path)

    def review(self):
        choices={MODES.get(mode,'模式待确认'):draft for mode in [*MODES,'unassigned']
                 if (draft:=read_json(self.folder/'boards'/mode/'pending.json'))}
        if choices:
            label,ok=QInputDialog.getItem(self,'选择待复核榜单','排位楚汉显示巅峰来源；复核巅峰楚汉会影响两个楚汉模式：',list(choices),0,False)
            if not ok:return
            self.pending=choices[label]
        if not self.pending:return
        dialog=ReviewDialog(self.pending,Names(),self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            old_mode=board_mode(self.pending)
            self.store.install(dialog.result_board);self.store.select(statistics_mode(self.current_mode()) or MINGDAO);self.pending=None
            write_json(BoardStore(self.folder,board_mode(dialog.result_board)).pending_path,None)
            if old_mode is None:write_json(self.folder/'boards/unassigned/pending.json',None)
            self.update_board_label();self.configure();self.data_status.setText('已启用人工复核榜单')

    def rollback(self):
        if not self.current_mode():QMessageBox.information(self,'模式待确认','请先选择需要回退的模式。');return
        try:self.store.rollback();self.update_board_label();self.configure();self.data_status.setText('已回退至上一份有效榜单'+('；两个楚汉模式同时使用该巅峰来源' if self.store.mode_id=='peak_chuhan_2v2' else ''))
        except Exception as e:QMessageBox.information(self,'回退',str(e))

    def closeEvent(self,event):
        if self.quitting:event.accept()
        else:self.hide();event.ignore()

    def quit(self):
        self.provider.cancel('助手退出');self.hotkeys.close()
        self.quitting=True;self.timer.stop();self.scan_timer.stop();self.update_timer.stop();self.overlay.hide();self.guide_panel.hide();self.tray.hide();self.hide()
        self.worker.requestInterruption()
        if self.data_worker:self.data_worker.requestInterruption()
        self.shutdown=QTimer(self);self.shutdown.timeout.connect(self.finish_quit);self.shutdown.start(100)

    def finish_quit(self):
        if not self.worker.isRunning() and not(self.data_worker and self.data_worker.isRunning()):QApplication.quit()


STYLE='''
QWidget {background:#12202b;color:#dce6ed;font-family:"Microsoft YaHei UI";font-size:13px;}
QLabel#title {font-size:27px;font-weight:600;color:#eed29b;}
QLabel#board {background:#1b303d;border:1px solid #34505b;border-radius:8px;padding:14px;color:#a8ded4;}
QLabel#status {color:#e8c788;padding:4px;} QLabel#muted {color:#849caa;font-size:12px;}
QPushButton {background:#233e4c;border:1px solid #3b5966;border-radius:5px;padding:8px 12px;}
QPushButton:hover {background:#315567;} QPushButton:disabled {color:#657c89;}
QComboBox,QLineEdit {background:#1a303d;border:1px solid #3c5966;padding:7px;}
QTableWidget {background:#142733;alternate-background-color:#1c323f;border:1px solid #334e5c;gridline-color:#273f4c;}
QHeaderView::section {background:#203b49;padding:9px;border:none;color:#a8cbd0;}
QMenu {background:#1b303d;} QMenu::item {padding:8px 18px;} QMenu::item:selected {background:#365869;}
'''


def main():
    from .capture import enable_dpi
    enable_dpi()
    app=QApplication(sys.argv);app.setStyleSheet(STYLE);app.setQuitOnLastWindowClosed(False);app.setWindowIcon(app_icon())
    folder=user_dir()
    from PySide6.QtCore import QLockFile
    lock=QLockFile(str(folder/'assistant.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(50):
        from .instance_control import request_settings
        info=lock.getLockInfo()
        if request_settings(folder,info[1] if info[0] else None):return 0
        QMessageBox.information(None,'名将浮窗助手','助手已运行，但窗口唤出未成功；旧版本需从托盘打开。');return 0
    config=read_json(folder/'settings.json',{})
    try:
        recorder=diagnostics.setup(folder,config.get('diagnostics',{}).get('capture_enabled',True),
            {'selected_mode':config.get('selected_mode'),
             'calibration_profiles':list(config.get('mode_profiles',{})),
             'models':read_json(ASSETS/'models/manifest.json',{}),
             'dependency_manifest':read_json(ASSETS/'dependencies.json',{}),
             'boards':{k:{f:b.get(f) for f in ('period_start','period_end','image_sha256','mode_id')} for k,b in BoardStore(folder).all_current().items()}})
        app.aboutToQuit.connect(recorder.close)
    except Exception:
        logging.exception('diagnostic initialization unavailable; statistics continue')
    try:
        window=MainWindow()
        ready=os.getenv('MJS_READY_FILE')
        if ready:
            # A responsive settings window alone must not accept a broken OCR
            # update. The launcher commits only after local models initialize.
            window.ready_timer=QTimer(window)
            def signal_ready():
                if window.worker.models_ready and window.worker.isRunning():
                    try:Path(ready).write_text(VERSION,encoding='utf8')
                    except OSError:logging.exception('startup handshake unavailable')
                    window.ready_timer.stop()
            window.ready_timer.timeout.connect(signal_ready);window.ready_timer.start(200)
        from .instance_control import SettingsServer
        try:window.settings_server=SettingsServer(folder,window.open_settings,window)
        except Exception:logging.exception('settings reopen channel unavailable; tray remains usable')
        if not getattr(sys,'frozen',False):
            from .software_update import SourceUpdateCheck
            window.software_check=SourceUpdateCheck(window)
            window.software_check.message.connect(lambda text:window.tray.showMessage('助手更新',text))
            window.software_check.start()
            app.aboutToQuit.connect(lambda:window.software_check.wait(14000))
        if '--tray' not in sys.argv:window.show()
        return app.exec()
    except Exception as e:
        logging.exception('startup');QMessageBox.critical(None,'启动失败',str(e));return 1

