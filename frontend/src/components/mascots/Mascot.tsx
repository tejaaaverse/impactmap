import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { Sparkles, X } from "lucide-react";
import { pickMessage } from "./mascotMessages";

export type MascotKind = "rabbit" | "tortoise";

type Anchor = "bottom-right" | "bottom-left" | "top-right";

export interface MascotProps {
  kind: MascotKind;
  src: string;
  alt: string;
  name: string;
  messages: string[];
  size: number;
  anchor: Anchor;
}

interface Point {
  x: number;
  y: number;
}

interface Sparkle {
  id: number;
  x: number;
  y: number;
  dx: number;
  dy: number;
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const handler = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }, []);

  return reduced;
}

function startPoint(anchor: Anchor, size: number): Point {
  if (typeof window === "undefined") return { x: 900, y: 600 };
  const width = window.innerWidth;
  const height = window.innerHeight;
  if (width >= 1024) {
    if (anchor === "top-right") return { x: width - 90, y: 150 };
    if (anchor === "bottom-left") return { x: 330, y: height - 110 };
    return { x: width - 100, y: height - 115 };
  }
  if (anchor === "top-right") return { x: width - 52, y: 112 };
  if (anchor === "bottom-left") return { x: size / 2 + 18, y: height - 110 };
  return { x: width - size / 2 - 16, y: height - 112 };
}

function overlapsOtherMascot(x: number, y: number, radius: number): boolean {
  const others = Array.from(
    document.querySelectorAll<HTMLElement>("[data-mascot]"),
  );
  return others.some((el) => {
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    return Math.hypot(cx - x, cy - y) < radius;
  });
}

function isBlocked(x: number, y: number, size: number): boolean {
  const probes: Array<[number, number]> = [
    [0, 0],
    [-size * 0.34, 0],
    [size * 0.34, 0],
    [0, -size * 0.34],
    [0, size * 0.34],
  ];
  const selector =
    "[data-mascot-avoid], a, button, input, select, textarea, nav, table, " +
    "[role='button'], .card, .retro-window, .retro-panel, .hero-panel, .y2k-window, " +
    ".y2k-bevel, .y2k-inset, h1, header, label";
  return probes.some(([dx, dy]) =>
    document
      .elementsFromPoint(x + dx, y + dy)
      .some(
        (el) =>
          el instanceof Element &&
          !el.closest("[data-mascot], [data-mascot-layer], .starfield") &&
          Boolean(el.closest(selector)),
      ),
  );
}

/**
 * A self-contained roaming mascot. Motion is deliberately independent from the
 * app's business logic: the component only reads the viewport and the DOM's
 * avoid-zones, never application state.
 */
