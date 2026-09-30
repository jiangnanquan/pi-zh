#!/usr/bin/env python3
"""
pi-zh — 插件 editor 边框行为探针（维护线 C 行为补丁的回归哨兵）

背景：`code_patches` 里的 `editor-chrome-thinking-border` 是一条**行为补丁**——
把 pi-powerline-footer 自己重画的 editor 上下边框，从硬编码的 ANSI 244 灰改成
继承 pi 注入到 editor 实例上的 `borderColor`（即随思考层级变化的 thinking 色）。
**该补丁已于 2026-09-22 退役**：powerline 0.17.2 起上游原生实现同类行为，
本探针转为「上游是否回退」的哨兵（未打补丁也应通过）。

本探针在 pty 中启动一次真实 pi，抓取启动期的原始 ANSI 流，统计 editor 宽度的长横线边框行。

**为什么不写死颜色**：0.99.0 起上游把主题调色板换成了 okhsl 体系（暗色主题的
`thinkingMax` 从 `#ff5fff` 变为 `okhsl(20 99% 63%)`），写死「紫色 `255;95;255`」的旧判定
在 0.99 上必然误报失败。现改为：**取 editor 宽度长横线的主色**，要求 ① 确有 editor 宽度的
边框线（chrome 在画）；② 主色不是中性 244 灰（说明边框确实跟着思考层级被着色）。
需要锁定具体颜色时用 `--expect-rgb R,G,B`。

基线（40×120 终端 / thinking=max）：
  0.17.1 未打补丁：editor 宽紫 2 / editor 宽灰 4 ⇒ 判定失败
  0.17.2 已打补丁：editor 宽紫 6 / editor 宽灰 0 ⇒ 判定通过
  0.99.1（当前）：editor 宽 `rgb(254,84,98)` 8 条 / editor 宽灰 0 条 ⇒ 判定通过

用法：
  python3 scripts/probe_editor_border.py                # 默认探测 9 秒
  python3 scripts/probe_editor_border.py --seconds 12 --cwd ~/Pkm
  python3 scripts/probe_editor_border.py --expect-rgb 254,84,98   # 锁定具体颜色（可选）
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
# 任意 Truecolor 前景色 + 长横线：用于「调色板无关」地找出 editor 边框主色
RGB_LINE = re.compile(rb"\x1b\[38;2;(\d+);(\d+);(\d+)m(?:" + "─".encode() + rb"){20,}")
BAR = "─".encode()
# editor 上下边框整宽重画（120 列终端下为 118/120 列）；欢迎页 box 分隔线只有 ~65~81 列
EDITOR_RUN_MIN = 100
DEFAULT_MIN_COLORED = 4


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
    parser.add_argument("--min-colored", type=int, default=DEFAULT_MIN_COLORED,
                        help="判定通过所需的最少「非中性灰」editor 宽度边框线数")
    parser.add_argument("--expect-rgb", default=None,
                        help="可选：锁定具体边框颜色（形如 254,84,98）；不填则只要求「被着色」")
    args = parser.parse_args()

    if not shutil.which("pi"):
        log("PATH 中未找到 pi，请确认全局安装并在当前 Shell 可用。", "ERROR")
        sys.exit(1)

    chunks = capture(args.seconds, args.cwd, args.rows, args.cols, {})
    raw = b"".join(data for _, data in chunks)
    if not raw:
        log("未捕获到任何输出：pi 可能未启动（检查 `which pi` 与终端环境）。", "ERROR")
        sys.exit(1)

    gray = len(GRAY_LINE.findall(raw))
    gray_editor = editor_width_runs(b"\x1b[38;5;244m", raw)
    # 调色板无关：统计每一种 Truecolor 下的 editor 宽度边框线
    colored = {}
    for m in RGB_LINE.finditer(raw):
        rgb = tuple(int(x) for x in m.groups())
        colored[rgb] = colored.get(rgb, 0) + 1
    colored_editor = {}
    for rgb in colored:
        runs = editor_width_runs(b"\x1b[38;2;" + f"{rgb[0]};{rgb[1]};{rgb[2]}".encode() + b"m", raw)
        if runs:
            colored_editor[rgb] = len(runs)

    log(f"捕获 {len(raw)} 字节 / {len(chunks)} 个输出块（{args.seconds:g}s，{args.cols}×{args.rows}）")
    log(f"中性 244 灰长横线 : {gray} 处，其中 editor 宽度 {len(gray_editor)} 处")
    if colored_editor:
        main_rgb, main_n = max(colored_editor.items(), key=lambda kv: kv[1])
        log(f"editor 宽度着色边框线（调色板无关统计）：")
        for rgb, n in sorted(colored_editor.items(), key=lambda kv: -kv[1]):
            log(f"    rgb{list(rgb)} × {n} 条")
    else:
        main_rgb, main_n = None, 0
        log("未找到任何 editor 宽度的着色边框线（只要 editor chrome 在画，这里不应该为空）", "WARN")

    # 可选：锁定具体颜色
    if args.expect_rgb:
        want = tuple(int(x) for x in args.expect_rgb.split(","))
        ok_rgb = colored_editor.get(want, 0) >= args.min_colored
        log(f"锁定颜色 rgb{list(want)}：{'命中' if ok_rgb else '未命中'}（{colored_editor.get(want, 0)} 条）",
            "SUCCESS" if ok_rgb else "ERROR")
        sys.exit(0 if ok_rgb else 1)

    if main_rgb is not None and main_n >= args.min_colored and len(gray_editor) < main_n:
        log(
            f"哨兵通过：editor 上下边框已跟随 pi 的思考层级色（主色 rgb{list(main_rgb)} 共 {main_n} 条，"
            f"≥ 阈值 {args.min_colored}，且多于中性灰的 {len(gray_editor)} 条）。",
            "SUCCESS",
        )
        return

    log(
        f"哨兵失败：editor 宽度着色边框线为 {main_n} 条（阈值 {args.min_colored}），"
        f"中性灰为 {len(gray_editor)} 条。可能原因：① 上游把 editor 边框改回了中性色；"
        "② 当前思考层级为 off；③ 终端尺寸/主题配置变化。"
        "先跑 `bash scripts/apply_plugin_ui.sh --check` 与 `pi --version` 确认基线，再人工判断。",
        "ERROR",
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
