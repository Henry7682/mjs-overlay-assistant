"""Fresh public page queries; only the native window root is request-local."""


class WindowRoot:
    """Reuse the HWND root, never a page, control or text across UI actions.

    ElementFromHandle itself is a remote call and measured up to hundreds of
    milliseconds. Each query still locates its live descendants. Empty results
    discard the root; stale COM proxies get one fresh-root retry.
    """
    def __init__(self,create,retry_errors):
        self.create=create;self.retry_errors=retry_errors;self.root=None

    def query(self,lookup):
        for attempt in range(2):
            try:
                if self.root is None:self.root=self.create()
                result=lookup(self.root)
                if not result:self.root=None
                return result
            except self.retry_errors:
                self.root=None
                if attempt:raise


def find_page(root,ids,condition,uia=None):
    """Observed tree: window / AppIndex / pane / Page-Frame, all queried fresh."""
    wanted=condition(title='Page-Frame',control_type='Document')
    if uia is not None:
        # Build a NEW UIA snapshot for this read. Fetch its visibility and Text
        # interface in one provider roundtrip instead of several Current calls.
        # Nothing here survives the next UI action.
        try:
            request=uia.CreateCacheRequest()
            request.TreeScope=ids.TreeScope_Element
            request.AddProperty(ids.UIA_BoundingRectanglePropertyId)
            request.AddProperty(ids.UIA_IsOffscreenPropertyId)
            request.AddPattern(ids.UIA_TextPatternId)
            page=root.FindFirstBuildCache(ids.TreeScope_Descendants,wanted,request)
            if page:return page
        except Exception:pass
    index=root.FindFirst(ids.TreeScope_Children,condition(title='AppIndex',control_type='Document'))
    if index:
        direct=index.FindFirst(ids.TreeScope_Children,wanted)
        if direct:return direct
        panes=index.FindAll(ids.TreeScope_Children,condition(control_type='Pane'))
        for n in range(min(panes.Length,8)):
            page=panes.GetElement(n).FindFirst(ids.TreeScope_Children,wanted)
            if page:return page
        return index.FindFirst(ids.TreeScope_Descendants,wanted)
    return root.FindFirst(ids.TreeScope_Descendants,wanted)


def locate_control(root,ids,condition,title,kind=None,uia=None,optimized=False):
    """Fresh bulk document read with live fallback; other controls keep their route."""
    wanted=condition(title=title,control_type=kind)
    if not optimized:return root.FindFirst(ids.TreeScope_Descendants,wanted)
    page=find_page(root,ids,condition,uia)
    if title=='Page-Frame' and kind=='Document':return page
    if page:
        direct=page.FindFirst(ids.TreeScope_Children,wanted)
        if direct:return direct
    return root.FindFirst(ids.TreeScope_Descendants,wanted)


def picker_range(area):
    """Only catalogue after the album/footer/canvas; exclude chips and guides."""
    area=area.Clone()
    footer=area.FindText('相册',False,False)
    if not footer:raise RuntimeError('公开武将列表底栏不可确认')
    area.MoveEndpointByRange(0,footer,1)
    marker=area.FindText('绘图区域',False,False)
    if not marker:raise RuntimeError('公开武将列表边界不可确认')
    area.MoveEndpointByRange(0,marker,1)
    end=area.FindText('绘图区域',False,False)
    if end:area.MoveEndpointByRange(1,end,0)
    return area,footer


def result_range(area):
    """Selected chips and guides without search, filters or catalogue."""
    area=area.Clone()
    selected=area.FindText('已选武将（点击移除）',False,False)
    if not selected:raise RuntimeError('已选武将区域尚未就绪')
    area.MoveEndpointByRange(0,selected,0)
    footer=area.FindText('位置:',False,False)
    if not footer:raise RuntimeError('配阵结果底栏尚未就绪')
    area.MoveEndpointByRange(1,footer,0)
    return area


def result_text(text):
    """Narrow one freshly read string locally instead of eight remote range calls.

    This is a verification scope, not a cached response. Loading/incomplete pages
    keep the full evidence so the caller can distinguish failure and empty pools.
    """
    heading='已选武将（点击移除）'
    start=text.find(heading)
    end=text.find('位置:',start) if start>=0 else -1
    return text[start:end] if start>=0 and end>start else text
