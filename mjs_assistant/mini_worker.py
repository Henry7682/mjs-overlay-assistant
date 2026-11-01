"""Public WeChat UI worker. Parent process owns cancellation and the hard deadline."""
from __future__ import annotations
import argparse
import json
import multiprocessing as mp
import re
import time
from pathlib import Path

MANUAL_REVIEW_SECONDS=90
PEAK_RETURN_TARGET=30
PEAK_RESULT_RESERVE=4


class PageNotReady(RuntimeError):pass


def parse_document(text):
    selected = re.search(r'已选武将（点击移除）\s*清空(.*?)(?:配阵结果|未找到匹配的组合搭配|位置:|$)', text, re.S)
    names = re.findall(r'([\u3400-\u9fff]{2,6})\s*✕', selected[1]) if selected else []
    no_result = '未找到匹配的组合搭配' in text
    section = text.split('配阵结果', 1)[-1].split('位置:', 1)[0]
    # Rating glyphs include grey stars in this UIA provider: deliberately omit.
    pattern = re.compile(r'([\u3400-\u9fff]{2,6})\s+\d+(?:\.\d+)?%\s*\+\s*'
                         r'([\u3400-\u9fff]{2,6})\s+\d+(?:\.\d+)?%\s*'
                         r'(.*?)\s*♡\s*\d+\s*作者\s*海报\s*(.*?)(?=★|$)', re.S)
    cards = []
    for first, second, seats, reason in pattern.findall(section):
        variants = re.findall(r'([\u3400-\u9fff]+)([1-4])/([\u3400-\u9fff]+)([1-4])号位', seats)
        if not variants: continue
        cards.append({'heroes':[first,second], 'seats':variants, 'reason':reason.strip(),
                      'rating':None, 'rating_note':'辅助功能文本不能可靠区分亮星与灰星'})
    return {'selected':names, 'cards':cards, 'no_result':no_result}


