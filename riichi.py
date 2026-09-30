# -*- coding: utf-8 -*-
"""立直辅助：给定手牌，算出哪些牌打出去之后仍然听牌。

只做“听牌 / 不听牌”的判定，纯 Python，不依赖任何第三方库。
算法是穷举分解：
    14 张 -> 出 1 张成 13 张 -> 再枚举 1 张进张 -> 判断能否凑成
    (4-暗杠数) 个面子 + 1 个雀头
带暗杠时，暗杠算一个已完成面子，暗牌按 3*(4-暗杠数)+1 张来判。
"""

_IDX = {
    "1m": 0, "2m": 1, "3m": 2, "4m": 3, "5m": 4, "6m": 5, "7m": 6, "8m": 7, "9m": 8,
    "1p": 9, "2p": 10, "3p": 11, "4p": 12, "5p": 13, "6p": 14, "7p": 15, "8p": 16, "9p": 17,
    "1s": 18, "2s": 19, "3s": 20, "4s": 21, "5s": 22, "6s": 23, "7s": 24, "8s": 25, "9s": 26,
    "E": 27, "S": 28, "W": 29, "N": 30, "P": 31, "F": 32, "C": 33,
}
# 赤宝牌按普通 5 处理（兼容 mjai 的 5mr 和 tenhou 的 0m 两种写法）
for _alias, _base in (("5mr", 4), ("5pr", 13), ("5sr", 22),
                      ("0m", 4), ("0p", 13), ("0s", 22)):
    _IDX[_alias] = _base

MJAI = [
    "1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m",
    "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p",
    "1s", "2s", "3s", "4s", "5s", "6s", "7s", "8s", "9s",
    "E", "S", "W", "N", "P", "F", "C",
]


def to_counts(tiles):
    c = [0] * 34
    for t in tiles:
        i = _IDX.get(t)
        if i is None:
            return None
        c[i] += 1
    return c


def _meld_decompose(c, start, need):
    if need == 0:
        return not any(c)
    i = start
    while i < 34 and c[i] == 0:
        i += 1
    if i == 34:
        return False
    if c[i] >= 3:
        c[i] -= 3
        ok = _meld_decompose(c, i, need - 1)
        c[i] += 3
        if ok:
            return True
    if i < 27 and i % 9 <= 6 and c[i + 1] and c[i + 2]:
        c[i] -= 1
        c[i + 1] -= 1
        c[i + 2] -= 1
        ok = _meld_decompose(c, i, need - 1)
        c[i] += 1
        c[i + 1] += 1
        c[i + 2] += 1
        if ok:
            return True
    return False


def _is_agari(c, need_melds):
    for i in range(34):
        if c[i] >= 2:
            c[i] -= 2
            ok = _meld_decompose(c, 0, need_melds)
            c[i] += 2
            if ok:
                return True
    return False


def is_tenpai(c, need_melds):
    """c: 34 长度暗牌计数，共 3*need_melds+1 张。"""
    for t in range(34):
        if c[t] >= 4:
            continue
        c[t] += 1
        ok = _is_agari(c, need_melds)
        c[t] -= 1
        if ok:
            return True
    return False


def tenpai_discards(hand_tiles, num_melds=0):
    """返回“打出之后仍然听牌”的牌名列表（mjai 记法），按牌种类排序。"""
    c = to_counts(hand_tiles)
    if c is None:
        return []
    need_melds = 4 - num_melds
    out = []
    for t in range(34):
        if c[t] == 0:
            continue
        c[t] -= 1
        ok = is_tenpai(c, need_melds)
        c[t] += 1
        if ok:
            out.append(MJAI[t])
    return out


if __name__ == "__main__":
    # 自检 1：123m 456m 789m 123p 9s + 摸 5s，立直应可打 5s
    print("case1:", tenpai_discards(
        ["1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m",
         "1p", "2p", "3p", "9s", "5s"], 0))
    # 自检 2：带一个暗杠（8p），听 3s/6s，只有打南能保持听牌
    print("case2:", tenpai_discards(
        ["0m", "5m", "6m", "7m", "8m", "S", "5p", "6p", "7p", "4s", "5s"], 1))
