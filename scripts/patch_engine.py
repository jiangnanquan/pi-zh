#!/usr/bin/env python3
"""
pi-zh — Pi Agent (pi-coding-agent) CLI 简体中文汉化补丁引擎
遵循原则：
1. 命令名称（name）与 flags 严格保持英文原文不变，仅汉化注释、描述与界面文本。
2. 每次打补丁均从干净基底 (.zh-backup) 应用，杜绝“补丁叠补丁”。
3. 补丁后自动通过 `node --check` 进行语法安全校验，失败立即中止并回滚。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SUPPORTED_VERSIONS = ["0.85.1", "0.86.1", "0.87.0", "0.87.1", "0.99.0", "0.99.1"]

# 次级 chunk 的选取规则：chunk 里至少命中 CHUNK_PHRASE_MIN_COUNT 条长度≥ CHUNK_PHRASE_MIN_LEN
# 的字典键，才纳入目标清单（主 chunk 按内容标记选取，不受此限）。
# 依据（2026-09-30 实测 0.99.1）：承载具体 TUI 对话框的次级 chunk 都命中多条长文案
# （信任对话框 2 条、显示图片选择器 2 条、设置列表提示 6 条）；而被第 3 方捆绑库或
# OAuth 流程顺带命中的 chunk 只有单条长文案（如 'Authentication failed'），
# 它们不是 TUI 界面，替换只会改到库/流程内部文案，故不纳入。
CHUNK_PHRASE_MIN_LEN = 20
CHUNK_PHRASE_MIN_COUNT = 2


def log(msg, level="INFO"):
    colors = {
        "INFO": "\033[1;34m[INFO]\033[0m",
        "SUCCESS": "\033[1;32m[OK]\033[0m",
        "WARN": "\033[1;33m[WARN]\033[0m",
        "ERROR": "\033[1;31m[ERROR]\033[0m",
    }
    prefix = colors.get(level, f"[{level}]")
    print(f"{prefix} {msg}")


def locate_pi_package(custom_dir=None):
    """定位全局安装的 @earendil-works/pi-coding-agent 目录"""
    if custom_dir:
        p = Path(custom_dir).resolve()
        if (p / "package.json").exists():
            return p
        raise FileNotFoundError(f"指定的目录不存在有效的 package.json: {custom_dir}")

    # 优先通过 which pi 解析符号链接真实路径
    pi_bin = shutil.which("pi")
    if pi_bin:
        real_bin = os.path.realpath(pi_bin)
        # /.../lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js
        # 向上跳 4 级到达包根目录
        pkg_root = Path(real_bin).resolve().parents[3]
        if (pkg_root / "package.json").exists():
            return pkg_root

    # 次选：通过 npm root -g 查找
    try:
        npm_root = subprocess.check_output(["npm", "root", "-g"], text=True).strip()
        pkg_root = Path(npm_root) / "@earendil-works" / "pi-coding-agent"
        if (pkg_root / "package.json").exists():
            return pkg_root.resolve()
    except Exception:
        pass

    raise FileNotFoundError("未检测到已安装的 @earendil-works/pi-coding-agent，请先确认 `which pi` 是否可用。")


def get_installed_version(pkg_dir: Path) -> str:
    pkg_json = pkg_dir / "package.json"
    with open(pkg_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("version", "unknown")


def load_i18n_data(repo_root: Path):
    """加载 i18n 规则字典"""
    i18n_dir = repo_root / "i18n"
    data = {}
    for name in ["commands", "keybindings", "settings", "cli", "ui"]:
        fp = i18n_dir / f"{name}.json"
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                data[name] = json.load(f)
        else:
            data[name] = {}
    return data


def backup_file(file_path: Path):
    """如果未曾备份，则保留干净的 .zh-backup 原文件"""
    backup_path = file_path.with_suffix(file_path.suffix + ".zh-backup")
    if not backup_path.exists():
        shutil.copy2(file_path, backup_path)
        log(f"已创建安全备份: {backup_path.name}")
    return backup_path


def restore_file(file_path: Path):
    """从 .zh-backup 恢复原始文件"""
    backup_path = file_path.with_suffix(file_path.suffix + ".zh-backup")
    if backup_path.exists():
        shutil.copy2(backup_path, file_path)
        backup_path.unlink()
        log(f"已还原: {file_path.name}")
        return True
    return False


def verify_js_syntax(file_path: Path):
    """使用 node --check 校验 JavaScript 语法"""
    result = subprocess.run(["node", "--check", str(file_path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SyntaxError(f"文件语法校验失败: {file_path}\n{result.stderr}")


def patch_slash_commands(content: str, commands_dict: dict) -> tuple[str, int]:
    """
    精确汉化斜杠命令的 description 与 argumentHint，严格锁定 name 保持英文
    """
    replaced_count = 0
    for cmd_name, item in commands_dict.items():
        zh_desc = item.get("description")
        zh_hint = item.get("argumentHint")

        # 匹配模式形如：{name:"compact",description:"..."} 或 { name: "compact", description: "..." }
        # 1. 替换 description
        if zh_desc:
            # 模式 A: name:"xxx",description:"yyy"
            pattern_a = re.compile(
                r'(\bname\s*:\s*["\']' + re.escape(cmd_name) + r'["\']\s*,\s*description\s*:\s*["\'])([^"\']+)(["\'])'
            )
            new_content, n = pattern_a.subn(r'\g<1>' + zh_desc + r'\g<3>', content)
            if n > 0:
                content = new_content
                replaced_count += n
            else:
                # 模式 B: description 在 name 前面的情况（防御性）
                pattern_b = re.compile(
                    r'(\bdescription\s*:\s*["\'])([^"\']+)(["\']\s*,\s*name\s*:\s*["\']' + re.escape(cmd_name) + r'["\'])'
                )
                new_content, n = pattern_b.subn(r'\g<1>' + zh_desc + r'\g<3>', content)
                if n > 0:
                    content = new_content
                    replaced_count += n

        # 模式 C: 内置扩展注册的命令描述 pi.registerCommand("xxx", { description: "yyy" })
        # 0.99.0 起 pi 把 mcp / codemode / tool-search / llama 等做成内置扩展，这些命令的
        # 描述随扩展模块发布（dist/extensions/<name>/index.js），不再集中在 slash-commands.js。
        # 只替换 description，命令名与参数保持英文原文。
        if zh_desc:
            pattern_c = re.compile(
                r'(registerCommand\(\s*["\']' + re.escape(cmd_name) + r'["\']\s*,\s*\{\s*description\s*:\s*["\'])([^"\']+)(["\'])'
            )
            new_content, n = pattern_c.subn(r'\g<1>' + zh_desc + r'\g<3>', content)
            if n > 0:
                content = new_content
                replaced_count += n

        # 2. 替换 argumentHint
        if zh_hint:
            pattern_hint = re.compile(
                r'(\bname\s*:\s*["\']' + re.escape(cmd_name) + r'["\'][^}]*\bargumentHint\s*:\s*["\'])([^"\']+)(["\'])'
            )
            new_content, n = pattern_hint.subn(r'\g<1>' + zh_hint + r'\g<3>', content)
            if n > 0:
                content = new_content
                replaced_count += n

    return content, replaced_count


def patch_keybindings(content: str, kb_dict: dict) -> tuple[str, int]:
    """
    汉化快捷键描述，保留 action ID 与 defaultKeys
    """
    replaced_count = 0
    for kb_id, zh_desc in kb_dict.items():
        # 匹配 "app.interrupt": { ..., description: "..." }
        pattern = re.compile(
            r'(' + re.escape(json.dumps(kb_id)) + r'\s*:\s*\{[^}]*\bdescription\s*:\s*["\'])([^"\']+)(["\'])'
        )
        new_content, n = pattern.subn(r'\g<1>' + zh_desc + r'\g<3>', content)
        if n > 0:
            content = new_content
            replaced_count += n
    return content, replaced_count


def patch_settings(content: str, settings_dict: dict) -> tuple[str, int]:
    """
    汉化交互设置菜单 label 和 description
    支持单引号、双引号、反引号以及内嵌引号与模版表达式
    """
    replaced_count = 0
    for item_id, item in settings_dict.items():
        zh_label = item.get("label")
        zh_desc = item.get("description")

        if zh_label:
            pattern_label = re.compile(
                r'(\bid\s*:\s*["\']' + re.escape(item_id) + r'["\'][\s\S]{0,150}?\blabel\s*:\s*)(["\'])(.*?)\2'
            )
            new_content, n = pattern_label.subn(r'\g<1>\g<2>' + zh_label + r'\g<2>', content)
            if n > 0:
                content = new_content
                replaced_count += n

        if zh_desc:
            pattern_desc = re.compile(
                r'(\bid\s*:\s*["\']' + re.escape(item_id) + r'["\'][\s\S]{0,350}?\bdescription\s*:\s*)(["\'`])([\s\S]*?)\2'
            )
            new_content, n = pattern_desc.subn(r'\g<1>\g<2>' + zh_desc + r'\g<2>', content)
            if n > 0:
                content = new_content
                replaced_count += n

    return content, replaced_count


def patch_cli_and_ui(content: str, cli_dict: dict, ui_dict: dict) -> tuple[str, int]:
    """
    汉化 CLI 帮助输出与 UI 短语。
    严格限制：仅匹配被引号或反引号包裹的真实字符串字面量，杜绝破坏标识符或变量名！
    """
    replaced_count = 0
    all_literals = {}
    for sec in ["header", "subcommands", "options", "diagnostics"]:
        all_literals.update(cli_dict.get(sec, {}))
    all_literals.update(ui_dict.get("exact_literals", {}))

    # 按长度降序替换：字典里存在「短键是长键前缀」的组合时（例如 'No models available'
    # 与 'No models available. '），必须先处理长键；否则短键先把长键的前缀改掉，
    # 长键就再也命不中，留下中英混排的尾巴。
    for en, zh in sorted(all_literals.items(), key=lambda kv: -len(kv[0])):
        if " " in en or "(" in en:
            # 包含空格或括号的描述文本，不可能碰撞 JS 标识符，可安全替换
            count = content.count(en)
            if count > 0:
                content = content.replace(en, zh)
                replaced_count += count
        else:
            # 单独单词（如 'Trust'）必须严格处于引号包裹内，防止误伤变量名
            pattern = re.compile(r'([\"\'`])' + re.escape(en) + r'\1')
            new_content, n = pattern.subn(r'\g<1>' + zh + r'\g<1>', content)
            if n > 0:
                content = new_content
                replaced_count += n

    return content, replaced_count


def patch_startup_banner(content: str, ui_dict: dict) -> tuple[str, int]:
    """
    汉化启动横幅提示、快速指令行与已加载资源区块头 (如 [Context] -> [上下文])
    """
    replaced_count = 0
    hints = ui_dict.get("startup_hints", {})

    # 1. 紧凑快捷栏条目 (compactInstructions)
    if "interrupt" in hints:
        content, n = re.subn(r'hint\(\s*["\']app\.interrupt["\']\s*,\s*["\']interrupt["\']\s*\)', f'hint("app.interrupt", "{hints["interrupt"]}")', content)
        replaced_count += n
    if "commands" in hints:
        content, n = re.subn(r'rawKeyHint\(\s*["\']/["\']\s*,\s*["\']commands["\']\s*\)', f'rawKeyHint("/", "{hints["commands"]}")', content)
        replaced_count += n
    if "bash" in hints:
        content, n = re.subn(r'rawKeyHint\(\s*["\']!["\']\s*,\s*["\']bash["\']\s*\)', f'rawKeyHint("!", "{hints["bash"]}")', content)
        replaced_count += n
    if "more" in hints:
        content, n = re.subn(r'hint\(\s*["\']app\.tools\.expand["\']\s*,\s*["\']more["\']\s*\)', f'hint("app.tools.expand", "{hints["more"]}")', content)
        replaced_count += n

    # 2. 展开帮助条目 (expandedInstructions)
    if "for commands" in hints:
        content, n = re.subn(r'rawKeyHint\(\s*["\']/["\']\s*,\s*["\']for commands["\']\s*\)', f'rawKeyHint("/", "{hints["for commands"]}")', content)
        replaced_count += n
    if "to run bash" in hints:
        content, n = re.subn(r'rawKeyHint\(\s*["\']!["\']\s*,\s*["\']to run bash["\']\s*\)', f'rawKeyHint("!", "{hints["to run bash"]}")', content)
        replaced_count += n
    if "to run bash (no context)" in hints:
        content, n = re.subn(r'rawKeyHint\(\s*["\']!!["\']\s*,\s*["\']to run bash \(no context\)["\']\s*\)', f'rawKeyHint("!!", "{hints["to run bash (no context)"]}")', content)
        replaced_count += n
    if "drop files" in hints and "to attach" in hints:
        content, n = re.subn(r'rawKeyHint\(\s*["\']drop files["\']\s*,\s*["\']to attach["\']\s*\)', f'rawKeyHint("{hints["drop files"]}", "{hints["to attach"]}")', content)
        replaced_count += n
    if "to expand tools" in hints:
        content, n = re.subn(r'hint\(\s*["\']app\.tools\.expand["\']\s*,\s*["\']to expand tools["\']\s*\)', f'hint("app.tools.expand", "{hints["to expand tools"]}")', content)
        replaced_count += n

    # 3. 资源区块标题 [Context] -> [上下文]
    sections = ui_dict.get("loaded_sections", {})
    for sec_en, sec_zh in sections.items():
        pat = re.compile(r'addLoadedSection\(\s*["\']' + re.escape(sec_en) + r'["\']\s*,')
        content, n = pat.subn(f'addLoadedSection("{sec_zh}",', content)
        replaced_count += n

    return content, replaced_count


def clean_text(path: Path) -> str:
    """读取文件的「干净基底」：存在 `.zh-backup` 时读备份，否则读当前文件。

    为什么重要：A 线是原位替换，文件的英文原文在打完补丁后就消失了。chunk 选取、
    预检、覆盖率判定都必须基于干净基底，否则会出现「打完补丁 → 文件不再命中字典键 →
    下次选取时掉出目标清单 → 预检误报残留」的循环假象。
    """
    backup = path.with_suffix(path.suffix + ".zh-backup")
    src = backup if backup.exists() else path
    try:
        return src.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def literal_keys(i18n: dict) -> list:
    """A 线按「字面量整串替换」处理的字典键：cli.* 与 ui.exact_literals。"""
    keys = []
    for sec in ("header", "subcommands", "options", "diagnostics"):
        keys.extend(i18n.get("cli", {}).get(sec, {}).keys())
    keys.extend(i18n.get("ui", {}).get("exact_literals", {}).keys())
    return keys


def collect_target_files(pkg_dir: Path, literal_keys_list=None) -> list:
    """收集需要打补丁的目标文件（顺序稳定、无重复）。

    独立成函数，供 apply_patch 与 scripts/check_patch_safety.py（字典键逻辑值用法预检）共用，
    保证「预检扫描的文件集合」与「实际写盘的文件集合」永远一致。

    literal_keys_list 为 None 时只按内容标记选 chunk（兼容旧调用）；传入字典键列表后，
    会额外纳入「承载具体 TUI 对话框」的次级 chunk（见 CHUNK_PHRASE_MIN_LEN 的说明）。
    """
    target_files = []
    phrase_keys = [k for k in (literal_keys_list or []) if len(k) >= CHUNK_PHRASE_MIN_LEN]

    # 1. 核心运行时 bundle chunk (包含所有交互逻辑)
    chunks_dir = pkg_dir / "dist" / "bundle" / "chunks"
    if chunks_dir.exists():
        for chunk in chunks_dir.glob("chunk-*.js"):
            content_sample = clean_text(chunk)
            is_main = ("BUILTIN_SLASH_COMMANDS" in content_sample
                       or "app.interrupt" in content_sample)
            is_ui_chunk = sum(1 for k in phrase_keys if k in content_sample) >= CHUNK_PHRASE_MIN_COUNT
            if is_main or is_ui_chunk:
                target_files.append(chunk)

    # 2. 模块级文件
    modular_candidates = [
        pkg_dir / "dist" / "core" / "slash-commands.js",
        pkg_dir / "dist" / "core" / "keybindings.js",
        pkg_dir / "dist" / "cli" / "args.js",
        pkg_dir / "dist" / "modes" / "interactive" / "interactive-mode.js",
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "model-selector.js",
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "settings-selector.js",
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "settings-submenu.js",
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "scoped-models-selector.js",
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "oauth-selector.js",
        # 0.99.0 新增展示面：资源来源标签（config-selector）与首次设置里的系统主题说明
        # （first-time-setup）。新增组件文件前必须先跑 scripts/check_patch_safety.py，
        # 确认字典键在该文件里没有「被当作逻辑值」的用法（如 message == "Request was aborted"）。
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "config-selector.js",
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "first-time-setup.js",
        # 信任对话框选项标签（纯展示：逻辑另由 trusted / updates 字段承载）
        pkg_dir / "dist" / "core" / "trust-manager.js",
        # 会话选择器（All / Current Folder 标签）与显示图片选择器
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "session-selector.js",
        pkg_dir / "dist" / "modes" / "interactive" / "components" / "show-images-selector.js",
    ]

    # 3. 内置扩展：0.99.0 起 mcp / codemode / tool-search / llama 以扩展模块形态发布，
    #    其斜杠命令描述与对话框文案只存在于 dist/extensions/<name>/{index,ui}.js。
    for pattern in ("*/index.js", "*/ui.js"):
        modular_candidates.extend(sorted((pkg_dir / "dist" / "extensions").glob(pattern)))

    seen = set()
    for mf in modular_candidates:
        if mf.exists() and mf not in seen:
            seen.add(mf)
            target_files.append(mf)

    return target_files


def apply_patch(pkg_dir: Path, repo_root: Path, force=False, dry_run=False):
    version = get_installed_version(pkg_dir)
    log(f"目标包路径: {pkg_dir}")
    log(f"检测到版本: v{version}")

    if version not in SUPPORTED_VERSIONS:
        msg = f"当前版本 v{version} 不在已知适配清单 ({', '.join(SUPPORTED_VERSIONS)}) 中！"
        if not force:
            log(msg, "ERROR")
            log("如需强制尝试，请使用 --force 参数。", "WARN")
            sys.exit(1)
        else:
            log(f"{msg} 已指定 --force，继续执行...", "WARN")

    i18n = load_i18n_data(repo_root)

    # 寻找需要处理的目标文件
    target_files = collect_target_files(pkg_dir, literal_keys(i18n))

    log(f"共发现 {len(target_files)} 个目标补丁文件。")

    total_changes = 0
    modified_files = []

    for target in target_files:
        rel_name = target.relative_to(pkg_dir)
        # 读取基底内容：若已存在 .zh-backup，则基于备份文件读取原文；否则读取当前文件
        backup = target.with_suffix(target.suffix + ".zh-backup")
        src_path = backup if backup.exists() else target

        with open(src_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        content = original_content
        file_replaced = 0

        # 应用命令汉化
        content, n1 = patch_slash_commands(content, i18n["commands"])
        file_replaced += n1

        # 应用快捷键汉化
        content, n2 = patch_keybindings(content, i18n["keybindings"])
        file_replaced += n2

        # 应用设置项汉化
        content, n3 = patch_settings(content, i18n["settings"])
        file_replaced += n3

        # 应用 CLI & UI 汉化
        content, n4 = patch_cli_and_ui(content, i18n["cli"], i18n["ui"])
        file_replaced += n4

        # 应用启动横幅与资源区块汉化
        content, n5 = patch_startup_banner(content, i18n["ui"])
        file_replaced += n5

        if content != original_content:
            total_changes += file_replaced
            log(f"[{rel_name}] 命中并替换 {file_replaced} 处词条。")
            if not dry_run:
                # 确保安全备份存在
                backup_file(target)
                # 写入目标文件
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
                # 语法校验
                try:
                    verify_js_syntax(target)
                except SyntaxError as e:
                    log(f"校验失败，立即回滚 {rel_name}: {e}", "ERROR")
                    restore_file(target)
                    sys.exit(1)
                modified_files.append(target)
        else:
            log(f"[{rel_name}] 无变化或已为最新汉化状态。")

    if dry_run:
        log(f"[DRY-RUN] 模拟完成，预计修改 {total_changes} 处。", "SUCCESS")
    else:
        log(f"补丁应用成功！共处理 {len(modified_files)} 个文件，累计替换 {total_changes} 处词条。", "SUCCESS")


def restore_all(pkg_dir: Path):
    log(f"正在从备份还原官方原版: {pkg_dir}")
    count = 0
    for root, _, files in os.walk(pkg_dir / "dist"):
        for f in files:
            if f.endswith(".zh-backup"):
                backup_path = Path(root) / f
                orig_path = backup_path.with_suffix("")
                shutil.copy2(backup_path, orig_path)
                backup_path.unlink()
                count += 1
                log(f"已恢复: {orig_path.name}")

    if count > 0:
        log(f"还原完成！成功恢复 {count} 个官方原版文件。", "SUCCESS")
    else:
        log("未发现任何备份文件，无需还原。", "INFO")


def check_status(pkg_dir: Path):
    version = get_installed_version(pkg_dir)
    log(f"目标包: {pkg_dir}")
    log(f"版本: v{version}")
    backups = list((pkg_dir / "dist").rglob("*.zh-backup")) if (pkg_dir / "dist").exists() else []
    if backups:
        log(f"当前状态: 已应用 pi-zh 汉化补丁 (检测到 {len(backups)} 个备份文件)", "SUCCESS")
    else:
        log("当前状态: 官方原版 (未应用补丁)", "INFO")


def main():
    parser = argparse.ArgumentParser(description="pi-zh 汉化补丁引擎")
    parser.add_argument("--apply", action="store_true", help="应用汉化补丁")
    parser.add_argument("--restore", action="store_true", help="还原官方原版")
    parser.add_argument("--status", action="store_true", help="检查汉化状态")
    parser.add_argument("--dry-run", action="store_true", help="仅模拟运行，不写文件")
    parser.add_argument("--force", action="store_true", help="跨版本强制打补丁")
    parser.add_argument("--pkg-dir", type=str, default=None, help="自定义 pi-coding-agent 安装目录")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    try:
        pkg_dir = locate_pi_package(args.pkg_dir)
    except FileNotFoundError as e:
        log(str(e), "ERROR")
        sys.exit(1)

    if args.restore:
        restore_all(pkg_dir)
    elif args.status:
        check_status(pkg_dir)
    elif args.apply or args.dry_run:
        apply_patch(pkg_dir, repo_root, force=args.force, dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
