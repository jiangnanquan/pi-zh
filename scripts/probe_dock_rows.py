#!/usr/bin/env python3
"""
pi-zh — 插件 dock 行数探针（维护线 C 行为补丁 `dock-trim-primary-into-footer` 的回归验收）

背景：powerline 为了拿 pi 的 `footerData`（git 分支、扩展状态）注册了一个 render() 只返回
`[""]` 的空壳 footer；而 pi 的 fullscreen dock（`chat-viewport.js`）给 footer 槽位
`minSize: 1` 保底，于是这行即使为空也占位。本补丁让 `placement=below` 时主状态行改由
footer 槽位渲染、`powerline-top` widget 让位——这类改动 jiti 体检证明不了行为，必须在
真实 TUI 里数行。

本探针在 pty 中启动一次真实 pi，把最终帧解码成字符网格，断言三件事：
  ① 屏幕最后一行就是主状态行（非空且够宽）⇒ 空壳占位行已消失；
  ② 全屏只出现一处主状态行 ⇒ widget 与 footer 没有重复渲染；
  ③ editor 下边框的下一行不空 ⇒ dock 紧贴 editor，没有留空档。
（扩展在窄宽度下会把 tps 之类的右段溢到 secondary 行，此时 footer 槽位仍是最底下一行，
所以判定取「屏幕最后一行」而不是「下边框的下一行」。）

回显行（`↳ 上次输入`）按 settings.json 的 `showLastPrompt` 判定：该开关为 false 时多出
回显行即判失败；为 true 时仅提示（说明当前配置会显示回显）。

基线（pi-powerline-footer 0.17.1 / 40×140 / placement=below / showLastPrompt=false）：
  未打补丁：editor 下边框之后是 [状态行, 空壳占位行] ⇒ 屏幕最后一行是空白 ⇒ ① 失败（退出码 1）
  已打补丁：editor 下边框之后只有 [状态行]，且它就是屏幕最后一行 ⇒ 退出码 0

可选参数 `--send-prompt` 会真发一次提问，让「回显行」真正出现，用于验证 `showLastPrompt`
开关的端到端效果。注意：该项会真实调用一次模型（`--no-session`，不落会话文件）。

用法：
  python3 scripts/probe_dock_rows.py                          # 默认探测 9 秒（离线，无模型调用）
  python3 scripts/probe_dock_rows.py --seconds 12 --cwd ~/Pkm
  python3 scripts/probe_dock_rows.py --send-prompt "探针：回显开关"   # 额外验证回显开关
"""

import argparse
import fcntl
import json
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
import unicodedata
from pathlib import Path

CSI_RE = re.compile(rb"\x1b\[([0-9;?<=>! ]*)([ -/]*)([@-~])")
OSC_RE = re.compile(rb"\x1b\](?:[^\x07\x1b]*)(?:\x07|\x1b\\)")
RULE_CHARS = {"\u2500"}                 # ─ ：editor 上下边框
SCROLL_MARKERS = {"\u2191", "\u2193"}   # ↑ ↓ ：滚动标记（出现时边框行不再全是 ─）
MIN_RULE_WIDTH = 20
MIN_STATUS_WIDTH = 30                   # 主状态行（路径/模型/花费…）不会窄于这个宽度


def log(msg, level="INFO"):
    colors = {
        "INFO": "\033[1;34m[INFO]\033[0m",
        "SUCCESS": "\033[1;32m[OK]\033[0m",
        "WARN": "\033[1;33m[WARN]\033[0m",
        "ERROR": "\033[1;31m[ERROR]\033[0m",
    }
    print(f"{colors.get(level, f'[{level}]')} {msg}")