def _worker(connection, path, expected, picker_only=False,physical_stop=None,bound_hwnd=None,game_hwnd=None,image_only=False,budget=15,deadline=None,read_existing=False,return_deadline=None):
    metrics={}
    def stage(name):connection.send({'event':'stage','stage':name,'metrics':{k:dict(v) for k,v in metrics.items()}})
    def measured(category):
        def decorate(fn):
            def run(*args,**kwargs):
                began=time.monotonic()
                try:return fn(*args,**kwargs)
                finally:
                    seconds=time.monotonic()-began
                    row=metrics.setdefault(category,{'count':0,'seconds':0.,'max_seconds':0.})
                    row['count']+=1;row['seconds']+=seconds;row['max_seconds']=max(row['max_seconds'],seconds)
            return run
        return decorate
    stage('加载自动化组件')
    import ctypes
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    import win32gui
    import win32api
    import win32process
    from pywinauto import Desktop
    from pywinauto.uia_defines import IUIA, get_elem_interface
    from comtypes import COMError

    class LastInput(ctypes.Structure):
        _fields_=[('cbSize',ctypes.c_uint),('dwTime',ctypes.c_uint)]
    def input_tick():
        info=LastInput();info.cbSize=ctypes.sizeof(info)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info));return info.dwTime
    def candidates():
        from .mini_windows import mini_windows
        return mini_windows()
    until=time.monotonic()+1
    while True:
        windows=candidates()
        if bound_hwnd in windows:mini=bound_hwnd;break
        if len(windows)==1:mini=windows[0];break
        if len(windows)>1 or time.monotonic()>=until:
            raise RuntimeError(f'请打开唯一名将小助手窗口（当前匹配 {len(windows)} 个）')
        time.sleep(.08)
    stage('验证小程序进程')
    # Match both title and real executable before any input.
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,win32process.GetWindowThreadProcessId(mini)[1])
    path_buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(32768)
    try:
        if not kernel.QueryFullProcessImageNameW(handle,0,path_buffer,ctypes.byref(size)):
            raise RuntimeError('无法验证小程序进程')
        if Path(path_buffer.value).name.lower()!='wechatappex.exe': raise RuntimeError('小程序进程不匹配')
    finally: kernel.CloseHandle(handle)
    original=game_hwnd or win32gui.GetForegroundWindow()
    api=IUIA();uia=api.iuia;ids=api.UIA_dll
    connection.send({'ready':True,'mini':mini,'original':original})
    if connection.recv()!='go': return
    result=None
    start=time.monotonic()
    deadline=min(deadline or start+budget-.5,start+budget-.5)
    # Parent deadline includes worker startup. Keep 40s as a hard failure guard,
    # but stop adding names early enough to return useful results near 30s.
    quick_peak=picker_only and budget>15 and not read_existing
    result_deadline=min(deadline,(return_deadline or deadline-budget+.7+PEAK_RETURN_TARGET)-1) if quick_peak else deadline
    input_deadline=result_deadline-PEAK_RESULT_RESERVE if quick_peak else deadline
    from .window_focus import activate_window
    stopped=lambda:False  # Do not interpret physical activity as cancellation.
    focus=activate_window(mini,original,stopped)
    stage('切至小程序：'+focus.method+(' 成功' if focus.ok else ' 失败'))
    if not focus.ok:
        connection.send({'status':'failed','error':'切至小程序失败：'+focus.reason,'seconds':time.monotonic()-start})
        return
    connection.send({'event':'activated'})
    time.sleep(.15)
    last_input=input_tick()
    read_only_results=False;manual_review=False;review_deadline=None;review_hint='';input_limit=''
    connection.send({'event':'input','tick':last_input})
    def check_request():
        while connection.poll():
            message=connection.recv()
            if message=='cancel': raise RuntimeError('配阵已取消')
            if isinstance(message,dict) and image_only and 'observed' in message:
                expected[:]=message['observed']
        if manual_review:
            if not win32gui.IsWindow(mini):raise RuntimeError('小程序已关闭，复核已取消')
            if time.monotonic()>=review_deadline:raise TimeoutError('等待人工复核已结束，请重新配阵')
            return  # Read-only observation: human input is expected, no focus changes.
        if not win32gui.IsWindow(mini):raise RuntimeError('小程序已关闭')
        if time.monotonic()>=deadline: raise TimeoutError('配阵超时')
    def guard():
        check_request()
        if read_only_results or manual_review:return
        from .input_phase import wait_input_target
        def ready():
            fg=win32gui.GetForegroundWindow()
            return bool(fg) and (fg==mini or win32gui.GetAncestor(fg,3)==mini)
        return wait_input_target(ready,check_request,lambda waiting:connection.send(dict(event='focus_wait',
            text='等待小程序回到前台后继续输入（仍计入本次时限）' if waiting else '小程序已回到前台，继续配阵')))
    previous_click=None
    def fast_click(coords,can_click=None):
        nonlocal previous_click
        if read_only_results:raise RuntimeError('结果读取阶段禁止自动输入')
        # pywinauto.mouse waits a system double-click interval after *any* input,
        # including typing in a different control. Only same-point clicks need it.
        if previous_click and abs(previous_click[0][0]-coords[0])<4 and abs(previous_click[0][1]-coords[1])<4:
            delay=win32gui.GetDoubleClickTime()/1000-(time.monotonic()-previous_click[1])
            if delay>0: time.sleep(delay)
        guard()
        if can_click is not None and not can_click():return False
        if win32gui.GetForegroundWindow()!=mini:raise RuntimeError('输入目标已变化，已停止')
        under=win32gui.WindowFromPoint(coords)
        if win32gui.GetAncestor(under,2)!=mini:raise RuntimeError('控件被其他窗口遮挡，已停止')
        left,top=win32api.GetSystemMetrics(76),win32api.GetSystemMetrics(77)
        width,height=win32api.GetSystemMetrics(78),win32api.GetSystemMetrics(79)
        stage(f'点击坐标 {coords} 桌面 {left},{top},{width},{height}')
        while True:
            guard()
            if can_click is not None and not can_click():return False
            if win32gui.GetForegroundWindow()!=mini or win32gui.GetAncestor(win32gui.WindowFromPoint(coords),2)!=mini:
                raise RuntimeError('点击目标已被遮挡或移动，未发送点击')
            win32api.mouse_event(0xC001,int((coords[0]-left)*65535/max(1,width-1)),int((coords[1]-top)*65535/max(1,height-1)),0,0)
            time.sleep(.03)
            check_request()
            if win32gui.GetForegroundWindow()==mini and win32api.GetCursorPos()==coords:
                break  # Cursor motion causes a bounded retry, not request cancellation.
        if can_click is not None and not can_click():return False
        win32api.mouse_event(0x0002,0,0,0,0)
        win32api.mouse_event(0x0004,0,0,0,0)
        previous_click=(coords,time.monotonic())
        time.sleep(.05)  # Let the target dispatch focus before a following key input.
        return True
    from .mini_page import WindowRoot
    window_root=WindowRoot(lambda:uia.ElementFromHandle(mini),(COMError,))
    @measured('control_lookup_with_wait')
    def find(title, kind=None,timeout=None):
        from .uia_wait import wait_visible
        from .mini_page import locate_control
        def fetch():
            return window_root.query(lambda root:locate_control(root,ids,api.build_condition,title,kind,uia,optimized=picker_only or kind=='Document'))
        began=time.monotonic()
        element,state=wait_visible(fetch,guard,review_deadline if manual_review else deadline,
            timeout=timeout if timeout is not None else (3 if kind=='Document' else 1),cached=kind=='Document')
        if time.monotonic()-began>.3:stage(f'等待页面控件 {title} {time.monotonic()-began:.2f}s {state}')
        if element:return element
        raise PageNotReady('小程序页面尚未就绪，请打开一键配阵后重试：'+title+' ('+state+')')
    def text_area(element):
        from pywinauto.uia_defines import pattern_ids
        try:
            pattern_id,interface=pattern_ids['Text']
            return element.GetCachedPattern(pattern_id).QueryInterface(interface).DocumentRange
        except Exception:return get_elem_interface(element,'Text').DocumentRange
    @measured('document_including_lookup')
    def document(timeout=None,results_only=False):
        began=time.monotonic()
        element=find('Page-Frame','Document',timeout)
        area=text_area(element)
        text=area.GetText(-1)
        if results_only:
            from .mini_page import result_text
            text=result_text(text)
        if time.monotonic()-began>.3:stage(f'页面文字读取耗时 {time.monotonic()-began:.2f}s')
        return text
    from .album_location import album_point,unique_point
    def album_text_point():
        try:
            bounds=win32gui.GetWindowRect(mini)
            doc=find('Page-Frame','Document',timeout=.15)
            matched=text_area(doc).FindText('相册',True,False)
            boxes=matched.GetBoundingRectangles() if matched else []
            if bounds!=win32gui.GetWindowRect(mini):return None
            stage(f'相册文字定位：矩形数 {len(boxes)//4}')
            return album_point(boxes,bounds)
        except (PageNotReady,COMError):
            stage('相册文字位置暂不可读');return None

    def album_control_point():
        # Use actual named controls when TextRange returns no clickable rectangle.
        from .mini_dialogs import album_click_allowed
        points=[];bounds=win32gui.GetWindowRect(mini)
        for label in ('📷 相册','相册','📷相册'):
            guard()
            if not album_click_allowed(mini,win32gui):return None
            try:
                elements=window_root.query(lambda root:root.FindAll(
                    ids.TreeScope_Descendants,api.build_condition(title=label)))
                count=elements.Length if elements is not None else 0
                if count>12:return None
                for index in range(count):
                    item=elements.GetElement(index)
                    if item.CurrentIsOffscreen:continue
                    rect=item.CurrentBoundingRectangle
                    points.append(album_point((rect.left,rect.top,rect.right-rect.left,
                                               rect.bottom-rect.top),bounds))
            except COMError:
                continue
        stage(f'相册控件定位：有效位置 {sum(p is not None for p in points)}')
        if bounds!=win32gui.GetWindowRect(mini):return None
        return unique_point(points)

    album_visual_used=False
    def album_image_point():
        nonlocal album_visual_used
        if album_visual_used:return None
        album_visual_used=True
        from .mini_dialogs import album_click_allowed
        from .capture import Capture,client_rect
        from .ocr import Ocr,clean_name
        capture=None
        try:
            guard()
            if not album_click_allowed(mini,win32gui):return None
            ocr=Ocr()  # Only on failure; never loaded on the successful UIA path.
            guard()
            if not album_click_allowed(mini,win32gui):return None
            capture=Capture(mini)
            until=min(deadline,time.monotonic()+1)
            while time.monotonic()<until:
                guard()
                try:frame,rect,stamp=capture.read();break
                except RuntimeError:time.sleep(.05)
            else:return None
            bounds=win32gui.GetWindowRect(mini)
            x,y,w,h=rect;top=int(h*.20)
            words=ocr.read(frame[top:,:])
            guard()
            if (not album_click_allowed(mini,win32gui) or rect!=client_rect(mini)
                    or bounds!=win32gui.GetWindowRect(mini)):return None
            points=[]
            for word in words:
                if clean_name(word.text)!='相册' or word.confidence<.90:continue
                a,b,c,d=word.box
                points.append(album_point((x+a,y+top+b,c-a,d-b),bounds))
            stage(f'相册局部识别：有效位置 {sum(p is not None for p in points)}')
            return unique_point(points)
        except Exception as error:
            # Cancellation and elapsed budgets must propagate, not trigger input.
            guard()
            stage('相册局部识别不可用：'+type(error).__name__)
            return None
        finally:
            if capture is not None:
                try:capture.stop()
                except Exception:pass

    def click(title,until_override=None):
        nonlocal last_input
        guard()
        can_click=None
        if title in expected:
            from .mini_picker import search_ready,portrait_point
            from .mini_page import picker_range
            until=min(deadline,until_override or deadline,time.monotonic()+2.8)
            scrolled=0
            settled_point=None
            while time.monotonic()<until:
                guard()
                doc=find('Page-Frame','Document')
                area,footer=picker_range(text_area(doc))
                text='相册 绘图区域 '+area.GetText(-1)+' 绘图区域'
                if not search_ready(text,title):
                    settled_point=None
                    time.sleep(.06);continue
                # Restrict to the picker after the footer; never use a chip,
                # search value or a same-name mention in a recommendation.
                matched=area.FindText(title,False,False)
                boxes=matched.GetBoundingRectangles() if matched else []
                fb=footer.GetBoundingRectangles()
                point=portrait_point(boxes,win32gui.GetWindowRect(mini),fb[1] if len(fb)==4 else 0)
                if point:
                    # A wheel animation can still move the tile after its label
                    # first becomes visible. Re-locate until two reads agree;
                    # clicking a moving portrait can turn into a drag/no-op.
                    if scrolled and (settled_point is None or max(abs(a-b) for a,b in zip(point,settled_point))>2):
                        settled_point=point;time.sleep(.06);continue
                    guard();fast_click(point)
                    last_input=input_tick();connection.send({'event':'input','tick':last_input})
                    time.sleep(.06);return
                if matched and len(fb)==4 and fb[3]>0 and scrolled<3:
                    # This public page does not implement Text.ScrollIntoView.
                    # Wheel the body immediately above its observed fixed footer.
                    bounds=win32gui.GetWindowRect(mini)
                    center=(int((bounds[0]+bounds[2])/2),int(fb[1]-fb[3]*3))
                    guard()
                    if win32gui.GetForegroundWindow()!=mini or win32gui.GetAncestor(win32gui.WindowFromPoint(center),2)!=mini:
                        raise RuntimeError('武将列表被其他窗口遮挡，已停止')
                    left,top=win32api.GetSystemMetrics(76),win32api.GetSystemMetrics(77)
                    width,height=win32api.GetSystemMetrics(78),win32api.GetSystemMetrics(79)
                    win32api.mouse_event(0xC001,int((center[0]-left)*65535/max(1,width-1)),int((center[1]-top)*65535/max(1,height-1)),0,0)
                    guard()
                    if win32gui.GetForegroundWindow()!=mini or win32api.GetCursorPos()!=center:
                        continue  # Re-read the live tile after a user's cursor move.
                    win32api.mouse_event(0x0800,0,0,-360,0);scrolled+=1
                    last_input=input_tick();connection.send({'event':'input','tick':last_input})
                    stage('滚动显示武将头像：'+title)
                    settled_point=None
                    time.sleep(.12);continue
                time.sleep(.06)
            from .picker_fill import CandidateUnavailable
            raise CandidateUnavailable('武将头像未在可点击区域就绪：'+title)
        if title=='📷 相册':
            from .mini_dialogs import album_click_allowed
            from .album_location import locate_album
            can_click=lambda:album_click_allowed(mini,win32gui)
            center=locate_album(album_text_point,album_control_point,album_image_point,
                                guard,can_click,deadline,stage)
            if center is None:return False
        else:
            # The sticky selected-pool header exposes a real Text control.
            # Chromium's document TextRange may report no rectangles for 清空
            # after scrolling results, while this control remains visible.
            element=find(title,timeout=4 if title=='清空' else None)
            rect=element.CurrentBoundingRectangle
            bounds=win32gui.GetWindowRect(mini)
            if rect.right<=rect.left or not(bounds[0]<=rect.left<rect.right<=bounds[2] and bounds[1]<=rect.top<rect.bottom<=bounds[3]):
                raise RuntimeError('控件不可见：'+title)
            center=((rect.left+rect.right)//2,(rect.top+rect.bottom)//2)
        guard()
        if not fast_click(center,can_click):return False
        last_input=input_tick();connection.send({'event':'input','tick':last_input})
        time.sleep(.06)
        return True
    search_value_supported=None
    @measured('search_value')
    def set_search(value):
        nonlocal last_input,search_value_supported
        guard()
        # The edit is near the start of the native tree; descending via the
        # document adds several remote UIA roundtrips with no smaller search.
        edit=window_root.query(lambda root:root.FindFirst(ids.TreeScope_Descendants,api.build_condition(control_type='Edit')))
        if not edit: raise RuntimeError('武将搜索框不存在')
        inner=edit.FindFirst(ids.TreeScope_Children,api.build_condition(control_type='Edit'))
        if inner:edit=inner
        # Each step sets a requested search once. Reading Value beforehand adds
        # a remote call without verifying the asynchronously rendered roster.
        if search_value_supported is not False:
            try:
                pattern=get_elem_interface(edit,'Value')
                guard();pattern.SetValue(value)
                if search_value_supported is None:stage('搜索框公开Value接口可用')
                search_value_supported=True
                last_input=input_tick();connection.send({'event':'input','tick':last_input})
                return  # Exact live roster/chip evidence gates the following click.
            except Exception as error:
                guard()  # A cancellation must never fall through into keyboard input.
                search_value_supported=False
                stage('搜索框Value接口不可用：'+type(error).__name__)
        raise RuntimeError('搜索框公开输入接口不可用；未向当前键盘焦点发送姓名')
    def correct_candidates():
        # Only use the public hero picker. Never accept the mini program's guesses.
        # The supplied candidates have been visually checked against the real PNG.
        click('取消')
        for name in expected:
            guard();set_search(name);click(name)
        set_search('')
    def fill_candidates():
        nonlocal input_limit
        from .picker_fill import fill_pool
        # Search each requested name directly. Waiting for two identical full
        # catalogues was redundant and could consume seconds before first input.
        click('全部');click('全')
        def read():
            text=document(results_only=True)
            return text,parse_document(text)
        def publish(parsed):
            limits=[f"候选输入进度 {len(parsed['selected'])}/{len(expected)}；阶段性攻略不完整"]
            connection.send(dict(event='batch',input_incomplete=True,complete=False,limits=limits,**parsed))
        last,input_limit=fill_pool(expected,set_search,measured('candidate_click')(click),
                                  read,publish,stage,guard,input_deadline)
        if input_limit:stage(input_limit)
        # This is the post-click verification of the final selected pool. Reuse
        # its parsed result instead of locating/reading the same page again.
        if last is None or len(last['selected'])<2:
            raise RuntimeError(input_limit or '已确认候选不足两名；请重新配阵')
        return last

    def clear_candidates(initial_text=None):
        nonlocal last_input
        # Confirm only this exact public Clear dialog, including a dialog left
        # by an interrupted prior request. A generic 确定 may belong elsewhere.
        def confirmation():
            index=window_root.query(lambda root:root.FindFirst(ids.TreeScope_Children,api.build_condition(title='AppIndex',control_type='Document')))
            if not index:return None
            question=index.FindFirst(ids.TreeScope_Children,api.build_condition(title='确定清空所有已选武将？'))
            if not question:return None
            return index.FindFirst(ids.TreeScope_Children,api.build_condition(title='确定'))
        def confirm_click(confirm):
            nonlocal last_input
            rect=confirm.CurrentBoundingRectangle
            if rect.right<=rect.left or rect.bottom<=rect.top:return False
            stage('确认清空')
            guard();fast_click(((rect.left+rect.right)//2,(rect.top+rect.bottom)//2))
            last_input=input_tick();connection.send({'event':'input','tick':last_input})
            return True
        def clear_click(attempts):
            stage('定位清空入口' if not attempts else '重新定位未响应的清空入口')
            click('清空')
        from .mini_clear import clear_pool
        clear_pool(document,lambda text:not parse_document(text)['selected'] and '一键配阵' in text and '相册' in text,
            confirmation,confirm_click,clear_click,guard,deadline,initial=initial_text)
    def handoff(reason):
        nonlocal manual_review,review_deadline,review_hint
        if not manual_review:
            manual_review=True;review_deadline=time.monotonic()+MANUAL_REVIEW_SECONDS
            connection.send({'event':'manual_review','seconds':MANUAL_REVIEW_SECONDS})
        if reason!=review_hint:
            review_hint=reason
            connection.send({'event':'review_hint','text':reason+'；请在小程序确认，完成后自行返回游戏'})
    def collect_results(first,verify_empty=False):
        """Read publicly rendered cards; send each validated batch immediately.

        UIA Text may already expose offscreen cards. A repeated text is not end
        evidence. Scroll only a live UIA scroll container with visible results.
        Human review stays read-only and therefore honestly returns partial data.
        """
        nonlocal last_input
        from .guide_reader import GuidePages
        pages=GuidePages();stalled=0;previous_position=None
        if input_limit:pages.limits.append(input_limit)
        if verify_empty and not first.get('cards'):
            # Chips can update before their recommendations. Do not declare a
            # global no-match from the first post-click empty response alone.
            guard()
            refreshed=parse_document(document(results_only=True))
            if set(refreshed['selected'])!=set(first['selected']):
                raise RuntimeError('读取期间小程序候选发生变化，保留已读结果')
            first=refreshed
        pages.add(first)
        connection.send(dict(event='batch',input_incomplete=bool(input_limit),**pages.payload()))
        while True:
            if pages.no_result:break
            if manual_review:
                pages.limits.append('人工复核后仅读取公开页面文字；未自动滚动验证末尾');break
            guard()
            if quick_peak and time.monotonic()>=result_deadline:
                pages.limits.append('达到优先返回时间；已读攻略保留，未验证全部结果');break
            if win32gui.GetForegroundWindow()!=mini:
                pages.limits.append('已离开小程序，保留已读攻略');break
            doc=find('Page-Frame','Document')
            area=text_area(doc)
            # One fresh document per scroll observation: use its text for both
            # pool verification/batches and its ranges for scroll geometry.
            # Never reuse an element across an input or mark repetitions complete.
            pages.add(parse_document(area.GetText(-1)))
            connection.send(dict(event='batch',input_incomplete=bool(input_limit),**pages.payload()))
            if pages.no_result:break
            heading=area.FindText('配阵结果',False,False)
            footer=area.FindText('位置:',False,False)
            selected=area.FindText('已选武将（点击移除）',False,False)
            if not heading or not footer or not selected:
                pages.limits.append('结果区结构暂不可确认；已读攻略保留');break
            chips=area.Clone();chips.MoveEndpointByRange(0,selected,0);chips.MoveEndpointByRange(1,heading,0)
            guides=area.Clone();guides.MoveEndpointByRange(0,heading,1);guides.MoveEndpointByRange(1,footer,0)
            # Reuse this fresh page snapshot instead of relocating the entire
            # document a second time solely to check the terminal message.
            tail=guides.GetText(-1)
            if re.search(r'(?:没有更多(?:了|组合|攻略)|已到底|全部(?:组合|攻略)已(?:显示|加载))',tail):
                pages.complete=True;break
            from .guide_reader import result_scroll_target
            bounds=win32gui.GetWindowRect(mini)
            center,position=result_scroll_target(bounds,footer.GetBoundingRectangles(),
                chips.GetBoundingRectangles(),guides.GetBoundingRectangles())
            if center is None:
                pages.limits.append('未找到可见结果卡片，已读攻略保留');break
            signature=(position,len(pages.cards))
            stalled=stalled+1 if signature==previous_position else 0
            previous_position=signature
            if stalled>=(2 if quick_peak else 4):
                pages.limits.append('当前已加载攻略已读取；滚动不再移动，但页面未提供明确末尾标识');break
            guard()
            if win32gui.GetForegroundWindow()!=mini or win32gui.GetAncestor(win32gui.WindowFromPoint(center),2)!=mini:
                pages.limits.append('结果区域不可操作，保留已读攻略；未验证末尾');break
            left,top=win32api.GetSystemMetrics(76),win32api.GetSystemMetrics(77)
            width,height=win32api.GetSystemMetrics(78),win32api.GetSystemMetrics(79)
            win32api.mouse_event(0xC001,int((center[0]-left)*65535/max(1,width-1)),int((center[1]-top)*65535/max(1,height-1)),0,0)
            guard()
            if win32gui.GetForegroundWindow()!=mini or win32api.GetCursorPos()!=center:
                pages.limits.append('游戏操作期间仅读取已显示攻略，未继续滚动');break
            # One wheel notch, not four: the result viewport can be only one
            # card tall when fourteen selected chips occupy the sticky header.
            win32api.mouse_event(0x0800,0,0,-120,0)
            last_input=input_tick();connection.send({'event':'input','tick':last_input})
            # Keep the existing settling allowance on unchanged pages; the next
            # iteration performs the fresh read instead of reading twice here
            # and then relocating the same document again for geometry.
            time.sleep(.55 if pages.unchanged else .30);guard()
        payload=pages.payload()
        payload['input_incomplete']=bool(input_limit)
        connection.send(dict(event='batch',**payload))
        return payload
    try:
        if read_existing:
            read_only_results=True
            current=parse_document(document())
            if not current['selected']:raise RuntimeError('当前页面没有已选名单')
            result=dict(status='ok',**collect_results(current),seconds=time.monotonic()-start)
            return
        from .mini_dialogs import image_dialogs,close_image_dialogs
        stage('检查上次图片选择框')
        if close_image_dialogs(mini,guard,deadline):
            stage('已取消上次未完成的图片选择')
        stage('读取配阵页面')
        try:text=document(timeout=.15)
        except (PageNotReady,COMError):
            # Only at initial connection, never while an image picker is opening
            # or while the human is reviewing names. One attempt, same 15s budget.
            from .mini_content import activate_content
            stage('激活小程序页面内容')
            activate_content(mini,guard,fast_click)
            last_input=input_tick();connection.send({'event':'input','tick':last_input})
            text=document()
        if '一键配阵' not in text or '相册' not in text: raise RuntimeError('请先打开一键配阵页')
        if '按强度' not in text or '位置: 不限' not in text: raise RuntimeError('原型需要按强度／位置不限')
        if '已选武将（点击移除）' in text:
            clear_candidates(text)
        if picker_only:
            stage('公开选择页填入候选')
            result=fill_candidates()
            selected=set(result['selected'])
            if selected!=set(expected) and not(input_limit and selected<=set(expected) and len(selected)>=2): raise RuntimeError('公开选择页候选核对不一致')
            read_only_results=True
            connection.send({'event':'input_complete'})
            result=collect_results(result,verify_empty=True)
            if input_limit:
                result['input_incomplete']=True;result['complete']=False
            result.update(seconds=time.monotonic()-start,status='success',source='名将小助手',route='public_picker')
            return
        stage('清除上次搜索');set_search('')
        from .mini_dialogs import open_image_dialog
        dialog_hwnd=open_image_dialog(mini,lambda:click('📷 相册'),guard,deadline,stage,win32gui)
        dialog=Desktop(backend='win32').window(handle=dialog_hwnd).wrapper_object()
        connection.send({'event':'dialog','hwnd':dialog.handle})
        stage('等待文件输入框')
        edits=[]
        while time.monotonic()<deadline:
            guard()
            edits=[e for e in dialog.descendants(class_name='Edit') if e.is_visible()
                   and (e.control_id()==1148 or e.parent().control_id()==1148)]
            if len(edits)==1: break
            time.sleep(.05)
        if len(edits)!=1: raise RuntimeError('无法唯一定位文件名输入框')
        guard();edits[0].set_edit_text(str(path))
        # Submit to the verified Open button, not whichever edit currently has
        # keyboard focus (the shell may focus its Search box while loading).
        guard()
        if edits[0].window_text()!=str(path):raise RuntimeError('图片路径未写入文件名输入框')
        if dialog.handle not in image_dialogs(mini):raise RuntimeError('图片选择框已变化')
        win32gui.PostMessage(win32gui.GetDlgItem(dialog.handle,1),0xF5,0,0)  # BM_CLICK
        stage('确认图片选择框关闭')
        until=min(deadline,time.monotonic()+2)
        while win32gui.IsWindow(dialog.handle) and win32gui.IsWindowVisible(dialog.handle):
            guard()
            if time.monotonic()>=until:raise RuntimeError('图片选择框未完成导入，已取消本次查询')
            time.sleep(.05)
        stage('等待图片识别与结果')
        if image_only:
            read_only_results=True
            connection.send({'event':'input_complete'})
        stable_result=None;stable_since=0
        while manual_review or time.monotonic()<deadline:
            time.sleep(.15)
            guard()
            try:text=document()
            except (PageNotReady,COMError):
                if manual_review or read_only_results:continue
                raise
            if '以下位置需确认' in text:
                if image_only:
                    handoff('等待人工确认小程序中的待复核位置')
                    stable_result=None
                    continue
                correct_candidates();text=document()
            result=parse_document(text)
            if image_only:
                from .recommendations import validate_image_candidates
                from .ocr import Names
                image_error=validate_image_candidates(result['selected'],Names().names,expected)
                matched=image_error is None
            else:matched=set(result['selected'])==set(expected)
            if matched and (result['cards'] or result['no_result']):
                if manual_review:
                    key=json.dumps(result,ensure_ascii=False,sort_keys=True)
                    if key!=stable_result:stable_result=key;stable_since=time.monotonic();continue
                    if time.monotonic()-stable_since<1:continue
                result=collect_results(result)
                result.update(seconds=time.monotonic()-start, source='名将小助手',
                              status='success',original=original,mini=mini,manually_reviewed=manual_review)
                return
            if image_only and result['selected'] and (result['cards'] or result['no_result']):
                missing=sorted(set(expected)-set(result['selected']))
                handoff(image_error+('：'+'、'.join(missing) if missing else ''))
                stable_result=None
                continue  # Incomplete/unknown candidates still require human review.
            if not image_only and result['selected'] and set(result['selected'])!=set(expected):
                raise RuntimeError('导入候选与本地样本不一致')
        raise TimeoutError('配阵超时')
    except Exception as error:
        result={'status':'failed','error':str(error),'seconds':time.monotonic()-start}
    finally:
        # Never reclaim focus after a human input or a switch to another app.
        try:
            fg=win32gui.GetForegroundWindow()
            if not manual_review and (fg==mini or win32gui.GetAncestor(fg,3)==mini):
                # Includes a picker that appeared late, before its HWND could
                # be reported to the parent; do not leave the next query blocked.
                from .mini_dialogs import image_dialogs
                for pending in image_dialogs(mini):win32gui.PostMessage(pending,0x111,2,0)
                if win32gui.IsWindow(original) and not win32gui.IsIconic(original):
                    back=activate_window(original,mini,stopped)
                    stage('返回游戏：'+back.method+(' 成功' if back.ok else ' 失败'))
                    if result is not None:
                        result['returned_to_game']=back.ok
                        if not back.ok:result['return_error']=back.reason
        except Exception as error:
            if result is not None:result['return_error']=str(error)
        if result is not None: connection.send(result)



def worker(connection, path, expected, picker_only=False,physical_stop=None,bound_hwnd=None,game_hwnd=None,image_only=False,budget=15,deadline=None,read_existing=False,return_deadline=None):
    try:
        _worker(connection,path,expected,picker_only,physical_stop,bound_hwnd,game_hwnd,image_only,budget,deadline,read_existing,return_deadline)
    except Exception as error:
        try: connection.send({'status':'failed','error':'小程序连接失败：'+str(error)})
        except (OSError,EOFError): pass
    finally:
        connection.close()
