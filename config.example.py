# -*- coding: utf-8 -*-
"""配置模板 —— 复制本文件为 config.py，再按你自己的环境填写。

    copy config.example.py config.py      (Windows)
    cp   config.example.py config.py      (Linux/macOS)

config.py 已在 .gitignore 中。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1) Mortal 的运行时目录
#    指向 Mortal 仓库里的 `mortal/` 目录，里面有 model.py / engine.py /
#    libriichi.pyd（需自己编译）。
#    例：  MORTAL_DIR = r"C:\ai\Mortal\mortal"
# ---------------------------------------------------------------------------
MORTAL_DIR = ""

# ---------------------------------------------------------------------------
# 2) mahjong_soul_api 目录
#    指向 mahjong_soul_api 仓库里的 `mahjong_soul_api-master` 目录，
#    其下有 ms/protocol_pb2.py。
#    例：  MS_API_DIR = r"C:\ai\mahjong_soul_api\mahjong_soul_api-master"
# ---------------------------------------------------------------------------
MS_API_DIR = ""

# ---------------------------------------------------------------------------
# 3) 解析协议所需的 XOR 混淆密钥
#    整数列表；长度与内容按你实际使用的密钥填写。
#    留空时解析器会提示需要配置。
# ---------------------------------------------------------------------------
ACTION_XOR_KEYS = []

# ---------------------------------------------------------------------------
# 4) 浏览器持久化目录（自动创建）
# ---------------------------------------------------------------------------
BROWSER_PROFILE = os.path.join(HERE, "browser_profile")
