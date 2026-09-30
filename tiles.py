# -*- coding: utf-8 -*-
"""雀魂牌码 <-> Mortal mjai Tile 字符串 的映射。

雀魂现在的牌是“可读字符串”形式，而不是 charCode：
    1m..9m   万子
    1p..9p   饼子
    1s..9s   索子
    1z..7z   字牌（东南西北白发中）
    0m/0p/0s 赤宝牌（红五）

Mortal 用的是 mjai 记法：
    1m..9m / 1p..9p / 1s..9s
    E S W N P F C（字牌）
    5mr / 5pr / 5sr（赤宝牌）
"""


# 字牌：雀魂 "1z".."7z" -> Mortal "E".."C"
_HONOR = {
    "1z": "E",  # 东
    "2z": "S",  # 南
    "3z": "W",  # 西
    "4z": "N",  # 北
    "5z": "P",  # 白
    "6z": "F",  # 发
    "7z": "C",  # 中
}

# 赤宝牌：雀魂 "0m".."0s" -> Mortal "5mr".."5sr"
_AKA = {
    "0m": "5mr",
    "0p": "5pr",
    "0s": "5sr",
}

# 场风/自风索引 -> mjai 字牌（雀魂 chang/ju 用 uint32，0=东 1=南 2=西 3=北）
FENG = ["E", "S", "W", "N"]


# mjai 牌名 -> 中文名（用于提示显示）
TILE_CN = {
    "1m": "一万", "2m": "二万", "3m": "三万", "4m": "四万", "5m": "五万",
    "6m": "六万", "7m": "七万", "8m": "八万", "9m": "九万",
    "1p": "一筒", "2p": "二筒", "3p": "三筒", "4p": "四筒", "5p": "五筒",
    "6p": "六筒", "7p": "七筒", "8p": "八筒", "9p": "九筒",
    "1s": "一索", "2s": "二索", "3s": "三索", "4s": "四索", "5s": "五索",
    "6s": "六索", "7s": "七索", "8s": "八索", "9s": "九索",
    "E": "东", "S": "南", "W": "西", "N": "北",
    "P": "白", "F": "发", "C": "中",
    "5mr": "赤五万", "5pr": "赤五筒", "5sr": "赤五索",
    "?": "?",
}


def tile_cn(tile):
    return TILE_CN.get(tile, tile)


def tile_str_to_mjai(tile):
    """单个雀魂牌字符串 -> Mortal 牌字符串；未知返回 "?"。"""
    if not tile:
        return "?"
    if tile in _HONOR:
        return _HONOR[tile]
    if tile in _AKA:
        return _AKA[tile]
    if len(tile) == 2 and tile[0] in "123456789" and tile[1] in "mps":
        return tile
    return "?"


def tile_str_to_mjai_list(tiles):
    """雀魂牌列表（每个元素是 2 字符牌串）-> Mortal 牌列表。"""
    return [tile_str_to_mjai(t) for t in tiles]


def chang_to_bakaze(chang):
    return FENG[chang % 4]
