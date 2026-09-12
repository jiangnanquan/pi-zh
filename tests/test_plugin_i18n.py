#!/usr/bin/env python3
"""
pi-zh — 插件简介汉化模块的单元测试与契约校验

覆盖三类红线与一类维护能力：
1. 字典结构完整：每条都有 source / en / zh，且 zh 已汉化、无残留英文占位；
2. 参数原名 100% 保留：`--flag`、`/command`、`<placeholder>`、`~/.pi/...` 路径、
   `[a|b|c]` 选项组在中文里必须与英文原文逐字一致；
3. 扫描器能在四种写法下正确抽取命令名与简介（字符串字面量 / 同文件变量 /
   跨文件常量 / 压缩包 `var f="x",C="y"` 写法）；
4. 漂移检测：新增、原文漂移、字典残留三类差异都能报出。
"""

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scan_plugin_commands as scanner  # noqa: E402

DICT_PATH = REPO_ROOT / "i18n" / "plugins.json"
CJK = re.compile(r"[\u4e00-\u9fff]")


class TestPluginI18nContract(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
        self.commands = self.data["commands"]

    # ---------- 字典结构 ----------

    def test_dict_structure(self):
        """每条命令都必须有来源、英文原文基线与中文简介"""
        self.assertGreaterEqual(len(self.commands), 30, "插件命令条目应不少于 30 条")
        for name, entry in self.commands.items():
            with self.subTest(command=name):
                self.assertRegex(name, r"^[a-z][a-z0-9:-]*$", "命令名必须保持英文小写形式")
                for field in ("source", "en", "zh"):
                    self.assertIn(field, entry, f"缺少字段 {field}")
                    self.assertTrue(entry[field].strip(), f"字段 {field} 不得为空")
                self.assertNotIn("\n", entry["zh"], "中文简介不得包含换行")

    def test_zh_is_actually_chinese(self):
        """中文简介必须真的含中文，且与原文字面不同"""
        for name, entry in self.commands.items():
            with self.subTest(command=name):
                self.assertNotEqual(entry["en"], entry["zh"], "中英文不得完全相同")
                self.assertRegex(entry["zh"], CJK, "中文简介应含中文字符")

    def test_placeholders_and_flags_preserved(self):
        """红线：参数名、命令名、占位符、路径必须逐字保留"""
        patterns = [
            r"--[a-z][\w-]*",             # 长参数，如 --child
            r"/[a-z][\w:-]*",             # 被引用的斜杠命令，如 /vibe
            r"<[^>]+>",                   # 占位符，如 <provider>
            r"~?/[\w./-]+\.json",         # 配置文件路径
            r"\[[a-zA-Z][\w|=\s-]*\]",    # 选项组，如 [theme|off|mode]
        ]
        for name, entry in self.commands.items():
            tokens = set()
            for pattern in patterns:
                tokens.update(re.findall(pattern, entry["en"]))
            for token in sorted(tokens):
                with self.subTest(command=name, token=token):
                    self.assertIn(token, entry["zh"], f"中文简介丢失了原名 {token}")

    # ---------- 与已装插件的一致性 ----------

    def test_dict_matches_installed_plugins(self):
        """字典基线必须与当前已安装插件完全一致（新增/漂移/残留均为 0）"""
        try:
            agent_dir = scanner.locate_agent_dir()
        except FileNotFoundError as exc:  # pragma: no cover - 环境缺失时跳过
            self.skipTest(str(exc))
        if not (agent_dir / "npm" / "node_modules").is_dir():  # pragma: no cover
            self.skipTest("本机未安装 pi 插件，跳过一致性校验")

        scanned = scanner.scan(agent_dir)
        added, missing, drift = scanner.diff(scanned, self.data)
        self.assertEqual([], added, f"有插件命令未登记到字典：{added}")
        self.assertEqual([], drift, f"插件原文已变化，字典需刷新：{drift}")
        self.assertEqual([], missing, f"字典中残留了插件已删除的命令：{missing}")

    # ---------- 扫描器能力 ----------

    def test_scanner_extraction(self):
        """四种书写方式都要能抽到命令名与简介"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp)
            (pkg / "a.ts").write_text(
                'pi.registerCommand("alpha", {\n  description: "Alpha description",\n});\n'
                'const BETA = "beta";\n'
                "pi.registerCommand(BETA, { description: 'Beta description' });\n",
                encoding="utf-8",
            )
            (pkg / "b.ts").write_text(
                'import { GAMMA } from "./c";\n'
                'pi.registerCommand(GAMMA, {\n  description: `Gamma description`,\n});\n',
                encoding="utf-8",
            )
            (pkg / "c.ts").write_text('export const GAMMA = "gamma";\n', encoding="utf-8")
            (pkg / "d.min.js").write_text(
                'var f="delta",C="Delta description";function s(o){o.registerCommand(f,'
                "{description:C,handler:async(n,e)=>{}})}",
                encoding="utf-8",
            )

            found = scanner.extract_commands(pkg, scanner.build_const_map(pkg))

        self.assertEqual(
            found,
            {
                "alpha": "Alpha description",
                "beta": "Beta description",
                "gamma": "Gamma description",
                "delta": "Delta description",
            },
        )

    # ---------- 漂移检测 ----------

    def test_diff_detection(self):
        """新增 / 漂移 / 残留三类差异都要被识别"""
        dictionary = {
            "commands": {
                "keep": {"source": "pkg", "en": "Keep me", "zh": "保留"},
                "drifted": {"source": "pkg", "en": "Old wording", "zh": "旧"},
                "gone": {"source": "pkg", "en": "Removed upstream", "zh": "已删除"},
            }
        }
        scanned = {"pkg": {"keep": "Keep me", "drifted": "New wording", "fresh": "Brand new"}}

        added, missing, drift = scanner.diff(scanned, dictionary)

        self.assertEqual([("pkg", "fresh", "Brand new")], added)
        self.assertEqual([("pkg", "drifted", "Old wording", "New wording")], drift)
        self.assertEqual([("pkg", "gone", "Removed upstream")], missing)

    def test_package_spec_parsing(self):
        """settings.json 里的包声明要能还原成 npm 包名"""
        cases = {
            "npm:pi-subagents": "pi-subagents",
            "npm:pi-subagents@0.67.0": "pi-subagents",
            "npm:@juicesharp/rpiv-todo@2.9.0": "@juicesharp/rpiv-todo",
            "@bacnh85/pi-deepseek-tools": "@bacnh85/pi-deepseek-tools",
            "git:github.com/user/repo@v1": "",
        }
        for spec, expected in cases.items():
            with self.subTest(spec=spec):
                self.assertEqual(expected, scanner.parse_package_spec(spec))


if __name__ == "__main__":
    unittest.main(verbosity=2)
