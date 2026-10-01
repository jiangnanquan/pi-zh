/**
 * context-bar — 底部状态栏用 ASCII 进度条显示上下文占用，替代内置的 `◫ 26k/1.0M (2.6%) AC`。
 *
 * 为什么单独做：pi-powerline-footer@0.17.1 的 `context.format` 只支持 "full" / "percent"
 * 两种形态，没有 bar；该包也不提供给扩展注册 segment 的 API。因此走
 * 「本地扩展 + powerline.customItems」路线（与 cache-hit / ds-balance 同一机制）。
 * 不修改 node_modules：npm 包升级或重装会静默覆盖补丁。
 *
 * 两套口径（v2 新增 agy 口径）：
 *
 *  1. antigravity 线路 —— agy 原生口径。
 *     Pi 上的 agy 模型由 @tian.zuo/pi-antigravity 注册，它对 Pi 上报的 contextWindow 恒为
 *     1_000_000（该插件的 AGY_PI_SCHEDULING_CONTEXT_WINDOW，一个"调度窗口"，故意大于
 *     agy 私有的约 185k 工作窗口）。用它算百分比会系统性低报——2.6% 的显示可能已经吃掉
 *     真实工作窗口的一大半。所以 antigravity 线路改读该插件持久化在 session entry
 *     `pi-antigravity-conversation-state` 里的 agy 原生 contextTokens
 *     （uncached input + cache read，即 agy 自己的模型上下文足迹），按当前分支、当前模型取值：
 *       有数据 → `[~53k]`（估算值，`~` 表示这是 agy 上报的观测值而非精确计量）
 *       无数据 → `[待回报]`（本分支/本模型还没有 agy 回合结束时的持久化记录）
 *     不做百分比：没有可信的真实上限，就不编一个百分比出来。
 *
 *  2. 其它 provider —— Pi 自己的 usage 口径，维持 v1 行为。
 *       形态 `[====------] 2.6%`；tokens 未知（刚压缩完、下一次响应前）显示 `[----------] ?`；
 *       拿不到 contextWindow 时整段隐藏（不显示误导性的 0%）。
 *
 * 形态与配色：
 *   - 宽度 10，percent > 0 时至少填 1 格 —— 否则 2.6% 会渲染成一条空槽，看起来像"没在跑"。
 *   - 阈值配色沿用内置 context_pct 规则：>90 error、>70 warning、其余 accent。
 *   - agy 口径：有估算值时 accent，`待回报` 用 dim。
 *
 * 同步时机：ctx.getContextUsage() 的值只由「最近一次 assistant 请求的 usage」和
 * 「最近一次 compaction」决定（见 pi 的 AgentSession.getContextUsage），轮内不变化。
 * agy 的 conversation-state entry 由 pi-antigravity 在回合收尾时 appendEntry，所以额外监听
 * agent_settled。下列事件各推一次即可覆盖全部跃变点：
 *   session_start / turn_start / message_end / session_compact / model_select / session_tree / agent_settled
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

/** pi-antigravity 持久化 agy 会话状态的 session entry 类型。 */
const AGY_STATE_ENTRY = "pi-antigravity-conversation-state";

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

type SessionEntryLike = {
	type?: string;
	customType?: string;
	data?: unknown;
};

