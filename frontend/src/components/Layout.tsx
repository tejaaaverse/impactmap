import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Boxes,
  Bot,
  Clock,
  LayoutDashboard,
  Lock,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Star,
} from "lucide-react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { StarField } from "./StarField";
import { MascotLayer } from "./mascots/MascotLayer";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/repositories", label: "Repositories", icon: Boxes },
  { to: "/analyses", label: "Analyses", icon: ScanSearch },
  { to: "/benchmarks", label: "Benchmarks", icon: BarChart3 },
  { to: "/copilot", label: "Copilot", icon: Bot },
];

const TICKER = [
  "☆ WELCOME TO IMPACTMAP ☆",
  "REAL AST GRAPHS",
  "GIT-DIFF IMPACT",
  "COVERAGE-GUIDED TEST SELECTION",
  "MEASURED BENCHMARKS",
  "NO SIMULATED DATA",
  "PIP & MOSS ARE ONLINE",
  "SIGN THE GUESTBOOK · PRESS ANY NAV LINK",
];

function HealthPill() {
  const { data, error, loading } = useAsync(() => api.health(), []);
  const online = Boolean(data) && !error;
  return (
    <div
      className="inline-flex items-center gap-2 rounded-md border border-violet-400/25 bg-ink-950/70 px-2.5 py-1.5"
      title={error ?? undefined}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          loading
            ? "animate-pulse bg-hot"
            : online
              ? "bg-lav shadow-[0_0_8px_#B78BFF]"
              : "bg-neon shadow-[0_0_8px_#E94FA8]"
        }`}
      />
      <span className="pixel-label text-[7px] text-slate-400">
        {loading ? "LINKING" : online ? `API v${data?.version}` : "OFFLINE"}
      </span>
    </div>
  );
}

function CompanionPill() {
  return (
    <div className="y2k-bevel rounded-xl p-3">
      <p className="pixel-label mb-2 flex items-center gap-1.5 text-hot">
        <Sparkles className="h-3 w-3" aria-hidden="true" />
        companions online
      </p>
      <div className="flex items-center gap-2">
        <img
          src="/assets/rabbit-pixel.svg"
          alt="Pip the rabbit"
          className="mascot-sprite h-10 w-10 animate-floaty"
          draggable={false}
        />
        <img
          src="/assets/tortoise-pixel.svg"
          alt="Moss the tortoise"
          className="mascot-sprite h-10 w-10 animate-floaty [animation-delay:1.2s]"
          draggable={false}
        />
        <p className="text-[10px] leading-snug text-slate-400">
          Click Pip or Moss anywhere for a coding pep talk.
        </p>
      </div>
    </div>
  );
}

function DesktopClock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const time = now.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-violet-400/20 bg-ink-950/60 px-2 py-1 font-mono text-[10px] text-blush"
      title={now.toLocaleString()}
    >
      <Clock className="h-2.5 w-2.5 text-lav" aria-hidden="true" />
      <span aria-label={`Local time ${time}`}>{time}</span>
      <span className="h-1 w-1 animate-pulse rounded-full bg-hot" aria-hidden="true" />
    </span>
  );
}

function AddressBar() {
  const { pathname } = useLocation();
  const path = pathname === "/" ? "dashboard" : pathname.replace(/^\//, "");
  return (
    <div className="hidden items-center gap-2 border-b border-violet-400/15 bg-ink-950/55 px-4 py-1.5 lg:flex">
      <span className="flex items-center gap-1" aria-hidden="true">
        <span className="window-control" data-tone="hot" />
        <span className="window-control" data-tone="lav" />
        <span className="window-control" data-tone="mint" />
      </span>
      <span className="pixel-label ml-1 hidden text-[5px] text-slate-600 xl:inline">
        file
      </span>
      <span className="pixel-label hidden text-[5px] text-slate-600 xl:inline">
        edit
      </span>
      <span className="pixel-label hidden text-[5px] text-slate-600 xl:inline">
        view
      </span>
      <div className="ml-2 flex min-w-0 flex-1 items-center gap-2 rounded-md border border-violet-400/20 bg-plum/70 px-2.5 py-1 text-[10px] text-slate-400 shadow-[inset_0_1px_0_rgba(255,197,232,0.1)]">
        <Lock className="h-2.5 w-2.5 shrink-0 text-lav" aria-hidden="true" />
        <span className="truncate font-mono">
          impactmap://<span className="text-blush">{path}</span>
        </span>
        <span className="ml-auto hidden shrink-0 items-center gap-1 text-[9px] text-slate-600 xl:inline-flex">
          <span className="h-1 w-1 animate-pulse rounded-full bg-lav" />
          connected
        </span>
      </div>
      <DesktopClock />
      <span className="pixel-label shrink-0 text-[5px] text-slate-600">
        local-first
      </span>
    </div>
  );
}

function Ticker() {
  return (
    <div className="marquee border-b border-violet-400/15 bg-ink-950/45 py-1.5">
      <div className="marquee-track">
        {[0, 1].map((group) => (
          <span
            key={group}
            className="flex items-center gap-5 pr-5"
            aria-hidden={group === 1 || undefined}
          >
            {TICKER.map((item) => (
              <span
                key={item}
                className="pixel-label flex items-center gap-5 text-[6px] text-mauve"
              >
                <Star className="h-2.5 w-2.5 text-hot" aria-hidden="true" />
                {item}
              </span>
            ))}
          </span>
        ))}
      </div>
    </div>
  );
}

export function Layout() {
  return (
    <div className="relative flex min-h-screen">
      <a
        href="#main-content"
        className="sr-only z-[100] rounded-lg border border-hot bg-plum px-3 py-2 text-sm text-pale focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      <StarField />
      <MascotLayer />
      <div className="crt-overlay" aria-hidden="true" />

      <aside className="scrollbar-thin fixed inset-y-0 left-0 z-20 hidden w-64 flex-col overflow-y-auto border-r border-violet-400/20 bg-gradient-to-b from-plum/95 via-plum/90 to-ink-950/95 px-4 py-5 backdrop-blur lg:flex">
        <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-60">
          <span className="absolute left-6 top-24 h-1 w-1 animate-twinkle rounded-full bg-hot" />
          <span className="absolute right-8 top-44 h-1.5 w-1.5 animate-twinkle rounded-full bg-lav [animation-delay:1.4s]" />
          <span className="absolute bottom-40 left-10 h-1 w-1 animate-twinkle rounded-full bg-blush [animation-delay:2.6s]" />
        </div>

        <NavLink
          to="/"
          className="group mb-5 flex items-center gap-3 px-1 focus-visible:rounded-lg"
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-hot/40 bg-gradient-to-br from-neon/20 to-lav/10 shadow-glow transition-transform group-hover:scale-105">
            <img
              src="/assets/mascot-mark.svg"
              alt=""
              aria-hidden="true"
              className="h-5 w-5"
            />
          </span>
          <span className="min-w-0">
            <span className="pixel-font block text-[11px] text-pale drop-shadow-[0_0_10px_rgba(255,121,201,0.45)]">
              IMPACTMAP
            </span>
            <span className="pixel-label mt-1 block text-[6px] text-mauve">
              impact &amp; test intelligence
            </span>
          </span>
        </NavLink>

        {/* Profile card: the nostalgic soul of the layout. */}
        <div className="y2k-bevel relative mb-4 overflow-hidden rounded-lg p-3">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -right-8 -top-10 h-24 w-24 rounded-full bg-neon/20 blur-2xl"
          />
          <div className="relative flex items-center gap-2.5">
            <span className="relative grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-md border border-hot/45 bg-gradient-to-br from-panel to-ink-950">
              <img
                src="/assets/rabbit-pixel.svg"
                alt=""
                aria-hidden="true"
                className="mascot-sprite h-7 w-7"
              />
              <span className="absolute bottom-0.5 right-0.5 h-1.5 w-1.5 rounded-full bg-lav shadow-[0_0_6px_#B78BFF]" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-[11px] font-semibold text-pale">
                dev@impactmap
              </p>
              <p className="pixel-label mt-0.5 text-[5px] text-mauve">
                status: building cool things
              </p>
            </div>
          </div>
          <div className="relative mt-2.5 flex items-center justify-between gap-2 border-t border-violet-400/15 pt-2 text-[9px] text-slate-500">
            <span className="inline-flex items-center gap-1.5">
              <span className="equalizer" aria-hidden="true">
                <span />
                <span />
                <span />
                <span />
              </span>
              now: static analysis
            </span>
            <span className="pixel-label text-[5px] text-hot">v1.0</span>
          </div>
        </div>

        <nav aria-label="Primary" className="flex flex-1 flex-col gap-1.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `nav-link group ${isActive ? "nav-link-active" : ""}`
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="tracking-wide">{label}</span>
              <span className="ml-auto h-1 w-1 rounded-full bg-hot opacity-0 transition-opacity group-hover:opacity-100" />
            </NavLink>
          ))}
        </nav>

        <div className="mt-5 space-y-3">
          <div className="y2k-inset rounded-xl p-3 text-[10px] leading-relaxed text-slate-500">
            <p className="pixel-label mb-1.5 flex items-center gap-1.5 text-lav">
              <Activity className="h-3 w-3" aria-hidden="true" />
              measured, not simulated
            </p>
            All graph, impact and benchmark metrics come from real code and real
            test runs.
          </div>
          <CompanionPill />
          <div className="flex items-center justify-between gap-2 px-1">
            <HealthPill />
            <span
              className="inline-flex items-center gap-1 text-[9px] text-slate-600"
              title="Read-only analysis"
            >
              <ShieldCheck className="h-3 w-3 text-lav" aria-hidden="true" />
              safe
            </span>
          </div>
          <p className="pixel-label px-1 text-[5px] leading-relaxed text-slate-700">
            best viewed at 1024×768 in a dream
          </p>
        </div>
      </aside>

      <div className="relative z-10 flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-violet-400/20 bg-plum/90 backdrop-blur-md lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <NavLink to="/" className="flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-md border border-hot/40 bg-neon/10">
                <img
                  src="/assets/mascot-mark.svg"
                  alt=""
                  aria-hidden="true"
                  className="h-4 w-4"
                />
              </span>
              <span className="pixel-font text-[10px] text-pale">IMPACTMAP</span>
            </NavLink>
            <HealthPill />
          </div>
          <nav
            aria-label="Primary mobile"
            className="scrollbar-thin flex gap-1 overflow-x-auto border-t border-violet-400/15 px-3 py-2"
          >
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] transition-colors ${
                    isActive
                      ? "border-hot/40 bg-neon/15 text-pale shadow-glow"
                      : "border-transparent text-slate-400 hover:bg-white/5 hover:text-pale"
                  }`
                }
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {label}
              </NavLink>
            ))}
          </nav>
        </header>

        <AddressBar />
        <Ticker />

        <main
          id="main-content"
          className="relative mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 sm:px-6 lg:px-8"
        >
          <Outlet />
        </main>

        <footer className="taskbar relative z-20 mt-4">
          <div className="mx-auto flex max-w-[1500px] flex-col items-center justify-between gap-3 px-4 py-3 text-center sm:flex-row sm:px-6 sm:text-left">
            <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
              <span className="taskbar-button">
                <img
                  src="/assets/mascot-mark.svg"
                  alt=""
                  aria-hidden="true"
                  className="h-3 w-3"
                />
                start
              </span>
              <span className="taskbar-button">
                <Boxes className="h-3 w-3 text-hot" aria-hidden="true" />
                impactmap.exe
              </span>
              <span className="taskbar-button hidden sm:inline-flex">
                <Bot className="h-3 w-3 text-lav" aria-hidden="true" />
                copilot
              </span>
            </div>
            <p className="pixel-label text-[6px] leading-relaxed text-slate-600">
              IMPACTMAP · STATIC ANALYSIS + GIT DIFF + COVERAGE-GUIDED TEST
              SELECTION
            </p>
            <p className="flex items-center gap-2 text-[10px] text-slate-600">
              <span className="h-1 w-1 animate-pulse rounded-full bg-lav" />
              Pip &amp; Moss are exploring the universe
            </p>
          </div>
          <div className="holo-strip h-px w-full opacity-60" aria-hidden="true" />
        </footer>
      </div>
    </div>
  );
}
