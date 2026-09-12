#!/usr/bin/env python3
"""
pi-zh 插件 UI 汉化（维护线 C）单元测试与契约校验

覆盖红线：
1. 字典条目必须是「自带上下文」的精确文本，严禁裸单词 raw 替换污染代码标识符；
2. literal 模式只命中引号包裹的字面量，`const Tips = 1` 这类标识符不得被改写；
3. 干净基底：首次备份后绝不覆盖，重复 apply 幂等（无补丁叠补丁）；
4. 未命中即报错：上游改措辞时严格模式拒绝写盘，不产生半成品汉化；
5. 可一键还原：restore 后文件与官方原件逐字节一致；
6. 行为补丁（code_patches）必须带 id / reason / authorized_on 授权记录，缺一不可。
"""

import argparse
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import patch_plugin_ui as ppu  # noqa: E402

PACKAGE = "pi-powerline-footer"

# 真实 welcome.ts 的等价摘录：覆盖 i18n/plugin-ui.json 全部锚点
SAMPLE_TS = """import { callout } from "./colors.ts";

function buildLeftColumn(data, colWidth) {
  return [
    "",
    centerText(bold("Welcome back!"), colWidth),
  ];
}

function buildRightColumn(data, colWidth) {
  return [
    ` ${bold(fgOnly("accent", "Tips"))}`,
    ` ${dim("/")} for commands`,
    ` ${dim("!")} to run bash`,
    ` ${dim("Shift+Tab")} cycle thinking`,
    ` ${bold(fgOnly("accent", "Loaded"))}`,
    ` ${itemPrefix}${fgOnly("gitClean", `${contextFiles}`)} context file${contextFiles !== 1 ? "s" : ""}`,
    ` ${itemPrefix}${fgOnly("gitClean", `${extensions}`)} extension${extensions !== 1 ? "s" : ""}`,
    ` ${itemPrefix}${fgOnly("gitClean", `${skills}`)} skill${skills !== 1 ? "s" : ""}`,
    ` ${itemPrefix}${fgOnly("gitClean", `${promptTemplates}`)} prompt template${promptTemplates !== 1 ? "s" : ""}`,
    ` ${itemPrefix}${fgOnly("gitClean", `= ${formatTokens(0)}`)} initial prompt tokens`,
    ` ${dim("No extensions loaded")}`,
    ` ${bold(fgOnly("accent", "Recent sessions"))}`,
    ` ${dim("No recent sessions")}`,
  ];
}

function formatTimeAgo(ms) {
  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return "just now";
}

function renderWidth() {
  const countdownText = ` Press any key to continue (${this.countdown}s) `;
  return countdownText;
}
"""

# index.ts 的等价摘录：承载全部「用户逐条授权」的行为补丁锚点
# （editor 边框继承思考色 3 处 + 欢迎页空壳先行 1 处 + dock 精简 3 处）
SAMPLE_INDEX_TS = """import { getFgAnsiCode, ansi } from "./colors.ts";

export function renderFastPowerlineEditor(editor: unknown, width: number) {
  const borderColor = getFgAnsiCode("sep");
  const border = (marker: "\u2191" | "\u2193" | "\u2500") => {
    const text = marker === "\u2500" ? "\u2500".repeat(width - 2) : `${marker}${"\u2500".repeat(Math.max(0, width - 3))}`;
    return ` ${borderColor}${text}${ansi.reset}`;
  };
  return [border("\u2500")];
}

export function buildChrome(editor: any, width: number) {
  const render = () => {
    try {
      if (width > 0) {
        return () => {
          const bc = (s: string) => `${getFgAnsiCode("sep")}${s}${ansi.reset}`;
          return bc("\u2500".repeat(width - 2));
        };
      }
    } catch {
      return () => "";
    }
    return () => "";
  };
  return render();
}

export function setupWelcomeHeader(ctx: any) {
  const request = beginWelcomeRequest(ctx);
  const generation = sessionGeneration;
  welcomeTimer = setTimeout(async () => {
    welcomeTimer = null;
    try {
        if (!canShowWelcome(ctx, request, generation)) return;
        const recentSessions = await getRecentSessions(3, request.signal);
        if (!canShowWelcome(ctx, request, generation)) return;
        const modelName = ctx.model?.name || ctx.model?.id || "No model";
        const providerName = ctx.model?.provider || "Unknown";
        const loadedCounts = discoverLoadedCounts();
        const initialContextTokens = estimateInitialContextTokens(ctx);

        const header = new WelcomeHeader(modelName, providerName, recentSessions, loadedCounts, initialContextTokens);
        welcomeHeaderActive = true;
        ctx.ui.setHeader(() => header);
    } catch (error) {}
  }, 0);
}

export function registerExtension(ctx: any) {
  function setupCustomEditor(ctx: any) {
    ctx.ui.setWidget("powerline-top", (_tui: any, theme: Theme) => ({
      dispose() {},
      invalidate() {
        resetLayoutCache();
      },
      render(width: number): string[] {
        return measureWidget("primary", () => renderPowerlinePrimaryLines(width, theme));
      },
    }), { placement: config.placement === "below" ? "belowEditor" : "aboveEditor" });

    ctx.ui.setFooter((tui: any, _theme: Theme, footerData: ReadonlyFooterDataProvider) => {
      footerDataRef = footerData;
      return {
        dispose() {},
        invalidate() {
          requestStatusRender();
        },
        render(): string[] {
          return [""];
        },
      };
    });
  }
}
"""