type CtxLike = {
	ui: UiLike;
	model?: { provider?: string; id?: string };
	getContextUsage?: () => ContextUsage | undefined;
	sessionManager?: { getBranch?: () => SessionEntryLike[] };
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

/**
 * 从当前会话分支里解析 agy 原生 contextTokens。
 *
 * 只认最后一个 `pi-antigravity-conversation-state`：
 *   - `kind: "reset"` → 该分支已主动重置，旧数据不可用
 *   - `kind: "conversation"` 且 modelId 与当前模型不同 → 当前模型无观测值
 *   - contextTokens 缺失/非正数 → 尚无观测值
 * 任何一项不满足都返回 undefined，由调用方显示「待回报」而不是拿旧数据充数。
 */
export function resolveAgyContextTokens(
	branch: readonly SessionEntryLike[] | undefined,
	modelId: string | undefined,
): number | undefined {
	if (!Array.isArray(branch)) return undefined;
	for (let index = branch.length - 1; index >= 0; index -= 1) {
		const entry = branch[index];
		if (entry?.type !== "custom" || entry.customType !== AGY_STATE_ENTRY) continue;
		const data = entry.data as
			| { kind?: unknown; modelId?: unknown; contextTokens?: unknown }
			| undefined;
		if (!data || typeof data !== "object") continue;
		if (data.kind === "reset") return undefined;
		if (data.kind !== "conversation") continue;
		if (
			typeof data.modelId === "string" &&
			typeof modelId === "string" &&
			data.modelId !== modelId
		) {
			return undefined;
		}
		const tokens = data.contextTokens;
		if (typeof tokens === "number" && Number.isFinite(tokens) && tokens > 0) return tokens;
		return undefined;
	}
	return undefined;
}

/** agy 足迹的紧凑写法：53k / 1.2m */
export function formatAgyTokens(tokens: number): string {
	if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}m`;
	if (tokens >= 10_000) return `${Math.round(tokens / 1_000)}k`;
	if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
	return String(Math.round(tokens));
}

/** agy 模型原生物理上下文基准为 1,000,000 (1M) tokens（可通过 PI_AGY_WORKING_WINDOW 环境变量覆盖） */
export const AGY_DEFAULT_WORKING_WINDOW = 1_000_000;

export function parseAgyWorkingWindow(raw: string | undefined): number {
	const n = Number((raw ?? "").trim());
	return Number.isFinite(n) && n > 0 ? Math.floor(n) : AGY_DEFAULT_WORKING_WINDOW;
}

/**
 * agy 口径文本与状态：
 * 有观测值时，以模型原生 1M 物理视窗为基准计算百分比与进度槽：
 *   `[==--------] 16% (~164k)`
 * 未知时显示：
 *   `[----------] ?`（与非 agy 线路保持统一视觉语言）
 */
export function renderAgyText(
	tokens: number | undefined,
	width = DEFAULT_WIDTH,
	workingWindow = AGY_DEFAULT_WORKING_WINDOW,
): { text: string; percent: number | null } {
	if (tokens === undefined || !Number.isFinite(tokens) || tokens <= 0) {
		return { text: `${renderBar(0, width)} ?`, percent: null };
	}
	const percent = (tokens / workingWindow) * 100;
	const bar = renderBar(percent, width);
	const text = `${bar} ${percent.toFixed(0)}% (~${formatAgyTokens(tokens)})`;
	return { text, percent };
}

// ---------------------------------------------------------------------------
// 扩展主体
// ---------------------------------------------------------------------------

export default function contextBar(pi: ExtensionAPI): void {
	const env = process.env as Record<string, string | undefined>;
	const width = parseWidth(env["PI_CONTEXT_BAR_WIDTH"]);
	const agyWorkingWindow = parseAgyWorkingWindow(env["PI_AGY_WORKING_WINDOW"]);

	let lastUi: UiLike | null = null;

	function sync(ctxRaw: unknown): void {
		const ctx = ctxRaw as CtxLike;
		if (!ctx?.ui) return;
		lastUi = ctx.ui;

		// —— antigravity 线路：agy 原生口径 ——
		if (ctx.model?.provider === "antigravity") {
			let branch: SessionEntryLike[] | undefined;
			try {
				branch = ctx.sessionManager?.getBranch?.();
			} catch {
				branch = undefined;
			}
			const tokens = resolveAgyContextTokens(branch, ctx.model?.id);
			const { text, percent } = renderAgyText(tokens, width, agyWorkingWindow);
			const color = percent === null ? "dim" : colorFor(percent);
			ctx.ui.setStatus(STATUS_KEY, ctx.ui.theme.fg(color, text));
			return;
		}

		// —— 其它 provider：Pi 自己的 usage 口径 ——
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
	// pi-antigravity 在回合收尾时 appendEntry，落盘晚于 message_end
	pi.on("agent_settled", async (_event: unknown, ctxRaw: unknown) => sync(ctxRaw));

	pi.on("session_shutdown", async () => {
		lastUi?.setStatus(STATUS_KEY, undefined);
		lastUi = null;
	});
}
