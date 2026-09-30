# -*- coding: utf-8 -*-
"""解析雀魂 WebSocket 帧（Liqi 协议），翻译成 Mortal 需要的 mjai 事件流。"""
import base64
import os
import sys

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

if cfg.MS_API_DIR:
    sys.path.insert(0, cfg.MS_API_DIR)

import ms.protocol_pb2 as pb

from tiles import (
    tile_str_to_mjai,
    tile_str_to_mjai_list,
    chang_to_bakaze,
    tile_cn,
)
from riichi import tenpai_discards


# 诊断输出（[CPG] 之类）默认关闭，设 MORTAL_DEBUG=1 打开
_DEBUG = os.environ.get("MORTAL_DEBUG", "0") == "1"


# ActionPrototype.data 的 XOR 混淆密钥，在 config.py 中配置。
_ACTION_KEYS = list(getattr(cfg, "ACTION_XOR_KEYS", []) or [])


def _decode_action_bytes(buf: bytes) -> bytearray:
    """对 ActionPrototype.data 做 XOR 解密，还原内层 protobuf 二进制。"""
    keys = _ACTION_KEYS
    if not keys:
        raise RuntimeError("ACTION_XOR_KEYS 尚未配置：请在 config.py 中填写。")
    decode = bytearray()
    for i, _byte in enumerate(buf):
        mask = ((23 ^ len(buf)) + 5 * i + keys[i % len(keys)]) & 255
        decode.append(_byte ^ mask)
    return decode


def _looks_like_base64(data: bytes) -> bool:
    """原始字节是否长得像 base64 ASCII（用于区分实时帧里 data 的两种形态）。"""
    if not data:
        return False
    alphabet = frozenset(
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    )
    return all(b in alphabet for b in data)


