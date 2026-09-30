# 编译 libriichi

`libriichi` 是 Mortal 的 Rust 扩展，需要在本机编译。

## 需要的工具

- **Rust**：<https://rustup.rs>，host 选 `x86_64-pc-windows-msvc`
- **C++ 生成工具**：Visual Studio Build Tools，勾选「使用 C++ 的桌面开发」
- **Python 3.12**：必须是运行本项目的那个解释器

## 编译

在「x64 Native Tools Command Prompt for VS」中执行（让 `cl.exe` 进入 PATH）：

```bat
git clone https://github.com/Equim-chan/Mortal
cd Mortal
set PYO3_PYTHON=<你的 python.exe 完整路径>
cargo build -p libriichi --lib --release
copy /Y target\release\riichi.dll mortal\libriichi.pyd
```

也可以用 maturin：`maturin build --release --manifest-path libriichi\Cargo.toml`。

产物放到 `mortal\` 目录下，与 `model.py` 同级；Linux / macOS 为 `libriichi.so` / `.dylib`。
若报 `link.exe not found`，说明当前不在 MSVC 环境中。
