"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type {
  ImpactReport,
  SpreadAgent,
  SpreadCohort,
  SpreadGraph,
} from "@/lib/types";

const W = 960;
const H = 520;
const CX = 480;
const CY = 268;
const FOCAL = 980;
const PITCH = 0.58;

type Pt = { x: number; y: number; z: number };
type Cam = { yaw: number };
type Screen = { x: number; y: number; depth: number; s: number };

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return (h >>> 0) / 2 ** 32;
}

function sideOf(agent: SpreadAgent) {
  if (agent.cohort === "in_target") return -1;
  if (agent.cohort === "out_of_target") return 1;
  return agent.in_target ? -1 : 1;
}

function layout(agents: SpreadAgent[]): Record<string, Pt> {
  const pos: Record<string, Pt> = {};
  const people = agents.filter((a) => a.cohort !== "origin").length;
  const n = Math.max(1, people);
  const golden = Math.PI * (3 - Math.sqrt(5));
  let idx = 0;
  agents.forEach((agent) => {
    const t = hash(agent.id);
    const u = hash(`${agent.id}:y`);
    if (agent.cohort === "origin") {
      pos[agent.id] = { x: CX, y: CY, z: 54 };
      return;
    }
    const radial = Math.sqrt((idx + 0.5) / n);
    const theta = idx * golden + t * 0.32;
    // Keep one stable, balanced field: a small cohort bias preserves readability
    // without making the graph collapse into two thin crescents during playback.
    const side = sideOf(agent);
    const x = Math.min(930, Math.max(30, CX + Math.cos(theta) * 360 * radial + side * 58 + (t - 0.5) * 14));
    const y = Math.min(492, Math.max(34, CY + Math.sin(theta) * 212 * radial + (u - 0.5) * 18));
    const z = 6 + t * 42;
    pos[agent.id] = { x, y, z };
    idx += 1;
  });
  return pos;
}

function bend(a: Screen, b: Screen) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  return `M ${a.x} ${a.y} Q ${mx - dy * 0.13} ${my + dx * 0.13} ${b.x} ${b.y}`;
}

function projectPt(p: Pt, mode: "2d" | "3d", cam: Cam): Screen {
  if (mode === "2d") return { x: p.x, y: p.y, depth: 0, s: 1 };
  const x = p.x - CX;
  const z = p.y - CY;
  const y = p.z;
  const cy = Math.cos(cam.yaw);
  const sy = Math.sin(cam.yaw);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const cp = Math.cos(PITCH);
  const sp = Math.sin(PITCH);
  const y2 = y * cp - z1 * sp;
  const z2 = y * sp + z1 * cp;
  const s = FOCAL / (FOCAL + z2 + 260);
  return { x: CX + x1 * s, y: CY - y2 * s + 42, depth: z2, s };
}

function floorRings(mode: "2d" | "3d", cam: Cam) {
  if (mode !== "3d") return [] as { d: string; k: number }[];
  return [4, 3, 2, 1].map((k) => {
    const rx = 90 * k;
    const ry = 78 * k;
    const pts: string[] = [];
    for (let i = 0; i <= 48; i += 1) {
      const a = (i / 48) * Math.PI * 2;
      const p = projectPt({ x: CX + Math.cos(a) * rx, y: CY + Math.sin(a) * ry, z: 0 }, mode, cam);
      pts.push(`${i === 0 ? "M" : "L"} ${p.x} ${p.y}`);
    }
    return { k, d: `${pts.join(" ")} Z` };
  });
}

function fill(cohort: SpreadCohort) {
  if (cohort === "in_target") return "#1947d1";
  if (cohort === "out_of_target") return "#f59a3d";
  if (cohort === "origin") return "#111111";
  return "#d2d2d0";
}

function agentActions(agent: SpreadAgent) {
  return agent.actions?.length ? agent.actions : [agent.action];
}

