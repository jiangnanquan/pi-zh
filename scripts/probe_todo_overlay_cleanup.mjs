#!/usr/bin/env node
/**
 * pi-zh — F 线行为探针：todo-overlay-cleanup（面板结算残留清理）
 *
 * 为什么需要它：F2 补丁修的是「全部结算后面板不消失」。静态检查
 * （`--check` 命中 + jiti 加载体检）只能证明源码被改对，不能证明行为符合预期。
 * 本探针用 pi 自带 jiti 加载待测模块，注入任务状态与 mock UI 上下文，断言三条路径：
 *
 *   ① 触发路径：面板只剩 completed（全部结算）→ hide 后必须调用
 *      `setWidget("rpiv-todos", undefined)`，即走标准注销路径；
 *   ② 不触发路径：面板仍有 pending → hide 后不得注销，只允许刷新渲染
 *      （与上游可见行为一致）；
 *   ③ 对照组：对 `.zh-backup` 原版跑同一条①路径，必须**不**注销 ——
 *      证明缺陷真实存在、且补丁确实改变了行为。
 *
 * 用法：
 *   node scripts/probe_todo_overlay_cleanup.mjs                # 测本机已装插件
 *   node scripts/probe_todo_overlay_cleanup.mjs --agent-dir <dir>
 * 退出码：0 三条路径全部符合预期；1 任一不符（并打印收到的调用序列）。
 */

import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

const PI_PACKAGE_NAME = "@earendil-works/pi-coding-agent";
const PLUGIN_PACKAGE = "@juicesharp/rpiv-todo";
const TARGET_FILE = "todo-overlay.ts";
const BACKUP_SUFFIX = ".zh-backup";
const WIDGET_KEY = "rpiv-todos";
/** 对照组临时副本：与目标同目录才能让相对导入（./state/store.js）正常解析 */
const ORIGINAL_PROBE_BASENAME = "todo-overlay.__probe-original__.ts";
const RENDER_WIDTH = 80;

function parseArgs(argv) {
	const args = { expect: [] };
	for (let i = 0; i < argv.length; i++) {
		const token = argv[i];
		if (!token.startsWith("--")) continue;
		const key = token.slice(2);
		const value = argv[i + 1];
		args[key] = value;
		i++;
	}
	return args;
}

function fail(message) {
	console.error(`[probe] 失败：${message}`);
	process.exit(1);
}

function ok(message) {
	console.log(`[probe] ${message}`);
}

function resolveAgentDir(override) {
	if (override) return path.resolve(override.replace(/^~(?=\/)/, process.env.HOME ?? "~"));
	const envDir = process.env.PI_CODING_AGENT_DIR;
	if (envDir) return path.resolve(envDir.replace(/^~(?=\/)/, process.env.HOME ?? "~"));
	return path.join(process.env.HOME ?? "~", ".pi", "agent");
}

/* —— 与 verify_plugin_ts.mjs 同源的 pi 定位 / 别名构建（保持探针可独立运行）—— */

function isPiPackageRoot(dir) {
	try {
		const meta = JSON.parse(fs.readFileSync(path.join(dir, "package.json"), "utf8"));
		return meta?.name === PI_PACKAGE_NAME;
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
		const resolved = path.resolve(explicit.replace(/^~(?=\/)/, process.env.HOME ?? "~"));
		if (isPiPackageRoot(resolved)) return resolved;
		fail(`--pi-pkg 未指向 ${PI_PACKAGE_NAME} 包目录：${resolved}`);
	}
	const piBin = process.env.PI_BIN || "pi";
	let resolvedBin = "";
	try {
		resolvedBin = execFileSync("bash", ["-lc", `command -v ${piBin}`], { encoding: "utf8" }).trim();
	} catch {
		resolvedBin = "";
	}
	if (resolvedBin) {
		let real = resolvedBin;
		try {
			real = fs.realpathSync(resolvedBin);
		} catch {
			/* 保留原始路径继续尝试 */
		}
		const fromBin = ascendToPiPackage(real);
		if (fromBin) return fromBin;
	}
	try {
		const npmRoot = execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim();
		const candidate = path.join(npmRoot, ...PI_PACKAGE_NAME.split("/"));
		if (isPiPackageRoot(candidate)) return candidate;
	} catch {
		/* 忽略，继续报错 */
	}
	fail(`未检测到已安装的 ${PI_PACKAGE_NAME}（command -v ${piBin} → ${resolvedBin || "空"}），可用 --pi-pkg 显式指定`);
}

