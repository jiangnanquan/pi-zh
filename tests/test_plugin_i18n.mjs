/**
 * pi-zh — 插件简介汉化扩展的端到端契约测试
 *
 * 直接加载 extensions/plugin-i18n.ts（复制成 .mts 交给 Node 的类型剥离），
 * 用假的 pi / ctx 捕获补全器包装函数，再用假的底层补全器构造候选项，
 * 验证：汉化命中、标签保留、未知条目回退英文、参数/文件补全透传、命令名不动。
 *
 * 运行：node tests/test_plugin_i18n.mjs
 */

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { test } from "node:test";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "..");
const EXTENSION_SRC = path.join(REPO_ROOT, "extensions", "plugin-i18n.ts");
const DICT_PATH = path.join(REPO_ROOT, "i18n", "plugins.json");
const SOURCE_TAG = "[u:npm:pi-powerline-footer] ";

/** 把 TS 扩展复制为 .mts 后导入（Node 22 默认剥离类型） */
async function loadExtension() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-zh-ext-"));
  const copy = path.join(dir, "plugin-i18n.mts");
  fs.copyFileSync(EXTENSION_SRC, copy);
  const module = await import(pathToFileURL(copy).href);
  return { factory: module.default, dir };
}

/** 构造假的底层补全器：getSuggestions 返回指定候选项并记录调用 */
function fakeBaseProvider(items, prefix = "/") {
  const calls = { getSuggestions: 0, applyCompletion: 0, shouldTriggerFileCompletion: 0 };
  return {
    calls,
    async getSuggestions() {
      calls.getSuggestions += 1;
      return { items, prefix };
    },
    applyCompletion(lines, cursorLine, cursorCol, item, pfx) {
      calls.applyCompletion += 1;
      return { lines: [...lines], cursorLine, cursorCol, item, prefix: pfx };
    },
    shouldTriggerFileCompletion() {
      calls.shouldTriggerFileCompletion += 1;
      return true;
    },
  };
}

/** 装载扩展，返回「包装后的补全器」 */
async function buildProvider(items, { lines, col, dictPath = DICT_PATH } = {}) {
  process.env.PI_ZH_PLUGIN_DICT = dictPath;
  const { factory } = await loadExtension();

  let sessionStart;
  const pi = {
    on(event, handler) {
      if (event === "session_start") sessionStart = handler;
    },
  };

  let wrapFactory;
  const ctx = {
    ui: {
      addAutocompleteProvider(factory) {
        wrapFactory = factory;
      },
      notify() {},
    },
  };

  factory(pi);
  assert.equal(typeof sessionStart, "function", "扩展应注册 session_start 处理器");
  sessionStart({ reason: "startup" }, ctx);
  assert.equal(typeof wrapFactory, "function", "session_start 时应注册补全器包装函数");

  const base = fakeBaseProvider(items);
  const provider = wrapFactory(base);
  const line = lines ?? "/";
  const suggestions = await provider.getSuggestions([line], 0, col ?? line.length, {
    signal: new AbortController().signal,
  });
  return { provider, base, suggestions };
}

const dict = JSON.parse(fs.readFileSync(DICT_PATH, "utf8"));

test("已登记命令：简介正文汉化，来源标签与命令名保持不变", async () => {
  const expected = dict.commands["bash-mode"];
  const { suggestions } = await buildProvider([
    {
      value: "bash-mode",
      label: "bash-mode",
      description: `${SOURCE_TAG}${expected.en}`,
    },
  ]);

  assert.equal(suggestions.items.length, 1);
  assert.equal(suggestions.items[0].value, "bash-mode", "命令名必须保持英文");
  assert.equal(suggestions.items[0].label, "bash-mode");
  assert.equal(suggestions.items[0].description, `${SOURCE_TAG}${expected.zh}`);
});

test("未知简介（内置命令、提示词模板）原样透传", async () => {
  const items = [
    { value: "compact", label: "compact", description: "手动压缩会话上下文" },
    { value: "llama", label: "llama", description: "[t] Manage llama.cpp router models" },
  ];
  const { suggestions } = await buildProvider(items, { lines: "/l", col: 2 });
  assert.deepEqual(suggestions.items, items);
});

