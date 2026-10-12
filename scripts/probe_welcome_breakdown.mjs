#!/usr/bin/env node
/**
 * pi-zh — 欢迎页「初始提示词分段统计」探针（维护线 C / welcome-prompt-breakdown 的回归哨兵）
 *
 * 为什么需要它：verify_plugin_ts.mjs 只做「能加载 + 行宽自洽 + 中文字面量在」，用的是合成数据。
 * 本探针回答两个它答不了的问题：
 *   ① 口径对不对 —— 用**真实会话记录**（sessions/*.jsonl 的 system 消息，含 sections 与 toolsAdded）
 *      还原当时的 system prompt 与工具声明，喂给 estimatePromptBreakdown()，
 *      断言结果与 Pi 自己的记账口径（字符数 / 4）一致；
 *   ② 渲染稳不稳 —— 在 44 / 50 / 76 / 96 / 110 列下渲染欢迎页，断言行宽自洽、分段区块出现、
 *      窄终端不崩、缺省数据时回退上游单行实现。
 *
 * 用法：
 *   node scripts/probe_welcome_breakdown.mjs                      # 自动挑最新一条真实会话
 *   node scripts/probe_welcome_breakdown.mjs --session <file.jsonl>
 *   node scripts/probe_welcome_breakdown.mjs --pi-pkg <pi 包目录>
 *
 * 退出码：0 通过；1 失败（回归）。
 */

import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

