# -*- coding: utf-8 -*-
"""桌面置顶提示悬浮窗（tkinter，单窗口）—— 建议显示 + AI 调参面板。

排版（分独立行，避免颜文字乱折行）：
    第 1 行 动作（含摸切/手切、吃碰杠的牌）
    第 2 行 颜文字
    第 3 行 补充（吃的排列 / 立直可打哪些牌），没有就收起
    第 4 行 向听数
    小  字 手牌/副露

右上角 ⚙ 折叠/展开调参面板（默认折叠，保持小巧）：
    探索概率 eps / 温度系数 temp / 核采样 top_p + 恢复默认
    拖动滑块实时写入同目录 ai_tuning.json；mortal_advisor.py 每局开头读一次生效。

交互：标题栏拖动、右下角 ◢ 调宽度（高度按内容自动）、[锁定穿透]/[解锁操作]
      鼠标穿透、透明度 50%~100%。窗口高度跟着内容自动走，折叠/展开不会留空。

只改显示层，不动主程序。主程序仍通过 queue.Queue 发
    {"kind": <动作>, "text": <主程序文本>, "hint": <手牌/副露>} 或 None(退出)。
"""
import ctypes
import json
import os
import queue
import re
import sys
import tkinter as tk


KIND_COLORS = {
    "dahai": "#FFFFFF",   # 打牌：白
    "chi":   "#7CFC00",   # 吃：亮绿
    "pon":   "#4FC3F7",   # 碰：蓝
    "kan":   "#FFB74D",   # 杠：橙
    "reach": "#FFEB3B",   # 立直：黄
    "hora":  "#FF5252",   # 和牌：红
    "none":  "#BDBDBD",   # 过：浅灰
    "info":  "#B0BEC5",
}

FONT_ACTION = ("Microsoft YaHei", 18, "bold")
FONT_KAOMOJI = ("Microsoft YaHei", 18, "bold")
FONT_EXTRA = ("Microsoft YaHei", 13, "bold")
FONT_SHANTEN = ("Microsoft YaHei", 14, "bold")
FONT_SUB = ("Microsoft YaHei", 11)
FONT_BAR = ("Microsoft YaHei", 10)
FONT_TUNE = ("Microsoft YaHei", 10)
FONT_HINT = ("Microsoft YaHei", 9)

BG = "#12161C"
BAR_BG = "#1B2430"
SET_BG = "#0F141A"
BAR_FG = "#CFD8DC"

DEFAULT_TUNING = {"eps": 0.15, "temp": 1.20, "top_p": 1.00}
TUNING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_tuning.json")