test("同名但原文不同（插件改词）时不误翻，回退英文", async () => {
  const drift = `${SOURCE_TAG}Toggle sticky bash mode (on, off or auto)`;
  const { suggestions } = await buildProvider([
    { value: "bash-mode", label: "bash-mode", description: drift },
  ]);
  assert.equal(suggestions.items[0].description, drift);
});

test("参数补全场景（输入已含空格）完全透传", async () => {
  const items = [{ value: "deepseek/deepseek-flash", label: "deepseek-flash", description: "deepseek" }];
  const { suggestions } = await buildProvider(items, { lines: "/model deep", col: "/model deep".length });
  assert.deepEqual(suggestions.items, items);
});

test("文件补全场景（@ 前缀）完全透传", async () => {
  const items = [{ value: "src/index.ts", label: "src/index.ts", description: "file" }];
  const { suggestions } = await buildProvider(items, { lines: "@src", col: 4 });
  assert.deepEqual(suggestions.items, items);
});

test("无 description 的候选项不报错", async () => {
  const items = [{ value: "bash-reset", label: "bash-reset" }];
  const { suggestions } = await buildProvider(items, { lines: "/bash", col: 5 });
  assert.deepEqual(suggestions.items, items);
});

test("applyCompletion 与 shouldTriggerFileCompletion 委托给底层补全器", async () => {
  const { provider, base } = await buildProvider([
    { value: "cd", label: "cd", description: `${SOURCE_TAG}Switch the Pi session working directory` },
  ]);

  const applied = provider.applyCompletion(["/cd"], 0, 3, { value: "cd", label: "cd" }, "/cd");
  assert.equal(base.calls.applyCompletion, 1);
  assert.equal(applied.item.value, "cd");

  assert.equal(provider.shouldTriggerFileCompletion(["/cd"], 0, 3), true);
  assert.equal(base.calls.shouldTriggerFileCompletion, 1);
});

test("字典热更新：改 zh 后无需重启即可生效", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-zh-dict-"));
  const custom = path.join(dir, "plugins.json");
  const payload = structuredClone(dict);
  payload.commands["cd"].zh = "占位中文 A";
  fs.writeFileSync(custom, JSON.stringify(payload), "utf8");

  const items = [
    { value: "cd", label: "cd", description: `${SOURCE_TAG}Switch the Pi session working directory` },
  ];
  const { provider } = await buildProvider(items, { dictPath: custom });
  let out = await provider.getSuggestions(["/cd"], 0, 3, { signal: new AbortController().signal });
  assert.equal(out.items[0].description, `${SOURCE_TAG}占位中文 A`);

  payload.commands["cd"].zh = "占位中文 B";
  fs.writeFileSync(custom, JSON.stringify(payload), "utf8");
  const bumped = new Date(Date.now() + 2000);
  fs.utimesSync(custom, bumped, bumped);

  out = await provider.getSuggestions(["/cd"], 0, 3, { signal: new AbortController().signal });
  assert.equal(out.items[0].description, `${SOURCE_TAG}占位中文 B`);
});

test("字典缺失时不注册补全器包装（不影响 pi 启动）", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-zh-nodict-"));
  const { factory } = await loadExtension();

  let sessionStart;
  const pi = { on: (event, handler) => { if (event === "session_start") sessionStart = handler; } };
  let wrapFactory;
  const ctx = {
    ui: {
      addAutocompleteProvider(factory) {
        wrapFactory = factory;
      },
      notify() {},
    },
  };

  // 同时改写 HOME，使扩展的兜底查找路径也落在临时目录里，保证测试与机器环境无关
  const previousHome = process.env.HOME;
  process.env.HOME = dir;
  process.env.PI_ZH_PLUGIN_DICT = path.join(dir, "does-not-exist.json");
  try {
    factory(pi);
    sessionStart({ reason: "startup" }, ctx);
  } finally {
    process.env.HOME = previousHome;
  }

  assert.equal(wrapFactory, undefined);
});
