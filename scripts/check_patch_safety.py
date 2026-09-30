#!/usr/bin/env python3
"""pi-zh — A 线打补丁前的只读预检（预检先于写盘）。

回答两个问题，两者都靠真实文件而非人工记忆：

1. **覆盖率**：字典里的字面量键，有几个在目标文件里「一次都没命中」？
   上游改措辞、删设置项、改命令名时，字典会静默地变成残留条目（旧键不再匹配，新文案留英文）。
   引擎的 dry-run 只统计命中数，报不出这个 —— 本脚本补上。

2. **逻辑值冲突**：字典键是否被当作**逻辑值**在代码里比较（`x === "key"`、`case "key"`、
   `{ "key": ... }` 映射键）？一旦如此，只有「该字符串的全部出现位置都在目标文件集合内」
   才能保证替换后逻辑自洽（两侧同时变成中文）；只要有一处出现在未打补丁的文件里
   （例如 SDK、provider 模块），替换就会让判断永远为假。

   实测案例：`"Request was aborted"` 的消费者在
   `dist/modes/interactive/components/assistant-message.js`（可作目标文件），
   但产者在未打补丁的 SDK 里 —— 因此该文件不得加入目标清单，否则中止态检测会失效。

用法：
    python3 scripts/check_patch_safety.py            # 全部检查
    python3 scripts/check_patch_safety.py --coverage # 只看覆盖率（字典残留/未命中）
    python3 scripts/check_patch_safety.py --safety   # 只看逻辑值冲突

退出码：发现「危险」逻辑值用法时为 1，否则 0（残留条目不阻断，只提示）。
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from patch_engine import clean_text, collect_target_files, literal_keys, load_i18n_data, locate_pi_package, log  # noqa: E402

LITERAL_SECTIONS = ("header", "subcommands", "options", "diagnostics")
DIST_SKIP_DIRS = ("node_modules", "docs", "examples")


def collect_literal_keys(i18n: dict) -> dict:
    """收集 A 线全部「按字面量整串替换」的键：cli.* 与 ui.exact_literals。"""
    keys = {}
    for sec in LITERAL_SECTIONS:
        for en, zh in i18n["cli"].get(sec, {}).items():
            keys[en] = f"cli.{sec}"
    for en, zh in i18n["ui"].get("exact_literals", {}).items():
        keys[en] = "ui.exact_literals"
    return keys


def read_js_files(root: Path) -> dict:
    """读取 dist 下所有 .js（跳过 sourcemap 与第三方/文档目录），返回 {相对路径: 文本}。

    注意：**不剥注释**。曾用自写的行注释剥离器，遇到正则字面量（如 `/['"]/g`）会把状态机
    带进字符串态、吞掉文件后半段（`session-selector.js` 因此整文件漏扫）。判定逻辑已改为
    「精确字面量提取」，注释里的同名文字不会被当成字面量，无需任何预处理。
    """
    out = {}
    for p in root.rglob("*.js"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in DIST_SKIP_DIRS for part in rel.split("/")):
            continue
        try:
            out[rel] = clean_text(p)
        except OSError:
            continue
    return out


def comparison_patterns(key: str) -> tuple:
    """逻辑值用法（比较 / case / 映射键）。注意排除三元表达式误报：
    形如 `? "key" : other` 的返回分支会命中 `"key":`，但那是展示值而非逻辑值，
    因此映射键模式要求冒号后**不是**表达式分隔（用 `":` 后跟非空白或换行判断不了，
    改为要求在映射/对象上下文里出现 `{` 或 `,` 前缀）。"""
    return (
        f'==="{key}"',
        f"==='{key}'",
        f'"{key}"===',
        f"'{key}'===",
        f'== "{key}"',
        f"== '{key}'",
        f'case "{key}"',
        f"case '{key}'",
        f'{{"{key}":',
        f"{{ '{key}':",
        f',"{key}":',
        f", '{key}':",
    )


def check_coverage(blob: dict, target_rels: set, keys: dict):
    """字典键在目标文件里的命中情况（按原文子串，与引擎的替换方式一致）。

    已知盲点（改用「字面量内命中」反而更差，故保留此口径）：注释里出现同名文字
    （如 `// no results`）会被算作命中；反向的「字面量内命中」又会被含嵌套引号的
    模板串漏报（`model-selector.js` 的 `no results` 就是这样消失的）。
    """
    log("覆盖率检查（字典键是否仍然命中目标文件）", "STEP")
    stale = []
    for key, section in sorted(keys.items()):
        hits = [rel for rel in target_rels if key in blob.get(rel, "")]
        if not hits:
            stale.append((key, section))
    if not stale:
        log(f"全部 {len(keys)} 个键均在目标文件中至少命中 1 次。", "SUCCESS")
        return 0
    log(f"{len(stale)} 个键未命中任何目标文件（上游可能改了措辞 / 删了条目）:", "WARN")
    for key, section in stale:
        log(f"    [{section}] {key!r}", "WARN")
    return len(stale)


LITERAL_RE = None


def literals_of(text: str) -> set:
    """提取文件中的字符串 / 模板字面量（已去注释）。用于「精确字面量相等」判定。"""
    global LITERAL_RE
    if LITERAL_RE is None:
        import re
        LITERAL_RE = re.compile(r"""(["'`])((?:\\.|(?!\1)[^\\])*)\1""", re.S)
    return {raw for _, raw in LITERAL_RE.findall(text)}


def check_safety(blob: dict, target_rels: set, keys: dict, confirmed: dict | None = None):
    """逻辑值一致性检查（字典键是否参与代码判断）。

    判定口径：若某键被用作逻辑值（`x === "key"`、`case "key"`、映射键），
    则它的每一处出现都必须在**同一批可替换范围**内，否则会出现一处中文一处英文的错配：

    - **危险**：比较点在目标文件内，但精确字面量也存在于未打补丁的文件 → 打完后
      判断侧变中文、产者仍英文（正是 2026-09-30 拓出的 `Login cancelled`）；
    - **已确认例外**：确认属于「同文件内产者+比较点」的跨模式副本（详见
      `i18n/ui.json` 的 `confirmed_comparisons`，带核对日期与理由）；
    - **提示**：比较点与字面量都在目标文件内 → 替换后两侧同时变中文，逻辑自洽。

    退出码只受「危险」影响。
    """
    confirmed = confirmed or {}
    log("逻辑值冲突检查（字典键是否参与代码判断）", "STEP")
    lits = {rel: literals_of(text) for rel, text in blob.items()}
    dangers, notes, reviewed = [], [], []
    for key in sorted(keys):
        pats = comparison_patterns(key)
        cmp_files = sorted(rel for rel, text in blob.items() if any(p in text for p in pats))
        if not cmp_files:
            continue
        lit_files = sorted(rel for rel, ls in lits.items() if key in ls)
        cmp_in = [r for r in cmp_files if r in target_rels]
        lit_out = [r for r in lit_files if r not in target_rels]
        cmp_out = [r for r in cmp_files if r not in target_rels]
        if cmp_in and lit_out:
            if key in confirmed:
                reviewed.append((key, cmp_in, lit_out, confirmed[key]))
            else:
                dangers.append((key, cmp_in, lit_out))
        elif cmp_out:
            notes.append((key, cmp_out, [r for r in lit_files if r in target_rels]))
        elif cmp_in:
            notes.append((key, cmp_in, [r for r in lit_files if r in target_rels]))

    for key, cmp_target, outside in dangers:
        log(f"危险：{key!r}", "ERROR")
        log(f"    逻辑比较处（目标文件）: {', '.join(cmp_target)}", "ERROR")
        log(f"    但精确字面量也存在于未打补丁的文件: {', '.join(outside[:3])}"
            + (" …" if len(outside) > 3 else ""), "ERROR")
        log("    处置：从字典移除该键（保英文，保逻辑）；确认属于跨模式副本可登记至 "
            "i18n/ui.json 的 confirmed_comparisons（带理由与日期）", "ERROR")
    for key, cmp_files, lit_out, reason in reviewed:
        log(f"已确认例外：{key!r}（{', '.join(cmp_files[:2])} ⇄ {', '.join(lit_out[:2])}）"
            f"\n    理由：{reason}", "WARN")
    for key, cmp_files, lit_inside in notes:
        log(f"提示：{key!r} 参与判断（{', '.join(cmp_files[:2])}）"
            + (f"，字面量在目标文件内：{', '.join(lit_inside[:2])}" if lit_inside else "，字面量不在目标文件内"),
            "WARN")
    if not dangers and not notes and not reviewed:
        log(f"全部 {len(keys)} 个键均未参与代码判断。", "SUCCESS")
    elif not dangers:
        log(f"无危险用法；{len(notes) + len(reviewed)} 条参与判断的键已逐条列出/确认。", "SUCCESS")
    return len(dangers)


def main():
    parser = argparse.ArgumentParser(description="A 线打补丁前只读预检")
    parser.add_argument("--coverage", action="store_true", help="只看字典覆盖率（残留/未命中）")
    parser.add_argument("--safety", action="store_true", help="只看逻辑值冲突")
    parser.add_argument("--pkg-dir", help="指定 pi-coding-agent 安装目录")
    args = parser.parse_args()
    both = not (args.coverage or args.safety)

    try:
        pkg_dir = locate_pi_package(args.pkg_dir)
    except FileNotFoundError as e:
        log(str(e), "ERROR")
        return 1

    dist = pkg_dir / "dist"
    i18n = load_i18n_data(REPO_ROOT)
    target_files = collect_target_files(pkg_dir, literal_keys(i18n))
    target_rels = {p.relative_to(dist).as_posix() for p in target_files}
    blob = read_js_files(dist)
    keys = collect_literal_keys(load_i18n_data(REPO_ROOT))
    confirmed = load_i18n_data(REPO_ROOT).get("ui", {}).get("confirmed_comparisons", {})

    log(f"目标包: {pkg_dir}")
    log(f"目标文件 {len(target_rels)} 个；字典字面量键 {len(keys)} 个；扫描文件 {len(blob)} 个")

    dangers = 0
    if both or args.coverage:
        check_coverage(blob, target_rels, keys)
    if both or args.safety:
        dangers = check_safety(blob, target_rels, keys, confirmed)
    return 1 if dangers else 0


if __name__ == "__main__":
    sys.exit(main())
