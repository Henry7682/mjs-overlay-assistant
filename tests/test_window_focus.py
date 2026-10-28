from mjs_assistant.window_focus import activate_window


class FakeWindows:
    def __init__(self, direct=False, bridge=True):
        self.fg=1;self.direct=direct;self.bridge=bridge;self.events=[]
    def foreground(self):return self.fg
    def exists(self,hwnd):return True
    def related(self,hwnd,owner):return hwnd==owner
    def pump(self):pass
    def request(self,hwnd):
        self.events.append(('request',hwnd))
        if self.direct or (self.fg==3 and self.bridge):self.fg=hwnd
    def create_bridge(self,source):self.events.append(('create',3));return 3
    def click_bridge(self,hwnd,stopped):
        if stopped():return False
        self.events.append(('click',hwnd));self.fg=hwnd;return True
    def destroy(self,hwnd):self.events.append(('destroy',hwnd))


def test_direct_requires_verified_foreground():
    api=FakeWindows(direct=True)
    result=activate_window(2,1,api=api)
    assert result.ok and result.method=='direct'
    assert api.events==[('request',2)]


def test_refusal_uses_only_own_bridge_and_cleans_up():
    api=FakeWindows()
    result=activate_window(2,1,api=api)
    assert result.ok and result.method=='bridge' and api.fg==2
    assert [e for e in api.events if e[0]=='click']==[('click',3)]
    assert api.events[-1]==('destroy',3)


def test_other_app_and_physical_input_prevent_activation():
    api=FakeWindows();api.fg=4
    assert not activate_window(2,1,api=api).ok
    assert not api.events
    api.fg=1
    assert not activate_window(2,1,lambda:True,api=api).ok
    assert not api.events


def test_bridge_failure_never_claims_success():
    api=FakeWindows(bridge=False)
    result=activate_window(2,1,api=api)
    assert not result.ok and api.events[-1]==('destroy',3)


def test_switching_to_other_app_during_bridge_stops_target_request():
    api=FakeWindows()
    def create(source):api.fg=4;return 3
    api.create_bridge=create
    assert not activate_window(2,1,api=api).ok
    assert api.events==[('request',2),('destroy',3)]


def test_transient_empty_foreground_is_not_user_intervention():
    api=FakeWindows()
    def click(hwnd,stopped):
        api.fg=0
        assert not stopped()
        api.fg=hwnd
        return True
    api.click_bridge=click
    assert activate_window(2,1,api=api).ok


def test_empty_foreground_before_request_is_not_permission():
    api=FakeWindows();api.fg=0
    assert not activate_window(2,1,api=api).ok
    assert not api.events
