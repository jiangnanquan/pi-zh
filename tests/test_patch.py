#!/usr/bin/env python3
"""
pi-zh 单元测试与契约校验
验证汉化规则字典与替换引擎的核心红线：
1. 斜杠命令的 name 100% 保持英文，仅 description 与 argumentHint 汉化
2. 快捷键标识符与按键组合不被污染，仅 description 汉化
3. 纯英文字符串替换不污染代码标识符
"""

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
import sys
sys.path.insert(0, str(SCRIPTS_DIR))
import patch_engine


class TestPiZhContract(unittest.TestCase):
    def setUp(self):
        self.i18n = patch_engine.load_i18n_data(REPO_ROOT)

    def test_commands_contract(self):
        """验证命令表：仅汉化注释，name 不变"""
        commands = self.i18n["commands"]
        self.assertGreaterEqual(len(commands), 20, "命令总数应不少于 20 条")

        sample_code = """
var BUILTIN_SLASH_COMMANDS = [
    { name: "settings", description: "Open settings menu" },
    { name: "model", description: "Select model (opens selector UI)", argumentHint: "<provider/model>" },
    { name: "compact", description: "Manually compact the session context" }
];
"""
        patched, count = patch_engine.patch_slash_commands(sample_code, commands)
        self.assertGreater(count, 0)
        # 验证 name 严格保持英文
        self.assertIn('name: "settings"', patched)
        self.assertIn('name: "model"', patched)
        self.assertIn('name: "compact"', patched)
        # 验证 description 成功汉化
        self.assertIn("打开设置菜单", patched)
        self.assertIn("选择模型（打开选择器界面）", patched)
        self.assertIn("手动压缩会话上下文", patched)
        self.assertIn("<服务商/模型>", patched)

    def test_keybindings_contract(self):
        """验证快捷键表：action ID 保持不变，description 汉化"""
        kb = self.i18n["keybindings"]
        self.assertGreaterEqual(len(kb), 30, "快捷键总数应不少于 30 条")

        sample_code = """
export const KEYBINDINGS = {
    "app.interrupt": { defaultKeys: "escape", description: "Cancel or abort" },
    "app.clear": { defaultKeys: "ctrl+c", description: "Clear editor" }
};
"""
        patched, count = patch_engine.patch_keybindings(sample_code, kb)
        self.assertGreater(count, 0)
        self.assertIn('"app.interrupt"', patched)
        self.assertIn('"app.clear"', patched)
        self.assertIn("defaultKeys: \"escape\"", patched)
        self.assertIn("取消或中止当前操作", patched)
        self.assertIn("清空输入框", patched)

    def test_settings_contract(self):
        """验证设置菜单项汉化，覆盖模版反引号、内嵌单引号及跨行格式"""
        settings = self.i18n["settings"]
        self.assertGreaterEqual(len(settings), 30, "设置项总数应不少于 30 条")

        sample_code = """
items = [
    { id: "autocompact", label: "Auto-compact", description: "Automatically compact context when it gets too large" },
    { id: "steering-mode", label: "Steering mode", description: "Enter while streaming queues steering messages. 'one-at-a-time': deliver one, wait for response. 'all': deliver all at once." },
    { id: "follow-up-mode", label: "Follow-up mode", description: `${followUpKey} queues follow-up messages until agent stops. 'one-at-a-time': deliver one, wait for response. 'all': deliver all at once.` },
    { id: "cache-miss-notices", label: "Cache miss notices", description: "Show transcript notices for cache costs and provider recovery diagnostics" }
];
"""
        patched, count = patch_engine.patch_settings(sample_code, settings)
        self.assertEqual(count, 8, "4 个设置项应各有 label 和 description 被成功汉化，共 8 处")
        self.assertIn('"自动压缩上下文"', patched)
        self.assertIn('"当会话上下文过大时自动执行压缩"', patched)
        self.assertIn('"实时转向模式"', patched)
        self.assertIn('"跟进消息模式"', patched)
        self.assertIn('`${followUpKey} 排队跟进', patched)
        self.assertIn('"缓存未命中提示"', patched)
        self.assertIn('"在会话记录中显示缓存成本与提供商恢复诊断提示"', patched)

    def test_red_line_identifier_isolation(self):
        """红线测试：字面量替换不得误伤变量名或标识符"""
        ui = {"exact_literals": {"Trust": "信任"}}
        cli = {}
        # 变量名 defaultProjectTrust 绝对不能被替换为 defaultProject信任
        sample_code = """
let defaultProjectTrust = "Trust";
let isTrustMode = true;
"""
        patched, count = patch_engine.patch_cli_and_ui(sample_code, cli, ui)
        self.assertEqual(count, 1)
        self.assertIn('let defaultProjectTrust = "信任";', patched)
        self.assertIn('let isTrustMode = true;', patched)
        self.assertNotIn("defaultProject信任", patched)

    def test_startup_banner_contract(self):
        """验证启动横幅与资源区块汉化"""
        ui = self.i18n["ui"]
        sample_code = """
compactInstructions=[hint("app.interrupt","interrupt"),rawKeyHint("/","commands"),rawKeyHint("!","bash"),hint("app.tools.expand","more")];
addLoadedSection("Context", contextCompactList, contextList);
"""
        patched, count = patch_engine.patch_startup_banner(sample_code, ui)
        self.assertGreater(count, 0)
        self.assertIn('"中断"', patched)
        self.assertIn('"命令"', patched)
        self.assertIn('"执行终端"', patched)
        self.assertIn('"更多"', patched)
        self.assertIn('addLoadedSection("上下文"', patched)

    def test_model_selector_contract(self):
        """验证模型选择器与交互菜单提示汉化"""
        ui = self.i18n["ui"]
        cli = self.i18n["cli"]

        # 模拟 bundle chunk 与 modular 组件代码
        sample_chunk = """
hintText="Only showing models from configured providers. Use /login to add providers.";
this.listContainer.addChild(new Text(theme.fg("muted","  No matching models"),0,0));
this.refreshStatusMessage="Model catalogs refreshed.";
this.addChild(new Text(theme.fg("dim",`  ${keyDisplayText("tui.select.confirm")} to select \\xB7 ${keyDisplayText("app.models.save")} to set as default \\xB7 ${keyDisplayText("tui.select.cancel")} to cancel`),0,0));
const hint="  Type to filter \\xB7 Enter to select \\xB7 Esc to go back";
"""
        patched, count = patch_engine.patch_cli_and_ui(sample_chunk, cli, ui)
        self.assertGreaterEqual(count, 5)
        self.assertIn("仅显示已配置提供商的模型。使用 /login 添加提供商。", patched)
        self.assertIn("未找到匹配的模型", patched)
        self.assertIn("模型目录已刷新。", patched)
        self.assertIn("确认选择 ·", patched)
        self.assertIn("设为默认 ·", patched)
        self.assertIn("取消`", patched)
        self.assertIn("输入文字过滤 · Enter 确认选择 · Esc 返回", patched)

    def test_update_notice_contract(self):
        """启动升级通知汉化：6 条文案命中，且不误伤 collapseChangelog 属性名

        回归背景：2026-09-17 首次为「新版本 / 插件包可更新」横幅补字典时，
        裸串 "Changelog: " 把源码中的 `collapseChangelog: ` 属性名一起替换了，
        被引擎的 node --check 拦下并原子回滚；随后将 key 收紧为带引号的 "\"Changelog: \""。
        """
        ui = self.i18n["ui"]
        cli = {}
        sample_code = (
            'const action = theme.fg("accent", `${APP_NAME} update --extensions`);\n'
            'const updateInstruction = theme.fg("muted", `New version ${release.version} is available. Run `) + action;\n'
            'const changelogLine = theme.fg("muted", "Changelog: ") + changelogLink;\n'
            'new Text(`${theme.bold(theme.fg("warning", "Update Available"))}`, 1, 0);\n'
            'collapseChangelog: this.settingsManager.getCollapseChangelog(),\n'
            'const pkgHint = theme.fg("muted", "Package updates are available. Run ");\n'
            'const header = theme.fg("warning", "Package Updates Available");\n'
            'const label = theme.fg("muted", "Packages:");\n'
        )
        patched, count = patch_engine.patch_cli_and_ui(sample_code, cli, ui)

        # 1) 新版本通知 3 条
        self.assertIn("新版本 ${release.version} 已发布，运行 ", patched)
        self.assertIn('"更新日志："', patched)
        self.assertIn('"发现新版本"', patched)
        # 2) 插件包更新通知 3 条
        self.assertIn("以下插件包有可用更新，运行 ", patched)
        self.assertIn('"插件包可更新"', patched)
        self.assertIn('"插件包："', patched)
        # 3) 红线：命令 action 保持英文（不得被字典吞掉）
        self.assertIn("${APP_NAME} update --extensions", patched)
        # 4) 红线：属性名 collapseChangelog 与 getCollapseChangelog() 绝不能被污染
        self.assertIn("collapseChangelog: this.settingsManager.getCollapseChangelog(),", patched)
        self.assertNotIn("collapse更新日志", patched)
        self.assertEqual(count, 6, "应恰好命中 6 条通知文案，多一条即为误伤信号")

    def test_diagnostics_contract(self):
        """验证 CLI 参数报错文案汉化：8 条命中，且 ${} 占位符与 flag 名严格保持原样

        覆盖范围：2026-09-23 补齐 `args.js` 的 diagnostics 错误提示——
        6 条 0.87.0 既有（--name / --use-theme / --tui-mode / thinking level /
        Unknown option）+ 2 条 0.87.1 新增（--mode 缺值与非法值），此前从未汉化。
        红线：`${...}` 模板占位符、flag 名与有效值字面量必须原样保留。
        """
        cli = self.i18n["cli"]
        self.assertGreaterEqual(len(cli.get("diagnostics", {})), 15, "报错文案应不少于 15 条")

        # 高频项：Unknown option 系列（含复数变体与 3 个 for-command 分支）
        plural_en = '`Unknown option${unknownFlags.length===1?"":"s"}: ${unknownFlags.map(name=>`--${name}`).join(", ")}`'
        self.assertIn(plural_en, cli["diagnostics"], "复数变体应已入字典")
        self.assertEqual(
            cli["diagnostics"][plural_en],
            '`未知选项: ${unknownFlags.map(name=>`--${name}`).join(", ")}`',
            "复数逻辑应被移除——中文无单复数，且必须保留嵌套模板表达式",
        )
        self.assertIn(
            '`未知选项 ${arg}（"config" 命令）`',
            cli["diagnostics"].values(),
            "for-command 分支应译为「（… 命令）」形态",
        )
        # 中频项：双引号串 + 真实换行的跨行模板串（不得误写成 \\n 转义序列）
        self.assertIn(
            "--api-key requires a model to be specified via --model, --provider/--model, or --models",
            cli["diagnostics"],
        )
        cross_line_en = '`Invalid models.json schema:\n${errors}\n\nFile: ${path14}`'
        self.assertIn(cross_line_en, cli["diagnostics"], "跨行模板串 key 必须用真实换行")
        self.assertNotIn(
            '`Invalid models.json schema:\\n${errors}\\n\\nFile: ${path14}`',
            cli["diagnostics"],
            "不得用 \\n 转义序列形态（与源文件逐字节不符，会静默不命中）",
        )

        sample_code = (
            'result.diagnostics.push({ type: "error", message: "--mode requires text, json, or rpc" });\n'
            'result.diagnostics.push({ type: "error", message: `Invalid mode "${mode}". Valid values: text, json, rpc` });\n'
            'result.diagnostics.push({ type: "error", message: "--name requires a value" });\n'
            'result.diagnostics.push({ type: "warning", message: `Invalid thinking level "${level}". Valid values: ${VALID_THINKING_LEVELS.join(", ")}` });\n'
            'result.diagnostics.push({ type: "error", message: "--use-theme requires a theme name" });\n'
            'result.diagnostics.push({ type: "error", message: "--tui-mode requires regular or fullscreen" });\n'
            'result.diagnostics.push({ type: "error", message: `Invalid TUI mode "${mode}". Valid values: regular, fullscreen` });\n'
            'result.diagnostics.push({ type: "error", message: `Unknown option: ${arg}` });\n'
        )
        patched, count = patch_engine.patch_cli_and_ui(sample_code, cli, {})
        self.assertEqual(count, 8, "应恰好命中 8 条报错文案，多一条即为误伤信号")

        # 1) 汉化生效
        self.assertIn('"--mode 需要指定 text、json 或 rpc"', patched)
        self.assertIn('`无效的模式 "${mode}"。有效值: text、json、rpc`', patched)
        self.assertIn('"--name 需要指定一个值"', patched)
        self.assertIn('"--use-theme 需要指定主题名称"', patched)
        self.assertIn('"--tui-mode 需要指定 regular 或 fullscreen"', patched)
        self.assertIn('`无效的 TUI 模式 "${mode}"。有效值: regular、fullscreen`', patched)
        self.assertIn('`未知选项: ${arg}`', patched)
        # 2) 红线：${} 模板占位符（含内嵌 JS 表达式）保持原样
        self.assertIn('`无效的思考级别 "${level}"。有效值: ${VALID_THINKING_LEVELS.join(", ")}`', patched)
        self.assertIn('${arg}', patched)
        # 3) 红线：flag 名与合法值字面量保留英文（命令/参数名锁定原文）
        self.assertIn('--mode 需要指定 text、json 或 rpc', patched)
        self.assertIn('--tui-mode 需要指定 regular 或 fullscreen', patched)


if __name__ == "__main__":
    unittest.main()
