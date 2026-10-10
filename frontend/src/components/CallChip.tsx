import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import { ShieldBanIcon, Tick02Icon } from "@hugeicons/core-free-icons";
import "./CallChip.css";

const HOLD_AT = 0.9;
const SHAKE = [0, -1, 1, -0.66, 0.66, -0.33, 0];
// A denial is not a failure and is not retryable, so the error state says what actually happened.
const WORDS: Record<CallStatus, string> = { running: "running", done: "done", error: "denied by AgntID", idle: "queued" };

export type CallStatus = "idle" | "running" | "done" | "error";
type Glyph = "tool" | "check" | "block";

const fmt = (ms: number) => (ms < 10000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);
const reduceMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
const glyphOf = (s: CallStatus): Glyph => (s === "done" ? "check" : s === "error" ? "block" : "tool");

export interface CallChipProps {
  /** the tool's own icon, shown while idle/running */
  icon?: ReactNode;
  name?: string;
  argument?: string;
  status?: CallStatus;
  expectedMs?: number;
  size?: number;
  radius?: number;
  color?: string;
  surfaceColor?: string;
  progressColor?: string;
  progressOpacity?: number;
  doneColor?: string;
  errorColor?: string;
  washOpacity?: number;
  shake?: number;
  showTimer?: boolean;
  className?: string;
  style?: CSSProperties;
}

export default function CallChip({
  icon = null, name = "tool", argument = "", status = "running", expectedMs = 2500, size = 34, radius = 10,
  color, surfaceColor, progressColor, progressOpacity = 0.08, doneColor, errorColor, washOpacity = 0.14, shake = 6,
  showTimer = true, className = "", style,
}: CallChipProps) {
  const rootRef = useRef<HTMLSpanElement>(null);
  const fillRef = useRef<HTMLSpanElement>(null);
  const timerRef = useRef<HTMLSpanElement>(null);
  const mountedRef = useRef(false);
  const fraction = useRef(0);
  const clock = useRef({ ms: 0 });
  const shakeAnim = useRef<Animation | null>(null);
  const statusRef = useRef(status);
  statusRef.current = status;
  const [mounted, setMounted] = useState(false);
  const [announce, setAnnounce] = useState("");
  const roll = useRef<{ cur: Glyph; prev: Glyph | null }>({ cur: glyphOf(status), prev: null });
  if (glyphOf(status) !== roll.current.cur) roll.current = { cur: glyphOf(status), prev: roll.current.cur };

  const setFraction = (f: number, instant: boolean) => {
    const fill = fillRef.current;
    if (!fill) return;
    fraction.current = f;
    if (instant) fill.style.transition = "none";
    fill.style.transform = `scaleX(${f})`;
    if (instant) { void fill.getBoundingClientRect(); fill.style.transition = ""; }
  };
  const apply = (s: CallStatus, animate: boolean) => {
    if (s === "running") {
      shakeAnim.current?.cancel();
      setFraction(0, true);
      if (animate) setFraction(HOLD_AT, false);
    } else if (s === "done") {
      setFraction(1, !animate);
    } else if (s === "error") {
      setFraction(1, true); // denied: the whole chip takes the magenta fill, running or static
      if (animate && shake > 0 && !reduceMotion() && rootRef.current) {
        shakeAnim.current = rootRef.current.animate(
          SHAKE.map((k) => ({ transform: `translateX(${k * shake}px)`, easing: "cubic-bezier(0.77, 0, 0.175, 1)" })),
          { duration: 450, composite: "add" },
        );
      }
    } else setFraction(0, true);
  };

  useEffect(() => {
    mountedRef.current = true;
    setMounted(true);
    apply(statusRef.current, statusRef.current === "running");
    return () => { mountedRef.current = false; shakeAnim.current?.cancel(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useLayoutEffect(() => {
    if (mountedRef.current) apply(status, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (!showTimer) return undefined;
    const write = (ms: number) => {
      clock.current.ms = ms;
      if (timerRef.current) timerRef.current.textContent = fmt(ms);
    };
    if (status !== "running") {
      if ((status === "idle" || !clock.current.ms) && timerRef.current) timerRef.current.textContent = "—";
      return undefined;
    }
    const startedAt = performance.now();
    write(0);
    if (reduceMotion()) {
      const id = setInterval(() => write(performance.now() - startedAt), 100);
      return () => { clearInterval(id); write(performance.now() - startedAt); };
    }
    let raf = 0;
    const tick = () => { write(performance.now() - startedAt); raf = requestAnimationFrame(tick); };
    tick();
    return () => { cancelAnimationFrame(raf); write(performance.now() - startedAt); };
  }, [status, showTimer]);
  useEffect(() => {
    const ms = showTimer && clock.current.ms ? Math.round(clock.current.ms) : 0;
    const when = status === "done" && ms ? ` in ${ms} ms` : status === "error" && ms ? ` after ${ms} ms` : "";
    setAnnounce(`${name} ${argument}, ${WORDS[status] ?? status}${when}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const font = Math.max(11, Math.round(size * 0.38));
  const glyphState = (g: Glyph) => (g === roll.current.cur ? "in" : g === roll.current.prev ? "out" : undefined);
  const iconSize = font + 2;

  const vars = {
    "--cc-size": `${size}px`, "--cc-font": `${font}px`, "--cc-pad": `${Math.round(size * 0.35)}px`,
    "--cc-gap": `${Math.round(font * 0.55)}px`, "--cc-radius": `${radius}px`,
    "--cc-progress-pct": `${progressOpacity * 100}%`, "--cc-wash-pct": `${washOpacity * 100}%`, "--cc-expected": `${expectedMs}ms`,
    ...(color && { "--cc-color": color }), ...(surfaceColor && { "--cc-surface": surfaceColor }),
    ...(progressColor && { "--cc-progress": progressColor }), ...(doneColor && { "--cc-done": doneColor }),
    ...(errorColor && { "--cc-error": errorColor }),
  } as CSSProperties;

  return (
    <span ref={rootRef} role="status" aria-busy={status === "running" || undefined} data-status={status}
      data-mounted={mounted ? "" : undefined} className={`call-chip${className ? ` ${className}` : ""}`} style={{ ...vars, ...style }}>
      <span ref={fillRef} className="call-chip__fill" aria-hidden="true" />
      <span className="call-chip__slot" aria-hidden="true">
        <span className="call-chip__glyph" data-state={glyphState("tool")}>{icon}</span>
        <span className="call-chip__glyph" data-state={glyphState("check")}>
          <HugeiconsIcon icon={Tick02Icon} size={iconSize} strokeWidth={2.2} />
        </span>
        <span className="call-chip__glyph" data-state={glyphState("block")}>
          <HugeiconsIcon icon={ShieldBanIcon} size={iconSize} strokeWidth={2} />
        </span>
      </span>
      <span className="call-chip__name" aria-hidden="true">{name}</span>
      {argument ? <span className="call-chip__arg" aria-hidden="true">{argument}</span> : null}
      {showTimer ? <span ref={timerRef} className="call-chip__timer" aria-hidden="true">0 ms</span> : null}
      <span className="call-chip__sr">{announce}</span>
    </span>
  );
}