const ANSI_RE = /\x1b\[[0-9;]*m/g;
const PI_PACKAGE_NAME = "@earendil-works/pi-coding-agent";
const PLUGIN_RELATIVE = ["npm", "node_modules", "pi-powerline-footer"];
const RENDER_WIDTHS = [44, 50, 76, 96, 110];
/** 内容断言（分支符号 / 标签文案）只在右栏足够宽时不截断的档位生效 */
const CONTENT_ASSERT_MIN_WIDTH = 76;

function parseArgs(argv) {
	const args = {};
	for (let i = 0; i < argv.length; i++) {
		if (!argv[i].startsWith("--")) continue;
		args[argv[i].slice(2)] = argv[i + 1];
		i++;
	}
	return args;
}

function fail(message) {
	console.error(`[probe] 失败：${message}`);
	process.exit(1);
}

function note(message) {
	console.log(`[probe] ${message}`);
}

/** 判断目录是否为 pi 包根（兼容 pnpm / fnm / npm 各种链接布局） */
function isPiPackageRoot(dir) {
	try {
		return JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf8"))?.name === PI_PACKAGE_NAME;
	} catch {
		return false;
	}
}

function ascendToPiPackage(startPath) {
	let dir = path.dirname(startPath);
	for (let i = 0; i < 8; i++) {
		if (isPiPackageRoot(dir)) return dir;
		const parent = path.dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return null;
}

function locatePiPackage(explicit) {
	if (explicit) {
		const resolved = path.resolve(explicit);
		if (isPiPackageRoot(resolved)) return resolved;
		fail(`--pi-pkg 未指向 ${PI_PACKAGE_NAME} 包目录：${resolved}`);
	}
	const resolvedBin = execFileSync("bash", ["-lc", `command -v ${process.env.PI_BIN || "pi"}`], { encoding: "utf8" }).trim();
	if (resolvedBin) {
		let real = resolvedBin;
		try {
			real = fs.realpathSync(resolvedBin);
		} catch {
			/* 保留原始路径 */
		}
		const fromBin = ascendToPiPackage(real);
		if (fromBin) return fromBin;
	}
	fail(`未检测到已安装的 ${PI_PACKAGE_NAME}`);
}

/** 复刻 pi 运行时给扩展用的模块别名（同 verify_plugin_ts.mjs） */
function buildAliases(piPkg, piRequire) {
	const resolveFromPi = (spec) => {
		try {
			return piRequire.resolve(spec);
		} catch {
			return null;
		}
	};
	const distIndex = path.join(piPkg, "dist", "index.js");
	const entries = {
		"@earendil-works/pi-coding-agent": distIndex,
		"@mariozechner/pi-coding-agent": distIndex,
		"@earendil-works/pi-tui": resolveFromPi("@earendil-works/pi-tui"),
		"@earendil-works/pi-agent-core": resolveFromPi("@earendil-works/pi-agent-core"),
		"@earendil-works/pi-ai": resolveFromPi("@earendil-works/pi-ai/compat") ?? resolveFromPi("@earendil-works/pi-ai"),
		"@earendil-works/pi-ai/compat": resolveFromPi("@earendil-works/pi-ai/compat"),
		"@earendil-works/pi-ai/oauth": resolveFromPi("@earendil-works/pi-ai/oauth"),
		"@earendil-works/pi-ai/providers/all": resolveFromPi("@earendil-works/pi-ai/providers/all"),
		typebox: resolveFromPi("typebox"),
		"typebox/compile": resolveFromPi("typebox/compile"),
		"typebox/value": resolveFromPi("typebox/value"),
	};
	return Object.fromEntries(Object.entries(entries).filter(([, value]) => value));
}

/** 找一条含 system 消息（带 sections / toolsAdded）的真实会话文件 */
function findLatestSessionWithSystemMessage() {
	const root = path.join(os.homedir(), ".pi", "agent", "sessions");
	if (!fs.existsSync(root)) fail(`未找到会话目录：${root}`);
	const candidates = [];
	for (const dir of fs.readdirSync(root)) {
		const dirPath = path.join(root, dir);
		if (!fs.statSync(dirPath).isDirectory()) continue;
		for (const file of fs.readdirSync(dirPath)) {
			if (!file.endsWith(".jsonl")) continue;
			candidates.push(path.join(dirPath, file));
		}
	}
	candidates.sort().reverse();
	for (const file of candidates) {
		const found = readSystemMessage(file);
		if (found.system && Object.keys(found.system.sections ?? {}).length > 0) return file;
	}
	fail("没有找到带 sections 的 system 消息（会话档案均由旧版 pi 写入？）");
}

function readSystemMessage(file) {
	for (const line of fs.readFileSync(file, "utf8").split("\n")) {
		if (!line.trim()) continue;
		let entry;
		try {
			entry = JSON.parse(line);
		} catch {
			continue;
		}
		if (entry.type === "message" && entry.message?.role === "system") return { system: entry.message };
	}
	return {};
}

async function main() {
	const args = parseArgs(process.argv.slice(2));
	const piPkg = locatePiPackage(args["pi-pkg"]);
	const loaderPath = path.join(piPkg, "dist", "core", "extensions", "loader.js");
	const hostRequire = createRequire(loaderPath);
	const jiti = hostRequire("jiti").createJiti(loaderPath, {
		moduleCache: false,
		alias: buildAliases(piPkg, createRequire(path.join(piPkg, "package.json"))),
	});

	const agentDir = process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi", "agent");
	const pluginDir = path.join(agentDir, ...PLUGIN_RELATIVE);
	for (const file of ["welcome.ts", "context-usage.ts"]) {
		if (!fs.existsSync(path.join(pluginDir, file))) fail(`插件文件不存在：${path.join(pluginDir, file)}`);
	}

	const welcome = await jiti.import(path.join(pluginDir, "welcome.ts"), { default: false });
	const contextUsage = await jiti.import(path.join(pluginDir, "context-usage.ts"), { default: false });
	const tui = await jiti.import("@earendil-works/pi-tui", { default: false }).catch(() => null);
	const measure = tui?.visibleWidth ?? ((line) => String(line).replace(ANSI_RE, "").length);

	// ── ① 口径校验：真实会话 → 分段估值 ────────────────────────────────────────
	const sessionFile = args.session ? path.resolve(args.session) : findLatestSessionWithSystemMessage();
	const { system } = readSystemMessage(sessionFile);
	const sections = system.sections ?? {};
	const tools = system.toolsAdded ?? [];
	if (Object.keys(sections).length === 0) fail(`${sessionFile} 的 system 消息没有 sections`);
	if (tools.length === 0) fail(`${sessionFile} 的 system 消息没有 toolsAdded`);

	// 复刻 pi-ai/utils/text.js 的 getSystemMessageText：段落用 \n\n 拼接
	const prompt = Object.values(sections).join("\n\n");
	const ctxStub = { getSystemPrompt: () => prompt };
	const piStub = {
		getAllTools: () => tools,
		getActiveTools: () => tools.map((tool) => tool.name),
	};

	const breakdown = contextUsage.estimatePromptBreakdown(ctxStub, piStub);
	if (!breakdown) fail("estimatePromptBreakdown 返回 null（解析失败？）");

	const expectedSystem = Math.ceil(prompt.length / 4);
	const piRecordedTools = Math.ceil(JSON.stringify(tools).length / 4);
	const declared = tools.map((tool) => ({
		name: tool.name,
		description: tool.description ?? "",
		parameters: tool.parameters ?? {},
	}));
	const expectedDeclaredTools = Math.ceil(JSON.stringify(declared).length / 4);

	if (breakdown.system !== expectedSystem) {
		fail(`system 估值不符：得到 ${breakdown.system}，期望 ${expectedSystem}`);
	}
	if (breakdown.tools !== expectedDeclaredTools) {
		fail(`tools 估值不符：得到 ${breakdown.tools}，期望 ${expectedDeclaredTools}（声明字段口径）`);
	}
	if (breakdown.total !== breakdown.system + breakdown.tools) {
		fail(`total 不等于 system + tools：${breakdown.total}`);
	}
	if (breakdown.toolCount !== tools.length) {
		fail(`toolCount 不符：得到 ${breakdown.toolCount}，期望 ${tools.length}`);
	}
	const recordedTags = Object.keys(sections).filter((name) => name !== "preamble");
	const missingTags = recordedTags.filter((name) => !breakdown.sections.some((section) => section.name === name));
	if (missingTags.length > 0) fail(`分段标签缺失：${missingTags.join(", ")}`);
	const sectionSum = breakdown.sections.reduce((sum, section) => sum + section.tokens, 0);
	if (sectionSum > breakdown.system + 1) {
		fail(`分段合计 ${sectionSum} 超过 system 总量 ${breakdown.system}`);
	}
	// 与 Pi 自己的记账口径对齐（排除 constrainedSampling 等非声明字段，容许 10% 偏差）
	const drift = Math.abs(breakdown.tools - piRecordedTools) / piRecordedTools;
	if (drift > 0.1) {
		fail(`工具声明口径漂移 ${(drift * 100).toFixed(1)}%（探针 ${breakdown.tools} vs Pi 记账 ${piRecordedTools}）`);
	}

	note(`会话：${path.basename(sessionFile)}`);
	note(
		`口径：system ${breakdown.system} + tools ${breakdown.tools}（${breakdown.toolCount} 个，` +
			`Pi 记账 ${piRecordedTools}，偏差 ${(drift * 100).toFixed(1)}%）= ${breakdown.total}`,
	);
	note(`分段：${breakdown.sections.map((section) => `${section.name} ${section.tokens}`).join(" · ")}`);

	// ── ② 渲染校验：多宽度 ─────────────────────────────────────────────────────
	const WelcomeHeader = welcome.WelcomeHeader;
	if (typeof WelcomeHeader !== "function") fail("welcome.ts 未导出 WelcomeHeader");

	const loadedCounts = { contextFiles: 1, skills: 12, promptTemplates: 3 };
	const margins = [
		{ label: "分段数据", breakdown },
		{ label: "缺省回退", breakdown: null },
	];
	for (const margin of margins) {
		for (const width of RENDER_WIDTHS) {
			const header = new WelcomeHeader("DeepSeek V4.1 Flash", "deepseek", [], loadedCounts, margin.breakdown?.total ?? 4200, margin.breakdown);
			const lines = header.render(width);
			if (!Array.isArray(lines) || lines.length === 0) {
				if (width < 44) continue;
				fail(`${margin.label} @${width} 列渲染为空`);
			}
			const widths = new Set();
			for (const line of lines) {
				if (!line.replace(ANSI_RE, "").trim()) continue;
				widths.add(measure(line));
			}
			if (widths.size !== 1) {
				fail(`${margin.label} @${width} 列行宽不自洽：${[...widths].join(", ")}`);
			}
			const plain = lines.map((line) => line.replace(ANSI_RE, "")).join("\n");
			if (width < CONTENT_ASSERT_MIN_WIDTH) continue;
			if (margin.breakdown) {
				if (!plain.includes("\u251c") || !plain.includes("\u2514")) {
					fail(`${margin.label} @${width} 列缺少分段分支符号`);
				}
				const firstSection = breakdown.sections[0].name;
				if (!plain.includes(firstSection)) fail(`${margin.label} @${width} 列缺少分段名 ${firstSection}`);
			} else {
				if (plain.includes("\u251c") || plain.includes("\u2514")) {
					fail(`${margin.label} @${width} 列不应出现分段分支符号`);
				}
				if (!/初始提示词 tokens|initial prompt tokens/.test(plain)) {
					fail(`${margin.label} @${width} 列缺少单行总量文案`);
				}
			}
		}
	}
	note(
		`渲染：${margins.length} 种数据 × ${RENDER_WIDTHS.length} 种宽度（${RENDER_WIDTHS.join("/")}）行宽自洽；` +
			`内容断言于 ≥${CONTENT_ASSERT_MIN_WIDTH} 列（窄列会被上游截断，属预期）`,
	);

	// 打印一条宽终端样例，便于人工核对
	const sample = new WelcomeHeader(
		"DeepSeek V4.1 Flash",
		"deepseek",
		[{ name: "Pkm", timeAgo: "3 分钟前" }],
		loadedCounts,
		breakdown.total,
		breakdown,
	).render(110);
	console.log(sample.map((line) => `[render] ${line}`).join("\n"));
	console.log(`[probe] 通过：口径与渲染均符合预期`);
}

main().catch((error) => fail(error?.stack ?? String(error)));
