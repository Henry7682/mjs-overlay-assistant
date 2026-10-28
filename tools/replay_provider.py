"""Opt-in public mini-program transport test with real, reviewed local samples.

This does not count as live-game end-to-end acceptance. Never sends game input.
By default the mini program must be in front; --from-game also exercises the
window roundtrip with an old sample, never the current game's live selection.
Physical input stops the whole run. --wait-ready passively waits at most 45s.
"""
import argparse,json,logging,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    import cv2,numpy as np,win32gui
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from mjs_assistant.provider import WeChatMiniProgramProvider
    from mjs_assistant.recommendations import ModeContext,SelectionSnapshot
    from mjs_assistant.capture import enable_dpi
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,default=1);parser.add_argument('--peak-only',action='store_true');parser.add_argument('--ranked-only',action='store_true');parser.add_argument('--image-only',action='store_true');parser.add_argument('--from-game',action='store_true');parser.add_argument('--wait-ready',type=float,default=0);parser.add_argument('--continue-safe-failures',action='store_true');parser.add_argument('--sample');parser.add_argument('--names',help='Comma-separated reviewed peak candidates');args=parser.parse_args()
    enable_dpi();app=QApplication([])
    root=Path('.research/v02');home=root/'provider-replay';home.mkdir(exist_ok=True)
    logging.basicConfig(filename=home/'stages.log',level=logging.INFO,encoding='utf8',format='%(asctime)s %(message)s')
    provider=WeChatMiniProgramProvider(home);records=[];state={};index=0
    report_path=home/('report-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
    cases=[('ranked_chuhan_2v2','session-205214/000.png','夏侯惇,孙策,张辽,项梁,萧何,鲁仲连,主父偃,卫玠',4,1),
           ('peak_chuhan_2v2','session-210943/009.png','张仪,如姬,袁术,巴清,金日磾,侯嬴,郭舍人,荀彧,孟姚',1,4)]
    if args.peak_only:cases=cases[1:]
    if args.ranked_only:cases=cases[:1]
    if args.names:
        if not args.peak_only:raise ValueError('--names requires --peak-only')
        cases=[(cases[0][0],cases[0][1],args.names,1,4)]
    if args.sample:
        if not args.ranked_only or not args.image_only:raise ValueError('--sample requires ranked image-only route')
        cases=[(cases[0][0],str(Path(args.sample).resolve()),'',4,1)]
    def status(text):state['status']=text
    provider.status.connect(status)
    def finished(result):
        state['result']={'no_match':result.no_match,'pairs':[[r.own_hero,r.ally_hero] for r in result.recommendations],
            'reasons':[r.reason for r in result.recommendations],'fingerprint':result.fingerprint,'selected':list(result.selected_candidates),'limits':list(result.limits),'complete':result.complete}
    provider.finished.connect(finished)
    ready_deadline=time.monotonic()+min(45,args.wait_ready)
    def begin():
        nonlocal index
        if index>=args.count*len(cases):app.quit();return
        mode,sample,names,own,ally=cases[index%len(cases)]
        fg=win32gui.GetForegroundWindow()
        if args.from_game:
            from mjs_assistant.capture import windows
            found=windows()
            ready=len(found)==1 and fg==found[0].hwnd
        else:ready=win32gui.GetWindowText(win32gui.GetAncestor(fg,3))=='名将小助手'
        from mjs_assistant.provider import input_idle_seconds
        ready=ready and input_idle_seconds()>=.5
        if not ready:
            if time.monotonic()<ready_deadline:QTimer.singleShot(150,begin);return
            print('STOP: 目标窗口不在前台或仍有输入，未执行查询',flush=True);app.quit();return
        frame=cv2.imdecode(np.fromfile(root/sample,np.uint8),1);pool=tuple(names.split(','))
        snapshot=SelectionSnapshot(ModeContext(mode,'replay-'+str(index),'selection','reviewed_sample'),pool,pool,
            own_seat=own,ally_seat=ally,phase='selection',pools_confirmed=True,reference_only=mode=='peak_chuhan_2v2',
            shared_pool_assumed=mode=='ranked_chuhan_2v2',visual_revision=sample)
        if args.image_only and mode=='ranked_chuhan_2v2':
            from dataclasses import replace
            snapshot=replace(snapshot,own_pool=(),ally_pool=(),pools_confirmed=False,reference_only=True,image_only=True)
        state.clear();state.update(mode=mode,sample=sample,began=time.monotonic(),status='initializing')
        try:provider.start(snapshot,frame,fg)
        except Exception as error:state['status']=str(error)
    def poll():
        nonlocal index
        if not state or provider.busy:return
        row={k:v for k,v in state.items() if k!='began'}
        row.update(seconds=time.monotonic()-state['began'],success='result' in state)
        records.append(row);(home/'report.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf8')
        report_path.write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf8')
        print(json.dumps(row,ensure_ascii=False),flush=True)
        state.clear();index+=1
        recoverable=any(s in row.get('status','') for s in ('15 秒','15秒','选择未生效','候选核对不一致','配阵超时'))
        if not row['success'] and not (args.continue_safe_failures and recoverable):
            app.quit();return  # No blind retry after any failure or intervention.
        timer.stop();QTimer.singleShot(500,lambda:(begin(),timer.start()))
    timer=QTimer();timer.setInterval(100);timer.timeout.connect(poll)
    QTimer.singleShot(0,begin);timer.start();app.exec()
    if provider.busy:provider.cancel('测试停止')

if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support();main()
