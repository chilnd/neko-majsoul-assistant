# 雀魂实时 AI 建议（Mortal 版）

> 本项目仅供学习与研究使用。使用本脚本可能违反《雀魂》用户协议，相关后果由使用者自行承担。

读取雀魂网页版的下行对局数据，解析成 mjai 事件后交给 [Mortal](https://github.com/Equim-chan/Mortal) 推理，
把每一步的出牌建议显示在置顶悬浮窗里。出牌由自己操作。

![截图](docs/img/screenshot.png)

## 需要准备

- Windows 10/11、Python 3.12
- [Mortal](https://github.com/Equim-chan/Mortal) 与 [mahjong_soul_api](https://github.com/MahjongRepository/mahjong_soul_api)
- Rust 与 C++ 工具链，用于编译 `libriichi`，见 [`docs/02-build-libriichi.md`](docs/02-build-libriichi.md)
- Playwright + Chromium

## 步骤

1. 编译 `libriichi`
2. 安装依赖：`python -m pip install -r requirements.txt`、`python -m playwright install chromium`
3. 复制 `config.example.py` 为 `config.py`，按注释填写（协议解析所需的 XOR 混淆密钥需自行准备）
4. 入口：`python main.py`；隐藏控制台可用 `pythonw run_headless.py`，日志写入 `run_log.txt`

## 目录

| 文件 | 作用 |
|---|---|
| `main.py` | 入口：启动浏览器、监听 WebSocket、调度解析与推理 |
| `liqi_parser.py` | Liqi 协议解析，翻译成 mjai 事件 |
| `tiles.py` / `riichi.py` | 牌码映射与听牌判定 |
| `mortal_advisor.py` | Mortal 引擎适配 |
| `overlay.py` | tkinter 置顶悬浮窗 |
| `run_headless.py` | 无控制台启动的日志重定向 |

## 调参

`ai_tuning.json` 中的 `eps`、`temp`、`top_p` 分别控制不取最优动作的概率、采样温度与核采样阈值，
从 `ai_tuning.example.json` 复制一份即可；悬浮窗右上角 ⚙ 面板也可直接调整，下一局生效。

## 许可与来源

- 本项目以 **AGPL-3.0** 发布，见 [`LICENSE`](LICENSE)。
- 上游项目见 [`NOTICE.md`](NOTICE.md)。