class LiqiGame:
    """把实时 Liqi 消息流翻译成 mjai 事件流。"""

    def __init__(self, self_seat=None):
        self.self_seat = self_seat
        self.account_id = None
        self.seat_list = []
        self._pending_requests = {}
        self.bakaze = "E"
        self.kyoku = 1
        self.honba = 0
        self.kyotaku = 0
        self.scores = [25000, 25000, 25000, 25000]
        self.dora_indicators = []
        self.my_tehai = []
        self.my_ankan_count = 0
        self.my_melds = []
        self.last_tsumo = None
        self._started_game = False
        self._started_kyoku = False

    def feed_frame(self, frame: bytes):
        """处理一个 WebSocket 二进制帧，返回 (mjai_events, notes)。"""
        if not frame:
            return [], ["empty_frame"]
        type_byte = frame[0]
        if type_byte == 1:
            return self._handle_notify(frame[1:])
        if type_byte == 2:
            return self._handle_request(frame[1:])
        if type_byte == 3:
            return self._handle_response(frame[1:])
        return [], [f"BAD type={type_byte} len={len(frame)} hex={frame[:16].hex()}"]

    @staticmethod
    def _parse_wrapper(payload):
        wrapper = pb.Wrapper()
        try:
            wrapper.ParseFromString(payload)
        except Exception:
            return None
        return wrapper

    def _handle_notify(self, payload):
        wrapper = self._parse_wrapper(payload)
        if wrapper is None:
            return [], ["BAD notify parse"]
        name = wrapper.name or ""
        short = name.rsplit(".", 1)[-1]
        cls = getattr(pb, short, None)
        if cls is None:
            return [], [f"NO_CLS name='{name}' hex={payload[:16].hex()}"]
        msg = cls()
        try:
            msg.ParseFromString(wrapper.data)
        except Exception:
            return [], [f"parse_error:{short}"]
        return self._handle(short, msg)

    def _handle_request(self, payload):
        if len(payload) < 3:
            return [], ["BAD request short"]
        idx = int.from_bytes(payload[0:2], "little")
        wrapper = self._parse_wrapper(payload[2:])
        if wrapper is None:
            return [], [f"BAD request parse idx={idx}"]
        method = (wrapper.name or "").rsplit(".", 1)[-1]
        self._pending_requests[idx] = method
        return [], [f"REQ {method} idx={idx}"]

    def _handle_response(self, payload):
        if len(payload) < 3:
            return [], ["BAD response short"]
        idx = int.from_bytes(payload[0:2], "little")
        wrapper = self._parse_wrapper(payload[2:])
        if wrapper is None:
            return [], [f"BAD response parse idx={idx}"]
        method = self._pending_requests.pop(idx, None)
        if method in ("oauth2Login", "login"):
            msg = pb.ResLogin()
            try:
                msg.ParseFromString(wrapper.data)
            except Exception:
                return [], [f"RES {method} parse_error idx={idx}"]
            if msg.account_id:
                self.account_id = msg.account_id
            return [], [f"RES {method} account_id={self.account_id}"]
        if method == "authGame":
            msg = pb.ResAuthGame()
            try:
                msg.ParseFromString(wrapper.data)
            except Exception:
                return [], [f"RES authGame parse_error idx={idx}"]
            return self._handle("ResAuthGame", msg)
        return [], [f"RES {method} idx={idx}"]

    def _handle(self, short, msg):
        # 单个事件里任何一个字段/解析出错，都不应该把整个事件悄悄丢掉，
        # 更不能让异常冒到 Playwright 那边。这里兜住并打出来。
        try:
            return self._dispatch(short, msg)
        except Exception as ex:
            print(f"[warn] 处理 {short} 出错，已跳过该事件: {ex!r}", flush=True)
            return [], [f"handler_error:{short}"]

    def _dispatch(self, short, msg):
        events = []
        notes = [short]
        if short == "ActionPrototype":
            return self._handle_action_prototype(msg)
        if short == "ResAuthGame":
            self.seat_list = list(msg.seat_list)
            if self.account_id is not None and self.account_id in self.seat_list:
                self.self_seat = self.seat_list.index(self.account_id)
                print(
                    f"[*] 座位已确定 seat={self.self_seat} "
                    f"account_id={self.account_id} seat_list={self.seat_list}",
                    flush=True,
                )
            else:
                print(
                    f"[!] 无法确定座位 account_id={self.account_id} "
                    f"seat_list={self.seat_list}",
                    flush=True,
                )
            notes.append(f"self_seat={self.self_seat}")
            return events, notes
        if short == "ActionNewRound":
            events += self._on_new_round(msg)
            return events, notes
        if short == "ActionDealTile":
            events += self._on_deal_tile(msg)
            return events, notes
        if short == "ActionDiscardTile":
            events += self._on_discard_tile(msg)
            return events, notes
        if short == "ActionChiPengGang":
            events += self._on_chi_peng_gang(msg)
            return events, notes
        if short == "ActionAnGangAddGang":
            events += self._on_an_gang_add_gang(msg)
            return events, notes
        if short == "ActionHule":
            events += self._on_hule(msg)
            return events, notes
        if short in ("ActionLiuJu", "ActionNoTile"):
            events += self._on_ryukyoku(msg)
            return events, notes
        return events, notes

    def _handle_action_prototype(self, msg):
        """解开 ActionPrototype{name, data}，data 可能是原始 XOR 字节或 base64 后再 XOR。"""
        inner_name = msg.name or ""
        inner_short = inner_name.rsplit(".", 1)[-1]
        inner_cls = getattr(pb, inner_short, None)
        if inner_cls is None:
            return [], [f"ActionPrototype unknown inner '{inner_name}'"]

        data = msg.data
        if not data:
            # ActionMJStart 之类本来就没有 payload，属正常，不必当异常刷屏。
            if inner_short in ("ActionMJStart",):
                return [], []
            return [], [f"ActionPrototype empty data {inner_short}"]

        candidates = []
        if _looks_like_base64(data):
            # 优先按 base64(XOR 混淆字节) 解释。
            try:
                candidates.append(
                    bytes(_decode_action_bytes(base64.b64decode(data, validate=True)))
                )
            except Exception:
                pass
        # 再按“原始 XOR 字节”解释（双保险，顺序可根据真实日志调整）。
        candidates.append(bytes(_decode_action_bytes(data)))

        for cand in candidates:
            inner_msg = inner_cls()
            try:
                inner_msg.ParseFromString(cand)
                return self._handle(inner_short, inner_msg)
            except Exception:
                continue

        diag = f"ActionPrototype parse_error:{inner_short} raw_hex={data[:24].hex()}"
        for i, c in enumerate(candidates):
            diag += f" cand{i}_hex={c[:24].hex()}"
        return [], [diag]

    def _emit_start_game(self):
        self._started_game = True
        return [{"type": "start_game", "names": ["p0", "p1", "p2", "p3"]}]

    def _on_new_round(self, msg):
        events = []
        if not self._started_game:
            events += self._emit_start_game()
        self.bakaze = chang_to_bakaze(msg.chang)
        self.kyoku = (msg.ju % 4) + 1
        self.honba = msg.ben
        self.kyotaku = msg.liqibang
        self.scores = list(msg.scores) if len(msg.scores) == 4 else [25000] * 4
        if msg.doras:
            self.dora_indicators = tile_str_to_mjai_list(msg.doras)
        elif msg.dora:
            self.dora_indicators = [tile_str_to_mjai(msg.dora)]
        else:
            self.dora_indicators = []
        dora_marker = self.dora_indicators[0] if self.dora_indicators else "?"
        if dora_marker == "?":
            # 防御：万一宝牌指示解析失败，退回一张合法牌，避免 Mortal 报错。
            dora_marker = "1m"
        my_tiles = tile_str_to_mjai_list(msg.tiles)
        # 防御：四人麻将起手至少 13 张；少于 13 说明 ActionNewRound 解密/解析异常，跳过。
        if len(my_tiles) < 13:
            print(f"[warn] ActionNewRound tiles={len(my_tiles)} <13, skip", flush=True)
            return events
        if "?" in my_tiles:
            print(f"[warn] 起手牌里有无法识别的牌：raw={list(msg.tiles)} -> "
                  f"{my_tiles}（seat={self.self_seat}）", flush=True)
        self.my_tehai = list(my_tiles)
        self.my_ankan_count = 0
        self.my_melds = []
        self.last_tsumo = None
        print(f"[*] 新一局：seat={self.self_seat} 起手牌={' '.join(my_tiles)}", flush=True)
        if self.self_seat is None:
            print("[warn] 还没确定自己的座位就收到 ActionNewRound，这一局可能无法跟踪", flush=True)
        # 闲家起手 13 张；庄家雀魂会直接给 14 张（第 14 张就是庄家开局的第一次摸牌，
        # 不会再单独发 ActionDealTile）。所以前 13 张进 start_kyoku，多出来的当 tsumo 发。
        base_tiles = my_tiles[:13]
        extra_tiles = my_tiles[13:]
        tehais = []
        for seat in range(4):
            if seat == self.self_seat:
                tehais.append(base_tiles + ["?"] * (13 - len(base_tiles)))
            else:
                tehais.append(["?"] * 13)
        oya = msg.ju % 4
        events.append({
            "type": "start_kyoku",
            "bakaze": self.bakaze,
            "dora_marker": dora_marker,
            "kyoku": self.kyoku,
            "honba": self.honba,
            "kyotaku": self.kyotaku,
            "oya": oya,
            "scores": self.scores,
            "tehais": tehais,
        })
        # 庄家的第 14 张补成一次摸牌，否则首巡不会给建议
        for t in extra_tiles:
            events.append({"type": "tsumo", "actor": self.self_seat, "pai": t})
        if extra_tiles:
            self.last_tsumo = extra_tiles[-1]
        self._started_kyoku = True
        return events

    def _on_deal_tile(self, msg):
        events = []
        seat = msg.seat
        tile = tile_str_to_mjai(msg.tile)
        events.append({"type": "tsumo", "actor": seat, "pai": tile})
        if seat == self.self_seat:
            self.last_tsumo = tile
            if tile != "?" and tile not in self.my_tehai:
                self.my_tehai.append(tile)
        # 注意：雀魂在 ActionDealTile 里通常会带上一个默认的 liqi 子消息，
        # 所以 HasField("liqi") 几乎恒为真，不能拿它判断“是否立直成功”。
        # 这里不再产生 reach_accepted，立直确认改在出牌事件里紧跟 reach 发出。
        events += self._maybe_dora(getattr(msg, "doras", None))
        return events

    def _on_discard_tile(self, msg):
        events = []
        seat = msg.seat
        tile = tile_str_to_mjai(msg.tile)
        tsumogiri = bool(msg.moqie)
        # 立直事件必须排在出牌之前。Mortal 处理 reach 时会把 can_discard 置回 true
        # （表示“接着要打立直牌”），紧跟的 dahai 才是真正打出的那张。
        # 如果顺序颠倒（先 dahai 再 reach），就会残留一个非法的 can_discard=true，
        # 下一帧 Mortal 想算建议时候选表为空 -> Rust panic。
        if msg.is_liqi:
            events.append({"type": "reach", "actor": seat})
        events.append({
            "type": "dahai",
            "actor": seat,
            "pai": tile,
            "tsumogiri": tsumogiri,
        })
        if msg.is_liqi:
            # 立直在 mjai 里的顺序是 reach -> dahai -> reach_accepted（见 Mortal 的测试）。
            # 这里紧跟出牌确认，避免像之前那样把“立直成功”拖到后面的摸牌事件里、
            # 甚至误判成自己立直，从而把吃/碰/杠建议全部屏蔽掉。
            events.append({"type": "reach_accepted", "actor": seat})
        if seat == self.self_seat and tile != "?" and tile in self.my_tehai:
            self.my_tehai.remove(tile)
            self.last_tsumo = None
        events += self._maybe_dora(getattr(msg, "doras", None))
        return events

    def _on_chi_peng_gang(self, msg):
        seat = msg.seat
        typ = msg.type
        tiles = tile_str_to_mjai_list(msg.tiles)
        froms = list(msg.froms)
        if not tiles:
            return []

        # 吃/碰/杠的类型优先用“牌型”判断，别只信 type 字段：
        #   4 张同牌 = 大明杠；3 张同牌 = 碰；其余（同花连续）= 吃
        all_same = len(set(tiles)) == 1
        if len(tiles) >= 4 or (typ == 2 and len(tiles) >= 3):
            call = "daiminkan"
        elif all_same:
            call = "pon"
        else:
            call = "chi"

        # Mortal 要的是：pai = 叫的那张牌（来自别家）+ consumed = 手上拿掉的牌。
        # 雀魂可能给全量（chi 3 / pon 3 / daiminkan 4 张），也可能只给手上那几张，
        # 两种情况都要能还原。
        n_total = {"chi": 3, "pon": 3, "daiminkan": 4}[call]
        n_consumed = {"chi": 2, "pon": 2, "daiminkan": 3}[call]
        if len(tiles) >= n_total:
            # 全量：来自别家的那张就是叫的牌
            called_idx = 0
            for i, f in enumerate(froms):
                if f != seat:
                    called_idx = i
                    break
            pai = tiles[called_idx]
            consumed = [t for j, t in enumerate(tiles) if j != called_idx][:n_consumed]
            target = froms[called_idx] if called_idx < len(froms) else ((seat - 1) % 4)
        else:
            # 只给了手上那几张：叫的牌与它们同类，直接用第一张顶上
            pai = tiles[0]
            consumed = tiles[:n_consumed]
            target = froms[0] if froms else ((seat - 1) % 4)

        ev = None
        if len(consumed) >= n_consumed:
            ev = {"type": call, "actor": seat, "target": target,
                  "pai": pai, "consumed": consumed}

        # 这类事件很少，日志一直开着，便于排查
        print(
            f"[CPG] type={typ} seat={seat} tiles={list(msg.tiles)} "
            f"froms={froms} -> {ev}",
            flush=True,
        )

        if seat == self.self_seat and ev is not None:
            for c in ev.get("consumed") or []:
                if c in self.my_tehai:
                    self.my_tehai.remove(c)
                else:
                    print(f"[warn] 碰/吃/杠要拿走 {c} 但手牌里没有：{self.my_tehai}", flush=True)
            self.my_melds.append([ev["pai"]] + list(ev.get("consumed") or []))
            self.last_tsumo = None
        events = [ev] if ev else []
        return events

    def _on_an_gang_add_gang(self, msg):
        seat = msg.seat
        typ = msg.type
        tile = tile_str_to_mjai(msg.tiles)
        ev = None
        if typ == 3:
            ev = {"type": "ankan", "actor": seat,
                  "consumed": [tile, tile, tile, tile]}
        elif typ == 2:
            ev = {"type": "kakan", "actor": seat, "pai": tile,
                  "consumed": [tile, tile, tile]}
        print(f"[CPG] angang_addgang type={typ} seat={seat} tiles={msg.tiles!r} -> {ev}", flush=True)
        if seat == self.self_seat and ev is not None:
            if typ == 3:  # 暗杠：手里拿掉 4 张，暗杠数 +1
                for _ in range(4):
                    if tile in self.my_tehai:
                        self.my_tehai.remove(tile)
                self.my_ankan_count += 1
                self.my_melds.append([tile, tile, tile, tile])
            elif typ == 2:  # 加杠：手里拿掉 1 张，已有碰变成杠，暗杠数不变
                if tile in self.my_tehai:
                    self.my_tehai.remove(tile)
                for m in self.my_melds:
                    if len(m) == 3 and m[0] == tile:
                        m.append(tile)
                        break
            self.last_tsumo = None
        events = [ev] if ev else []
        events += self._maybe_dora(getattr(msg, "doras", None))
        return events

    def _on_hule(self, msg):
        events = []
        for h in msg.hules:
            actor = h.seat
            target = actor if h.zimo else ((actor + 1) % 4)
            events.append({"type": "hora", "actor": actor, "target": target})
        events.append({"type": "end_kyoku"})
        self._started_kyoku = False
        return events

    def _on_ryukyoku(self, msg):
        events = [{"type": "ryukyoku"}, {"type": "end_kyoku"}]
        self._started_kyoku = False
        return events

    def _maybe_dora(self, doras_field):
        if not doras_field:
            return []
        new_doras = tile_str_to_mjai_list(doras_field)
        added = []
        for d in new_doras[len(self.dora_indicators):]:
            added.append({"type": "dora", "dora_marker": d})
        if new_doras:
            self.dora_indicators = new_doras
        return added

    def riichi_discard_candidates(self):
        """立直时可打（仍保持听牌）的牌，返回中文牌名列表；算不出来就返回空列表。

        只在自己手牌是 3n+2 张（刚摸完）时才有意义。
        """
        try:
            tiles = list(self.my_tehai)
            if len(tiles) % 3 != 2:
                return []
            discards = tenpai_discards(tiles, self.my_ankan_count)
        except Exception:
            return []
        return [tile_cn(t) for t in discards]

    def my_hand_str(self):
        """本地跟踪的手牌 + 副露，用于悬浮窗 / 排查。"""
        hand = " ".join(sorted(tile_cn(t) for t in self.my_tehai)) if self.my_tehai else "-"
        if self.my_melds:
            melds = " | ".join(
                "".join(sorted(tile_cn(t) for t in m)) for m in self.my_melds
            )
        else:
            melds = "-"
        parts = [f"手牌: {hand}", f"副露: {melds}"]
        kan = self.my_kan_candidates()
        if kan:
            parts.append("可杠: " + " / ".join(kan))
        return "    ".join(parts)

    def my_kan_candidates(self):
        """当前能杠的牌：暗杠（手里 4 张）/ 加杠（碰过且有第 4 张）。"""
        from collections import Counter
        cnt = Counter(self.my_tehai)
        out = []
        for t, n in cnt.items():
            if n >= 4:
                out.append(tile_cn(t) + "（暗杠）")
        for m in self.my_melds:
            if len(m) == 3 and cnt.get(m[0], 0) >= 1:
                out.append(tile_cn(m[0]) + "（加杠）")
        return out
