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


if __name__ == "__main__":
    unittest.main()