function actionIcon(agent: SpreadAgent) {
  const actions = agentActions(agent);
  if (actions.some((action) => action === "repost" || action === "quote" || action === "share")) return "🔁";
  if (actions.includes("reply")) return "💬";
  if (actions.includes("like")) return "♥";
  return "";
}

function placeholders(n: number): SpreadGraph {
  const agents: SpreadAgent[] = Array.from({ length: n }, (_, i) => ({
    id: `A${String(i + 1).padStart(2, "0")}`,
    persona_id: "pending",
    name: "Persona",
    role: "",
    interests: [],
    cohort: "never_shown",
    in_target: false,
    shown_round: null,
    action: "ignore",
    watched: 0,
    reason: "",
    skepticism: 0,
    share_tendency: 0,
  }));
  return { agents, edges: [] };
}

export function SpreadView({
  report,
  loading,
  population,
}: {
  report: ImpactReport | null;
  loading: boolean;
  population: number;
}) {
  const graph = report?.simulation.graph;
  const field = loading || Boolean(graph);
  const idle = !field;
  const live = useMemo(
    () => graph ?? (field ? placeholders(population) : { agents: [], edges: [] }),
    [graph, field, population],
  );
  const [mode, setMode] = useState<"2d" | "3d">("2d");
  const [yaw, setYaw] = useState(-0.22);
  const [tick, setTick] = useState(0);
  const [playRound, setPlayRound] = useState(0);
  const [selected, setSelected] = useState<SpreadAgent | null>(null);
  const [hover, setHover] = useState<SpreadAgent | null>(null);
  const playTimer = useRef<number | null>(null);
  const playRoundRef = useRef(0);
  const speedRef = useRef<0.75 | 1 | 1.5>(1);
  const maxRoundRef = useRef(1);
  const drag = useRef<{ x: number; yaw: number } | null>(null);
  const cam = useMemo(() => ({ yaw }), [yaw]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<0.75 | 1 | 1.5>(1);
  useEffect(() => { playRoundRef.current = playRound; }, [playRound]);
  useEffect(() => { speedRef.current = speed; }, [speed]);
  const stopPlay = useCallback(() => {
    if (playTimer.current != null) {
      window.clearInterval(playTimer.current);
      playTimer.current = null;
    }
    setIsPlaying(false);
  }, []);

  const play = useCallback((restart = true) => {
    stopPlay();
    const top = maxRoundRef.current;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const current = Math.max(1, playRoundRef.current);
    const firstRound = restart || current >= top ? 1 : current;
    setPlayRound(reduceMotion ? top : firstRound);
    if (reduceMotion || top <= firstRound) return;
    setIsPlaying(true);
    let round = firstRound;
    playTimer.current = window.setInterval(() => {
      round += 1;
      setPlayRound(Math.min(top, round));
      if (round >= top) stopPlay();
    }, Math.round(900 / speedRef.current));
  }, [stopPlay]);

  const togglePlay = useCallback(() => {
    if (!graph) return;
    if (isPlaying) stopPlay();
    else play(false);
  }, [graph, isPlaying, play, stopPlay]);

  useEffect(() => {
    if (!field || graph) return undefined;
    const resetId = window.setTimeout(() => setTick(0), 0);
    const id = window.setInterval(() => {
      setTick((n) => Math.min(population, n + Math.max(1, Math.round(population / 18))));
    }, 55);
    return () => {
      window.clearTimeout(resetId);
      window.clearInterval(id);
    };
  }, [field, graph, population]);

  useEffect(() => {
    const id = window.setTimeout(() => {
      setSelected(null);
      if (graph) play();
      else setPlayRound(0);
    }, 0);
    return () => {
      window.clearTimeout(id);
      stopPlay();
    };
  }, [graph, play, stopPlay]);

  const maxRound = Math.max(
    1,
    ...live.edges.map((e) => e.round),
    ...live.agents.map((a) => a.shown_round ?? 0),
    report?.simulation.rounds.length ?? 1,
  );
  useEffect(() => { maxRoundRef.current = maxRound; }, [maxRound]);
  const shown = graph ? Math.max(playRound, 1) : 0;
  const people = live.agents.filter((a) => a.cohort !== "origin");
  const visibleAgents = live.agents.filter((agent) => {
    if (agent.cohort === "origin") return Boolean(graph);
    if (!graph) return people.indexOf(agent) < tick;
    return true;
  });
  const painted = (agent: SpreadAgent) => {
    if (!graph || agent.cohort === "origin") return agent.cohort;
    if (agent.cohort === "never_shown") return "never_shown";
    return (agent.shown_round ?? 99) <= shown ? agent.cohort : "never_shown";
  };
  const visibleIds = new Set(visibleAgents.map((a) => a.id));
  const visibleEdges = live.edges.filter(
    (edge) => edge.round <= shown && visibleIds.has(edge.source) && visibleIds.has(edge.target),
  );
  const pos = useMemo(() => layout(live.agents), [live.agents]);
  const projected = useMemo(() => {
    const out: Record<string, Screen> = {};
    for (const agent of live.agents) {
      const p = pos[agent.id];
      if (p) out[agent.id] = projectPt(p, mode, cam);
    }
    return out;
  }, [live.agents, pos, mode, cam]);
  const rings = useMemo(() => floorRings(mode, cam), [mode, cam]);

  const onPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (mode !== "3d") return;
    drag.current = { x: event.clientX, yaw };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    setYaw(drag.current.yaw + (event.clientX - drag.current.x) * 0.006);
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  const replay = useCallback(() => {
    if (!graph) return;
    play();
  }, [graph, play]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== "Space" || !graph) return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "SUMMARY" || target?.isContentEditable) return;
      if (target?.closest("button, a, [role='button'], [role='link']")) return;
      event.preventDefault();
      replay();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [graph, replay]);

  if (loading) {
    return (
      <div role="status" aria-live="polite" className="flex min-h-48 flex-col justify-center border border-[var(--line)] bg-white px-8">
        <p className="text-[18px] font-semibold">Waiting for the analysis...</p>
        <p className="mt-2 text-[13px] text-[var(--muted)]">The completed report will show the simulated distribution rounds.</p>
      </div>
    );
  }

  return (
    <div className="border border-[var(--line)] bg-white">
      <div className={`grid ${idle || !selected ? "" : "md:grid-cols-[minmax(0,1fr)_15rem]"}`}>
        <div className={`relative overflow-hidden bg-white ${idle ? "h-[8rem]" : "min-h-[22rem]"}`}>
          {!idle ? (
            <div className="absolute right-3 top-3 z-10 flex border border-[var(--line)] bg-white">
              {(["2d", "3d"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={mode === item}
                  onClick={() => setMode(item)}
                  className={
                    mode === item
                      ? "bg-[#2b2b2b] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white"
                      : "px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]"
                  }
                >
                  {item}
                </button>
              ))}
            </div>
          ) : null}

          {idle ? (
            <div className="flex h-full flex-col justify-center px-8">
              <p className="text-[18px] font-semibold">No simulation yet.</p>
              <p className="mt-2 max-w-xl text-[13px] leading-5 text-[var(--muted)]">
                Write a draft and choose a niche above, then run the simulation. Media is optional.
              </p>
            </div>
          ) : (
            <div className={`spread-in h-[22rem] w-full sm:h-[25rem] ${mode === "3d" ? "cursor-grab active:cursor-grabbing" : ""}`}>
              <svg
                viewBox={`0 0 ${W} ${H}`}
                className="h-full w-full"
                aria-label="Simulated audience spread. Select a person to inspect their reaction."
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerLeave={onPointerUp}
              >
                {rings.map((ring) => (
                  <path
                    key={ring.k}
                    d={ring.d}
                    fill={ring.k === 4 ? "#f4f4f1" : "none"}
                    stroke="#e6e6e2"
                    strokeWidth={0.8}
                    opacity={0.9}
                  />
                ))}
                {mode === "3d"
                  ? visibleAgents.map((agent) => {
                      const p = pos[agent.id];
                      const top = projected[agent.id];
                      if (!p || !top) return null;
                      const ground = projectPt({ x: p.x, y: p.y, z: 0 }, mode, cam);
                      return (
                        <g key={`stem-${agent.id}`} opacity={painted(agent) === "never_shown" ? 0.28 : 0.55}>
                          <ellipse cx={ground.x} cy={ground.y} rx={7 * ground.s} ry={3 * ground.s} fill="#d8d8d4" />
                          <line x1={ground.x} y1={ground.y} x2={top.x} y2={top.y} stroke="#cfcfca" strokeWidth={0.9} />
                        </g>
                      );
                    })
                  : null}
                {visibleEdges.map((edge) => {
                  const ap = projected[edge.source];
                  const bp = projected[edge.target];
                  if (!ap || !bp) return null;
                  const fresh = edge.round === shown;
                  return (
                    <path
                      key={`${edge.source}-${edge.target}-${edge.round}`}
                      d={bend(ap, bp)}
                      fill="none"
                      stroke={edge.kind === "share" ? "#c23b3b" : "#9aa5ad"}
                      strokeWidth={(edge.kind === "share" ? 1.8 : 1.2) * ((ap.s + bp.s) / 2)}
                      strokeDasharray={edge.kind === "share" ? undefined : "5 3"}
                      opacity={fresh ? 1 : 0.82}
                      className={fresh ? "edge-draw" : undefined}
                    />
                  );
                })}
                {[...visibleAgents]
                  .sort((a, b) => (projected[b.id]?.depth ?? 0) - (projected[a.id]?.depth ?? 0))
                  .map((agent) => {
                    const pt = projected[agent.id];
                    if (!pt) return null;
                    const cohort = painted(agent);
                    const base =
                      agent.cohort === "origin"
                        ? 13
                        : people.length > 160
                          ? 5
                          : people.length > 60
                            ? 7.5
                            : 10;
                    const r = (cohort === "never_shown" && agent.cohort !== "origin" ? base * 0.72 : base) * pt.s;
                    const icon =
                      agent.cohort === "origin"
                        ? ""
                        : graph && cohort !== "never_shown"
                          ? actionIcon(agent)
                          : "";
                    const active = selected?.id === agent.id;
                    const popping = Boolean(graph && agent.shown_round === shown);
                    return (
                      <g
                        key={agent.id}
                        transform={`translate(${pt.x} ${pt.y})`}
                        className="cursor-pointer"
                        role="button"
                        tabIndex={graph ? 0 : -1}
                        aria-label={`${agent.id}, ${agent.name}`}
                        onClick={() => graph && setSelected(agent)}
                        onKeyDown={(event) => {
                          if ((event.key === "Enter" || event.key === " ") && graph) {
                            event.preventDefault();
                            setSelected(agent);
                          }
                        }}
                        onMouseEnter={() => setHover(agent)}
                        onMouseLeave={() => setHover((cur) => (cur?.id === agent.id ? null : cur))}
                      >
                        <circle
                          className={popping ? "bulb-pop" : undefined}
                          r={r + (active ? 2 : 0)}
                          fill={fill(cohort)}
                          stroke={active ? "#111" : "#f7f7f5"}
                          strokeWidth={active ? 2 : 0.7}
                        />
                        {agent.cohort === "origin" ? <circle r={3.2 * pt.s} fill="#f7f7f5" /> : null}
                        {icon ? (
                          <text textAnchor="middle" dy="0.35em" fontSize={r > 7 ? 8 : 6} fill="white">
                            {icon}
                          </text>
                        ) : null}
                      </g>
                    );
                  })}
              </svg>
            </div>
          )}
          {hover && projected[hover.id] && !idle ? (
            <div
              className="pointer-events-none absolute z-10 border border-[var(--line)] bg-white px-2 py-1.5 text-[11px]"
              style={{
                left: `${(projected[hover.id].x / W) * 100}%`,
                top: `${(projected[hover.id].y / H) * 100}%`,
              }}
            >
              <p className="font-semibold text-[var(--fg)]">{hover.id} · {hover.name}</p>
              <p className="text-[var(--muted)]">{hover.role} · {agentActions(hover).join(" + ")}</p>
            </div>
          ) : null}

          {!idle ? (
            <div className="absolute bottom-3 left-3 z-10 flex flex-wrap gap-x-3 gap-y-1 bg-white/90 px-2 py-1 text-[11px] text-[var(--muted)]">
              <LegendDot color="#1947d1" label="in-target" />
              <LegendDot color="#f59a3d" label="out-of-target" />
              <LegendDot color="#d2d2d0" label="never shown" />
              <span className="inline-flex items-center gap-1.5">
                <i className="h-px w-3 bg-[#c23b3b]" />
                shared
              </span>
              <span className="inline-flex items-center gap-1.5">
                <i className="h-px w-3 border-t border-dashed border-[#9aa5ad]" />
                algo
              </span>
            </div>
          ) : null}

          {graph ? (
            <p className="absolute bottom-3 right-3 z-10 hidden lg:block bg-white/90 px-2 py-1 font-[family-name:var(--font-geist-mono)] text-[11px] tracking-wide text-[var(--muted)]">
              {mode === "3d" ? "Drag to orbit · [Space]" : "Press [Space]"}
            </p>
          ) : null}
        </div>

        {idle || !selected ? null : (
          <aside className="relative border-t border-[var(--line)] p-4 text-[12px] md:border-l md:border-t-0">
            <button type="button" aria-label="Close persona details" onClick={() => setSelected(null)} className="absolute right-2 top-2 px-2 py-1 text-[var(--muted)] hover:text-[var(--fg)]">×</button>
            <AgentCard agent={selected} />
          </aside>
        )}
      </div>

      {graph ? (
        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--line)] px-3 py-2 text-[11px] text-[var(--muted)]">
          <button
            type="button"
            onClick={togglePlay}
            aria-label={isPlaying ? "Pause round playback" : "Resume round playback"}
            className="rounded-none border border-[var(--line)] px-3 py-1 font-semibold uppercase tracking-wide text-[var(--fg)]"
          >
            {isPlaying ? "Pause" : "Play"}
          </button>
          <button type="button" onClick={replay} className="rounded-none border border-[var(--line)] px-3 py-1 font-semibold uppercase tracking-wide text-[var(--fg)]">
            Replay
          </button>
          <label className="flex min-w-[13rem] flex-1 items-center gap-2">
            <span className="sr-only">Simulation round</span>
            <input
              type="range"
              min={1}
              max={maxRound}
              step={1}
              value={Math.max(1, playRound)}
              aria-valuetext={"Round " + Math.max(1, playRound) + " of " + maxRound}
              onChange={(event) => {
                stopPlay();
                setPlayRound(Number(event.target.value));
              }}
              className="w-full"
            />
          </label>
          <label className="inline-flex items-center gap-1.5">
            <span>Speed</span>
            <select value={speed} aria-label="Playback speed" onChange={(event) => { const nextSpeed = Number(event.target.value) as 0.75 | 1 | 1.5; speedRef.current = nextSpeed; setSpeed(nextSpeed); if (isPlaying) play(false); }} className="border border-[var(--line)] bg-white px-1.5 py-1 text-[11px] text-[var(--fg)]">
              <option value="0.75">0.75×</option>
              <option value="1">1×</option>
              <option value="1.5">1.5×</option>
            </select>
          </label>
          <span className="font-[family-name:var(--font-geist-mono)] uppercase tracking-wide">
            {"round " + Math.max(1, playRound)}
          </span>
          <span className="inline-flex h-7 min-w-12 items-center justify-center rounded-none border border-[var(--line)] px-2 font-[family-name:var(--font-geist-mono)]">
            {Math.max(playRound, 1) + "/" + maxRound}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <i className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function AgentCard({ agent }: { agent: SpreadAgent }) {
  const actions = agentActions(agent).filter((item) => item !== "ignore");
  const action = actions.length ? actions.map((item) => item.replace("_", " ").toUpperCase()).join(" + ") : "SKIP";
  const dwell = Math.max(0, Math.min(100, Math.round(agent.watched * 100)));
  const sharing = Math.max(0, Math.min(100, Math.round(agent.share_tendency * 100)));
  const skepticism = Math.max(0, Math.min(100, Math.round(agent.skepticism * 100)));
  const topicAffinity = agent.topic_affinity == null
    ? null
    : Math.max(0, Math.min(100, Math.round(agent.topic_affinity * 100)));
  return (
    <div>
      <p className="lab-label">
        {agent.id} · round {agent.shown_round ?? "—"}
      </p>
      <p className="mt-2 text-[17px] font-semibold leading-5">{agent.name}</p>
      <p className="mt-1 text-[12px] text-[var(--muted)]">{agent.role}</p>
      {agent.interests.length > 0 ? (
        <p className="mt-2 text-[12px] leading-4 text-[var(--muted)]">{agent.interests.join(" · ")}</p>
      ) : null}
      <div className="mt-4 flex items-start gap-3 border-y border-[var(--line)] py-2">
        <p className="lab-label">Action</p>
        <p className="border border-[var(--line)] px-1.5 text-[10px] font-semibold uppercase tracking-wide">{action}</p>
      </div>
      <p className="lab-label mt-4">Dwell proxy {dwell}%</p>
      <span className="mt-1 block h-1.5 bg-[var(--fill)]">
        <span className="block h-1.5 bg-[#2b2b2b]" style={{ width: `${dwell}%` }} />
      </span>
      <p className="mt-1 text-[10px] leading-4 text-[var(--muted)]">Relative model signal; not watch completion.</p>
      {topicAffinity != null ? (
        <>
          <p className="lab-label mt-3">Topic affinity {topicAffinity}%</p>
          <span className="mt-1 block h-1.5 bg-[var(--fill)]">
            <span className="block h-1.5 bg-[var(--blue)]" style={{ width: `${topicAffinity}%` }} />
          </span>
        </>
      ) : null}
      <p className="lab-label mt-3">Sharing tendency {sharing}%</p>
      <span className="mt-1 block h-1.5 bg-[var(--fill)]">
        <span className="block h-1.5 bg-[#2b2b2b]" style={{ width: `${sharing}%` }} />
      </span>
      <p className="lab-label mt-3">Skepticism {skepticism}%</p>
      <span className="mt-1 block h-1.5 bg-[var(--fill)]">
        <span className="block h-1.5 bg-[var(--out)]" style={{ width: `${skepticism}%` }} />
      </span>
      {agent.in_network != null || agent.ranking_position != null ? (
        <p className="mt-3 text-[11px] leading-4 text-[var(--muted)]">
          {agent.in_network == null ? "Network not reported" : agent.in_network ? "In-network" : "Out-of-network"}
          {agent.ranking_position != null ? ` · candidate rank ${agent.ranking_position}` : ""}
          {agent.ranking_selected === false ? " · not selected" : ""}
        </p>
      ) : null}
      {agent.behavior_profile_id || agent.persona_source ? (
        <p className="mt-2 break-words text-[10px] leading-4 text-[var(--muted)]">
          {agent.behavior_profile_id ? `behavior ${agent.behavior_profile_id}` : "behavior profile not reported"}
          {agent.persona_source ? ` · ${agent.persona_source}` : ""}
          {agent.persona_version ? ` ${agent.persona_version}` : ""}
        </p>
      ) : null}
      <p className="lab-label mt-4">Why</p>
      <p className="mt-1 text-[12px] leading-5 text-[var(--muted)]">{agent.reason || "No reason on this agent."}</p>
    </div>
  );
}

