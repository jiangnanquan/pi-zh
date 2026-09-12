// @ts-nocheck
/**
 * tps-status — 实时 token 生成速率（tok/s）
 *
 * 通过 ctx.ui.setStatus("tps", ...) 发布，由 pi-powerline-footer 的
 * powerline.customItems（statusKey: "tps"）提升为 footer 上的独立 segment；
 * 未装 powerline-footer 时降级显示在 pi 内置 footer 的扩展状态行。
 *
 * 口径（与「整轮墙钟均值」的关键区别）：
 *   流式中 → 1.5s 滑动窗口的瞬时速率
 *   结束后 → 本轮 output ÷ 本轮「纯生成时段」之和
 *   分母只累加真正在吐 token 的时段，因此首字延迟、工具执行、用户等待、
 *   自动重试间隔都不计入 —— 不会出现「分母被弹窗重置导致速率虚高」的失真。
 *   分子在流式期间用字符估算，本轮结束时优先用 provider 返回的真实 usage.output 校正。
 */

const WINDOW_MS = 1500; // 滑动窗口长度（毫秒）
const PAINT_MS = 200; // setStatus 刷新节流（毫秒）
const MIN_SEG_MS = 200; // 过短的生成段忽略，避免噪声
const MIN_GEN_MS = 500; // 本轮生成总时长下限，低于此值沿用上一次的显示值

export default function (pi) {
  /** 滑动窗口：[{ t: 时间戳, n: 估算 token 数 }] */
  let win = [];
  /** 本轮累计：字符估算 token 数与纯生成耗时 */
  let runTokens = 0;
  let runGenMs = 0;
  /** 当前生成段（首个 delta → 末个 delta） */
  let segFirst = 0;
  let segLast = 0;
  /** 显示控制 */
  let lastPaint = 0;
  let lastTps = 0;
  let ctxRef = null;

  /** CJK 约 1 token/字，其余约 4 字符/token */
  const estTokens = (s) => {
    let cjk = 0;
    let ascii = 0;
    for (const ch of s) {
      const cp = ch.codePointAt(0);
      if (
        (cp >= 0x2e80 && cp <= 0x9fff) ||
        (cp >= 0xf900 && cp <= 0xfaff) ||
        (cp >= 0xff00 && cp <= 0xff60)
      ) {
        cjk++;
      } else {
        ascii++;
      }
    }
    return cjk + ascii / 4;
  };

  /** 结束当前生成段，把时长并入本轮分母 */
  const closeSegment = () => {
    if (segFirst > 0 && segLast > segFirst) {
      const span = segLast - segFirst;
      if (span >= MIN_SEG_MS) runGenMs += span;
    }
    segFirst = 0;
    segLast = 0;
  };

  /** 滑动窗口瞬时速率 */
  const windowTps = (now) => {
    const cut = now - WINDOW_MS;
    while (win.length > 0 && win[0].t < cut) win.shift();
    if (win.length === 0) return 0;
    let tokens = 0;
    for (const x of win) tokens += x.n;
    const span = (now - win[0].t) / 1000;
    return span >= 0.15 ? tokens / span : 0;
  };

  const paint = (tps) => {
    if (!ctxRef || !ctxRef.ui) return;
    lastTps = tps;
    ctxRef.ui.setStatus("tps", `${tps.toFixed(1)} tok/s`);
  };

  pi.on("session_start", (_event, ctx) => {
    ctxRef = ctx;
  });

  pi.on("agent_start", () => {
    win = [];
    runTokens = 0;
    runGenMs = 0;
    segFirst = 0;
    segLast = 0;
  });

  pi.on("message_update", (event, ctx) => {
    if (!ctxRef) ctxRef = ctx;
    const e = event && event.assistantMessageEvent;
    if (!e) return;

    // 内容块起点 = 新的生成段（thinking 与正文分别成段）
    if (e.type === "start" || e.type === "text_start" || e.type === "thinking_start") {
      closeSegment();
      return;
    }
    if (e.type !== "text_delta" && e.type !== "thinking_delta") return;
    if (typeof e.delta !== "string" || e.delta.length === 0) return;

    const now = Date.now();
    const n = estTokens(e.delta);
    if (n <= 0) return;

    if (segFirst === 0) segFirst = now;
    segLast = now;
    runTokens += n;
    win.push({ t: now, n });

    if (now - lastPaint >= PAINT_MS) {
      lastPaint = now;
      paint(windowTps(now));
    }
  });

  // 工具执行 / 等待用户输入：结束当前生成段，停顿不计入分母
  pi.on("tool_execution_start", closeSegment);
  pi.on("ui_prompt_start", closeSegment);

  pi.on("agent_end", (event, ctx) => {
    if (!ctxRef) ctxRef = ctx;
    closeSegment();

    // 优先用 provider 的真实 output token 校正字符估算
    let real = 0;
    const msgs = (event && event.messages) || [];
    for (const m of msgs) {
      if (m && m.role === "assistant" && m.usage && typeof m.usage.output === "number") {
        real += m.usage.output;
      }
    }

    const tokens = real > 0 ? real : runTokens;
    const tps = runGenMs >= MIN_GEN_MS && tokens > 0 ? tokens / (runGenMs / 1000) : lastTps;

    lastPaint = Date.now();
    paint(tps);
  });

  pi.on("session_shutdown", () => {
    if (ctxRef && ctxRef.ui) ctxRef.ui.setStatus("tps", undefined);
    ctxRef = null;
  });
}