def fake_args(node_modules_dir, allow_missing=False, dry_run=False, skip_verify=True):
    return argparse.Namespace(
        agent_dir=None,
        node_modules_dir=str(node_modules_dir),
        allow_missing=allow_missing,
        dry_run=dry_run,
        skip_verify=skip_verify,
        dict=str(ppu.DICT_PATH),
        apply=True,
        restore=False,
        status=False,
        check=False,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TempPluginCase(unittest.TestCase):
    """在临时目录中搭建伪插件包，隔离验证写盘行为"""

    source = SAMPLE_TS
    index_source = SAMPLE_INDEX_TS

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.nm_dir = self.tmp / "npm" / "node_modules"
        self.pkg_dir = self.nm_dir / PACKAGE
        self.pkg_dir.mkdir(parents=True)
        (self.pkg_dir / "package.json").write_text(
            json.dumps({"name": PACKAGE, "version": "0.17.1"}), encoding="utf-8"
        )
        self.target_file = self.pkg_dir / "welcome.ts"
        self.target_file.write_text(self.source, encoding="utf-8")
        self.original = self.target_file.read_text(encoding="utf-8")
        self.backup = ppu.backup_path_for(self.target_file)

        self.index_file = self.pkg_dir / "index.ts"
        self.index_file.write_text(self.index_source, encoding="utf-8")
        self.index_original = self.index_file.read_text(encoding="utf-8")
        self.index_backup = ppu.backup_path_for(self.index_file)

        _data, self.targets = ppu.load_dict(ppu.DICT_PATH)
        self.target = next(t for t in self.targets if t["file"] == "welcome.ts")
        self.index_target = next(t for t in self.targets if t["file"] == "index.ts")

    def tearDown(self):
        self._tmp.cleanup()

    def apply_once(self, **kwargs):
        return ppu.apply_targets(self.targets, fake_args(self.nm_dir, **kwargs), verify_override=False)


class TestDictContract(unittest.TestCase):
    def setUp(self):
        self.data, self.targets = ppu.load_dict(ppu.DICT_PATH)

    def test_target_shape(self):
        for target in self.targets:
            for field in ("package", "file", "source_version", "replacements", "verify_expect"):
                self.assertIn(field, target, f"target 缺少字段 {field}")
            if target["replacements"]:
                self.assertTrue(target["verify_expect"], "有汉化文案的 target 必须给 verify_expect 以断言中文生效")
            if not target["replacements"]:
                self.assertTrue(target.get("code_patches"), "无汉化文案的 target 只能是行为补丁 target")

    def test_replacements_are_valid(self):
        for target in self.targets:
            self.assertEqual([], ppu.validate_replacements(target["replacements"]))

    def test_replacement_scale(self):
        total = sum(len(t["replacements"]) for t in self.targets)
        self.assertGreaterEqual(total, 19, "欢迎页条目数不应少于 19 条")

    def test_patch_scale_is_pinned(self):
        """条目规模是维护基线：变更必须同步 00_状态.md 与本节数字"""
        text = sum(len(t["replacements"]) for t in self.targets)
        code = sum(len(t.get("code_patches", [])) for t in self.targets)
        self.assertEqual(19, text, "文案条目数变化需同步 00_状态.md")
        self.assertEqual(7, code, "行为补丁锚点数变化需同步 00_状态.md")

    def test_modes_are_known(self):
        for target in self.targets:
            for item in target["replacements"]:
                self.assertIn(item["mode"], ("literal", "raw"))

    def test_brand_and_runtime_data_not_translated(self):
        """品牌标题与运行时数据不得进字典"""
        for target in self.targets:
            for item in target["replacements"]:
                self.assertNotIn("pi agent", item["en"])
                self.assertNotIn("DeepSeek", item["en"])


class TestLiteralSafety(unittest.TestCase):
    """literal 模式只命中引号内字面量，绝不污染代码标识符"""

    def setUp(self):
        self.items = [
            {"mode": "literal", "en": "Tips", "zh": "提示"},
            {"mode": "literal", "en": "Loaded", "zh": "已加载"},
            {"mode": "literal", "en": "just now", "zh": "刚刚"},
        ]

    def test_does_not_touch_identifiers(self):
        code = 'const Tips = 1;\nconst Loaded = false;\nlet justNow = Tips;\n'
        patched, results = ppu.patch_text(code, self.items)
        self.assertEqual(code, patched, "标识符被误伤")
        self.assertTrue(all(r["hits"] == 0 for r in results))

    def test_rewrites_quoted_literals(self):
        code = 'bold("Tips"); bold(\'Loaded\'); return "just now";\n'
        patched, results = ppu.patch_text(code, self.items)
        self.assertIn('bold("提示")', patched)
        self.assertIn('bold("已加载")', patched)
        self.assertIn('return "刚刚"', patched)
        self.assertEqual(sum(r["hits"] for r in results), 3)

    def test_rejects_literal_with_quotes(self):
        problems = ppu.validate_replacements([{"mode": "literal", "en": 'say "hi"', "zh": "你好"}])
        self.assertTrue(any("不能含引号" in p for p in problems))


class TestCodePatchContract(unittest.TestCase):
    """行为补丁是 C 线红线（只改文案）的唯一例外通道，必须留下完整授权记录"""

    def setUp(self):
        self.data, self.targets = ppu.load_dict(ppu.DICT_PATH)
        self.code_targets = [t for t in self.targets if t.get("code_patches")]
        self.patches = [p for t in self.code_targets for p in t["code_patches"]]

    def test_patches_exist_and_are_authorized(self):
        self.assertTrue(self.patches, "至少应存在一条行为补丁（editor 边框继承思考色）")
        for patch in self.patches:
            self.assertTrue(patch.get("id"))
            self.assertTrue(patch.get("reason"))
            self.assertRegex(patch.get("authorized_on", ""), r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(patch.get("from"))
            self.assertTrue(patch.get("to"))

    def test_patches_are_valid(self):
        for target in self.code_targets:
            self.assertEqual([], ppu.validate_code_patches(target))

    def test_missing_authorization_is_rejected(self):
        bad = {"code_patches": [{"id": "x", "from": "a" * 40, "to": "b" * 40}]}
        problems = ppu.validate_code_patches(bad)
        self.assertTrue(any("reason" in p for p in problems))
        self.assertTrue(any("authorized_on" in p for p in problems))

    def test_short_anchor_is_rejected(self):
        bad = {"code_patches": [{
            "id": "x", "reason": "y", "authorized_on": "2026-09-12",
            "from": "sep", "to": "abc",
        }]}
        self.assertTrue(any("过短" in p for p in ppu.validate_code_patches(bad)))

    def test_code_patch_is_applied_as_raw_and_tagged(self):
        items = ppu.build_patch_items(self.code_targets[0])
        self.assertTrue(all(item["kind"] == "code" for item in items))
        content, results = ppu.patch_text(SAMPLE_INDEX_TS, items)
        self.assertEqual([], [r["en"] for r in results if r["hits"] == 0])
        self.assertIn('Reflect.get(editor as object, "borderColor")', content)
        self.assertIn("typeof piBorderColor === \"function\"", content)
        self.assertNotIn('const borderColor = getFgAnsiCode("sep");', content)

    def test_patch_keeps_gray_fallback(self):
        items = ppu.build_patch_items(self.code_targets[0])
        content, _ = ppu.patch_text(SAMPLE_INDEX_TS, items)
        self.assertEqual(
            2, content.count('getFgAnsiCode("sep")'),
            "两处边框绘制都必须保留原灰色实现作为回退分支",
        )

    def test_dock_trim_moves_primary_line_into_footer_slot(self):
        """dock 精简补丁：placement=below 时主状态行改由 footer 槽位渲染，widget 让位不重复占行"""
        items = ppu.build_patch_items(self.code_targets[0])
        content, results = ppu.patch_text(SAMPLE_INDEX_TS, items)
        self.assertEqual([], [r["en"] for r in results if r["hits"] == 0])
        # footer 槽位：below 走主状态行，其他 placement 保留原空壳
        self.assertIn('if (config.placement !== "below") return [""];', content)
        self.assertIn("return renderPowerlinePrimaryLines(width, theme);", content)
        # widget 让位：below 时返回空数组，避免同一行渲染两次
        self.assertIn('if (config.placement === "below") return [];', content)
        # 原空壳与 perf 计时段仍作为回退分支保留
        self.assertEqual(1, content.count('return [""];'), "空壳回退分支必须保留且只剩一处")
        self.assertIn('measureWidget("primary", () => renderPowerlinePrimaryLines(width, theme))', content)
        self.assertNotIn("_theme: Theme", content, "footer 工厂形参应启用为 theme 供渲染使用")
        self.assertIn("ctx.ui.setFooter((tui: any, theme: Theme", content)


class TestRawTemplateRewrites(unittest.TestCase):
    def setUp(self):
        _data, self.targets = ppu.load_dict(ppu.DICT_PATH)
        self.items = self.targets[0]["replacements"]

    def test_count_line_singular_plural(self):
        code = 'x = ` ${p}${fg("c", `${contextFiles}`)} context file${contextFiles !== 1 ? "s" : ""}`;'
        patched, _ = ppu.patch_text(code, self.items)
        self.assertIn("个上下文文件", patched)
        self.assertNotIn("context file", patched)
        self.assertNotIn('? "s" : ""', patched)

    def test_time_ago_units(self):
        code = 'a = `${days}d ago`; b = `${hours}h ago`; c = `${minutes}m ago`; d = "just now";'
        patched, _ = ppu.patch_text(code, self.items)
        self.assertIn("${days} 天前", patched)
        self.assertIn("${hours} 小时前", patched)
        self.assertIn("${minutes} 分钟前", patched)
        self.assertIn('"刚刚"', patched)
        self.assertNotIn("ago`", patched)

    def test_countdown_and_hints(self):
        code = 'a = ` Press any key to continue (${this.countdown}s) `;\nb = ` ${dim("/")} for commands`;'
        patched, _ = ppu.patch_text(code, self.items)
        self.assertIn("按任意键继续（${this.countdown}s）", patched)
        self.assertIn("查看命令列表", patched)

    def test_full_sample_hits_every_entry(self):
        _patched, results = ppu.patch_text(SAMPLE_TS, self.items)
        missing = [r["en"] for r in results if r["hits"] == 0]
        self.assertEqual([], missing, f"样例摘录未覆盖条目：{missing}")

    def test_raw_rejects_bare_short_word(self):
        problems = ppu.validate_replacements([{"mode": "raw", "en": "Tips", "zh": "提示"}])
        self.assertTrue(any("过短" in p for p in problems))


class TestApplyIdempotentAndRestore(TempPluginCase):
    def _dict_entry_total(self) -> int:
        """从字典动态统计条目总数（文案 + 行为补丁），避免测试随字典增长而硬编码漂移。"""
        _data, targets = ppu.load_dict(ppu.DICT_PATH)
        return sum(len(t.get("replacements", [])) + len(t.get("code_patches", [])) for t in targets)

    def test_apply_then_reapply_is_idempotent(self):
        processed, changes, failures = self.apply_once()
        self.assertEqual([], failures)
        self.assertEqual(2, processed, "welcome.ts 与 index.ts 两个 target 都应处理")
        expected_total = self._dict_entry_total()
        self.assertEqual(expected_total, changes, f"应命中字典全量 {expected_total} 处（文案 + 行为补丁）")
        self.assertTrue(self.backup.exists(), "首次 apply 必须留下干净基底备份")
        self.assertTrue(self.index_backup.exists(), "行为补丁 target 同样必须留备份")

        first_pass = self.target_file.read_text(encoding="utf-8")
        index_pass = self.index_file.read_text(encoding="utf-8")
        backup_hash = sha256(self.backup)
        index_backup_hash = sha256(self.index_backup)
        self.assertIn("欢迎回来！", first_pass)
        self.assertIn("个上下文文件", first_pass)
        self.assertNotIn("Welcome back!", first_pass)
        self.assertIn('Reflect.get(editor as object, "borderColor")', index_pass)
        self.assertIn(
            "const shellHeader = new WelcomeHeader(modelName, providerName);",
            index_pass,
            "启动时序补丁（welcome-header-eager-shell）应已写入：先挂空壳 header",
        )

        # 二次 apply：以备份为源，结果必须完全一致，备份不得被覆盖
        _processed, changes2, failures2 = self.apply_once()
        self.assertEqual([], failures2)
        self.assertEqual(expected_total, changes2, f"二次 apply 仍应命中 {expected_total} 处（从备份重算），而非叠加")
        self.assertEqual(first_pass, self.target_file.read_text(encoding="utf-8"))
        self.assertEqual(index_pass, self.index_file.read_text(encoding="utf-8"))
        self.assertEqual(backup_hash, sha256(self.backup), "备份被覆盖，违反干净基底红线")
        self.assertEqual(index_backup_hash, sha256(self.index_backup))

    def test_restore_is_byte_identical(self):
        self.apply_once()
        self.assertNotEqual(self.original, self.target_file.read_text(encoding="utf-8"))
        self.assertNotEqual(self.index_original, self.index_file.read_text(encoding="utf-8"))

        restored = ppu.restore_targets(self.targets, fake_args(self.nm_dir))
        self.assertEqual(2, restored)
        self.assertEqual(self.original, self.target_file.read_text(encoding="utf-8"))
        self.assertEqual(self.index_original, self.index_file.read_text(encoding="utf-8"))
        self.assertFalse(self.backup.exists(), "还原后备份应被移除")
        self.assertFalse(self.index_backup.exists())

    def test_status_reflects_state(self):
        plan = ppu.plan_target(self.target, self.pkg_dir)
        self.assertTrue(plan["changed"])
        self.assertEqual([], plan["missing"])

        self.apply_once()
        plan_after = ppu.plan_target(self.target, self.pkg_dir)
        self.assertEqual([], plan_after["missing"])
        self.assertEqual(
            plan_after["patched_content"], plan_after["file_path"].read_text(encoding="utf-8")
        )


class TestMissingDetection(TempPluginCase):
    # 模拟上游改了措辞：原文 "just now" 变成 "moments ago"，字典未同步
    source = SAMPLE_TS.replace('  return "just now";\n', '  return "moments ago";\n')

    def test_missing_entry_blocks_write(self):
        plan = ppu.plan_target(self.target, self.pkg_dir)
        self.assertTrue(plan["missing"], "删掉锚点后必须报未命中")
        self.assertIn("just now", [item["en"] for item in plan["missing"]])

        _processed, _changes, failures = self.apply_once()
        self.assertEqual(["welcome.ts"], failures)
        self.assertEqual(self.original, self.target_file.read_text(encoding="utf-8"), "严格模式不得写盘")
        self.assertFalse(self.backup.exists(), "失败时不应留下备份")
        self.assertEqual(self.index_original, self.index_file.read_text(encoding="utf-8"))

    def test_allow_missing_writes_rest(self):
        _processed, _changes, failures = self.apply_once(allow_missing=True)
        self.assertEqual([], failures)
        patched = self.target_file.read_text(encoding="utf-8")
        self.assertIn("欢迎回来！", patched)
        self.assertIn('"moments ago"', patched, "未命中条目应保留英文原文，不得留下半成品翻译")

    def test_dry_run_never_writes(self):
        _processed, _changes, _failures = self.apply_once(dry_run=True, allow_missing=True)
        self.assertEqual(self.original, self.target_file.read_text(encoding="utf-8"))
        self.assertFalse(self.backup.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