export function Mascot({ kind, src, alt, name, messages, size, anchor }: MascotProps) {
  const reducedMotion = usePrefersReducedMotion();
  const wrapperRef = useRef<HTMLButtonElement | null>(null);
  const bubbleRef = useRef<HTMLDivElement | null>(null);
  const posRef = useRef<Point>(startPoint(anchor, size));
  const bubbleOpenRef = useRef(false);
  const lastMessageRef = useRef<string | null>(null);
  const sparkleIdRef = useRef(0);
  const sparkleTimerRef = useRef<number | undefined>(undefined);
  const leapTimerRef = useRef<number | undefined>(undefined);

  const [position, setPosition] = useState<Point>(posRef.current);
  const [moving, setMoving] = useState(false);
  const [leaping, setLeaping] = useState(false);
  const [direction, setDirection] = useState<1 | -1>(1);
  const [travelMs, setTravelMs] = useState(kind === "rabbit" ? 1200 : 3400);
  const [bubble, setBubble] = useState<string | null>(null);
  const [sparkles, setSparkles] = useState<Sparkle[]>([]);
  const [viewport, setViewport] = useState(() =>
    typeof window === "undefined" ? 1200 : window.innerWidth,
  );

  const moveTo = useCallback((next: Point) => {
    posRef.current = next;
    setPosition(next);
  }, []);

  const spawnSparkles = useCallback(() => {
    const next = Array.from({ length: 5 }, () => ({
      id: sparkleIdRef.current++,
      x: randomBetween(-18, 18),
      y: randomBetween(-16, 18),
      dx: randomBetween(-18, 18),
      dy: randomBetween(-34, -12),
    }));
    setSparkles(next);
    if (sparkleTimerRef.current) window.clearTimeout(sparkleTimerRef.current);
    sparkleTimerRef.current = window.setTimeout(() => setSparkles([]), 1150);
  }, []);

  const findTarget = useCallback((): Point | null => {
    if (typeof window === "undefined") return null;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const margin = size / 2 + 14;
    const sidebar = width >= 1024 ? 268 : 0;
    const current = posRef.current;

    for (let attempt = 0; attempt < 34; attempt += 1) {
      const roll = Math.random();
      let x: number;
      let y: number;
      if (roll < 0.28) {
        // Calm left gutter (outside the sidebar on desktop).
        const minX = sidebar + margin + 22;
        x = randomBetween(minX, Math.max(minX + 60, sidebar + width * 0.22));
        y = randomBetween(108, height - margin - 12);
      } else if (roll < 0.61) {
        // Right edge.
        x = randomBetween(width * 0.7, width - margin);
        y = randomBetween(108, height - margin - 12);
      } else if (roll < 0.86) {
        // Bottom strip.
        x = randomBetween(width * 0.18, width - margin - 8);
        y = randomBetween(height * 0.78, height - margin);
      } else {
        // Top strip.
        x = randomBetween(width * 0.22, width * 0.82);
        y = randomBetween(96, Math.max(140, height * 0.22));
      }

      x = clamp(x, margin + 8, width - margin - 8);
      y = clamp(y, 92, height - margin - 8);

      if (width >= 1024 && x < sidebar + margin) continue;
      if (Math.hypot(x - current.x, y - current.y) < 120) continue;
      if (overlapsOtherMascot(x, y, size + 56)) continue;
      if (isBlocked(x, y, size)) continue;
      return { x, y };
    }
    return null;
  }, [size]);

  // Clamp the mascot into the viewport on resize.
  useEffect(() => {
    function handleResize() {
      setViewport(window.innerWidth);
      setPosition((current) => {
        const next = {
          x: clamp(current.x, size / 2 + 10, window.innerWidth - size / 2 - 10),
          y: clamp(current.y, 84, window.innerHeight - size / 2 - 10),
        };
        posRef.current = next;
        return next;
      });
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [size]);

  // Independent movement scheduler.
  useEffect(() => {
    if (reducedMotion) return undefined;
    let cancelled = false;
    let nextTimer = 0;
    let stopTimer = 0;

    const tick = () => {
      if (cancelled) return;
      if (bubbleOpenRef.current) {
        nextTimer = window.setTimeout(tick, randomBetween(4000, 7000));
        return;
      }
      const target = findTarget();
      if (!target) {
        nextTimer = window.setTimeout(tick, randomBetween(5000, 9000));
        return;
      }
      const deltaX = target.x - posRef.current.x;
      if (Math.abs(deltaX) > 12) setDirection(deltaX < 0 ? -1 : 1);
      const travel =
        kind === "rabbit" ? randomBetween(850, 1650) : randomBetween(2600, 4600);
      setTravelMs(travel);
      setMoving(true);
      moveTo(target);
      if (kind === "rabbit" && Math.random() < 0.72) spawnSparkles();
      if (kind === "rabbit" && Math.random() < 0.55) {
        setLeaping(true);
        if (leapTimerRef.current) window.clearTimeout(leapTimerRef.current);
        leapTimerRef.current = window.setTimeout(
          () => setLeaping(false),
          Math.min(travel, 1300),
        );
      }
      stopTimer = window.setTimeout(() => {
        if (!cancelled) setMoving(false);
      }, travel + 220);
      nextTimer = window.setTimeout(tick, randomBetween(5000, 15000));
    };

    nextTimer = window.setTimeout(tick, randomBetween(2600, 5600));
    return () => {
      cancelled = true;
      window.clearTimeout(nextTimer);
      window.clearTimeout(stopTimer);
    };
  }, [findTarget, kind, moveTo, reducedMotion, spawnSparkles]);

  // Keep only one bubble open across both mascots.
  useEffect(() => {
    function onOtherOpen(event: Event) {
      const detail = (event as CustomEvent<{ kind: MascotKind }>).detail;
      if (detail?.kind !== kind) setBubble(null);
    }
    window.addEventListener("impactmap:mascot-open", onOtherOpen);
    return () => window.removeEventListener("impactmap:mascot-open", onOtherOpen);
  }, [kind]);

  // Auto-dismiss the speech bubble.
  useEffect(() => {
    bubbleOpenRef.current = Boolean(bubble);
    if (!bubble) return undefined;
    const timer = window.setTimeout(() => setBubble(null), 6800);
    return () => {
      bubbleOpenRef.current = false;
      window.clearTimeout(timer);
    };
  }, [bubble]);

  // Clicking anywhere else or pressing Escape dismisses the bubble.
  useEffect(() => {
    if (!bubble) return undefined;
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node | null;
      if (!target) return;
      if (wrapperRef.current?.contains(target)) return;
      if (bubbleRef.current?.contains(target)) return;
      setBubble(null);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setBubble(null);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [bubble]);

  useEffect(
    () => () => {
      if (sparkleTimerRef.current) window.clearTimeout(sparkleTimerRef.current);
      if (leapTimerRef.current) window.clearTimeout(leapTimerRef.current);
    },
    [],
  );

  function openBubble() {
    const message = pickMessage(messages, lastMessageRef.current);
    lastMessageRef.current = message;
    setBubble(message);
    window.dispatchEvent(
      new CustomEvent("impactmap:mascot-open", { detail: { kind } }),
    );
  }

  const bubbleWidth = viewport < 640 ? 220 : 252;
  const bubbleLeft = clamp(
    position.x - bubbleWidth / 2,
    10,
    Math.max(10, viewport - bubbleWidth - 10),
  );
  const tailOffset = clamp(position.x - bubbleLeft, 22, bubbleWidth - 22);
  const below = position.y < 210;
  const bubbleStyle: CSSProperties = {
    position: "fixed",
    left: bubbleLeft,
    width: bubbleWidth,
    zIndex: 60,
    ...(below
      ? { top: position.y + size / 2 + 14 }
      : {
          bottom:
            (typeof window === "undefined" ? 800 : window.innerHeight) -
            (position.y - size / 2) +
            12,
        }),
    ["--tail-x" as string]: `${tailOffset}px`,
  } as CSSProperties;

  return (
    <>
      <button
        ref={wrapperRef}
        type="button"
        data-mascot={kind}
        onClick={openBubble}
        aria-label={`${alt}. Click for a message from ${name}.`}
        aria-haspopup="dialog"
        aria-expanded={Boolean(bubble)}
        title={`${name} — click for a coding message`}
        className={`mascot-${kind} group pointer-events-auto fixed left-0 top-0 grid place-items-center rounded-full bg-transparent p-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-hot ${
          moving ? "is-moving" : ""
        } ${leaping ? "is-leaping" : ""}`}
        style={{
          width: size,
          height: size,
          zIndex: 40,
          transform: `translate3d(${position.x - size / 2}px, ${
            position.y - size / 2
          }px, 0)`,
          transitionProperty: "transform",
          transitionDuration: `${travelMs}ms`,
          transitionTimingFunction:
            kind === "rabbit"
              ? "cubic-bezier(0.34, 1.25, 0.64, 1)"
              : "cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <span
          className="block h-full w-full transition-transform duration-300 group-hover:scale-105"
          style={{ transform: `scaleX(${direction})` }}
        >
          <img
            src={src}
            alt=""
            draggable={false}
            className="mascot-sprite h-full w-full select-none object-contain"
          />
        </span>
        {sparkles.map((sparkle) => (
          <span
            key={sparkle.id}
            className="mascot-sparkle"
            aria-hidden="true"
            style={
              {
                left: `calc(50% + ${sparkle.x}px)`,
                top: `calc(50% + ${sparkle.y}px)`,
                ["--spark-x" as string]: `${sparkle.dx}px`,
                ["--spark-y" as string]: `${sparkle.dy}px`,
              } as CSSProperties
            }
          />
        ))}
      </button>

      {bubble && (
        <div
          ref={bubbleRef}
          role="dialog"
          aria-label={`${name} says`}
          aria-live="polite"
          className="speech-bubble rounded-xl px-3.5 py-3 text-left"
          data-side={below ? "below" : "above"}
          style={bubbleStyle}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="pixel-label flex items-center gap-1.5 text-hot">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              {name}
            </span>
            <button
              type="button"
              onClick={() => setBubble(null)}
              className="rounded p-0.5 text-slate-400 transition-colors hover:bg-white/5 hover:text-pale"
              aria-label={`Close ${name}'s message`}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="text-[12px] leading-relaxed text-pale">{bubble}</p>
        </div>
      )}
    </>
  );
}
