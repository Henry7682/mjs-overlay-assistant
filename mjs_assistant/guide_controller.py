"""Qt controller for round caches; all game interaction remains read-only."""
import logging
import time
import uuid
from dataclasses import replace
from html import escape
from PySide6.QtWidgets import QInputDialog,QMessageBox
from .modes import RANKED_CHUHAN,PEAK_CHUHAN
from .recommendations import (ModeContext,SelectionSnapshot,RECOMMENDATION_MODES,
                              refresh_image_result,retain_previous_selection)
from .guide_state import RoundGuideCache,PeakDraft,BattleTracker,GuideQuery,enemy_auto_allowed,CandidateStability
from .guide_panel import GuidePanel,card_html
from .capture import foreground
from .provider import input_idle_seconds
from .storage import write_json
from .peak_layout import draft_count


class GuideController:
    def current_mode(self):
        return self.mode_box.currentData() or getattr(self,'auto_mode',None)

    def guides_enabled(self):
        return self.config.get('recommendation',{}).get('guides_enabled',True)

    def safe_guide_call(self, operation, *args):
        """Guide failures must never unwind the statistics/update UI path."""
        try:return operation(*args)
        except Exception as error:
            now=time.monotonic();last=getattr(self,'_guide_error_at',0)
            if now-last>10:
                logging.exception('guide operation failed; statistics continue')
                self._guide_error_at=now
            message='攻略流程异常；本地统计继续，已读攻略保留：'+str(error)
            self.rec_status.setText(message);self.overlay.recommendation_status=message
            return None

    def init_guides(self):
        self.guide_panel=GuidePanel(self.config.get('recommendation',{}).get('panel_anchor',[.02,.4]))
        self.guide_panel.position_saved.connect(self.save_guide_position)
        self.guide_panel.retry_enemy.connect(self.retry_enemy_query)
        self.guide_cache=RoundGuideCache(None,self.game_id)
        self.enemy_cache=RoundGuideCache(None,self.game_id)
        self.peak_draft=PeakDraft();self.battle_tracker=BattleTracker()
        self.candidate_stability=CandidateStability(hold_seconds=0);self.peak_auto_ready=False
        self.selection_started_at=None
        self.enemy_attempted=False;self.enemy_status='敌方尚未查询';self.pool_signature=();self.pool_since=0
        self.unknown_frames=0;self.ranked_request_changed=False
        self.provider.batch.connect(lambda result:self.safe_guide_call(self.recommendation_batch,result))

    def save_guide_position(self,anchor):
        self.config.setdefault('recommendation',{})['panel_anchor']=list(anchor)
        write_json(self.folder/'settings.json',self.config)

    def reset_round(self,reason):
        # Revoke identity before cancellation can publish a partial final batch.
        self.request_id=None
        if self.provider.busy:self.safe_guide_call(self.provider.cancel,reason)
        self.game_id=uuid.uuid4().hex;mode=self.current_mode()
        self.guide_cache=RoundGuideCache(mode,self.game_id);self.enemy_cache=RoundGuideCache(mode,self.game_id)
        self.peak_draft=PeakDraft();self.battle_tracker=BattleTracker()
        self.enemy_attempted=False;self.enemy_status='敌方尚未查询'
        self.auto_attempted=False;self.auto_launch_count=0;self.auto_retry_at=0;self.auto_launch_id=None
        self._auto_wait_reason=None
        self.candidate_stability=CandidateStability(hold_seconds=0);self.peak_auto_ready=False
        self.selection_started_at=None
        self.pool_signature=();self.pool_since=0
        self.snapshot=self.confirmed_snapshot=None;self.ranked_request_changed=False
        self.overlay.recommendation=None;self.overlay.recommendation_status=''
        self.guide_panel.reset();self.selection_guard.clear();self.previous_scene='unknown'
        self.observed_seats=(None,None);self.unknown_frames=0
        logging.info('guide round reset: %s %s',self.game_id,reason)

    def recommendation_status(self,text):
        logging.info('recommendation: %s',text);self.rec_status.setText(text)
        self.overlay.recommendation_status=text
        if self.latest and self.latest.get('scene')=='battle' and self.enemy_attempted:
            self.enemy_status=text
        # Continue HWND-bound OCR during automation and while a 2v2 round exists.
        with self.worker.lock:
            self.worker.allow_background=self.guides_enabled() and self.current_mode() in RECOMMENDATION_MODES

    def invalidate_recommendation(self,reason):
        # Lifecycle reset is explicit in reset_round. Capture errors, minimize,
        # cancellation and settings dialogs do not delete a round's valid cache.
        self.confirmed_snapshot=None
        if reason=='游戏截图不可用':reason='游戏窗口暂时无法截图；请还原游戏窗口。已读攻略保留'
        if self.provider.busy:
            self.provider.cancel(reason)
            return  # Keep the provider's partial-cache/return-focus explanation.
        if reason=='正在确认选将状态':return
        self.recommendation_status(reason)

    def retain_ranked_recommendation(self):
        self.ranked_request_changed=True;self.confirmed_snapshot=None
        if self.overlay.recommendation:
            key=self.config.get('recommendation',{}).get('hotkeys',{}).get('request','Ctrl+Alt+P')
            self.overlay.recommendation=retain_previous_selection(self.overlay.recommendation,key)

    def update_selection(self,data):
        mode=self.current_mode();scene=data['scene'];phase=data.get('phase','unknown')
        if mode not in RECOMMENDATION_MODES:
            self.snapshot=None;self.guide_panel.hide();return
        if self.guide_cache.mode_id!=mode:self.reset_round('模式变化')
        if scene=='selection' and self.previous_scene=='battle':self.reset_round('新一局选将')
        names=tuple(dict.fromkeys(d.name for d in data.get('items',()) if d.confirmed and d.name))
        if not hasattr(self,'candidate_stability'):self.candidate_stability=CandidateStability(hold_seconds=0)
        eligible=mode==PEAK_CHUHAN and scene=='selection' and phase in ('ban','selection','transition')
        # Names here already passed the recognition worker's two-frame check.
        # Do not add another one-second hold on top of that evidence.
        if eligible and getattr(self,'selection_started_at',None) is None:
            self.selection_started_at=data['stamp']
            logging.info('peak selection first observed: round=%s stamp=%.3f',self.game_id,data['stamp'])
        self.peak_auto_ready=self.candidate_stability.update(names if eligible else (),time.monotonic(),
            (mode,self.game_id,scene,phase))
        if phase=='puppet':
            # A puppet choice is never part of the main-hero roster or draft.
            if self.snapshot:self.snapshot=replace(self.snapshot,phase='puppet')
            return
        if scene=='unknown':
            self.unknown_frames+=1
            if self.unknown_frames>=3 and self.provider.busy:self.provider.cancel('画面暂不可确认，已停止自动操作；保留本局缓存')
            self.snapshot=None;return
        self.unknown_frames=0
        if scene=='battle':
            if self.provider.busy and self.provider.active['snapshot'].purpose!='enemy_battle':
                self.provider.cancel('已进入战斗，保留已读攻略')
            self.snapshot=None;self.previous_scene='battle'
            self.peak_draft.update('battle',data.get('layout'),(),0,time.monotonic())
            self.battle_tracker.update(data['items'],data.get('battle_badges',{}))
            self.maybe_enemy_query();return
        self.previous_scene='selection'
        now=time.monotonic()
        image_only=mode==RANKED_CHUHAN
        if image_only:
            self.ranked_scene_frames=getattr(self,'ranked_scene_frames',0)+1 if phase=='selection' else 0
            revision,changed=self.selection_guard.update(data['frame'],data['items'],mode,scene,phase,image_only=True)
            seats=data.get('seats',(None,None))
            if all(seats):
                if all(self.observed_seats) and self.observed_seats!=seats:changed=True
                self.observed_seats=seats
            if changed and (self.overlay.recommendation or self.provider.busy):self.retain_ranked_recommendation()
        else:
            revision=self.game_id
            self.peak_draft.update(phase,data.get('layout'),names,len(data['items']),now,data.get('locked_names',()))
            if self.peak_draft.frozen:self.guide_cache.freeze(self.peak_draft.excluded)
            if data.get('layout')=='ban14':
                # A transient lost glyph must not erase previously two-frame
                # confirmed ban candidates before the initial request.
                names=tuple(sorted(self.peak_draft.ban_seen))
            seats=(None,None)  # Ban pool spans all directions; keep source seat variants.
        signature=tuple(sorted(names))
        if signature!=self.pool_signature:self.pool_signature=signature;self.pool_since=now
        self.snapshot=SelectionSnapshot(ModeContext(mode,self.game_id,scene,self.mode_evidence),names,names,
            phase=phase,own_seat=seats[0],ally_seat=seats[1],captured_at=data['stamp'],
            remaining_seconds=data.get('remaining'),reference_only=True,image_only=image_only,
            shared_pool_assumed=image_only,visual_revision=revision)
        if self.provider.busy and image_only and not self.ranked_request_changed:
            self.provider.update_evidence(self.snapshot)
        if image_only and self.overlay.recommendation and not self.ranked_request_changed:
            result=refresh_image_result(self.overlay.recommendation,self.snapshot)
            self.overlay.recommendation=result;self.guide_cache.accept(result)
        self.maybe_auto_recommend()

    def maybe_auto_recommend(self):
        if not self.guides_enabled() or not getattr(self,'enabled',True):return
        settings=self.config.get('recommendation',{})
        if not (settings.get('enabled',True) and settings.get('automatic',True)):
            self.auto_query_wait('自动查询已关闭，请检查配阵设置');return
        if self.auto_attempted or self.provider.busy:return
        if not self.snapshot or not self.snapshot.can_request(True):
            self.auto_query_wait('等待可查询的选将阶段、候选及剩余时间');return
        if not foreground(self.window_box.currentData()):
            self.auto_query_wait('等待游戏回到前台后自动查询');return
        if time.monotonic()<getattr(self,'auto_retry_at',0):return
        if self.snapshot.image_only:
            if getattr(self,'ranked_scene_frames',0)<2:
                self.auto_query_wait('等待连续确认普通楚汉选将画面');return
        elif not getattr(self,'peak_auto_ready',False):
            self.auto_query_wait('等待至少两名当前候选通过两帧姓名确认');return
        ready,message=self.provider.connection_status()
        if not ready:self.auto_query_wait(message);return
        self.request_recommendation(automatic=True)

    def auto_query_wait(self,reason):
        if reason!=getattr(self,'_auto_wait_reason',None):
            logging.info('automatic guide waiting: round=%s reason=%s',self.game_id,reason)
            self._auto_wait_reason=reason
        self.rec_status.setText(reason)

    def request_recommendation(self,checked=False,automatic=False):
        if not self.guides_enabled():
            self.rec_status.setText('攻略浮窗已关闭；本地统计仍可使用');return
        if self.latest and self.latest.get('scene')=='battle':
            if self.current_mode()==RANKED_CHUHAN:self.start_enemy_query()
            else:self.recommendation_status('巅峰战斗只使用本局缓存，不追加查询')
            return
        if not self.config.get('recommendation',{}).get('enabled',True):
            self.rec_status.setText('请先在小程序配阵设置启用');return
        if self.provider.busy:return
        if not self.snapshot or not self.snapshot.can_request(automatic):
            self.rec_status.setText('选将画面或候选尚未确认');return
        freshness=4 if self.snapshot.context.mode_id==PEAK_CHUHAN else 2.5
        if not self.latest or time.monotonic()-self.latest['stamp']>freshness:
            (self.auto_query_wait if automatic else self.rec_status.setText)('请返回游戏等待新画面');return
        budget=40 if self.snapshot.context.mode_id==PEAK_CHUHAN else 15
        target_budget=30 if self.snapshot.context.mode_id==PEAK_CHUHAN else budget
        if self.snapshot.remaining_seconds is not None and self.snapshot.remaining_seconds<target_budget+3:
            (self.auto_query_wait if automatic else self.rec_status.setText)('选将时间不足，跳过本次查询');return
        if automatic:self.auto_launch_count=getattr(self,'auto_launch_count',0)+1
        self.auto_launch_id=None
        started=False
        try:
            self.ranked_request_changed=False
            with self.worker.lock:self.worker.allow_background=True
            self.request_id=self.provider.start(replace(self.snapshot,selection_started_at=
                getattr(self,'selection_started_at',None) if automatic else None),
                self.latest['frame'],self.window_box.currentData())
            started=True;self.auto_attempted=True
            self._auto_wait_reason=None
            self.auto_launch_id=self.request_id if automatic else None
            query=self.provider.active['query'];self.guide_cache.begin(query)
            self.guide_cache.local_incomplete=(not self.snapshot.image_only and
                len(query.submitted)<(14 if self.snapshot.phase in ('ban','transition') else draft_count(self.latest.get('layout')) or 14))
            self.overlay.recommendation=None
        except Exception as error:
            if automatic and not started:self.retry_auto_launch(str(error))
            else:self.recommendation_status(str(error))

    def retry_auto_launch(self,reason):
        # Only startup failures are retried, not page/input failures or cancel.
        # Each retry still requires a fresh eligible frame and game foreground.
        self.auto_launch_id=None
        self.auto_attempted=getattr(self,'auto_launch_count',0)>=3
        self.auto_retry_at=time.monotonic()+2
        self.provider._connection_cache=None
        suffix='；本局自动启动已尝试3次，请用热键重试' if self.auto_attempted else '；等待游戏前台和新画面后自动重试'
        self.recommendation_status(reason+suffix)

    def recommendation_launch_failed(self,event):
        if (event['request_id']!=getattr(self,'auto_launch_id',None)
            or event['game_id']!=self.game_id):return
        self.retry_auto_launch(event['reason'])

    def maybe_enemy_query(self):
        if not self.guides_enabled():return
        settings=self.config.get('recommendation',{})
        if not(settings.get('enabled',True) and settings.get('automatic',True)):return
        if (enemy_auto_allowed(self.current_mode(),self.battle_tracker.roster,self.enemy_attempted)
            and not self.provider.busy and foreground(self.window_box.currentData())):
            ready,message=self.provider.connection_status()
            if ready:self.start_enemy_query()
            else:self.enemy_status=message

    def retry_enemy_query(self):
        if self.latest and self.latest.get('scene')=='battle':self.start_enemy_query()

    def start_enemy_query(self):
        if not self.guides_enabled():return
        roster=self.battle_tracker.roster
        if self.current_mode()!=RANKED_CHUHAN or not (roster.enemy_confirmed or roster.confirmed):
            self.enemy_status='敌方主将和阵营尚未确认';return
        if not self.config.get('recommendation',{}).get('enabled',True):
            self.enemy_status='配阵未启用';return
        if self.provider.busy:return
        if not foreground(self.window_box.currentData()):
            self.enemy_status='请返回游戏后按重新配阵热键查询敌方';return
        if not self.latest or time.monotonic()-self.latest['stamp']>2.5:return
        names=roster.enemy
        snap=SelectionSnapshot(ModeContext(RANKED_CHUHAN,self.game_id,'battle',self.mode_evidence),names,names,
            phase='battle',reference_only=True,pools_confirmed=True,purpose='enemy_battle')
        self.enemy_attempted=True  # Count failures and human interruption as the one automatic attempt.
        try:
            self.request_id=self.provider.start(snap,self.latest['frame'],self.window_box.currentData())
            self.enemy_cache.begin(self.provider.active['query']);self.enemy_status='正在查询敌方组合'
        except Exception as error:self.enemy_status='敌方查询失败：'+str(error)

    def recommendation_batch(self,result):
        if result.game_id!=self.game_id or result.request_id!=self.request_id:return
        target=self.enemy_cache if result.request_id==self.enemy_cache.request_id else self.guide_cache
        if target.accept(result) and target is self.guide_cache:
            self.overlay.recommendation=result
            if self.ranked_request_changed and target.mode_id==RANKED_CHUHAN:self.retain_ranked_recommendation()

    def recommendation_finished(self,result):
        self.recommendation_batch(result);self.tick()

    def cancel_recommendation(self):
        self.auto_launch_id=None
        self.auto_attempted=True
        if self.latest and self.latest.get('scene')=='battle':self.enemy_attempted=True
        self.invalidate_recommendation('用户已取消配阵；保留已读攻略')

    def toggle_details(self):
        if not self.guides_enabled():return
        self.guide_panel.toggle();self.tick()

    def confirm_peak_roster(self):
        if self.current_mode()!=PEAK_CHUHAN or self.peak_draft.frozen:
            QMessageBox.information(self,'禁将筛选','仅用于巅峰禁将结束后的待确认名单；本局已冻结时不可再次修改。');return
        expected=draft_count(self.latest.get('layout')) if self.latest else 0
        if not self.latest or self.latest.get('phase')!='selection' or not expected:
            QMessageBox.information(self,'等待选将阶段','请等待禁将结束并确认实际候选牌阵（6～13名）。');return
        initial='、'.join(self.peak_draft.candidate_signature)
        with self.worker.lock:self.worker.allow_background=True
        game=self.game_id
        text,ok=QInputDialog.getText(self,'确认禁将后的完整名单','填写禁将结束后保留的全部武将，包含已选走者，用顿号分隔。确认后本局仅筛选一次：',text=initial)
        if not ok or game!=self.game_id:return
        from .ocr import Names
        import re
        names=tuple(n.strip() for n in re.split('[、,，\n ]+',text) if n.strip())
        if len(names)!=expected or len(set(names))!=expected or not set(names)<=Names().names:
            QMessageBox.information(self,'名单未启用',f'当前布局需{expected}个不同的已知武将，请补齐或纠正。');return
        if self.peak_draft.confirm(names):self.guide_cache.freeze(self.peak_draft.excluded)

    def guide_html(self,scene):
        cache=self.guide_cache
        if scene=='battle':
            roster=self.battle_tracker.roster
            if not roster.camp:return '<h3>战斗组合攻略</h3><p>等待己方阵营确认，不按位置猜测。</p>'
            sections=[]
            for label,names,seats,current in (
                ('己方组合攻略',roster.friendly,roster.friendly_seats,cache),
                ('敌方组合攻略',roster.enemy,roster.enemy_seats,self.enemy_cache if cache.mode_id==RANKED_CHUHAN else cache)):
                partial=label.startswith('己方') and len(names)==1
                cards=current.hero_cards(names[0]) if partial else current.pair_cards(names,seats)
                color='#9bd9bd' if label.startswith('己方') else '#f0b1a3'
                status=current.empty_message()
                if current is self.enemy_cache and not current.received:status=self.enemy_status
                seat_note=('当前座次：'+'、'.join(f'{n} {s}' for n,s in zip(names,seats))) if len(names)==2 and all(seats) else '当前座次未确认；以下保留小程序原始方向'
                if partial:seat_note='己方另一名武将待识别；以下为包含已识别武将的缓存参考，尚未确认实际组合'
                elif len(names)<2:status='等待该阵营两名主将识别；不影响另一方已有攻略'
                sections.append(f'<h3 style="color:{color}">{label}</h3><p>{escape(" ＋ ".join(names))}<br>{escape(seat_note)}</p>'
                    +(card_html(cards) if cards else '<p>'+escape(status)+'</p>')
                    +'<p>'+escape('；'.join(current.limits))+'</p>')
            if cache.mode_id==PEAK_CHUHAN and not cache.frozen:sections.insert(0,'<p>禁将筛选未确认；按已识别的双方主将显示缓存参考。</p>')
            return ''.join(sections)
        cards=cache.visible_cards()
        parts=['<h3>组合参考 · 来源：名将小助手</h3>']
        if cache.mode_id==PEAK_CHUHAN:parts.append('<p>'+escape(self.peak_draft.message)+'</p>')
        if cache.local_incomplete:parts.append('<p>本地提交名单不完整，缓存不包含未提交武将的搭配；可用热键重查。</p>')
        if self.overlay.recommendation_status:parts.append('<p>'+escape(self.overlay.recommendation_status)+'</p>')
        parts.append(card_html(cards) if cards else '<p>'+escape(cache.empty_message())+'</p>')
        parts.append('<p>'+escape('；'.join(cache.limits))+'</p>')
        return ''.join(parts)
