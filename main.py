# -*- coding: utf-8 -*-
"""实时截流主程序：Playwright 抓雀魂 WebSocket 帧 -> 翻译 mjai -> Mortal 建议。

运行：
    python main.py        # 先按 README 配好环境，并把 config.example.py 复制成 config.py

线程模型（重要）：
    - 主线程：跑 tkinter 置顶悬浮窗（Tk 只能在它被创建的线程里操作）。
    - 后台线程：跑 Playwright 抓包 + Mortal 决策，把建议塞进 queue.Queue。
    - 主线程用 root.after(100, ...) 轮询队列再刷新界面，
      绝不跨线程直接改 Tk 控件。

环境变量：
    MORTAL_DEBUG=1        打开控制台详细日志（[liqi]/[feed]/[CPG]）
    MORTAL_OVERLAY_X/Y    悬浮窗位置（默认左上角 24,24）
    MORTAL_NO_OVERLAY=1   只跑控制台，不开悬浮窗
"""
import json
import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from liqi_parser import LiqiGame
from tiles import tile_cn as cn


MAJSOUL_URL = "https://game.maj-soul.com/1/"

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import config as cfg
except ImportError as exc:          # 还没复制 config.example.py -> config.py
    raise SystemExit(
        "缺少 config.py：请先复制 config.example.py 为 config.py，"
        "并按其中的说明填写 MORTAL_DIR / MS_API_DIR / ACTION_XOR_KEYS。"
    ) from exc

# 浏览器持久化目录（自动创建）
PROFILE_DIR = getattr(cfg, "BROWSER_PROFILE", "") or os.path.join(HERE, "browser_profile")
DEBUG = os.environ.get("MORTAL_DEBUG", "0") == "1"


def format_suggestion(r, game):
    """把 Mortal 的反应转成 (多行文本, 颜色类别)。"""
    typ = r.get("type")
    pai = r.get("pai")
    tsumogiri = r.get("tsumogiri", False)
    meta = r.get("meta") or {}
    shanten = meta.get("shanten")
    lines = []

    if typ == "dahai":
        kind = "dahai"
        cut = "摸切" if tsumogiri else "手切"
        lines.append(f"[建议打出] {cn(pai)}（{cut}）")
    elif typ == "reach":
        kind = "reach"
        lines.append("[建议立直]")
        cands = game.riichi_discard_candidates()
        if cands:
            lines.append("[立直可打] " + " / ".join(cands))
        else:
            lines.append("[立直可打] 以游戏高亮为准")
    elif typ == "chi":
        kind = "chi"
        # Mortal 的吃会给出「叫的牌 pai + 手上出的 consumed」，一并显示，
        # 好让你在游戏里“请选择要吃的牌”时知道该选哪种排列。
        consumed = [cn(t) for t in (r.get("consumed") or [])]
        if consumed:
            lines.append(f"[建议吃] 用 {'·'.join(consumed)} 吃 {cn(pai)}")
        else:
            lines.append(f"[建议吃] {cn(pai)}")
    elif typ == "pon":
        kind = "pon"
        lines.append(f"[建议碰] {cn(pai)}")
    elif typ in ("daiminkan", "kakan", "ankan"):
        kind = "kan"
        tile = r.get("pai")
        lines.append(f"[建议杠] {cn(tile)}" if tile else "[建议杠]")
    elif typ == "hora":
        kind = "hora"
        lines.append("[建议和牌！]")
    elif typ == "none":
        kind = "none"
        lines.append("[不叫牌]")
    else:
        kind = "info"
        lines.append(f"[{typ}]")

    if shanten is not None:
        lines.append(f"[向听数] {shanten}")
    return "\n".join(lines), kind