class Screen:
    """极简终端网格解码器：只实现 pi 全屏渲染实际用到的 CSI/OSC 子集。"""

    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.grid = [[" "] * cols for _ in range(rows)]
        self.r = self.c = 0
        self.pending = b""

    def clear(self, mode=2):
        if mode in (2, 3):
            self.grid = [[" "] * self.cols for _ in range(self.rows)]
        elif mode == 0:
            for cc in range(self.c, self.cols):
                self.grid[self.r][cc] = " "
            for rr in range(self.r + 1, self.rows):
                self.grid[rr] = [" "] * self.cols
        elif mode == 1:
            for rr in range(0, self.r):
                self.grid[rr] = [" "] * self.cols
            for cc in range(0, self.c + 1):
                self.grid[self.r][cc] = " "

    def put(self, ch):
        wide = unicodedata.east_asian_width(ch) in ("W", "F")
        if self.c >= self.cols:
            return
        self.grid[self.r][self.c] = ch
        if wide and self.c + 1 < self.cols:
            self.grid[self.r][self.c + 1] = ""
        self.c = min(self.cols, self.c + (2 if wide else 1))

    def csi(self, params, final):
        nums = [int(p) for p in params.split(";") if p.isdigit()] if params else []
        first = nums[0] if nums else 1
        if final in ("H", "f"):
            self.r = min(self.rows - 1, max(0, (nums[0] if nums else 1) - 1))
            self.c = min(self.cols, max(0, (nums[1] if len(nums) > 1 else 1) - 1))
        elif final == "A":
            self.r = max(0, self.r - first)
        elif final == "B":
            self.r = min(self.rows - 1, self.r + first)
        elif final == "C":
            self.c = min(self.cols, self.c + first)
        elif final == "D":
            self.c = max(0, self.c - first)
        elif final == "G":
            self.c = min(self.cols, max(0, first - 1))
        elif final == "d":
            self.r = min(self.rows - 1, max(0, first - 1))
        elif final == "J":
            self.clear(nums[0] if nums else 0)
        elif final == "K":
            mode = nums[0] if nums else 0
            if mode == 0:
                for cc in range(self.c, self.cols):
                    self.grid[self.r][cc] = " "
            elif mode == 1:
                for cc in range(0, self.c + 1):
                    self.grid[self.r][cc] = " "
            else:
                self.grid[self.r] = [" "] * self.cols

    def feed(self, data: bytes):
        data = self.pending + data
        self.pending = b""
        i = 0
        while i < len(data):
            byte = data[i : i + 1]
            if byte == b"\x1b":
                match = CSI_RE.match(data, i)
                if match:
                    self.csi(match.group(1).decode(), match.group(3).decode())
                    i = match.end()
                    continue
                match = OSC_RE.match(data, i)
                if match:
                    i = match.end()
                    continue
                if i + 1 >= len(data):
                    self.pending = data[i:]
                    return
                nxt = data[i + 1 : i + 2]
                if nxt in b"()#":
                    i += 3
                    continue
                if nxt == b"[":
                    self.pending = data[i:]
                    return
                i += 2
                continue
            if byte == b"\r":
                self.c = 0
            elif byte == b"\n":
                self.r = min(self.rows - 1, self.r + 1)
            elif byte == b"\b":
                self.c = max(0, self.c - 1)
            elif byte == b"\t":
                self.c = min(self.cols, (self.c // 8 + 1) * 8)
            elif byte < b"\x20":
                pass
            else:
                need = 1
                lead = byte[0]
                if lead >= 0xF0:
                    need = 4
                elif lead >= 0xE0:
                    need = 3
                elif lead >= 0xC0:
                    need = 2
                chunk = data[i : i + need]
                if len(chunk) < need:
                    self.pending = data[i:]
                    return
                try:
                    self.put(chunk.decode("utf-8"))
                except UnicodeDecodeError:
                    self.put("?")
                i += need
                continue
            i += 1

    def line(self, index):
        return "".join(self.grid[index]).rstrip()

    def lines(self):
        return [self.line(i) for i in range(self.rows)]


def read_show_last_prompt(cwd):
    """读取 powerline 的 showLastPrompt 开关（全局 settings.json + 项目 .pi/settings.json 合并，默认 true）"""
    agent_dir = os.environ.get("PI_CODING_AGENT_DIR") or os.path.expanduser("~/.pi/agent")
    candidates = [Path(agent_dir) / "settings.json", Path(os.path.expanduser(cwd)) / ".pi" / "settings.json"]
    value = None
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "showLastPrompt" in data:
            value = data["showLastPrompt"]
    return True if value is None else bool(value)


def capture(seconds, cwd, rows, cols, send_prompt=None, send_after=2.5, settle=4.0):
    """在 pty 中真启一次 pi，抓取原始 ANSI 流；可选在启动后发一次提问。"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PI_") and k != "AI_AGENT"}
    env["TERM"] = "xterm-256color"

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
    deadline = seconds + (settle if send_prompt else 0)
    chunks = []
    sent = False
    while time.time() - started < deadline:
        elapsed = time.time() - started
        if send_prompt and not sent and elapsed >= send_after:
            os.write(fd, (send_prompt + "\r").encode())
            sent = True
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        try:
            data = os.read(fd, 1 << 16)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return b"".join(chunks)


def is_rule(line):
    stripped = line.strip()
    if len(stripped) < MIN_RULE_WIDTH:
        return False
    return all(ch in RULE_CHARS or ch in SCROLL_MARKERS for ch in stripped)


def find_editor_box(lines):
    """定位 editor 框：返回 (上边框行号, 输入行号, 下边框行号)；行号为 1 基，找不到返回 None。"""
    found = None
    for i in range(len(lines) - 2):
        if not is_rule(lines[i]) or not is_rule(lines[i + 2]):
            continue
        prompt = lines[i + 1].strip()
        if prompt.startswith(">") and len(prompt) <= 8:
            found = (i + 1, i + 2, i + 3)
    return found


def visible_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def main():
    parser = argparse.ArgumentParser(description="插件 dock 行数探针（dock-trim 行为补丁验收）")
    parser.add_argument("--seconds", type=float, default=9.0, help="启动抓取时长（秒）")
    parser.add_argument("--cwd", default=os.getcwd(), help="启动 pi 的工作目录")
    parser.add_argument("--rows", type=int, default=40)
    parser.add_argument("--cols", type=int, default=140)
    parser.add_argument("--send-prompt", default=None, help="额外发一次提问（会真实调用模型），用于验证回显开关")
    args = parser.parse_args()

    if not shutil.which("pi"):
        log("PATH 中未找到 pi，请确认全局安装并在当前 Shell 可用。", "ERROR")
        sys.exit(1)

    raw = capture(
        args.seconds,
        args.cwd,
        args.rows,
        args.cols,
        send_prompt=args.send_prompt,
        send_after=min(2.5, args.seconds / 3),
    )
    if not raw:
        log("未捕获到任何输出：pi 可能未启动（检查 `which pi` 与终端环境）。", "ERROR")
        sys.exit(1)

    screen = Screen(args.rows, args.cols)
    screen.feed(raw)
    lines = screen.lines()

    log(f"捕获 {len(raw)} 字节 / 解码 {args.cols}×{args.rows} 网格")
    print("----- 底部 6 行 -----")
    for index in range(max(0, args.rows - 6), args.rows):
        text = lines[index]
        print(f"{index + 1:03d}| {text if text.strip() else '<blank>'}")
    print("---------------------")

    box = find_editor_box(lines)
    if not box:
        log("未定位到 editor 框（上下边框 + `>` 输入行）：pi 可能未完成首帧渲染。", "ERROR")
        sys.exit(1)
    _top, _prompt_row, border_row = box

    problems = []

    # ① 屏幕最后一行必须是主状态行（空壳 footer 占位行的特征就是「最后一行空白」）
    last_index = args.rows - 1
    last_text = lines[last_index]
    if visible_width(last_text.strip()) < MIN_STATUS_WIDTH:
        problems.append(
            f"屏幕最后一行不是主状态行（{last_text.strip()!r}）⇒ 空壳 footer 占位行仍在，"
            "或状态行没有画进 footer 槽位"
        )
    else:
        log(f"主状态行：第 {args.rows} 行 {last_text.strip()[:80]!r}")

        # ② 同一状态行不得重复出现（widget 与 footer 都在画就会被抓出来）
        duplicates = [n + 1 for n in range(args.rows) if lines[n] == last_text]
        if len(duplicates) > 1:
            problems.append(f"同一状态行出现 {len(duplicates)} 次（第 {duplicates} 行）⇒ widget 与 footer 重复渲染")

    # ③ editor 下边框的下一行不应是空白（dock 紧贴 editor，不留空档）
    if not lines[border_row].strip():
        problems.append(f"editor 下边框（第 {border_row} 行）之后是空行 ⇒ dock 与 editor 之间出现空档")

    # ④ 回显行按 showLastPrompt 开关判定（只看 dock：editor 下边框之后；
    #    transcript 里 pi 自带的「↳ N lines returned」折叠提示不算）
    echo_rows = [n + 1 for n in range(border_row, args.rows) if lines[n].strip().startswith("\u21b3")]
    if read_show_last_prompt(args.cwd):
        log(
            "settings.json 的 showLastPrompt 当前为 true：回显行（↳）属预期，"
            "如需回到「无回显」基线请设为 false。",
            "WARN",
        )
    elif echo_rows:
        problems.append(f"第 {echo_rows} 行仍是上次输入回显（↳）⇒ settings.json 的 showLastPrompt: false 未生效")

    if problems:
        for item in problems:
            log(item, "ERROR")
        log(
            "dock 行数补丁未生效：未打补丁的基线是「下边框 → 状态行 → 空壳占位行」。"
            "请先跑 `bash scripts/apply_plugin_ui.sh --check` 与 `--status`。",
            "ERROR",
        )
        sys.exit(1)

    suffix = (
        "，无空壳占位行、无重复渲染、无回显行。"
        if not read_show_last_prompt(args.cwd)
        else "，无空壳占位行、无重复渲染（回显行按 showLastPrompt: true 保留）。"
    )
    log("dock 行数补丁生效：屏幕最后一行即主状态行" + suffix, "SUCCESS")


if __name__ == "__main__":
    main()