function buildAliases(piPkg, piRequire) {
	const resolveFromPi = (spec) => {
		try {
			return piRequire.resolve(spec);
		} catch {
			return null;
		}
	};
	const distIndex = path.join(piPkg, "dist", "index.js");
	const piTui = resolveFromPi("@earendil-works/pi-tui");
	const piAgentCore = resolveFromPi("@earendil-works/pi-agent-core");
	const piAiCompat = resolveFromPi("@earendil-works/pi-ai/compat") ?? resolveFromPi("@earendil-works/pi-ai");
	const piAiOauth = resolveFromPi("@earendil-works/pi-ai/oauth");
	const piAiProviders = resolveFromPi("@earendil-works/pi-ai/providers/all");
	const aliases = {
		"@earendil-works/pi-coding-agent": distIndex,
		"@mariozechner/pi-coding-agent": distIndex,
	};
	const optional = {
		"@earendil-works/pi-tui": piTui,
		"@mariozechner/pi-tui": piTui,
		"@earendil-works/pi-agent-core": piAgentCore,
		"@mariozechner/pi-agent-core": piAgentCore,
		"@earendil-works/pi-ai": piAiCompat,
		"@earendil-works/pi-ai/compat": piAiCompat,
		"@earendil-works/pi-ai/oauth": piAiOauth,
		"@earendil-works/pi-ai/providers/all": piAiProviders,
	};
	for (const [spec, entry] of Object.entries(optional)) {
		if (entry) aliases[spec] = entry;
	}
	return aliases;
}

async function loadJiti(explicitPiPkg) {
	const piPkg = locatePiPackage(explicitPiPkg);
	const loaderPath = path.join(piPkg, "dist", "core", "extensions", "loader.js");
	const require = createRequire(loaderPath);
	let createJiti;
	try {
		({ createJiti } = require("jiti"));
	} catch (error) {
		fail(`无法从 pi 加载 jiti：${error?.message ?? error}`);
	}
	// moduleCache 保持开启：store 必须是单例，否则状态注入进不到 overlay 读取的那个槽位。
	return createJiti(loaderPath, {
		moduleCache: true,
		alias: buildAliases(piPkg, createRequire(path.join(piPkg, "package.json"))),
	});
}

/* —— 场景执行 —— */

function makeTasks(spec) {
	return spec.map(([id, status], index) => ({
		id,
		subject: `探针任务 ${id}`,
		status,
		...(status === "in_progress" ? { activeForm: `执行探针任务 ${id}` } : {}),
	}));
}

/**
 * 跑一条路径：注入状态 → 注册面板 → 首帧渲染（填充 pending）→ 触发 hide，
 * 返回 hide 触发的调用序列。
 */
async function runScenario(jiti, pkgDir, modulePath, tasks) {
	const overlayNs = await jiti.import(modulePath, { default: false });
	const store = await jiti.import(path.join(pkgDir, "state", "store.ts"), { default: false });
	const TodoOverlay = overlayNs?.TodoOverlay;
	if (typeof TodoOverlay !== "function") throw new Error(`未在 ${path.basename(modulePath)} 中导出 TodoOverlay 类`);

	const calls = [];
	let factory = null;
	const mockTui = {
		requestRender: (shapeChanged) => calls.push({ call: "requestRender", shapeChanged: shapeChanged === true }),
	};
	// Theme 在渲染期只作样式包装：任何方法都退化为「取最后一个字符串参数」，
	// 探针只关心渲染了几行、调用了哪些 widget 操作，不关心配色。
	const mockTheme = new Proxy(
		{},
		{
			get: () =>
				(...params) => {
					const last = params[params.length - 1];
					return typeof last === "string" ? last : String(params[0] ?? "");
				},
		},
	);
	const mockCtx = {
		theme: mockTheme,
		getToolsExpanded: () => false,
		setWidget: (key, widgetFactory) => {
			calls.push({
				call: "setWidget",
				key,
				kind: widgetFactory === undefined ? "unregister" : "register",
			});
			if (widgetFactory !== undefined) factory = widgetFactory;
		},
	};

	store.__resetState();
	store.setActiveRenderSession("probe-session");
	store.replaceState("probe-session", { tasks, nextId: tasks.length + 1 });

	const overlay = new TodoOverlay();
	overlay.setUICtx(mockCtx);
	overlay.update(); // 面板注册
	if (factory) factory(mockTui, mockTheme).render(RENDER_WIDTH); // 首帧渲染 → 追踪 completed 行

	const mark = calls.length;
	overlay.hideCompletedTasksFromPreviousTurn(); // 模拟下一轮 agent_start
	return calls.slice(mark);
}

