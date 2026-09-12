#!/usr/bin/env python3
"""
pi-zh — 插件 editor 边框行为探针（维护线 C 行为补丁的回归验证）

背景：`code_patches` 里的 `editor-chrome-thinking-border` 是一条**行为补丁**——
把 pi-powerline-footer 自己重画的 editor 上下边框，从硬编码的 ANSI 244 灰改成
继承 pi 注入到 editor 实例上的 `borderColor`（即随思考层级变化的 thinking 色）。
这类改动 jiti 体检（能否加载）证明不了行为，必须在真实 TUI 里看颜色。

本探针在 pty 中启动一次真实 pi，抓取启动期的原始 ANSI 流，统计两类「长横线边框行」：
  紫色 = `\\x1b[38;2;255;95;255m` + ≥20 个 ─   → pi 的 thinkingMax 边框（max 层级）
  灰色 = `\\x1b[38;5;244m` + ≥20 个 ─          → 244 灰边框（含欢迎页 box 与分隔线）

判定只看 **editor 宽度的长横线**（≥100 列）：editor 上下边框整宽重画，而欢迎页 box 的分隔线
只有 65~81 列。这样即使 welcome-header-eager-shell 补丁让欢迎页多画一次（多出若干 244 灰
分隔线），判定也不会被带偏。

基线（pi-powerline-footer 0.17.1 / 40×120 终端 / thinking=max）：
  未打补丁：editor 宽紫 2 / editor 宽灰 4（全量：紫 2，灰 9）⇒ 判定失败
  已打补丁：editor 宽紫 6 / editor 宽灰 0（全量：紫 6，灰 8，灰全部来自欢迎页 box）⇒ 判定通过

用法：
  python3 scripts/probe_editor_border.py                # 默认探测 9 秒
  python3 scripts/probe_editor_border.py --seconds 12 --cwd ~/Pkm
"""

import argparse
import fcntl
import os
import pty
import re
import select
import shutil
import signal
import struct
import sys
import termios
import time

PURPLE_LINE = re.compile(rb"\x1b\[38;2;255;95;255m(?:" + "─".encode() + rb"){20,}")
GRAY_LINE = re.compile(rb"\x1b\[38;5;244m(?:" + "─".encode() + rb"){20,}")
BAR = "─".encode()
# editor 上下边框整宽重画（120 列终端下为 118/120 列）；欢迎页 box 分隔线只有 ~65~81 列
EDITOR_RUN_MIN = 100
DEFAULT_MIN_PURPLE = 4


def log(msg, level="INFO"):
    colors = {"INFO": "\033[1;34m[INFO]\033[0m", "SUCCESS": "\033[1;32m[OK]\033[0m", "ERROR": "\033[1;31m[ERROR]\033[0m"}
    print(f"{colors.get(level, f'[{level}]')} {msg}")


def capture(seconds, cwd, rows, cols, extra_env):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PI_") and k != "AI_AGENT"}
    env["TERM"] = "xterm-256color"
    env.update(extra_env)

    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.chdir(os.path.expanduser(cwd))
        except OSError:
            pass
        os.execvpe("pi", ["pi", "--no-session"], env)
        os._exit(1)

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    started = time.time()
    chunks = []
    while time.time() - started < seconds:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        try:
            data = os.read(fd, 1 << 16)
        except OSError:
            break
        if not data:
            break
        chunks.append((time.time() - started, data))

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return chunks


def editor_width_runs(color: bytes, raw: bytes) -> list:
    """统计该颜色下「editor 宽度」的长横线次数（行宽 ≥ EDITOR_RUN_MIN 列）"""
    runs = []
    for match in re.finditer(re.escape(color) + b"((?:" + BAR + b"){20,})", raw):
        length = len(match.group(1)) // len(BAR)
        if length >= EDITOR_RUN_MIN:
            runs.append(length)
    return runs


def main():
    parser = argparse.ArgumentParser(description="插件 editor 边框行为探针")
    parser.add_argument("--seconds", type=float, default=9.0, help="抓取时长（秒）")
    parser.add_argument("--cwd", default=os.getcwd(), help="启动 pi 的工作目录")
    parser.add_argument("--rows", type=int, default=40)
    parser.add_argument("--cols", type=int, default=120)
    parser.add_argument("--min-purple", type=int, default=DEFAULT_MIN_PURPLE,
                        help="判定行为补丁生效所需的最少紫色边框行数")
    args = parser.parse_args()

    if not shutil.which("pi"):
        log("PATH 中未找到 pi，请确认全局安装并在当前 Shell 可用。", "ERROR")
        sys.exit(1)

    chunks = capture(args.seconds, args.cwd, args.rows, args.cols, {})
    raw = b"".join(data for _, data in chunks)
    if not raw:
        log("未捕获到任何输出：pi 可能未启动（检查 `which pi` 与终端环境）。", "ERROR")
        sys.exit(1)

    purple = len(PURPLE_LINE.findall(raw))
    gray = len(GRAY_LINE.findall(raw))
    purple_editor = editor_width_runs(b"\x1b[38;2;255;95;255m", raw)
    gray_editor = editor_width_runs(b"\x1b[38;5;244m", raw)
    purple_first = next((round(t, 2) for t, data in chunks if PURPLE_LINE.search(data)), None)
    gray_last = next((round(t, 2) for t, data in reversed(chunks) if GRAY_LINE.search(data)), None)

    log(f"捕获 {len(raw)} 字节 / {len(chunks)} 个输出块（{args.seconds:g}s，{args.cols}×{args.rows}）")
    log(f"紫色 thinking 边框行: {purple} 处（首现 {purple_first}s）")
    log(f"灰色 244 边框行   : {gray} 处（末现 {gray_last}s；含欢迎页 box 与分隔线，不计入判定）")
    log(
        f"判定口径（editor 宽度 ≥{EDITOR_RUN_MIN} 列）: 紫 {len(purple_editor)} 处 "
        f"{sorted(set(purple_editor))} / 灰 {len(gray_editor)} 处 {sorted(set(gray_editor))}"
    )

    if len(purple_editor) >= args.min_purple and len(purple_editor) > len(gray_editor):
        log(
            f"行为补丁生效：editor 上下边框已跟随 pi 的思考层级色（阈值 ≥{args.min_purple} 且紫 > 灰）。",
            "SUCCESS",
        )
        return

    log(
        f"行为补丁疑似未生效：editor 宽紫色边框行 {len(purple_editor)} < 阈值 {args.min_purple}"
        "（未打补丁的基线约为 editor 宽 紫 2 / 灰 4）。"
        "若有漂移，先跑 `bash scripts/apply_plugin_ui.sh --check`，再重打补丁后复测。",
        "ERROR",
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
