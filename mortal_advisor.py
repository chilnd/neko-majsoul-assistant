# -*- coding: utf-8 -*-
"""常驻 Mortal 引擎：加载一次模型权重，增量喂 mjai 事件、拿回出牌建议。

调参（不是改模型，只是改“怎么从 Q 值里挑动作”）：
    同目录 ai_tuning.json
        {"eps": 0.15, "temp": 1.20, "top_p": 1.00}
    eps    -> boltzmann_epsilon：多大概率不走最优解（0=永远最优）
    temp   -> boltzmann_temp   ：采样温度，越大越随机
    top_p  -> 核采样阈值
    每局开头（收到 start_kyoku）重读一次，改完存盘下一局生效。

这个模块必须在能 import Mortal 源码的环境中运行。我们通过把 Mortal 的
`mortal/` 目录插到 sys.path 前面，让 `model` / `engine` / `libriichi` 可被导入。
"""
import json
import os
import sys

import toml
import torch

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

MORTAL_DIR = cfg.MORTAL_DIR
TUNING_FILE = os.path.join(HERE, "ai_tuning.json")

DEFAULT_TUNING = {"eps": 0.15, "temp": 1.20, "top_p": 1.00}


def load_tuning():
    """读调参文件；缺项/坏值一律回退默认，保证配置坏了也不会崩。"""
    cfg = dict(DEFAULT_TUNING)
    try:
        with open(TUNING_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k in ("eps", "temp", "top_p"):
            if k in data:
                cfg[k] = float(data[k])
    except Exception:
        pass
    cfg["eps"] = max(0.0, min(0.5, cfg["eps"]))
    cfg["temp"] = max(0.1, min(2.0, cfg["temp"]))
    cfg["top_p"] = max(0.1, min(1.0, cfg["top_p"]))
    return cfg


class MortalAdvisor:
    def __init__(self, player_id: int):
        assert player_id in range(4)
        self.player_id = player_id

        if not MORTAL_DIR or not os.path.isdir(MORTAL_DIR):
            raise SystemExit(
                f"config.py 里的 MORTAL_DIR 没填或不存在: {MORTAL_DIR!r}\n"
                "请指向 Mortal 仓库里的 mortal/ 目录（含 model.py / engine.py / libriichi.pyd）。"
            )

        # 把 Mortal 源码目录放到 import 路径最前，并保证配置能被读到。
        if MORTAL_DIR not in sys.path:
            sys.path.insert(0, MORTAL_DIR)

        cfg_path = os.path.join(MORTAL_DIR, "config.toml")
        cfg = toml.load(cfg_path)
        state_file = os.path.join(MORTAL_DIR, cfg["control"]["state_file"])

        from model import Brain, DQN
        from engine import MortalEngine
        from libriichi.mjai import Bot

        device = torch.device("cpu")
        state = torch.load(state_file, weights_only=True, map_location="cpu")
        scfg = state["config"]
        version = scfg["control"].get("version", 1)
        num_blocks = scfg["resnet"]["num_blocks"]
        conv_channels = scfg["resnet"]["conv_channels"]

        mortal = Brain(
            version=version, num_blocks=num_blocks, conv_channels=conv_channels
        ).eval()
        dqn = DQN(version=version).eval()
        mortal.load_state_dict(state["mortal"])
        dqn.load_state_dict(state["current_dqn"])

        self._tuning = load_tuning()
        engine = MortalEngine(
            mortal,
            dqn,
            version=version,
            is_oracle=False,
            device=device,
            enable_amp=False,
            enable_quick_eval=True,
            enable_rule_based_agari_guard=True,
            name="mortal",
            boltzmann_epsilon=self._tuning["eps"],
            boltzmann_temp=self._tuning["temp"],
            top_p=self._tuning["top_p"],
        )
        self._engine = engine
        self._bot = Bot(engine, player_id)
        print(
            f"[tune] 初始参数 eps={self._tuning['eps']:.2f} "
            f"temp={self._tuning['temp']:.2f} top_p={self._tuning['top_p']:.2f}",
            flush=True,
        )

    def _apply_tuning(self):
        """每局开头重读调参文件并写回引擎（引擎是同一个 Python 对象，改了立刻生效）。"""
        try:
            self._tuning = load_tuning()
            self._engine.boltzmann_epsilon = self._tuning["eps"]
            self._engine.boltzmann_temp = self._tuning["temp"]
            self._engine.top_p = self._tuning["top_p"]
            print(
                f"[tune] 本局参数 eps={self._tuning['eps']:.2f} "
                f"temp={self._tuning['temp']:.2f} top_p={self._tuning['top_p']:.2f}",
                flush=True,
            )
        except Exception as ex:
            print(f"[tune] 重读调参失败（沿用上一局）: {ex}", flush=True)

    def react(self, mjai_json: str):
        """喂一行 mjai 事件；若轮到我决策则返回建议 JSON 字符串，否则 None。"""
        if '"start_kyoku"' in mjai_json:
            self._apply_tuning()
        return self._bot.react(mjai_json)

    def validate(self, mjai_json: str):
        """校验一个动作是否合法（调试用）。"""
        return self._bot.validate_reaction(mjai_json)


if __name__ == "__main__":
    # 自检：加载模型并回放 mjai_test.jsonl，打印出所有决策建议。
    player_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    print("[*] loading model ...", flush=True)
    advisor = MortalAdvisor(player_id)
    print("[*] model loaded.", flush=True)

    test_file = os.environ.get("MJAI_TEST_FILE", os.path.join(HERE, "mjai_test.jsonl"))
    with open(test_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = advisor.react(line)
            if r is not None:
                print("SUGGESTION:", r, flush=True)
