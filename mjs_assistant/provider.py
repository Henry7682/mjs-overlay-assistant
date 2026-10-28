"""Bounded public-UI recommendation provider; no dependency on developer tools."""
from __future__ import annotations

import ctypes
import multiprocessing as mp
import time
import uuid
import logging
from pathlib import Path
from dataclasses import replace

import cv2
from PySide6.QtCore import QObject, QTimer, Signal

from .mini_worker import worker
from .recommendations import RecommendationResult, capability_limits, filter_cards,validate_image_candidates,filter_image_cards
from .storage import read_json, write_json
from .guide_state import GuideQuery
from . import diagnostics


def input_tick():
    class LastInput(ctypes.Structure):
        _fields_=[('cbSize',ctypes.c_uint),('dwTime',ctypes.c_uint)]
    value=LastInput();value.cbSize=ctypes.sizeof(value)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(value))
    return value.dwTime


def input_idle_seconds():
    now=ctypes.windll.kernel32.GetTickCount() & 0xffffffff
    return ((now-input_tick()) & 0xffffffff)/1000


class ManagedImages:
    """Delete only individually registered PNGs directly inside our dedicated folder."""
    def __init__(self,folder):
        self.folder=Path(folder).resolve()/'recommendation-temp'
        self.folder.mkdir(parents=True,exist_ok=True)
        self.registry=self.folder/'manifest.json'
        self.cleanup()

    def cleanup(self):
        for name in read_json(self.registry,[]) or []:
            if not isinstance(name,str) or Path(name).name!=name: continue
            path=self.folder/name
            if path.suffix.lower()=='.png' and path.resolve().parent==self.folder:
                try:path.unlink(missing_ok=True)
                except OSError:continue
        # Keep entries that could not be removed for retry next launch.
        remaining=[p for p in read_json(self.registry,[]) or [] if isinstance(p,str)
                   and Path(p).name==p and (self.folder/p).is_file()]
        write_json(self.registry,remaining)

    def save(self,frame):
        name=uuid.uuid4().hex+'.png'
        write_json(self.registry,(read_json(self.registry,[]) or [])+[name])
        path=self.folder/name
        ok,data=cv2.imencode('.png',frame)
        if not ok:raise RuntimeError('无法生成游戏 PNG')
        data.tofile(path)
        return path


