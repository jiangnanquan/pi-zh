#!/usr/bin/env python3
"""
pi-zh 扩展环境懒人包（维护线 D 安装 / E 导出）单元测试与契约校验

覆盖红线：
1. 白名单提取：只提取协同必需字段，非白名单字段绝不出现在产物中；
2. 单向导出：SSOT 是本机、bundle/ 是派生物；漂移检测能报出「本机改了但没导出」；
3. 无绝对路径：导出的文件内容与清单不得含本机绝对路径；
4. 预检先于写盘：冲突时默认拒绝写盘（退出码 2），不产生半成品；
5. 幂等：重复安装结果一致，且不重写首次安装的状态指针（它是回滚基准）；
6. 可回滚：配置字段精确恢复（原先缺失的删除）、文件按 created / overwritten 区分处理；
7. 保护用户改动：卸载时若当前值/内容已被手工修改，则跳过该字段/文件，不强行回滚；
8. 只改白名单字段：安装不得触碰 settings.json 的其它字段。
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import bundle_engine as be  # noqa: E402

FAKE_PI = """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${PI_BIN_LOG}"
python3 - "$1" "$2" <<'PY'
import json, os, sys
cmd, spec = sys.argv[1], sys.argv[2]
p = os.path.join(os.environ["PI_CODING_AGENT_DIR"], "settings.json")
data = json.load(open(p))
pkgs = data.setdefault("packages", [])
if cmd == "install":
    if spec not in pkgs:
        pkgs.append(spec)
elif cmd == "remove":
    data["packages"] = [s for s in pkgs if s != spec]
json.dump(data, open(p, "w"), ensure_ascii=False, indent=2)
PY
"""

SAMPLE_POWERLINE = {
    "customItems": [{"id": "context-bar", "statusKey": "context-bar", "position": "left", "selfColorize": True}],
    "layout": {"left": ["path", "custom:context-bar"], "right": ["custom:tps"]},
    "disabledSegments": ["context_pct", "cache_read"],
}

SAMPLE_SETTINGS = {
    "theme": "light/dark",
    "defaultProvider": "deepseek",
    "quietStartup": True,
    "tuiMode": "fullscreen",
    "packages": ["npm:pi-subagents", "npm:pi-powerline-footer"],
    "skills": ["~/.agents/skills"],
    "powerline": dict(SAMPLE_POWERLINE),
}

SAMPLE_EXTENSIONS = {
    "cache-hit.ts": "// cache-hit v1\n",
    "context-bar.ts": "// context-bar v1\n",
    "ds-balance.ts": "// ds-balance v1\n",
    "tps-status.ts": "// tps-status v1\n",
}


class Args:
    """构造 argparse 结果对象，供引擎函数直接调用"""

    def __init__(self, **kw):
        defaults = dict(agent_dir=None, dry_run=False, init=False, force_settings=False,
                        force_files=False, skip_packages=False, keep_packages=False,
                        restore_from=None)
        defaults.update(kw)
        self.__dict__.update(defaults)


def run_quiet(fn, *a, **kw):
    """执行引擎函数并吞掉彩色日志，返回 (退出码, 输出文本)"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


class BundleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pi-zh-bundle-test-")).resolve()
        self.agent = self.tmp / "agent"
        (self.agent / "extensions").mkdir(parents=True)
        self._write_agent(SAMPLE_SETTINGS, SAMPLE_EXTENSIONS)

        self.bin_log = self.tmp / "fake-pi.log"
        self.fake_pi = self.tmp / "fake-pi"
        self.fake_pi.write_text(FAKE_PI, encoding="utf-8")
        self.fake_pi.chmod(0o755)
        os.environ["PI_BIN"] = str(self.fake_pi)
        os.environ["PI_BIN_LOG"] = str(self.bin_log)

    def tearDown(self):
        os.environ.pop("PI_BIN", None)
        os.environ.pop("PI_BIN_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 工具 ----

    def _write_agent(self, settings: dict, extensions: dict, claude_style=True):
        be.dump_json(self.agent / "settings.json", settings)
        if claude_style:
            be.dump_json(self.agent / "pi-cc-extensions.json", {
                "showStartupHeader": False,
                "mode": "on",
                "enableCustomFooter": True,
            })
        for name, text in extensions.items():
            (self.agent / "extensions" / name).write_text(text, encoding="utf-8")

    def _manifest(self):
        return be.build_manifest(self.agent)

    def read_settings(self) -> dict:
        return json.loads((self.agent / "settings.json").read_text(encoding="utf-8"))

    def install(self, **kw):
        kw.setdefault("init", True)
        return run_quiet(be.cmd_install, Args(agent_dir=str(self.agent), **kw))


class TestDeepPath(unittest.TestCase):
    def test_set_get_pop(self):
        obj = {}
        be.deep_set(obj, "powerline.layout.left", ["a"])
        self.assertEqual(["a"], be.deep_get(obj, "powerline.layout.left"))
        self.assertIs(be._MISSING, be.deep_get(obj, "powerline.layout.right"))
        self.assertTrue(be.deep_pop(obj, "powerline.layout.left"))
        self.assertEqual({}, obj, "父对象逐级变空时应被完整清理，不能留下空壳")
        self.assertFalse(be.deep_pop(obj, "powerline.layout.left"), "重复删除应返回 False")

    def test_pop_cleans_empty_shell(self):
        obj = {"powerline": {"layout": {"left": ["a"]}}, "keep": 1}
        self.assertTrue(be.deep_pop(obj, "powerline.layout.left"))
        self.assertNotIn("powerline", obj, "父对象变空时应清理空壳，不能留下 {\"powerline\": {}}")


class TestWhitelistExtraction(BundleCase):
    def test_only_whitelist_fields_extracted(self):
        manifest = self._manifest()
        settings = manifest["settings"]
        self.assertEqual(True, settings["quietStartup"])
        self.assertEqual("fullscreen", settings["tuiMode"])
        self.assertEqual(SAMPLE_POWERLINE["customItems"], settings["powerline"]["customItems"])
        self.assertEqual(SAMPLE_POWERLINE["layout"], settings["powerline"]["layout"])
        self.assertEqual(SAMPLE_POWERLINE["disabledSegments"], settings["powerline"]["disabledSegments"])

        # 非白名单字段绝不进包
        flat = json.dumps(settings, ensure_ascii=False)
        for leaked in ("theme", "defaultProvider", "skills", "packages", "placement", "currency"):
            self.assertNotIn(leaked, flat, f"{leaked} 不是协同必需字段，不得进包")

    def test_missing_whitelist_field_blocks_export(self):
        settings = json.loads(json.dumps(SAMPLE_SETTINGS))
        del settings["quietStartup"]
        self._write_agent(settings, SAMPLE_EXTENSIONS)
        with self.assertRaises(be.BundleError) as ctx:
            self._manifest()
        self.assertIn("quietStartup", str(ctx.exception))


class TestManifestIntegrity(BundleCase):
    def test_manifest_has_no_absolute_paths(self):
        manifest = self._manifest()
        blob = json.dumps(manifest, ensure_ascii=False)
        self.assertNotIn(str(Path.home()), blob, "清单不得含本机绝对路径")

    def test_file_entries_have_hashes(self):
        manifest = self._manifest()
        by_path = {f["path"]: f for f in manifest["files"]}
        self.assertIn("extensions/cache-hit.ts", by_path)
        expected = be.sha256_bytes(SAMPLE_EXTENSIONS["cache-hit.ts"].encode("utf-8"))
        self.assertEqual(expected, by_path["extensions/cache-hit.ts"]["sha256"])

    def test_file_json_fields_whitelist(self):
        """配置文件按字段白名单提取：只带非默认的协同必需字段，个人偏好不进包"""
        manifest = self._manifest()
        entry = next(f for f in manifest["files"] if f["path"] == "pi-cc-extensions.json")
        content = be.bundle_file_content(self.agent, "pi-cc-extensions.json")
        self.assertEqual(
            {"showStartupHeader": False}, json.loads(content),
            "只有 showStartupHeader 属协同必需（默认 true 会与欢迎页冲突），mode / enableCustomFooter 等不得进包",
        )
        self.assertEqual(
            entry["sha256"], be.sha256_bytes(content.encode("utf-8")),
            "清单哈希必须与写入 bundle/files 的进包内容一致",
        )

    def test_absolute_path_in_file_blocks_export(self):
        extensions = dict(SAMPLE_EXTENSIONS)
        extensions["cache-hit.ts"] = 'const p = "/Users/someone/secret";\n'
        self._write_agent(SAMPLE_SETTINGS, extensions)
        with self.assertRaises(be.BundleError) as ctx:
            self._manifest()
        self.assertIn("绝对路径", str(ctx.exception))

    def test_diff_manifest_reports_changes(self):
        old = self._manifest()
        new = json.loads(json.dumps(old))
        new["packages"].append({"spec": "npm:new-pkg", "note": ""})
        new["settings"]["quietStartup"] = False
        new["files"][0]["sha256"] = "0" * 64
        lines = be.diff_manifest(old, new)
        self.assertIn("+ 包 npm:new-pkg", lines)
        self.assertIn("~ 配置 quietStartup", lines)
        self.assertTrue(any("~ 文件" in line for line in lines))


class TestInstallContract(BundleCase):
    def setUp(self):
        super().setUp()
        # 把 bundle 产物写到临时目录（不碰仓库 bundle/）
        self.manifest = self._manifest()
        self.bundle_backup = (be.BUNDLE_FILES_DIR, be.MANIFEST_PATH)
        self.fixture = self.tmp / "bundle-fixture"
        (self.fixture / "files").mkdir(parents=True)
        for entry in self.manifest["files"]:
            dest = self.fixture / "files" / entry["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            # 与真实导出同一路径：应用文件级字段白名单，保证哈希与清单一致
            dest.write_text(be.bundle_file_content(self.agent, entry["path"]), encoding="utf-8")
        self._old_bundle_dir = be.BUNDLE_FILES_DIR
        self._old_manifest = be.MANIFEST_PATH
        be.BUNDLE_FILES_DIR = self.fixture / "files"
        be.MANIFEST_PATH = self.fixture / "manifest.json"
        be.dump_json(be.MANIFEST_PATH, self.manifest)

    def tearDown(self):
        be.BUNDLE_FILES_DIR = self._old_bundle_dir
        be.MANIFEST_PATH = self._old_manifest
        super().tearDown()

    # ---- 安装：只改白名单字段 ----

    def test_install_only_touches_whitelist(self):
        # 目标机器：已有自有配置 + 冲突字段 + 自有扩展文件
        target = self.tmp / "target"
        (target / "extensions").mkdir(parents=True)
        be.dump_json(target / "settings.json", {
            "theme": "dark", "myOwnSetting": "keep-me",
            "quietStartup": False, "packages": [],
        })
        (target / "extensions" / "cache-hit.ts").write_text("// user variant\n", encoding="utf-8")

        rc, out = run_quiet(be.cmd_install, Args(agent_dir=str(target), force_settings=True,
                                                 force_files=True, init=True))
        self.assertEqual(0, rc, out)
        settings = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual("dark", settings["theme"], "非白名单字段不得被改动")
        self.assertEqual("keep-me", settings["myOwnSetting"])
        self.assertEqual(True, settings["quietStartup"])
        self.assertEqual("fullscreen", settings["tuiMode"])
        self.assertEqual(SAMPLE_POWERLINE["customItems"], settings["powerline"]["customItems"])
        self.assertTrue((target / "pi-cc-extensions.json").exists())
        self.assertIn("npm:pi-subagents", settings["packages"])

    def test_conflict_stops_before_write(self):
        target = self.tmp / "target2"
        (target / "extensions").mkdir(parents=True)
        be.dump_json(target / "settings.json", {"quietStartup": False, "packages": []})
        (target / "extensions" / "cache-hit.ts").write_text("// user variant\n", encoding="utf-8")

        rc, out = run_quiet(be.cmd_install, Args(agent_dir=str(target), init=True))
        self.assertEqual(2, rc, "冲突时必须拒绝写盘")
        settings = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(False, settings.get("quietStartup"), "冲突拦截后不得改动配置")
        self.assertNotIn("tuiMode", settings, "冲突拦截后不得有半成品写入")
        self.assertFalse((target / "pi-cc-extensions.json").exists())
        self.assertFalse((target / be.STATE_NAME).exists())
        self.assertFalse(self.bin_log.exists(), "冲突拦截时不应调用 pi install")

    # ---- 幂等 / 状态累积 ----

    def test_reinstall_is_idempotent(self):
        target = self.tmp / "t3"
        target.mkdir()
        rc, _ = run_quiet(be.cmd_install, Args(agent_dir=str(target), init=True))
        self.assertEqual(0, rc)
        state_before = (target / be.STATE_NAME).read_text(encoding="utf-8")
        backup_dirs_before = sorted(p.name for p in target.glob(f"{be.BACKUP_PREFIX}*"))

        rc, out = run_quiet(be.cmd_install, Args(agent_dir=str(target), init=True))
        self.assertEqual(0, rc)
        self.assertIn("已是目标状态", out)
        self.assertEqual(state_before, (target / be.STATE_NAME).read_text(encoding="utf-8"),
                         "重跑不得重写状态指针（它是回滚基准）")
        self.assertEqual(backup_dirs_before, sorted(p.name for p in target.glob(f"{be.BACKUP_PREFIX}*")),
                         "重跑不得新建备份目录")

    # ---- 回滚 ----

    def test_uninstall_restores_original_state(self):
        target = self.tmp / "t4"
        (target / "extensions").mkdir(parents=True)
        be.dump_json(target / "settings.json", {
            "theme": "dark", "quietStartup": False, "packages": ["npm:pi-powerline-footer"],
        })
        (target / "extensions" / "cache-hit.ts").write_text("// user variant\n", encoding="utf-8")

        rc, _ = run_quiet(be.cmd_install, Args(agent_dir=str(target), force_settings=True,
                                               force_files=True, init=True))
        self.assertEqual(0, rc)

        rc, _ = run_quiet(be.cmd_uninstall, Args(agent_dir=str(target)))
        self.assertEqual(0, rc)
        settings = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual({"theme", "quietStartup", "packages"}, set(settings),
                         "只应保留安装前的字段（tuiMode/powerline 应被完整移除）")
        self.assertEqual(False, settings["quietStartup"], "应恢复安装前的值")
        self.assertEqual(["npm:pi-powerline-footer"], settings["packages"], "只移除本包安装的扩展")
        self.assertEqual("// user variant\n", (target / "extensions" / "cache-hit.ts").read_text(encoding="utf-8"),
                         "被覆盖的用户文件应还原")
        self.assertFalse((target / "extensions" / "context-bar.ts").exists(), "本包新建的文件应删除")
        self.assertFalse((target / "pi-cc-extensions.json").exists())
        self.assertFalse((target / be.STATE_NAME).exists(), "卸载后应删除状态指针")

    def test_uninstall_protects_manual_edits(self):
        target = self.tmp / "t5"
        target.mkdir()
        rc, _ = run_quiet(be.cmd_install, Args(agent_dir=str(target), init=True))
        self.assertEqual(0, rc)

        # 用户手工改动：字段改值 + 文件改内容
        settings = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        settings["quietStartup"] = False
        be.dump_json(target / "settings.json", settings)
        (target / "extensions" / "tps-status.ts").write_text("// user tweaked\n", encoding="utf-8")

        rc, out = run_quiet(be.cmd_uninstall, Args(agent_dir=str(target), keep_packages=True))
        self.assertEqual(0, rc)
        settings = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(False, settings.get("quietStartup"), "手工改过的字段应跳过，保留现值")
        self.assertTrue((target / "extensions" / "tps-status.ts").exists(), "手工改过的文件不得删除")
        self.assertEqual("// user tweaked\n", (target / "extensions" / "tps-status.ts").read_text(encoding="utf-8"))
        self.assertIn("跳过配置 quietStartup", out)


class TestCheckCommand(BundleCase):
    def test_check_reports_drift_for_unrelated_dir(self):
        manifest = be.load_manifest()
        rc, out = run_quiet(be.cmd_check, Args(agent_dir=str(self.agent)))
        self.assertEqual(1, rc, "临时环境与本仓库 bundle 不一致，应报漂移")
        self.assertIn("漂移", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