const isUnregister = (entry) => entry.call === "setWidget" && entry.key === WIDGET_KEY && entry.kind === "unregister";

async function main() {
	const args = parseArgs(process.argv.slice(2));
	const agentDir = resolveAgentDir(args["agent-dir"]);
	const pkgDir = path.join(agentDir, "npm", "node_modules", PLUGIN_PACKAGE);
	if (!fs.existsSync(pkgDir)) fail(`未找到插件包：${pkgDir}（该插件未安装？）`);

	const targetPath = path.join(pkgDir, TARGET_FILE);
	if (!fs.existsSync(targetPath)) fail(`未找到目标文件：${targetPath}`);
	const backupPath = `${targetPath}${BACKUP_SUFFIX}`;

	const jiti = await loadJiti(args["pi-pkg"]);

	// 补丁版 · ① 触发路径
	const settleCalls = await runScenario(
		jiti,
		pkgDir,
		targetPath,
		makeTasks([
			[1, "completed"],
			[2, "completed"],
			[3, "completed"],
			[4, "completed"],
			[5, "completed"],
			[6, "completed"],
		]),
	);
	if (!settleCalls.some(isUnregister)) {
		fail(
			`触发路径未注销面板（全部 completed 应调用 setWidget("${WIDGET_KEY}", undefined)）；收到的调用：` +
				JSON.stringify(settleCalls),
		);
	}
	ok("触发路径 ✓ 全部结算后 hide 即注销面板（setWidget → undefined）");

	// 补丁版 · ② 不触发路径
	const mixedCalls = await runScenario(
		jiti,
		pkgDir,
		targetPath,
		makeTasks([
			[1, "completed"],
			[2, "completed"],
			[3, "completed"],
			[4, "pending"],
			[5, "in_progress"],
		]),
	);
	if (mixedCalls.some(isUnregister)) {
		fail(`不触发路径误注销面板（仍有 pending 时应保留）；收到的调用：${JSON.stringify(mixedCalls)}`);
	}
	if (!mixedCalls.some((entry) => entry.call === "requestRender")) {
		fail(`不触发路径未刷新渲染；收到的调用：${JSON.stringify(mixedCalls)}`);
	}
	ok("不触发路径 ✓ 仍有未完成任务时只刷新、不注销（与上游一致）");

	// ③ 对照组：原版必须复现缺陷
	if (!fs.existsSync(backupPath)) {
		ok("对照路径 — 未发现 .zh-backup（未打补丁或已被 --restore 清理），跳过");
		return;
	}
	const probeCopy = path.join(pkgDir, ORIGINAL_PROBE_BASENAME);
	fs.copyFileSync(backupPath, probeCopy);
	try {
		const originalCalls = await runScenario(
			jiti,
			pkgDir,
			probeCopy,
			makeTasks([
				[1, "completed"],
				[2, "completed"],
				[3, "completed"],
				[4, "completed"],
				[5, "completed"],
				[6, "completed"],
			]),
		);
		if (originalCalls.some(isUnregister)) {
			fail(`对照组异常：未打补丁的原版竟然注销了面板，补丁前提不成立；收到的调用：${JSON.stringify(originalCalls)}`);
		}
		ok("对照路径 ✓ 原版不注销面板（缺陷可复现，补丁确实改变了行为）");
	} finally {
		fs.rmSync(probeCopy, { force: true });
	}

	console.log(`[probe] 三条路径全部通过（面板结算残留清理已生效）`);
}

main().catch((error) => fail(error?.stack ?? String(error)));
