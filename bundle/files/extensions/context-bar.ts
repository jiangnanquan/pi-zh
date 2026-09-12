/**
 * context-bar — 底部状态栏用 ASCII 进度条显示上下文占用，替代内置的 `◫ 26k/1.0M (2.6%) AC`。
 *
 * 为什么单独做：pi-powerline-footer@0.17.1 的 `context.format` 只支持 "full" / "percent"
 * 两种形态，没有 bar；该包也不提供给扩展注册 segment 的 API。因此走
 * 「本地扩展 + powerline.customItems」路线（与 cache-hit / ds-balance 同一机制）。
 * 不修改 node_modules：npm 包升级或重装会静默覆盖补丁。
 *
 * 形态：`[====------] 2.6%`
 *   - 宽度 10，percent > 0 时至少填 1 格 —— 否则 2.6% 会渲染成一条空槽，看起来像"没在跑"。
 *   - 阈值配色沿用内置 context_pct 规则：>90 error、>70 warning、其余 accent。
 *   - tokens 未知（刚压缩完、下一次响应前）显示 `[----------] ?`；拿不到 contextWindow
 *     时整段隐藏（不显示误导性的 0%）。
 *
 * 同步时机：ctx.getContextUsage() 的值只由「最近一次 assistant 请求的 usage」和
 * 「最近一次 compaction」决定（见 pi 的 AgentSession.getContextUsage），轮内不变化，
 * 所以无需每帧重算 —— 下列事件各推一次即与现实完全同步：
 *   session_start / turn_start / message_end / session_compact / model_select / session_tree
 * turn_start 兼作 /reload 兜底：/reload 重载扩展不保证重发 session_start。
 *
 * 相对内置段舍弃的信息：上下文窗口大小（1.0M）与 auto-compact 标记（AC）。
 * 窗口是模型的固定属性；AC 属于压缩开关状态，需要时查 /status。
 *
 * 环境变量：
 *   PI_CONTEXT_BAR_WIDTH  进度条格数（4–40，默认 10）
 *
 * 配合 pi-powerline-footer 时在 settings.json 提升为 footer segment：
 *   "powerline": {
 *     "disabledSegments": ["context_pct"],
 *     "layout": { "left": ["model", "thinking", "shell_mode", "path", "git",
 *                          "queue", "custom:context-bar", "cost"] },
 *     "customItems": [
 *       { "id": "context-bar", "statusKey": "context-bar",
 *         "position": "left", "selfColorize": true } ]
 *   }
 * 注意必须用 layout 显式摆位：customItems 默认只能追加到组尾（会跑到 cost 后面）。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const STATUS_KEY = "context-bar";
const DEFAULT_WIDTH = 10;
const MIN_WIDTH = 4;
const MAX_WIDTH = 40;

/** 阈值：与内置 context_pct 段保持一致 */
const WARN_PERCENT = 70;
const ERROR_PERCENT = 90;

// ---------------------------------------------------------------------------
// 类型（最小依赖面，避免绑定可能变动的内部类型）
// ---------------------------------------------------------------------------

type ContextUsage = {
	tokens: number | null;
	contextWindow: number;
	percent: number | null;
};

type UiLike = {
	setStatus: (key: string, text?: string) => void;
	theme: { fg: (color: string, text: string) => string };
};

type CtxLike = {
	ui: UiLike;
	getContextUsage?: () => ContextUsage | undefined;
};

// ---------------------------------------------------------------------------
// 纯函数（导出以便单测）
// ---------------------------------------------------------------------------

/** 宽度解析：非数字/越界回落到默认值 */
export function parseWidth(raw: string | undefined): number {
	const n = Number((raw ?? "").trim());
	if (!Number.isFinite(n) || n < MIN_WIDTH || n > MAX_WIDTH) return DEFAULT_WIDTH;
	return Math.floor(n);
}

/**
 * 进度条本体：`[====------]`
 * percent 夹到 [0, 100]；percent > 0 时至少填 1 格（小数百分比在窄条上会全空）。
 */
export function renderBar(percent: number, width: number): string {
	const w = Math.max(MIN_WIDTH, Math.floor(width));
	const clamped = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0;
	const filled = clamped <= 0
		? 0
		: Math.max(1, Math.min(w, Math.round((clamped / 100) * w)));
	return `[${"=".repeat(filled)}${"-".repeat(w - filled)}]`;
}

/** 阈值配色（与内置 context_pct 同规则） */
export function colorFor(percent: number): string {
	if (percent > ERROR_PERCENT) return "error";
	if (percent > WARN_PERCENT) return "warning";
	return "accent";
}

/** 段文本：`[====------] 2.6%`；tokens 未知时 `[----------] ?` */
export function renderText(usage: ContextUsage | undefined, width: number): string | undefined {
	if (!usage || typeof usage.contextWindow !== "number" || usage.contextWindow <= 0) {
		return undefined; // 拿不到窗口大小 → 整段隐藏
	}
	if (usage.tokens === null || usage.percent === null || !Number.isFinite(usage.percent)) {
		return `${renderBar(0, width)} ?`;
	}
	return `${renderBar(usage.percent, width)} ${usage.percent.toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// 扩展主体
// ---------------------------------------------------------------------------

export default function contextBar(pi: ExtensionAPI): void {
	const env = process.env as Record<string, string | undefined>;
	const width = parseWidth(env["PI_CONTEXT_BAR_WIDTH"]);

	let lastUi: UiLike | null = null;

	function sync(ctxRaw: unknown): void {
		const ctx = ctxRaw as CtxLike;
		if (!ctx?.ui) return;
		lastUi = ctx.ui;

		const usage = ctx.getContextUsage?.();
		const text = renderText(usage, width);
		if (text === undefined) {
			ctx.ui.setStatus(STATUS_KEY, undefined);
			return;
		}
		// tokens 未知时 text 以 "?" 结尾，用 dim 区分于正常的百分比
		const unknown = usage?.tokens === null;
		ctx.ui.setStatus(STATUS_KEY, ctx.ui.theme.fg(unknown ? "dim" : colorFor(usage?.percent ?? 0), text));
	}

	// 值只在「一次 assistant 请求完成」或「一次压缩」时变化，这些事件足够覆盖全部跃变点
	pi.on("session_start", async (_event: unknown, ctxRaw: unknown) => sync(ctxRaw));
	pi.on("turn_start", async (_event: unknown, ctxRaw: unknown) => sync(ctxRaw));
	pi.on("message_end", async (_event: unknown, ctxRaw: unknown) => sync(ctxRaw));
	pi.on("session_compact", async (_event: unknown, ctxRaw: unknown) => sync(ctxRaw));
	pi.on("model_select", async (_event: unknown, ctxRaw: unknown) => sync(ctxRaw));
	pi.on("session_tree", async (_event: unknown, ctxRaw: unknown) => sync(ctxRaw));

	pi.on("session_shutdown", async () => {
		lastUi?.setStatus(STATUS_KEY, undefined);
		lastUi = null;
	});
}