class WeChatMiniProgramProvider(QObject):
    status=Signal(str)
    finished=Signal(object)
    batch=Signal(object)

    def __init__(self,folder,parent=None):
        super().__init__(parent)
        self.folder=Path(folder);self.images=None;self.active=None;self.bound_hwnd=None
        try:self.images=ManagedImages(folder)
        except OSError:logging.exception('guide image directory unavailable; local statistics remain usable')
        self._connection_cache=None
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.poll)

    @property
    def busy(self):return self.active is not None

    def update_evidence(self,snapshot):
        """Reuse ongoing local OCR without making complete names a PNG gate."""
        state=self.active
        if not state or not snapshot.image_only or snapshot.fingerprint!=state['snapshot'].fingerprint:return
        old=set(state['snapshot'].own_pool+state['snapshot'].ally_pool)
        names=old|set(snapshot.own_pool+snapshot.ally_pool)
        if names==old:return
        state['snapshot']=replace(state['snapshot'],own_pool=tuple(sorted(names)),ally_pool=tuple(sorted(names)))
        if not state.get('mini'):return  # The first child message must remain 'go'.
        try:state['pipe'].send({'observed':sorted(names)})
        except (EOFError,OSError):self.cancel('小程序连接已断开')

    def connection_status(self):
        """Read-only discovery; no focus changes or worker launch while absent."""
        cached=self._connection_cache
        if cached and cached[1]==self.bound_hwnd and time.monotonic()-cached[0]<1:return cached[2]
        from .mini_windows import mini_windows,select_mini_window
        try:
            candidates=mini_windows();chosen=select_mini_window(candidates,self.bound_hwnd)
            status=(True,'小程序已连接') if chosen else (False,
                '等待打开名将小助手的一键配阵页，回到游戏后自动查询' if not candidates else '存在多个小程序窗口，请在配阵设置中选择')
        except Exception:status=(False,'暂时无法检测小程序窗口，稍后自动重试')
        self._connection_cache=(time.monotonic(),self.bound_hwnd,status)
        return status

    def start(self,snapshot,frame,game_hwnd):
        if self.busy:raise RuntimeError('已有配阵请求进行中')
        if not snapshot.can_request():raise RuntimeError('候选范围或选将状态尚未确认')
        import win32gui
        if win32gui.GetForegroundWindow()!=game_hwnd:raise RuntimeError('请返回游戏后按配阵热键')
        began=time.monotonic();request_id=uuid.uuid4().hex
        picker=snapshot.context.mode_id=='peak_chuhan_2v2' or snapshot.purpose=='enemy_battle'
        budget=40 if snapshot.context.mode_id=='peak_chuhan_2v2' else 15
        names=sorted(set(snapshot.own_pool+snapshot.ally_pool+((snapshot.ally_locked,) if snapshot.ally_locked else ())))
        if not picker and self.images is None:self.images=ManagedImages(self.folder)
        path=None if picker else self.images.save(frame)
        parent,child=mp.get_context('spawn').Pipe()
        physical_stop=mp.get_context('spawn').Event()
        watch=None  # Physical mouse/keyboard activity no longer cancels requests.
        process=mp.get_context('spawn').Process(target=worker,args=(child,path,names,picker,physical_stop,self.bound_hwnd,game_hwnd,snapshot.image_only,budget,began+budget-.7),daemon=True)
        self.active=dict(process=process,pipe=parent,snapshot=snapshot,id=request_id,began=began,
                         game=game_hwnd,mini=0,tick=None,physical_stop=physical_stop,watch=watch,budget=budget,
                         query=GuideQuery(snapshot.purpose,snapshot.context.mode_id,snapshot.context.game_id,request_id,tuple(names),budget))
        diagnostics.event('query_start',request_id=request_id,round_id=snapshot.context.game_id,mode=snapshot.context.mode_id,selected=names)
        try:
            process.start();child.close()
            # When a hotkey gave this process activation permission, pass it
            # only to our own worker. Automatic requests can use the visible bridge.
            ctypes.windll.user32.AllowSetForegroundWindow(process.pid)
        except Exception:
            self._finish();child.close();raise
        self.timer.start();self.status.emit(f'正在配阵，最多 {budget} 秒；可用取消热键中止')
        return request_id

    @staticmethod
    def make_result(state,message):
        snap=state['snapshot'];selected=tuple(message.get('selected',[]));source_cards=tuple(message.get('cards',[]))
        conflict_limits=()
        if snap.image_only:
            from .ocr import Names
            problem=validate_image_candidates(selected,Names().names,snap.own_pool+snap.ally_pool)
            if problem:raise ValueError(problem)
            cards,conflict_limits=filter_image_cards(source_cards,selected,snap.own_pool+snap.ally_pool,snap)
        else:
            expected=set(snap.own_pool+snap.ally_pool+((snap.ally_locked,) if snap.ally_locked else ()))
            if set(selected)!=expected and not(message.get('input_incomplete') and len(set(selected))>=2 and set(selected)<=expected):
                raise ValueError('公开选择页候选核对不一致；未启用本批结果')
            cards=filter_cards(source_cards,snap)
        source_cards=tuple(c for c in source_cards if len(c.get('heroes',[]))==2 and set(c['heroes'])<=set(selected))
        cards=tuple(r for r in cards if {r.own_hero,r.ally_hero}<=set(selected))
        complete=bool(message.get('complete') or message.get('no_result')) and not message.get('input_incomplete')
        limits=conflict_limits+capability_limits(snap)+tuple(message.get('limits',()))
        if not complete:limits+=('攻略读取不完整；展示已读取全部适用组合',)
        return RecommendationResult(state['id'],snap.context.game_id,snap.fingerprint,cards,
            complete=complete,no_match=bool(message.get('no_result')) and not message.get('input_incomplete'),
            reference_only=snap.reference_only,selected_candidates=selected,source_cards=source_cards,
            local_observed=tuple(sorted(set(snap.own_pool+snap.ally_pool))),limits=limits)

    def poll(self):
        state=self.active
        if not state:return
        try:
            while state['pipe'].poll():
                message=state['pipe'].recv()
                if message.get('ready'):
                    if diagnostics._recorder:diagnostics._recorder.mini_hwnd=message['mini']
                    state['mini']=message['mini'];self.bound_hwnd=message['mini'];state['tick']=input_tick()
                    state['pipe'].send('go')
                    if state['snapshot'].image_only:
                        state['pipe'].send({'observed':sorted(set(state['snapshot'].own_pool+state['snapshot'].ally_pool))})
                    continue
                if message.get('event')=='input':state['tick']=message['tick'];continue
                if message.get('event')=='dialog':state['dialog']=message['hwnd'];continue
                if message.get('event')=='input_complete':
                    state['input_complete']=True
                    self.status.emit('提交完成；可切回游戏操作，继续读取攻略')
                    continue
                if message.get('event')=='focus_wait':
                    self.status.emit(message['text']);continue
                if message.get('event')=='manual_review':
                    if time.monotonic()-state['began']>=state.get('budget',15):
                        self.cancel('配阵超过时限，已停止');return
                    state['manual_review']=True
                    state['review_deadline']=time.monotonic()+90
                    if state.get('watch'):state['watch'].close()
                    self.cleanup_images()  # PNG has already been submitted; no more uploads.
                    self.status.emit('等待小程序人工确认；完成后自动读取推荐，请自行返回游戏。换将或离开选将将取消')
                    continue
                if message.get('event')=='review_hint':
                    self.status.emit(message['text']);continue
                if message.get('event')=='stage':
                    diagnostics.event('query_stage',request_id=state['id'],round_id=state['snapshot'].context.game_id,stage=message['stage'],elapsed=time.monotonic()-state['began'])
                    logging.info('mini stage: %s %.2fs',message['stage'],time.monotonic()-state['began']);continue
                if message.get('event')=='batch':
                    try:result=WeChatMiniProgramProvider.make_result(state,message)
                    except ValueError as error:self.cancel(str(error));return
                    state['partial']=result
                    self.batch.emit(result)
                    continue
                if not state.get('manual_review') and time.monotonic()-state['began']>=state.get('budget',15):
                    self.cancel('配阵已达时限，保留已读攻略');return
                if message.get('status')=='success':
                    try:result=WeChatMiniProgramProvider.make_result(state,message)
                    except ValueError as error:self.cancel(str(error));return
                    cards=result.recommendations
                    self._finish()
                    message_text=('未找到匹配组合' if result.no_match else
                        ('配阵已完成' if cards else '已读取组合中没有符合当前候选和座次的搭配'))
                    if message.get('input_incomplete'):
                        message_text='已取得部分配阵参考；未查询武将见攻略说明'
                    if message.get('return_error'):message_text+='；未能返回游戏：'+message['return_error']
                    if any('冲突' in s for s in result.limits):message_text=('已过滤冲突组合' if cards else '冲突过滤后暂无适用组合')
                    if message.get('manually_reviewed'):message_text='人工复核完成；'+message_text+'；请自行返回游戏'
                    self.status.emit(message_text)
                    self.finished.emit(result);return
                self.cancel(message.get('error','配阵失败'));return
            if state.get('manual_review'):
                if time.monotonic()>=state['review_deadline']:self.cancel('等待人工复核已结束，请重新配阵')
                elif not state['process'].is_alive():self.cancel('小程序工作进程已退出')
            elif time.monotonic()-state['began']>=state.get('budget',15):self.cancel('配阵已达时限，保留已读攻略')
            elif not state['process'].is_alive():self.cancel('小程序工作进程已退出')
        except (EOFError,OSError):self.cancel('小程序连接已断开')
        except Exception as error:
            logging.exception('guide message processing failed')
            self.cancel('配阵结果处理异常，保留已读攻略：'+str(error))

    def _return_game(self,state):
        # Restore only from the mini program, never a different foreground app.
        import win32gui
        if state.get('manual_review'):return  # Manual handoff owns focus until user returns.
        try:
            fg=win32gui.GetForegroundWindow();mini=state['mini']
            if mini:
                if fg==mini or win32gui.GetAncestor(fg,3)==mini:
                    from .mini_dialogs import image_dialogs
                    for dialog in image_dialogs(mini):win32gui.PostMessage(dialog,0x111,2,0)
                    if win32gui.IsWindow(state['game']) and not win32gui.IsIconic(state['game']):
                        from .window_focus import activate_window
                        focus=activate_window(state['game'],mini)
                        logging.info('cancel return focus: %s %s',focus.method,focus.ok)
                        return focus.ok
        except Exception:return False

    def _finish(self,restore=False):
        if diagnostics._recorder:diagnostics._recorder.mini_hwnd=0
        self._return_failed=False
        state=self.active;self.active=None;self.timer.stop()
        if state:
            try:
                if state['process'].is_alive():state['process'].terminate()
                if state['process'].pid is not None:state['process'].join(.1)
                if not state['process'].is_alive():state['process'].close()
            except Exception:logging.exception('guide process cleanup failed')
            try:state['pipe'].close()
            except Exception:logging.exception('guide pipe cleanup failed')
            if restore:self._return_failed=self._return_game(state) is False
            if state.get('watch'):
                try:state['watch'].close()
                except Exception:logging.exception('guide watch cleanup failed')
        self.cleanup_images()

    def cleanup_images(self):
        try:
            if self.images:self.images.cleanup()
        except OSError:
            logging.exception('temporary PNG cleanup failed; registry retained for next retry')

    def cancel(self,reason='配阵已取消'):
        diagnostics.event('query_stop',reason=reason)
        if any(x in reason for x in ('失败','超时','异常','未就绪')):diagnostics.fault(reason)
        state=self.active
        partial=state.get('partial') if state else None
        if state:
            self._finish(restore=True)
            if self._return_failed:reason+='；请手动返回游戏'
        if partial:
            self.finished.emit(replace(partial,complete=False,limits=partial.limits+(reason,)))
            reason+='；已保留已读攻略，请展开攻略面板查看'
        self.status.emit(reason)
