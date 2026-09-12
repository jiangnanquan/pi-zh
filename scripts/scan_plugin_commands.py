#!/usr/bin/env python3
"""
pi-zh — 第三方插件斜杠命令简介扫描器

用途：
1. 扫描 `~/.pi/agent` 下已安装的 pi 插件，抽取全部 `pi.registerCommand(name, {...})`
   的 `description` 英文原文，作为 `i18n/plugins.json` 的维护基线。
2. 与 `i18n/plugins.json` 比对，报告「新增 / 缺失 / 原文漂移」三类差异，
   供插件升级后低成本增量补齐（对应 AGENTS.md「版本跟随」原则）。

设计约束：
- 只读取，不修改任何插件源码（汉化走运行时覆盖，见 extensions/plugin-i18n.ts）。
- 命令名（name）仅用于建立映射键，绝不改写。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DICT_PATH = REPO_ROOT / "i18n" / "plugins.json"

# 扫描时跳过的目录 / 文件
SKIP_DIRS = {"node_modules", ".git", "test", "tests", "__tests__", "coverage"}
SOURCE_SUFFIXES = (".ts", ".js", ".mjs", ".cjs")
SKIP_SUFFIXES = (".d.ts", ".map", ".min.js.map")


def log(msg, level="INFO"):
    colors = {
        "INFO": "\033[1;34m[INFO]\033[0m",
        "SUCCESS": "\033[1;32m[OK]\033[0m",
        "WARN": "\033[1;33m[WARN]\033[0m",
        "ERROR": "\033[1;31m[ERROR]\033[0m",
    }
    print(f"{colors.get(level, f'[{level}]')} {msg}")


def locate_agent_dir(custom_dir=None) -> Path:
    """定位 pi 的 agent 配置目录（默认 ~/.pi/agent）"""
    if custom_dir:
        p = Path(custom_dir).expanduser().resolve()
        if p.is_dir():
            return p
        raise FileNotFoundError(f"指定的 agent 目录不存在: {custom_dir}")
    return Path(os.environ.get("PI_AGENT_DIR", Path.home() / ".pi" / "agent")).expanduser()


def parse_package_spec(spec: str) -> str:
    """从 settings.json 的包声明中取出 npm 包名：'npm:pi-subagents@0.67.0' -> 'pi-subagents'

    仅 npm 源（含无前缀的裸包名）参与本地 node_modules 扫描；git 仓库、本地路径返回空串。
    """
    name = spec
    if spec.startswith(("git:", "file:", "path:", "http://", "https://", "ssh://", "git@")):
        return ""  # 非 npm 源（git 仓库、本地路径）不参与 node_modules 扫描
    if spec.startswith("npm:"):
        name = spec[len("npm:"):]
    if not name:
        return ""
    # 形如 github.com/user/repo 的裸仓库地址不是 npm 包名（npm 作用域包最多一个斜杠）
    if not name.startswith("@") and name.count("/") > 1:
        return ""
    # 去掉 @scope/name@version 中结尾的版本号
    if "@" in name[1:]:
        head, _, tail = name.rpartition("@")
        if re.fullmatch(r"[\dvx^~<>=.*\-+]+", tail):
            name = head
    return name


def installed_package_dirs(agent_dir: Path):
    """返回 {包名: 目录}，来源为 settings.json 的 packages 声明 + 实际 node_modules 布局"""
    settings_path = agent_dir / "settings.json"
    specs = []
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            specs = settings.get("packages", []) or []
        except Exception as exc:  # noqa: BLE001
            log(f"settings.json 解析失败：{exc}", "WARN")

    modules_root = agent_dir / "npm" / "node_modules"
    result = {}
    for spec in specs:
        pkg_name = parse_package_spec(spec)
        if not pkg_name:
            continue
        pkg_dir = modules_root / pkg_name
        if pkg_dir.is_dir():
            result[pkg_name] = pkg_dir
        else:
            log(f"插件 {pkg_name} 未安装到 {modules_root}，跳过扫描", "WARN")
    return dict(sorted(result.items()))


def source_files(pkg_dir: Path):
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if not name.endswith(SOURCE_SUFFIXES):
                continue
            if name.endswith(SKIP_SUFFIXES):
                continue
            yield Path(root) / name


STRING_LITERAL = r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`((?:[^`\\]|\\.)*)`'


def _literal_value(match: "re.Match[str]") -> str:
    """取出三选一字符串字面量的内容"""
    for group in match.groups():
        if group is not None:
            return group
    return ""


def _unescape(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except Exception:  # noqa: BLE001
        return raw


def _extract_object(text: str, start: int, limit: int = 4000) -> str:
    """从 `{` 起做括号配对，返回对象字面量文本（跳过字符串内的括号）"""
    depth = 0
    i = start
    end = min(len(text), start + limit)
    in_string = None
    while i < end:
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
        elif ch in "\"'`":
            in_string = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return text[start:end]


def _resolve_field(obj_text: str, field: str, file_text: str):
    """解析对象里 `field:` 的值；支持字符串字面量与简单标识符引用（压缩包常见写法）"""
ASSIGNMENT = re.compile(
    rf"(?:var|let|const|export\s+const|export\s+let)\s+([A-Za-z_$][\w$]*)\s*=\s*({STRING_LITERAL})"
)


def build_const_map(pkg_dir: Path):
    """建立包级「标识符 -> 字符串字面量」映射，用于解析跨文件常量引用"""
    consts = {}
    for file in source_files(pkg_dir):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for match in ASSIGNMENT.finditer(text):
            inner = re.search(STRING_LITERAL, match.group(2))
            if inner is None:
                continue
            consts.setdefault(match.group(1), _unescape(_literal_value(inner)))
    return consts


def _resolve_expr(raw: str, file_text: str, consts):
    """解析一个表达式：字符串字面量直接取值；标识符则回溯赋值（先文件内，再包级常量表）"""
    raw = raw.strip()
    if raw.startswith(('"', "'", "`")):
        return _unescape(raw[1:-1])
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", raw):
        return None
    assign = re.search(rf"(?:var|let|const|\b){re.escape(raw)}\s*=\s*({STRING_LITERAL})", file_text)
    if assign:
        inner = re.search(STRING_LITERAL, assign.group(1))
        if inner is not None:
            return _unescape(_literal_value(inner))
    return consts.get(raw)


def _resolve_field(obj_text: str, field: str, file_text: str, consts):
    """解析对象里 `field:` 的值；支持字符串字面量与标识符引用（压缩包常见写法）"""
    match = re.search(rf"(?:^|[{{,\s]){field}\s*:\s*({STRING_LITERAL}|[A-Za-z_$][\w$]*)", obj_text)
    if not match:
        return None
    return _resolve_expr(match.group(1), file_text, consts)


def extract_commands(pkg_dir: Path, consts=None):
    """抽取插件中的 {命令名: 英文简介}"""
    if consts is None:
        consts = build_const_map(pkg_dir)
    found = {}
    pattern = re.compile(
        rf"registerCommand\(\s*({STRING_LITERAL}|[A-Za-z_$][\w$]*)\s*,\s*\{{"
    )
    for file in source_files(pkg_dir):
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        if "registerCommand(" not in text:
            continue
        for match in pattern.finditer(text):
            name = _resolve_expr(match.group(1), text, consts)
            if not name:
                continue
            obj_text = _extract_object(text, text.index("{", match.start()))
            description = _resolve_field(obj_text, "description", text, consts)
            if description is None:
                continue
            found.setdefault(name, description)
    return found


def scan(agent_dir: Path):
    """返回 {包名: {命令名: 英文简介}}"""
    result = {}
    for pkg_name, pkg_dir in installed_package_dirs(agent_dir).items():
        commands = extract_commands(pkg_dir, build_const_map(pkg_dir))
        if commands:
            result[pkg_name] = dict(sorted(commands.items()))
    return result


def load_dict(path=DICT_PATH):
    if not Path(path).exists():
        return {"commands": {}}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def diff(scanned, dictionary):
    """比对扫描结果与字典，返回 (新增, 缺失, 漂移) 三类差异"""
    known = dictionary.get("commands", {})
    by_en = {entry.get("en"): name for name, entry in known.items() if entry.get("en")}

    added, drift = [], []
    seen = set()
    for pkg_name, commands in scanned.items():
        for name, description in commands.items():
            seen.add(name)
            entry = known.get(name)
            if entry is None:
                # 原文已在字典中登记为别的名字（如插件改过命令名）也算命中，避免误报
                if description in by_en:
                    continue
                added.append((pkg_name, name, description))
                continue
            if entry.get("en") != description:
                drift.append((pkg_name, name, entry.get("en", ""), description))
    missing = [
        (entry.get("source", "?"), name, entry.get("en", ""))
        for name, entry in sorted(known.items())
        if name not in seen
    ]
    return added, missing, drift


def cmd_scan(agent_dir, as_json):
    scanned = scan(agent_dir)
    if as_json:
        print(json.dumps(scanned, ensure_ascii=False, indent=2))
        return 0
    total = 0
    for pkg_name, commands in scanned.items():
        log(f"{pkg_name} — {len(commands)} 条命令")
        for name, description in commands.items():
            print(f"    /{name:<38} {description}")
        total += len(commands)
    log(f"合计 {len(scanned)} 个插件、{total} 条命令简介", "SUCCESS")
    return 0


def cmd_check(agent_dir):
    scanned = scan(agent_dir)
    dictionary = load_dict()
    added, missing, drift = diff(scanned, dictionary)

    if not (added or missing or drift):
        total = sum(len(c) for c in scanned.values())
        log(f"字典与已装插件完全一致（{len(scanned)} 个插件 / {total} 条命令）", "SUCCESS")
        return 0

    for pkg_name, name, description in added:
        log(f"新增未翻译：/{name} ({pkg_name}) — {description}", "WARN")
    for pkg_name, name, old, new in drift:
        log(f"原文漂移：/{name} ({pkg_name})\n      字典: {old}\n      现存: {new}", "WARN")
    for pkg_name, name, old in missing:
        log(f"字典残留：/{name} ({pkg_name}) 已不在插件中 — {old}", "WARN")
    log(f"差异合计：新增 {len(added)} / 漂移 {len(drift)} / 残留 {len(missing)}", "ERROR")
    return 1


def cmd_update_baseline(agent_dir):
    scanned = scan(agent_dir)
    dictionary = load_dict()
    known = dictionary.setdefault("commands", {})

    changed = 0
    for pkg_name, commands in scanned.items():
        for name, description in commands.items():
            entry = known.get(name)
            if entry is None:
                known[name] = {"source": pkg_name, "en": description, "zh": ""}
                log(f"登记新命令 /{name}（待汉化）", "WARN")
                changed += 1
            elif entry.get("en") != description:
                log(f"刷新原文 /{name}: {entry.get('en')!r} -> {description!r}", "WARN")
                entry["en"] = description
                changed += 1

    # 保持文件中的键序稳定：按来源包、再按命令名排序
    dictionary["commands"] = dict(sorted(
        known.items(), key=lambda kv: (kv[1].get("source", ""), kv[0])
    ))
    DICT_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log(f"已更新 {DICT_PATH.relative_to(REPO_ROOT)}（{changed} 处变更）", "SUCCESS")
    return 0


def main():
    parser = argparse.ArgumentParser(description="扫描已安装 pi 插件的斜杠命令简介")
    parser.add_argument("--agent-dir", help="pi agent 目录（默认 ~/.pi/agent）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出扫描结果")
    parser.add_argument("--check", action="store_true", help="与 i18n/plugins.json 比对差异")
    parser.add_argument("--update-baseline", action="store_true", help="把扫描结果写回字典基线")
    args = parser.parse_args()

    try:
        agent_dir = locate_agent_dir(args.agent_dir)
    except FileNotFoundError as exc:
        log(str(exc), "ERROR")
        return 2

    if args.update_baseline:
        return cmd_update_baseline(agent_dir)
    if args.check:
        return cmd_check(agent_dir)
    return cmd_scan(agent_dir, args.json)


if __name__ == "__main__":
    sys.exit(main())
