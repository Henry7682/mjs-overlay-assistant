import sys
import multiprocessing
if __name__=='__main__':
    multiprocessing.freeze_support()
    from mjs_assistant.windows_compat import runtime_issue
    issue=runtime_issue()
    if issue:
        import ctypes
        if '--smoke' not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None,issue,'名将浮窗助手：系统组件检查',0x10)
        raise SystemExit(issue)
if '--capture-check' in sys.argv:
    from tools.capture_check import run
    raise SystemExit(run(sys.argv[sys.argv.index('--capture-check')+1]))
if '--focus-check' in sys.argv:
    from tools.probe_focus_roundtrip import run
    run(sys.argv[sys.argv.index('--focus-check')+1], '--exercise-bridge' in sys.argv)
    raise SystemExit(0)
if '--worker-smoke' in sys.argv:
    from tools.portable_worker_smoke import run
    run(sys.argv[sys.argv.index('--worker-smoke')+1])
    raise SystemExit(0)
if '--replay-mini' in sys.argv:
    # Explicit local diagnostic with reviewed samples; never runs at startup.
    sys.argv.remove('--replay-mini')
    from tools.replay_provider import main as replay_main
    replay_main()
    raise SystemExit(0)
if '--smoke' in sys.argv:
    from tools.smoke import run
    i=sys.argv.index('--smoke')
    run(sys.argv[i+1],sys.argv[i+2] if len(sys.argv)>i+2 else None)
    raise SystemExit(0)
from mjs_assistant.app import main
if __name__=='__main__':sys.exit(main())