def _enable_dpi_awareness():
    """让窗口在高分屏上按真实像素渲染，避免系统缩放导致的模糊。"""
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _load_tuning():
    cfg = dict(DEFAULT_TUNING)
    try:
        with open(TUNING_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k in ("eps", "temp", "top_p"):
            if k in data:
                cfg[k] = float(data[k])
    except Exception:
        pass
    return cfg


def _save_tuning(cfg):
    try:
        data = {k: round(float(cfg[k]), 2) for k in ("eps", "temp", "top_p")}
        with open(TUNING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        print(f"[overlay] 写 ai_tuning.json 失败（忽略）: {ex}", flush=True)


def _extract(text):
    """从主程序文本里抽出：牌名 / 摸切手切 / 立的可打牌 / 向听数 / 吃的排列。"""
    tile = cut = cands = shanten = chi_hand = None
    m = re.search(r"\[建议打出\]\s*(\S+?)（(摸切|手切)）", text)
    if m:
        tile, cut = m.group(1), m.group(2)
    m = re.search(r"\[建议吃\]\s*用\s*(\S+?)\s*吃\s*(\S+)", text)
    if m:
        chi_hand, tile = m.group(1), m.group(2)
    else:
        for pat in (r"\[建议吃\][ \t]*([^\s\[]+)",
                    r"\[建议碰\][ \t]*([^\s\[]+)",
                    r"\[建议杠\][ \t]*([^\s\[]+)"):
            mm = re.search(pat, text)
            if mm:
                tile = mm.group(1)
                break
    mm = re.search(r"\[立直可打\]\s*(.+)", text)
    if mm:
        cands = mm.group(1).strip()
    mm = re.search(r"\[向听数\]\s*(-?\d+)", text)
    if mm:
        shanten = mm.group(1)
    return tile, cut, cands, shanten, chi_hand


def cute_lines(kind, text):
    """把主程序提示翻译成 [(角色, 文本)]；角色决定字号。"""
    tile, cut, cands, shanten, chi_hand = _extract(text)
    out = []
    if kind == "dahai":
        out.append(("action", f"建议打出 {tile}（{cut}）"))
        out.append(("kaomoji", "喵~ (≧∇≦)ﾉ"))
    elif kind == "chi":
        out.append(("action", f"吃喵！吃 {tile}" if tile else "吃喵！"))
        out.append(("kaomoji", "(๑´ڡ`๑)"))
        if chi_hand:
            out.append(("extra", f"用 {chi_hand}"))
    elif kind == "pon":
        out.append(("action", f"碰喵！碰 {tile}" if tile else "碰喵！"))
        out.append(("kaomoji", "(๑•̀ㅂ•́)و✧"))
    elif kind == "kan":
        out.append(("action", f"杠喵！杠 {tile}" if tile else "杠喵！"))
        out.append(("kaomoji", "(≧∇≦)ﾉ"))
    elif kind == "reach":
        out.append(("action", "立直喵！"))
        out.append(("kaomoji", "(ﾉ>ω<)ﾉ"))
        if cands and "高亮" not in cands:
            out.append(("extra", f"可以打出 {cands}"))
        else:
            out.append(("extra", "照着游戏高亮选一张打"))
    elif kind == "hora":
        out.append(("action", "主人 荣喵！"))
        out.append(("kaomoji", "٩(๑>◡<๑)۶"))
    elif kind == "none":
        out.append(("action", "过喵..."))
        out.append(("kaomoji", "(｡•́︿•̀｡)"))
    else:
        out.append(("action", text.replace("\n", "  ") if text else ""))
    if shanten is not None:
        out.append(("shanten", f"向听数 {shanten}"))
    return out


def cute_text(kind, text):
    """兼容旧用法：拼成一个字符串。"""
    return "\n".join(s for _role, s in cute_lines(kind, text) if s)


class Overlay:
    def __init__(self, msg_queue, alpha=0.85, width=560):
        self.q = msg_queue
        self.locked = False
        self.expanded = False
        self.alpha0 = alpha
        self.width = width
        self.x = int(os.environ.get("MORTAL_OVERLAY_X", "40"))
        self.y = int(os.environ.get("MORTAL_OVERLAY_Y", "40"))
        self.tuning = _load_tuning()
        self._drag = None
        self._resize = None
        self._bar_hover = False

        _enable_dpi_awareness()          # 必须在建 Tk 之前
        self.root = tk.Tk()
        self.root.title("Mortal 建议喵")
        self.root.overrideredirect(True)          # 无标题栏
        self.root.attributes("-topmost", True)    # 置顶
        self.root.attributes("-alpha", alpha)     # 半透明
        self.root.configure(bg=BG)

        self._build_bar()
        self._build_body()
        self._build_settings()
        self._build_grip()

        self._fit()
        self.root.update_idletasks()
        self._apply_lock()

    # ---------- 自适应大小 ----------
    def _fit(self):
        """宽度用 self.width，高度按内容自动（折叠/展开、补充行有无都能自适应）。"""
        try:
            self.root.update_idletasks()
            h = self.root.winfo_reqheight()
            self.root.geometry(f"{self.width}x{h}+{self.x}+{self.y}")
        except Exception:
            pass

    # ---------- 标题栏 ----------
    def _build_bar(self):
        bar = tk.Frame(self.root, bg=BAR_BG, height=30)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)
        self.bar = bar

        handle = tk.Label(bar, text=" ⣿ 建议喵 ", bg=BAR_BG, fg=BAR_FG,
                          font=FONT_BAR, cursor="fleur")
        handle.pack(side="left", padx=(6, 2))
        for w in (bar, handle):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._end_drag)

        self.lock_btn = tk.Button(
            bar, text="[锁定穿透]", command=self.toggle_lock,
            bg=BAR_BG, fg="#EF9A9A", font=FONT_BAR, relief="flat", bd=0,
            activebackground="#37474F", activeforeground="#FFFFFF",
            cursor="hand2", padx=6,
        )
        self.lock_btn.pack(side="left", padx=4)

        close_btn = tk.Button(
            bar, text="✕", command=self.stop, bg=BAR_BG, fg="#EF9A9A",
            font=FONT_BAR, relief="flat", bd=0, activebackground="#B71C1C",
            activeforeground="#FFFFFF", cursor="hand2", padx=6,
        )
        close_btn.pack(side="right", padx=(2, 6))

        self.gear_btn = tk.Button(
            bar, text="⚙", command=self.toggle_settings,
            bg=BAR_BG, fg="#90CAF9", font=FONT_BAR, relief="flat", bd=0,
            activebackground="#37474F", activeforeground="#FFFFFF",
            cursor="hand2", padx=6,
        )
        self.gear_btn.pack(side="right", padx=2)

        self.alpha_var = tk.DoubleVar(value=self.alpha0 * 100)
        tk.Scale(
            bar, from_=50, to=100, orient="horizontal", variable=self.alpha_var,
            command=self._on_alpha, bg=BAR_BG, fg=BAR_FG, troughcolor="#37474F",
            highlightthickness=0, bd=0, sliderrelief="flat", length=80,
            font=FONT_BAR, showvalue=False,
        ).pack(side="right", padx=(2, 4))
        tk.Label(bar, text="透明度", bg=BAR_BG, fg="#90A4AE",
                 font=FONT_BAR).pack(side="right")

    # ---------- 建议正文 ----------
    def _build_body(self):
        wrap = max(120, self.width - 44)
        self.l_action = tk.Label(
            self.root, text="麻将建议喵", justify="left", anchor="w",
            font=FONT_ACTION, fg="#FFFFFF", bg=BG, padx=18, pady=12,
            wraplength=wrap,
        )
        self.l_action.pack(fill="x")

        self.l_kaomoji = tk.Label(
            self.root, text="（等待对局…）", justify="left", anchor="w",
            font=FONT_KAOMOJI, fg="#FFFFFF", bg=BG, padx=18, pady=0,
            wraplength=wrap,
        )
        self.l_kaomoji.pack(fill="x")

        self.l_extra = tk.Label(
            self.root, text="", justify="left", anchor="w",
            font=FONT_EXTRA, fg="#B0BEC5", bg=BG, padx=18, pady=1,
            wraplength=wrap,
        )
        self.l_extra.pack(fill="x")

        self.l_shanten = tk.Label(
            self.root, text="", justify="left", anchor="w",
            font=FONT_SHANTEN, fg="#B0BEC5", bg=BG, padx=18, pady=1,
            wraplength=wrap,
        )
        self.l_shanten.pack(fill="x")

        self.status = tk.Label(
            self.root, text="", justify="left", anchor="sw", font=FONT_SUB,
            fg="#8FA8B8", bg=BG, padx=18, pady=6, wraplength=wrap,
        )
        self.status.pack(fill="x", side="bottom")

    # ---------- 调参面板 ----------
    def _build_settings(self):
        self.settings = tk.Frame(self.root, bg=SET_BG)
        self.vars = {}
        self.val_labels = {}
        tk.Label(self.settings, text="AI 调参（下一局生效）", bg=SET_BG,
                 fg="#90A4AE", font=FONT_TUNE, anchor="w").pack(
            fill="x", padx=14, pady=(6, 0))

        self.var_eps = self._add_slider(
            "探索概率 eps", "eps", 0.0, 0.50, 0.01,
            "0 = 绝对理性，0.5 = 一半概率乱打")
        self.var_temp = self._add_slider(
            "温度系数 temp", "temp", 0.10, 2.00, 0.10,
            "越大越随机（1.2 温和，2.0 很飘）")
        self.var_topp = self._add_slider(
            "核采样 top_p", "top_p", 0.10, 1.00, 0.05,
            "1.0 = 全考虑，越小越保守")

        tk.Button(
            self.settings, text="恢复默认 (0.15 / 1.20 / 1.00)",
            command=self.restore_defaults, bg="#263238", fg="#CFD8DC",
            font=FONT_TUNE, relief="flat", bd=0, activebackground="#37474F",
            activeforeground="#FFFFFF", cursor="hand2",
        ).pack(fill="x", padx=14, pady=(8, 10))

    def _add_slider(self, label, key, frm, to, step, hint):
        row = tk.Frame(self.settings, bg=SET_BG)
        row.pack(fill="x", padx=14, pady=(8, 0))
        tk.Label(row, text=label, bg=SET_BG, fg="#CFD8DC",
                 font=FONT_TUNE).pack(side="left")
        val = tk.Label(row, text=f"{self.tuning[key]:.2f}", bg=SET_BG,
                       fg="#FFEB3B", font=FONT_TUNE, width=5, anchor="e")
        val.pack(side="right")
        self.val_labels[key] = val

        var = tk.DoubleVar(value=self.tuning[key])
        self.vars[key] = var

        def on_change(*_a, _key=key):
            try:
                fv = round(float(self.vars[_key].get()), 2)
            except Exception:
                return
            self.tuning[_key] = fv
            self.val_labels[_key].config(text=f"{fv:.2f}")
            _save_tuning(self.tuning)

        # 用变量的 trace 而不是 Scale 的 command：这样 set() 也会触发（恢复默认要用到），
        # 拖动滑块时同样会触发。
        var.trace_add("write", on_change)

        # 注意：滑块只在 settings 这一层，没有绑定窗口拖动事件，
        # 所以拖滑块不会把整个窗口一起拖走。
        tk.Scale(
            self.settings, from_=frm, to=to, resolution=step, orient="horizontal",
            variable=var, showvalue=False,
            bg=SET_BG, fg="#CFD8DC", troughcolor="#37474F",
            highlightthickness=0, bd=0, sliderrelief="flat",
        ).pack(fill="x", padx=14)
        tk.Label(self.settings, text=hint, bg=SET_BG, fg="#78909C",
                 font=FONT_HINT, anchor="w").pack(fill="x", padx=16)
        return var

    def toggle_settings(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.settings.pack(fill="x", side="top")
            self.gear_btn.config(text="⚙ 收起")
        else:
            self.settings.pack_forget()
            self.gear_btn.config(text="⚙")
        self._fit()

    def restore_defaults(self):
        for key in ("eps", "temp", "top_p"):
            self.tuning[key] = DEFAULT_TUNING[key]
            self.vars[key].set(DEFAULT_TUNING[key])
            self.val_labels[key].config(text=f"{DEFAULT_TUNING[key]:.2f}")
        _save_tuning(self.tuning)
        self._fit()

    # ---------- 右下缩放把手（调宽度；高度自动）----------
    def _build_grip(self):
        self.grip = tk.Label(self.root, text="◢", bg=BG, fg="#78909C",
                             font=FONT_SUB, cursor="size_nw_se")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<ButtonPress-1>", self._start_resize)
        self.grip.bind("<B1-Motion>", self._on_resize)
        self.grip.bind("<ButtonRelease-1>", self._end_resize)

    def _hwnd(self):
        try:
            return ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        except Exception:
            return None

    def _set_click_through(self, on):
        if not sys.platform.startswith("win"):
            return
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            gwl_exstyle = -20
            ws_ex_layered = 0x00080000
            ws_ex_transparent = 0x00000020
            ws_ex_toolwindow = 0x00000080
            style = user32.GetWindowLongW(hwnd, gwl_exstyle)
            style |= ws_ex_layered | ws_ex_toolwindow
            style = (style | ws_ex_transparent) if on else (style & ~ws_ex_transparent)
            user32.SetWindowLongW(hwnd, gwl_exstyle, style)
        except Exception as ex:
            print(f"[overlay] 设置穿透失败（忽略）: {ex}", flush=True)

    def _apply_lock(self):
        self.lock_btn.config(
            text="[解锁操作]" if self.locked else "[锁定穿透]",
            fg="#FFCC80" if self.locked else "#EF9A9A",
        )
        self._set_click_through(self.locked)

    def toggle_lock(self):
        self.locked = not self.locked
        self._apply_lock()
        print(f"[overlay] {'锁定（鼠标穿透）' if self.locked else '解锁（可拖动/缩放）'}", flush=True)

    # ---------- 拖动 ----------
    def _start_drag(self, e):
        if self.locked:
            return
        self._drag = (e.x_root - self.x, e.y_root - self.y)

    def _on_drag(self, e):
        if self.locked or not self._drag:
            return
        dx, dy = self._drag
        self.x = e.x_root - dx
        self.y = e.y_root - dy
        self._fit()

    def _end_drag(self, _e):
        self._drag = None

    # ---------- 缩放 ----------
    def _start_resize(self, e):
        if self.locked:
            return
        self._resize = (e.x_root, self.width)

    def _on_resize(self, e):
        if self.locked or not self._resize:
            return
        x0, w0 = self._resize
        self.width = max(380, w0 + (e.x_root - x0))
        wrap = max(120, self.width - 44)
        for lbl in (self.l_action, self.l_kaomoji, self.l_extra,
                    self.l_shanten, self.status):
            lbl.config(wraplength=wrap)
        self._fit()

    def _end_resize(self, _e):
        self._resize = None

    def _on_alpha(self, value):
        try:
            self.root.attributes("-alpha", max(0.50, min(1.0, float(value) / 100.0)))
        except Exception:
            pass

    def _poll_cursor(self):
        """锁定穿透时，鼠标移到标题栏上临时恢复可点击，避免锁死解不开。
        只读坐标 + 改扩展样式，不碰 Windows 消息队列。"""
        if self.locked and sys.platform.startswith("win"):
            try:
                import ctypes.wintypes as wt
                pt = wt.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                x = self.root.winfo_rootx()
                y = self.root.winfo_rooty()
                w = self.root.winfo_width()
                h = self.bar.winfo_height() + 8
                over = (x <= pt.x <= x + w) and (y <= pt.y <= y + h)
                if over != self._bar_hover:
                    self._bar_hover = over
                    self._set_click_through(not over)
            except Exception:
                pass
        self.root.after(120, self._poll_cursor)

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg is None:
                    self.stop()
                    return
                self._apply(msg)
        except queue.Empty:
            pass
        except Exception as ex:
            print(f"[overlay] 刷新出错（忽略）: {ex}", flush=True)
        try:
            self.root.after(100, self._poll)
        except Exception:
            pass

    def _apply(self, msg):
        kind = msg.get("kind", "info")
        color = KIND_COLORS.get(kind, "#FFFFFF")
        slots = {"action": "", "kaomoji": "", "extra": "", "shanten": ""}
        for role, s in cute_lines(kind, msg.get("text", "")):
            if role in slots:
                slots[role] = s
        self.l_action.config(text=slots["action"], fg=color)
        self.l_kaomoji.config(text=slots["kaomoji"], fg=color)
        self.l_extra.config(text=slots["extra"])
        self.l_shanten.config(text=slots["shanten"], fg=color)
        # extra 没内容时收起来，避免多出一行空白
        if slots["extra"]:
            if self.l_extra.winfo_manager() != "pack":
                self.l_extra.pack(fill="x", before=self.l_shanten)
        else:
            self.l_extra.pack_forget()
        hint = msg.get("hint")
        if hint is not None:
            self.status.config(text=hint)
        self._fit()

    def run(self):
        self.root.after(100, self._poll)
        self.root.after(120, self._poll_cursor)
        self.root.after(300, self._apply_lock)     # 窗口映射后再确保一次
        try:
            self.root.bind_all("<Control-Alt-l>", lambda _e: self.toggle_lock())
            self.root.bind_all("<Control-Alt-L>", lambda _e: self.toggle_lock())
        except Exception:
            pass
        self.root.mainloop()

    def stop(self):
        try:
            self.root.destroy()
        except Exception:
            pass
