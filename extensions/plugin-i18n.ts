// @ts-nocheck
/**
 * plugin-i18n — 第三方插件斜杠命令简介汉化（运行时覆盖）
 *
 * 背景：第三方插件用 `pi.registerCommand(name, { description })` 注册斜杠命令，
 * 其 description 是英文且随插件发布节奏变化，直接改 node_modules 会被插件升级覆盖。
 *
 * 本扩展的做法：用 ctx.ui.addAutocompleteProvider 包一层内置补全器，只在「/ 开头且
 * 尚未输入空格的命令名补全」场景下，把候选项第二列的英文简介正文替换成中文，
 * 其余场景（参数补全、@ 文件补全、路径补全）原样透传。
 *
 * 红线（与 AGENTS.md 一致）：
 *   1. 命令名（item.value）与参数原名绝不改写，只动展示用的 description；
 *   2. 来源标签 `[u:npm:xxx]` 原样保留；
 *   3. 仅当英文原文与 i18n/plugins.json 的 `en` 基线**完全一致**时才替换，
 *      因此绝不会误伤同名但不同来源的命令（如内置命令、提示词模板、skill）；
 *   4. 插件升级改了措辞时只是回退成英文，不会翻错 —— 漂移由
 *      `python3 scripts/scan_plugin_commands.py --check` 负责报出来。
 *
 * 字典查找顺序：$PI_ZH_PLUGIN_DICT → <扩展目录>/../plugin-i18n/plugins.json
 * （即 ~/.pi/agent/plugin-i18n/plugins.json，由 scripts/install_plugin_i18n.sh 建立软链）
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const EXTENSION_DIR = path.dirname(fileURLToPath(import.meta.url));

function dictCandidates() {
  return [
    process.env.PI_ZH_PLUGIN_DICT,
    path.join(os.homedir(), ".pi", "agent", "plugin-i18n", "plugins.json"),
    path.join(EXTENSION_DIR, "..", "plugin-i18n", "plugins.json"),
  ].filter(Boolean);
}

/** en 原文 -> 中文简介 */
let byEn = new Map();
let dictPath = "";
let dictMtime = -1;
/** 同一进程内只包一层补全器（/reload 会重置包装栈并重新加载本模块，故用模块级标志） */
let wrapped = false;

function resolveDictPath() {
  for (const candidate of dictCandidates()) {
    try {
      if (fs.statSync(candidate).isFile()) return candidate;
    } catch {
      /* 候选路径不存在，继续尝试下一个 */
    }
  }
  return "";
}

/**
 * 载入（或按 mtime 热更新）字典，返回可用条目数。
 * 未填 zh 的条目自动跳过，对应命令保持英文显示。
 */
function loadDict() {
  const resolved = resolveDictPath();
  if (!resolved) return byEn.size;

  let mtime;
  try {
    mtime = fs.statSync(resolved).mtimeMs;
  } catch {
    return byEn.size;
  }
  if (resolved === dictPath && mtime === dictMtime) return byEn.size;

  const parsed = JSON.parse(fs.readFileSync(resolved, "utf8"));
  const next = new Map();
  for (const entry of Object.values(parsed?.commands ?? {})) {
    const en = typeof entry?.en === "string" ? entry.en.trim() : "";
    const zh = typeof entry?.zh === "string" ? entry.zh.trim() : "";
    if (en && zh) next.set(en, zh);
  }

  byEn = next;
  dictPath = resolved;
  dictMtime = mtime;
  return byEn.size;
}

/** 拆出 `[来源标签] ` 前缀，只替换其后的简介正文 */
function translateItem(item) {
  const description = item?.description;
  if (typeof description !== "string" || !description) return item;

  const match = description.match(/^(\[[^\]]*\]\s*)?([\s\S]*)$/);
  if (!match) return item;

  const tag = match[1] ?? "";
  const body = (match[2] ?? "").trim();
  const zh = byEn.get(body);
  if (!zh) return item;

  return { ...item, description: `${tag}${zh}` };
}

export default function (pi) {
  pi.on("session_start", (_event, ctx) => {
    let count = 0;
    try {
      count = loadDict();
    } catch (error) {
      ctx.ui?.notify?.(`plugin-i18n: 字典加载失败：${error?.message ?? error}`, "warning");
      return;
    }
    if (!count) return;

    if (wrapped || typeof ctx.ui?.addAutocompleteProvider !== "function") return;

    ctx.ui.addAutocompleteProvider((current) => ({
      async getSuggestions(lines, cursorLine, cursorCol, options) {
        const suggestions = await current.getSuggestions(lines, cursorLine, cursorCol, options);
        if (!suggestions?.items?.length) return suggestions;

        // 仅限「/ 开头的命令名补全」：一旦出现空格就是参数补全，一律透传
        const beforeCursor = (lines?.[cursorLine] ?? "").slice(0, cursorCol);
        if (!beforeCursor.startsWith("/") || beforeCursor.includes(" ")) return suggestions;

        try {
          loadDict(); // 允许运行中编辑字典，按 mtime 热更新
        } catch {
          return suggestions;
        }

        return { ...suggestions, items: suggestions.items.map(translateItem) };
      },

      applyCompletion(lines, cursorLine, cursorCol, item, prefix) {
        return current.applyCompletion(lines, cursorLine, cursorCol, item, prefix);
      },

      shouldTriggerFileCompletion(lines, cursorLine, cursorCol) {
        return current.shouldTriggerFileCompletion?.(lines, cursorLine, cursorCol) ?? true;
      },
    }));

    wrapped = true;
  });
}
