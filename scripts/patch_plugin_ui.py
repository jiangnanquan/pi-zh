#!/usr/bin/env python3
"""
pi-zh — 插件 UI 汉化补丁引擎（维护线 C）

与维护线 A（pi 本体）的区别：
  A 线汉化官方 dist bundle，B 线用运行时覆盖汉化插件命令简介；
  C 线处理插件「渲染期硬编码文案」——第三方插件用字面量渲染 TUI 组件，
  没有任何注册接口可拦截，只能对插件源文件打精确字面量补丁。

遵循原则：
1. 干净基底：首次打补丁前留存官方原件 `<file>.zh-backup`；已存在备份时以备份为读取源，绝不覆盖，
   因此重复运行幂等，永不「补丁叠补丁」。
2. 未命中即报错：任一条目在基底中找不到原文说明上游改了措辞（漂移），默认拒绝写盘，
   不产生半成品汉化。
3. 写盘后强制体检：调用 verify_plugin_ts.mjs 用 pi 自带的 jiti 加载器真实 import 目标文件，
   并断言渲染行宽自洽；失败立即原子回滚。
4. 命令名、变量名、品牌标题一律不收录进字典（见 i18n/plugin-ui.json 的 _update_policy）。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DICT_PATH = REPO_ROOT / "i18n" / "plugin-ui.json"
VERIFY_SCRIPT = SCRIPT_DIR / "verify_plugin_ts.mjs"
BACKUP_SUFFIX = ".zh-backup"
# 行为补丁（code_patches）的最小锚点长度：过短的片段容易误伤，且无法体现上游改动
CODE_PATCH_MIN_LENGTH = 30


def log(msg, level="INFO"):
    colors = {
        "INFO": "\033[1;34m[INFO]\033[0m",
        "SUCCESS": "\033[1;32m[OK]\033[0m",
        "WARN": "\033[1;33m[WARN]\033[0m",
        "ERROR": "\033[1;31m[ERROR]\033[0m",
    }
    print(f"{colors.get(level, f'[{level}]')} {msg}")


def load_dict(dict_path=DICT_PATH):
    with open(dict_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    targets = data.get("targets") or []
    if not targets:
        raise ValueError(f"字典中没有 target: {dict_path}")
    return data, targets


def resolve_agent_dir(override=None):
    """定位 pi agent 配置目录（插件 npm 包的家）"""
    if override:
        return Path(override).expanduser().resolve()
    env_dir = os.environ.get("PI_CODING_AGENT_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return Path.home() / ".pi" / "agent"


def locate_plugin_package(package_name, agent_dir=None, node_modules_dir=None):
    """定位插件包目录：<agent>/npm/node_modules/<package>"""
    if node_modules_dir:
        pkg_dir = Path(node_modules_dir).expanduser().resolve() / package_name
    else:
        base = agent_dir or resolve_agent_dir()
        pkg_dir = base / "npm" / "node_modules" / package_name

    pkg_json = pkg_dir / "package.json"
    if not pkg_json.exists():
        raise FileNotFoundError(f"未找到插件包 {package_name}：{pkg_dir}（该插件未安装？）")
    with open(pkg_json, "r", encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("name") != package_name:
        raise ValueError(f"{pkg_json} 的 name 字段为 {meta.get('name')!r}，与预期 {package_name!r} 不符")
    return pkg_dir, meta


def backup_path_for(file_path: Path) -> Path:
    return file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)


def ensure_backup(file_path: Path) -> bool:
    """首次打补丁时留存官方原件；已存在则绝不覆盖"""
    bp = backup_path_for(file_path)
    if bp.exists():
        return False
    shutil.copy2(file_path, bp)
    log(f"已创建安全备份: {bp.name}")
    return True


def build_patch_items(target: dict) -> list:
    """
    把两类补丁统一成同一种补丁项：
      kind=text — 汉化文案（replacements，literal / raw）
      kind=code — 经用户逐条授权的插件行为补丁（code_patches，固定 raw 精确片段）
    两类共用同一套干净基底、未命中拦截、写盘后体检与一键还原。
    """
    items = []
    for item in target.get("replacements", []):
        items.append({
            "kind": "text",
            "mode": item.get("mode", "literal"),
            "en": item["en"],
            "zh": item["zh"],
        })
    for patch in target.get("code_patches", []):
        items.append({
            "kind": "code",
            "mode": "raw",
            "en": patch["from"],
            "zh": patch["to"],
            "id": patch.get("id", ""),
            "authorized_on": patch.get("authorized_on", ""),
        })
    return items


def patch_text(content: str, replacements: list) -> tuple:
    """
    逐条精确替换。返回 (新内容, 结果列表)。

    mode = "literal"：en 必须处于引号包裹中（自动尝试双引号与单引号），
                      替换为双引号包裹的 zh —— 短词/单词的防误伤模式。
    mode = "raw"    ：en 作为任意精确子串替换，en 自身必须自带足够上下文。
    """
    results = []
    for item in replacements:
        en = item["en"]
        zh = item["zh"]
        mode = item.get("mode", "literal")
        hits = 0

        if mode == "literal":
            for quote in ('"', "'"):
                needle = f"{quote}{en}{quote}"
                count = content.count(needle)
                if count:
                    content = content.replace(needle, f'"{zh}"')
                    hits += count
        elif mode == "raw":
            hits = content.count(en)
            if hits:
                content = content.replace(en, zh)
        else:
            raise ValueError(f"未知替换模式 {mode!r}（条目: {en!r}）")

        results.append({
            "kind": item.get("kind", "text"),
            "en": en,
            "zh": zh,
            "mode": mode,
            "hits": hits,
            "id": item.get("id", ""),
            "authorized_on": item.get("authorized_on", ""),
        })

    return content, results


def validate_replacements(replacements: list):
    """字典自检：字面量模式的 en 不得含引号，raw 模式不得是裸单词"""
    problems = []
    for item in replacements:
        en = item.get("en", "")
        zh = item.get("zh", "")
        mode = item.get("mode", "literal")
        if not en or not zh:
            problems.append(f"条目缺少 en/zh: {item!r}")
            continue
        if en == zh:
            problems.append(f"条目 en 与 zh 相同（无意义翻译）: {en!r}")
        if mode == "literal" and ("\"" in en or "'" in en):
            problems.append(f"literal 模式的 en 不能含引号: {en!r}")
        if mode == "raw" and " " not in en and len(en) <= 8:
            problems.append(f"raw 模式的 en 过短，易误伤，请补上下文: {en!r}")
        if mode == "raw" and "`" in zh.replace("${", ""):
            problems.append(f"raw 模式的 zh 含裸反引号，会破坏模板字符串: {zh!r}")
    return problems


def validate_code_patches(target: dict) -> list:
    """
    行为补丁的准入校验：没有授权记录的代码改动一律拒绝入字典。
    这是 C 线红线（只改文案/模板片段）的唯一例外通道，必须留下完整审计信息。
    """
    problems = []
    for patch in target.get("code_patches", []):
        pid = patch.get("id") or "<无 id>"
        frm = patch.get("from", "")
        to = patch.get("to", "")
        if not patch.get("id"):
            problems.append("code_patches 条目缺少 id")
        if not patch.get("reason"):
            problems.append(f"code_patches[{pid}] 缺少 reason（必须写明补丁目的与依据）")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", patch.get("authorized_on", "")):
            problems.append(f"code_patches[{pid}] 缺少合法的 authorized_on（YYYY-MM-DD）")
        if len(frm) < CODE_PATCH_MIN_LENGTH:
            problems.append(f"code_patches[{pid}] from 片段过短（<{CODE_PATCH_MIN_LENGTH} 字符），易误伤")
        if not to.strip():
            problems.append(f"code_patches[{pid}] to 为空")
        if frm == to:
            problems.append(f"code_patches[{pid}] from 与 to 相同（无效补丁）")
    return problems


def verify_patched_file(file_path: Path, expect_zh: list) -> tuple:
    """用 pi 自带 jiti 加载器真实 import 目标文件，验证语法与渲染行宽"""
    if not VERIFY_SCRIPT.exists():
        return True, "未找到校验脚本，跳过语法体检"
    if not shutil.which("node"):
        return True, "未检测到 node，跳过语法体检"

    cmd = ["node", str(VERIFY_SCRIPT), "--target", str(file_path)]
    for marker in expect_zh:
        cmd += ["--expect", marker]
    if file_path.suffix == ".ts":
        cmd += ["--render-width", "110"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, " / ".join(detail[-6:]) if detail else "校验失败"
    tail = [line for line in (result.stdout or "").strip().splitlines() if line.startswith("[verify]")]
    return True, tail[-1].replace("[verify] ", "") if tail else "校验通过"


def plan_target(target, pkg_dir):
    """计算单个 target 的补丁计划（不写盘）"""
    file_path = pkg_dir / target["file"]
    if not file_path.exists():
        raise FileNotFoundError(f"目标文件不存在: {file_path}")

    bp = backup_path_for(file_path)
    base_path = bp if bp.exists() else file_path
    base_content = base_path.read_text(encoding="utf-8")

    patched, results = patch_text(base_content, build_patch_items(target))
    missing = [r for r in results if r["hits"] == 0]

    return {
        "file_path": file_path,
        "backup_path": bp,
        "base_path": base_path,
        "base_content": base_content,
        "patched_content": patched,
        "results": results,
        "missing": missing,
        "changed": patched != base_content,
    }


def report_plan(target, plan, plugin_version, source_version, strict=True, log_fn=None):
    log_fn = log_fn or log
    text_hits = sum(r["hits"] for r in plan["results"] if r["kind"] == "text")
    code_hits = sum(r["hits"] for r in plan["results"] if r["kind"] == "code")
    total = text_hits + code_hits
    rel = f"{target['package']}/{target['file']}"

    log_fn(f"[{rel}] 插件版本 v{plugin_version}（字典适配版本 v{source_version}）")
    if source_version and plugin_version and source_version != plugin_version:
        log_fn(f"[{rel}] 插件版本与字典适配版本不一致，命中检测将给出真实结论", "WARN")

    for item in plan["results"]:
        if item["kind"] == "code" and item["hits"]:
            log_fn(
                f"[{rel}] 行为补丁 {item['id']}（用户授权于 {item['authorized_on']}）命中 {item['hits']} 处"
            )

    if plan["missing"]:
        for item in plan["missing"]:
            if item["kind"] == "code":
                log_fn(
                    f"[{rel}] 行为补丁 {item['id']} 未命中（上游改了该段实现）: {item['en'].strip()[:70]!r}",
                    "ERROR",
                )
            else:
                log_fn(f"[{rel}] 未命中（上游可能改了措辞）: {item['en']!r}", "ERROR")
        if strict:
            log_fn(
                f"[{rel}] 共 {len(plan['missing'])} 条未命中，已按严格模式拒绝写盘。"
                "请人工核对上游原文后更新 i18n/plugin-ui.json（或临时加 --allow-missing 应急）。",
                "ERROR",
            )
    if not plan["changed"] and not plan["missing"]:
        log_fn(f"[{rel}] 内容已是最新状态（幂等命中 {total} 处：文案 {text_hits} + 行为补丁 {code_hits}）")
    elif plan["changed"]:
        log_fn(f"[{rel}] 计划替换：文案 {text_hits} 处，行为补丁 {code_hits} 处")
    return total


def apply_targets(targets, args, verify_override=None):
    """
    两轮流程，保证跨文件原子性：
      第一轮：全量预检（只读）。任一 target 未命中且处于严格模式 → 整体拒绝，不修改任何文件，
              避免出现「welcome.ts 汉化了、index.ts 的行为补丁没打」这类半成品状态。
      第二轮：逐个写盘 + 体检，体检失败的文件单独回滚。
    """
    do_verify = (not getattr(args, "skip_verify", False)) if verify_override is None else verify_override
    strict = not args.allow_missing

    plans = []
    blocked_files = []
    for target in targets:
        pkg_dir, meta = locate_plugin_package(
            target["package"],
            agent_dir=args.agent_dir,
            node_modules_dir=args.node_modules_dir,
        )
        log(f"目标插件: {pkg_dir}")
        plan = plan_target(target, pkg_dir)
        total = report_plan(
            target, plan, meta.get("version", "unknown"), target.get("source_version", ""), strict=strict
        )
        plans.append((target, plan, total))
        if plan["missing"] and strict:
            blocked_files.append(target["file"])

    if blocked_files:
        log(
            f"严格模式拒绝写盘：{', '.join(blocked_files)} 存在未命中条目，所有文件均保持原样。"
            "请先核对并更新 i18n/plugin-ui.json（应急可用 --allow-missing）。",
            "ERROR",
        )
        return 0, 0, blocked_files

    processed, total_changes, failures = 0, 0, []
    for target, plan, total in plans:
        if args.dry_run or not plan["changed"]:
            processed += 1
            total_changes += total
            continue

        ensure_backup(plan["file_path"])
        plan["file_path"].write_text(plan["patched_content"], encoding="utf-8")

        expect = target.get("verify_expect") or []
        ok, detail = verify_patched_file(plan["file_path"], expect) if do_verify else (True, "已跳过体检（--skip-verify）")
        if not ok:
            log(f"[{target['file']}] 体检失败，立即回滚：{detail}", "ERROR")
            shutil.copy2(plan["backup_path"], plan["file_path"])
            failures.append(target["file"])
            continue

        log(f"[{target['file']}] 已写入并体检通过（{detail}）", "SUCCESS")
        processed += 1
        total_changes += total

    return processed, total_changes, failures


def restore_targets(targets, args):
    restored = 0
    for target in targets:
        pkg_dir, _meta = locate_plugin_package(
            target["package"],
            agent_dir=args.agent_dir,
            node_modules_dir=args.node_modules_dir,
        )
        file_path = pkg_dir / target["file"]
        bp = backup_path_for(file_path)
        if not bp.exists():
            log(f"[{target['file']}] 未发现备份，无需还原")
            continue
        shutil.copy2(bp, file_path)
        bp.unlink()
        log(f"[{target['file']}] 已还原官方原版并移除备份", "SUCCESS")
        restored += 1
    return restored


def check_targets(targets, args):
    """漂移检测：不写盘，只判断字典能否在基地中全部命中"""
    problems = 0
    for target in targets:
        try:
            pkg_dir, meta = locate_plugin_package(
                target["package"],
                agent_dir=args.agent_dir,
                node_modules_dir=args.node_modules_dir,
            )
        except (FileNotFoundError, ValueError) as exc:
            log(f"{exc}", "ERROR")
            problems += 1
            continue

        plan = plan_target(target, pkg_dir)
        plugin_version = meta.get("version", "unknown")
        rel = f"{target['package']}/{target['file']}"
        if plan["missing"]:
            problems += len(plan["missing"])
            log(f"[{rel}] {len(plan['missing'])} 条未命中，字典已漂移：", "ERROR")
            for item in plan["missing"]:
                log(f"    - {item['en']!r}", "ERROR")
        else:
            hits = sum(r["hits"] for r in plan["results"])
            code = sum(1 for r in plan["results"] if r["kind"] == "code")
            extra = f"（含 {code} 条用户授权行为补丁）" if code else ""
            note = "内容已是最新" if not plan["changed"] else "可安全执行 --apply"
            log(f"[{rel}] 字典全部命中 {hits} 处{extra}（插件 v{plugin_version}，{note}）", "SUCCESS")
    return problems


def check_status(targets, args):
    for target in targets:
        try:
            pkg_dir, meta = locate_plugin_package(
                target["package"],
                agent_dir=args.agent_dir,
                node_modules_dir=args.node_modules_dir,
            )
        except (FileNotFoundError, ValueError) as exc:
            log(f"{exc}", "ERROR")
            continue

        plan = plan_target(target, pkg_dir)
        rel = f"{target['package']}/{target['file']}"
        current = plan["file_path"].read_text(encoding="utf-8")

        if plan["backup_path"].exists():
            if current == plan["patched_content"]:
                log(f"[{rel}] 状态：已应用 pi-zh 插件 UI 补丁（备份完好，可 --restore）", "SUCCESS")
            else:
                log(f"[{rel}] 状态：备份存在但当前内容与预期不一致（上游改版或人工修改），建议 --check", "WARN")
        elif any(r["hits"] and r["zh"] in current for r in plan["results"] if r["mode"] == "raw"):
            log(f"[{rel}] 状态：疑似已打过补丁但无备份（可能为手工修改），建议 --restore 前先人工确认", "WARN")
        else:
            log(f"[{rel}] 状态：官方原版（未应用汉化）", "INFO")
        log(f"[{rel}] 插件版本 v{meta.get('version', 'unknown')}；字典适配版本 v{target.get('source_version', '')}")


def main():
    parser = argparse.ArgumentParser(description="pi-zh 插件 UI 汉化补丁引擎（维护线 C）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="应用汉化补丁（幂等）")
    group.add_argument("--restore", action="store_true", help="还原官方原版")
    group.add_argument("--status", action="store_true", help="查看汉化状态")
    group.add_argument("--check", action="store_true", help="漂移检测：字典是否全部命中（不写盘）")
    group.add_argument("--dry-run", action="store_true", help="仅模拟运行，不写文件")
    parser.add_argument("--agent-dir", type=str, default=None, help="pi agent 目录（默认 ~/.pi/agent）")
    parser.add_argument("--node-modules-dir", type=str, default=None,
                        help="插件 node_modules 目录（默认 <agent-dir>/npm/node_modules）")
    parser.add_argument("--allow-missing", action="store_true", help="应急：允许部分条目未命中仍写盘")
    parser.add_argument("--skip-verify", action="store_true",
                        help="应急：跳过 jiti 加载体检（仅限离线单测，正常流程禁用）")
    parser.add_argument("--dict", type=str, default=str(DICT_PATH), help="翻译字典路径")

    args = parser.parse_args()

    try:
        _data, targets = load_dict(Path(args.dict))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log(f"字典加载失败：{exc}", "ERROR")
        sys.exit(1)

    for target in targets:
        problems = validate_replacements(target["replacements"]) + validate_code_patches(target)
        if problems:
            for p in problems:
                log(f"字典条目不合规：{p}", "ERROR")
            sys.exit(1)

    if args.restore:
        count = restore_targets(targets, args)
        log(f"还原完成：{count} 个文件恢复官方原版。" if count else "无需还原。", "SUCCESS" if count else "INFO")
        return

    if args.status:
        check_status(targets, args)
        return

    if args.check:
        problems = check_targets(targets, args)
        if problems:
            log(f"漂移检测未通过：{problems} 条未命中。", "ERROR")
            sys.exit(1)
        log("漂移检测通过：字典与已装插件完全一致。", "SUCCESS")
        return

    if args.apply or args.dry_run:
        processed, total_changes, failures = apply_targets(targets, args)
        if args.dry_run:
            log(f"[DRY-RUN] 模拟完成：{processed} 个文件、{total_changes} 处词条。", "SUCCESS")
        elif failures:
            log(f"补丁失败：{', '.join(failures)}", "ERROR")
            sys.exit(1)
        else:
            log(f"补丁应用成功：{processed} 个文件，累计替换 {total_changes} 处词条。", "SUCCESS")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