class Session:
    def __init__(self):
        self.game = LiqiGame()
        self.advisor = None
        self.advisor_loading = False
        self.advisor_seat = None
        self.ui_queue = queue.Queue()
        self.stop_event = threading.Event()
        self._diag_count = 0
        self._unknown_count = 0
        self._feed_diag_count = 0

    # ---- 日志 ----
    def _log(self, text):
        print(text, flush=True)

    # ---- WebSocket 回调（在后台线程里被 Playwright 调用）----
    def on_frame(self, payload):
        if isinstance(payload, (bytes, bytearray)):
            self._process(bytes(payload))

    def on_frame_sent(self, payload):
        if isinstance(payload, (bytes, bytearray)):
            self._process(bytes(payload))

    def _process(self, frame):
        try:
            self._process_inner(frame)
        except BaseException as ex:
            self._log(f"[!] 处理帧异常（已忽略，避免闪退）: {ex}")

    def _process_inner(self, frame):
        events, notes = self.game.feed_frame(frame)
        for note in notes:
            is_diag = (note.startswith("BAD") or note.startswith("NO_CLS")
                       or note.startswith("empty") or note.startswith("parse_error")
                       or note.startswith("ActionPrototype"))
            if is_diag:
                self._unknown_count += 1
                if self._unknown_count <= 25:
                    self._log(f"  [diag] {note}")
            elif DEBUG and self._diag_count < 60:
                self._log(f"  [liqi] {note}")
            self._diag_count += 1
        if not events:
            return

        # 座位确定后加载 Mortal；如果座位变了（换了一局）必须重建，
        # 否则 Mortal 会去读 tehais[旧座位]（全是 '?'）而直接报错。
        seat = self.game.self_seat
        if seat is not None and seat in range(4):
            if self.advisor is None and not self.advisor_loading:
                self.advisor_loading = True
                self._log(f"[*] 检测到自己的座位 seat={seat}，加载 Mortal 模型 ...")
                from mortal_advisor import MortalAdvisor
                self.advisor = MortalAdvisor(seat)
                self.advisor_seat = seat
                self._log("[*] Mortal 模型加载完成，开始给建议。")
            elif self.advisor is not None and seat != self.advisor_seat:
                self._log(f"[!] 座位由 {self.advisor_seat} 变为 {seat}，重建 Mortal ...")
                from mortal_advisor import MortalAdvisor
                self.advisor = MortalAdvisor(seat)
                self.advisor_seat = seat
                self._log("[*] Mortal 重建完成，继续给建议。")

        for ev in events:
            self._feed_mortal(ev)

    def _feed_mortal(self, ev):
        if self.advisor is None:
            return
        reason = self._unknown_tile_reason(ev)
        if reason:
            # 这种情况很关键（整轮可能因此丢状态），一直打出来。
            self._log(f"[warn] 跳过含未知牌的事件 {ev.get('type')}: {reason}")
            return
        line = json.dumps(ev, ensure_ascii=False)
        if (DEBUG
                and ev.get("type") in ("pon", "chi", "daiminkan", "ankan",
                                       "kakan", "dahai", "tsumo")
                and self._feed_diag_count < 120):
            self._log(f"[feed] {ev.get('type')} actor={ev.get('actor')} "
                      f"pai={ev.get('pai')} consumed={ev.get('consumed')}")
            self._feed_diag_count += 1
        try:
            reaction = self.advisor.react(line)
        except BaseException as ex:
            self._log(f"[!] Mortal 处理事件失败: {ex}")
            return
        if reaction:
            self._show(reaction)

    def _unknown_tile_reason(self, ev):
        """若事件含 Mortal 无法处理的未知牌 '?'，返回原因字符串；否则 None。"""
        if ev.get("dora_marker") == "?":
            return "dora_marker=?"
        if ev.get("type") == "start_kyoku":
            seat = self.game.self_seat
            tehais = ev.get("tehais") or []
            if seat in range(4) and seat < len(tehais):
                if any(t == "?" for t in tehais[seat]):
                    return f"自己的起手牌里有未知牌 {tehais[seat]}"
        if ev.get("actor") == self.game.self_seat and ev.get("pai") == "?":
            return "自己的摸牌/出牌是未知牌"
        if ev.get("actor") == self.game.self_seat:
            for c in (ev.get("consumed") or []):
                if c == "?":
                    return f"自己的副露里有未知牌 {ev.get('consumed')}"
        return None

    def _show(self, reaction_json):
        try:
            r = json.loads(reaction_json)
        except Exception:
            self._emit("info", f"建议: {reaction_json}")
            return
        text, kind = format_suggestion(r, self.game)
        self._emit(kind, text)

    def _emit(self, kind, text):
        # 控制台（压成一行）
        self._log("  >>> " + text.replace("\n", "   "))
        if DEBUG:
            self._log("      " + self.game.my_hand_str())
        # 悬浮窗（多行 + 底部手牌提示，方便核对“打的牌到底在不在手里”）
        self.ui_queue.put({"kind": kind, "text": text, "hint": self.game.my_hand_str()})


# ---- 后台线程：Playwright ----
def browser_worker(session):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False,
                viewport={"width": 1440, "height": 900},
                args=["--ignore-certificate-errors"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()

            def on_websocket(ws):
                ws.on("framereceived", session.on_frame)
                ws.on("framesent", session.on_frame_sent)

            page.on("websocket", on_websocket)

            session._log("[*] 正在打开雀魂网页版 ...")
            page.goto(MAJSOUL_URL, wait_until="domcontentloaded")
            session._log("[*] 请在浏览器窗口里登录，然后进入友人房、和 CPU 开始对局。")
            session._log("[*] 对局开始后，建议会显示在左上角的悬浮窗里（同时也打印在这）。")

            while not session.stop_event.is_set():
                page.wait_for_timeout(1000)
            try:
                browser.close()
            except Exception:
                pass
    except BaseException as ex:
        session._log(f"[!] 浏览器线程异常退出: {ex}")
    finally:
        session.stop_event.set()
        session.ui_queue.put({"kind": "info", "text": "浏览器已退出\n（可关闭本窗口）"})
        time.sleep(2.0)
        session.ui_queue.put(None)   # 让主线程的悬浮窗自己关掉


def run_console_loop(session):
    """不开悬浮窗时的兜底：主线程就等后台线程结束。"""
    try:
        while not session.stop_event.is_set():
            session.stop_event.wait(1.0)
    except KeyboardInterrupt:
        session.stop_event.set()


def main():
    session = Session()
    worker = threading.Thread(target=browser_worker, args=(session,), daemon=True)
    worker.start()

    if os.environ.get("MORTAL_NO_OVERLAY", "0") == "1":
        run_console_loop(session)
        return

    try:
        from overlay import Overlay
        overlay = Overlay(session.ui_queue)
    except Exception as ex:
        print(f"[!] 悬浮窗初始化失败，退回控制台模式: {ex}", flush=True)
        run_console_loop(session)
        return

    try:
        overlay.run()          # 主线程跑 Tk 事件循环
    except KeyboardInterrupt:
        pass
    finally:
        session.stop_event.set()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
