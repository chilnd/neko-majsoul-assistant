# -*- coding: utf-8 -*-
"""静默启动包装器：把日志重定向到 run_log.txt，再跑 main.py。

为什么需要它：
    用 pythonw.exe 启动时没有控制台，sys.stdout / sys.stderr 是 None，
    任何 print 都会报错；而且 libriichi 的 Rust panic 走的是系统 stderr。
    这里把 Python 层和系统层（fd 1/2）一起重定向到日志文件，
    这样窗口隐藏了也还能打开 run_log.txt 排查。

注意：本文件不改动 main.py / liqi_parser.py，只是“外面套一层”。

用法（由启动器调用）：
    pythonw run_headless.py        # pythonw.exe 没有控制台，日志见 run_log.txt
"""
import os
import sys
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "run_log.txt")
LOG_PREV = os.path.join(HERE, "run_log.old.txt")
LOG_MAX_BYTES = 2 * 1024 * 1024        # 超过 2MB 就转存一份旧的


def _rotate_if_big():
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            if os.path.exists(LOG_PREV):
                os.remove(LOG_PREV)
            os.replace(LOG_PATH, LOG_PREV)
    except Exception:
        pass


def main():
    _rotate_if_big()
    log = open(LOG_PATH, "a", encoding="utf-8", buffering=1, errors="replace")

    # 系统层重定向：Rust panic、以及子进程写到 fd1/fd2 的内容都会进日志
    try:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    except Exception:
        pass
    # Python 层重定向：pythonw 下这两个本来是 None，不换掉的话 print 会报错
    sys.stdout = log
    sys.stderr = log

    print(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} 启动 =====", flush=True)
    print(f"python : {sys.executable}", flush=True)
    print(f"script : {os.path.join(HERE, 'main.py')}", flush=True)
    print(f"cwd    : {os.getcwd()}", flush=True)

    code = 0
    try:
        sys.path.insert(0, HERE)
        import main as app
        app.main()
    except KeyboardInterrupt:
        print("===== 收到 Ctrl+C，退出 =====", flush=True)
    except BaseException:
        code = 1
        print("===== 出错了，下面是详细堆栈 =====", flush=True)
        traceback.print_exc()
    else:
        print("===== 已正常退出 =====", flush=True)
    finally:
        try:
            print(f"===== {datetime.now():%Y-%m-%d %H:%M:%S} 结束 =====", flush=True)
            log.flush()
        except Exception:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
