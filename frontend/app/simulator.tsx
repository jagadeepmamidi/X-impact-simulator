"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { NICHES, NICHE_COPY, type CompareReport, type ImpactReport, type Niche, type OutcomeRecord, type RecentRun } from "@/lib/types";
import { GITHUB_REPO } from "@/lib/repo";
import { SpreadView } from "./spread";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
const DEV_API_TOKEN = process.env.NODE_ENV === "production" ? "" : (process.env.NEXT_PUBLIC_SIM_DEV_TOKEN ?? "");
const ACCESS_KEY_STORAGE = "x-impact-simulator-access-key";
const MAX_MEDIA_BYTES = 3_500_000;
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);
const VIDEO_TYPES = new Set(["video/mp4", "video/webm", "video/quicktime"]);

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function apiHeaders(init?: HeadersInit) {
  const headers = new Headers(init);
  // Production keys are entered by the operator and held only for this browser tab.
  // The optional bundled token remains restricted to local development builds.
  const sessionToken = typeof window === "undefined" ? "" : sessionStorage.getItem(ACCESS_KEY_STORAGE) ?? "";
  const token = sessionToken || DEV_API_TOKEN;
  if (token) headers.set("X-API-Key", token);
  return headers;
}

async function apiFetch(url: string, init?: RequestInit) {
  const response = await fetch(url, { ...init, headers: apiHeaders(init?.headers) });
  if (response.status === 401) throw new ApiError("API access token required or invalid", 401);
  if (response.status === 429) throw new ApiError("Too many requests. Wait and try again.", 429);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const message = typeof detail.detail === "string" ? detail.detail : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return response;
}

const NICHE_LABEL: Record<Niche, string> = {
  tech: "Tech",
  fitness: "Fitness",
  finance: "Finance",
  comedy: "Comedy",
};

export function Simulator() {
  const [niche, setNiche] = useState<Niche>("tech");
  const [text, setText] = useState("");
  const [textB, setTextB] = useState("");
  const [loadId, setLoadId] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [video, setVideo] = useState<File | null>(null);
  const [population, setPopulation] = useState("40");
  const [boost, setBoost] = useState(6);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Working…");
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [compare, setCompare] = useState<CompareReport | null>(null);
  const mediaInput = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [apiKey, setApiKey] = useState(() => typeof window === "undefined" ? "" : sessionStorage.getItem(ACCESS_KEY_STORAGE) ?? "");
  const [keyInput, setKeyInput] = useState("");
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`${API}/api/simulations?limit=20`)
      .then((response) => response.json() as Promise<{ runs?: RecentRun[] }>)
      .then((payload) => { if (!cancelled) { setRecentRuns(payload.runs ?? []); setHistoryError(null); } })
      .catch((err) => { if (!cancelled) { setRecentRuns([]); setHistoryError(err instanceof Error ? err.message : "Could not load recent runs"); } });
    return () => { cancelled = true; };
  }, [apiKey, report?.run_id, historyVersion]);

  const mediaLabel = video?.name
    ?? (images.length > 1 ? `${images.length} images selected` : images[0]?.name)
    ?? "Drop a video or images here, or click to choose.";

  const clearMedia = () => {
    setVideo(null);
    setImages([]);
    if (mediaInput.current) mediaInput.current.value = "";
  };

  const onFiles = (list: FileList | File[]) => {
    const files = [...list];
    if (files.some((file) => !IMAGE_TYPES.has(file.type) && !VIDEO_TYPES.has(file.type))) {
      clearMedia();
      setError("Choose JPEG, PNG, WebP, GIF, MP4, WebM or MOV files.");
      return;
    }
    if (files.reduce((sum, file) => sum + file.size, 0) > MAX_MEDIA_BYTES) {
      clearMedia();
      setError("Keep total media at or below 3.5 MB for this pilot.");
      return;
    }
    const vid = files.find((f) => VIDEO_TYPES.has(f.type));
    const pics = files.filter((f) => IMAGE_TYPES.has(f.type));
    if (vid) {
      if (files.length !== 1) { clearMedia(); setError("Choose one video or up to five images."); return; }
      setVideo(vid);
      setImages([]);
      setError(null);
      return;
    }
    if (pics.length) {
      if (pics.length > 5) {
        clearMedia();
        setError("Choose up to five images.");
        return;
      }
      setImages(pics);
      setVideo(null);
      setError(null);
      return;
    }
    clearMedia();
    if (files.length) setError("Choose one supported video or up to five supported images.");
  };

  const onSubmit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (loading) return;
    if ((!text.trim() && !images.length && !video) || (textB.trim() && !text.trim())) {
      setError("Enter Hook A to compare captions, or provide text or media for a single run.");
      return;
    }
    if (text.length > 10000 || textB.length > 10000) { setError("Captions must be 10,000 characters or fewer."); return; }
    const mediaBytes = images.reduce((sum, file) => sum + file.size, 0) + (video?.size ?? 0);
    if (mediaBytes > MAX_MEDIA_BYTES) { setError("Keep total media at or below 3.5 MB for this pilot."); return; }
    setLoading(true);
    setLoadingLabel(textB.trim() ? "Comparing hooks…" : "Running simulation…");
    setError(null);
    setCompare(null);
    setReport(null);
    const body = new FormData();
    body.append("niche", niche);
    body.append("boost", String(boost));
    body.append("population", population);
    images.forEach((file) => body.append("images", file));
    if (video) body.append("video", video);
    const comparing = Boolean(textB.trim());
    if (comparing) {
      body.append("text_a", text);
      body.append("text_b", textB);
    } else {
      body.append("text", text);
    }
    try {
      abortRef.current = new AbortController();
      const response = await apiFetch(`${API}${comparing ? "/api/compare" : "/api/simulate"}`, { method: "POST", body, signal: abortRef.current.signal });
      if (comparing) {
        const result = (await response.json()) as CompareReport;
        if (abortRef.current?.signal.aborted) return;
        setCompare(result);
        setReport(result.a);
        if (result.a.run_id) setLoadId(result.a.run_id);
      } else {
        const loaded = (await response.json()) as ImpactReport;
        if (abortRef.current?.signal.aborted) return;
        setReport(loaded);
        if (loaded.run_id) setLoadId(loaded.run_id);
      }
    } catch (err) {
      setError(err instanceof DOMException && err.name === "AbortError" ? "Stopped waiting. The server may still finish this run; refresh Recent runs to check." : err instanceof Error ? err.message : "Simulation failed");
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  const onLoad = async () => {
    const id = loadId.trim();
    if (!id) return;
    setLoading(true);
    setLoadingLabel("Loading saved run…");
    setError(null);
    setCompare(null);
    abortRef.current = new AbortController();
    try {
      const response = await apiFetch(`${API}/api/simulations/${encodeURIComponent(id)}`, { signal: abortRef.current.signal });
      const loaded = (await response.json()) as ImpactReport;
      if (abortRef.current?.signal.aborted) return;
      setReport(loaded);
      setNiche(loaded.niche);
      setText(loaded.input_text ?? "");
      setTextB("");
      setPopulation(String(loaded.population ?? 100));
      setBoost(loaded.boost ?? 6);
      clearMedia();
    } catch (err) {
      setError(err instanceof DOMException && err.name === "AbortError" ? "Stopped waiting. The server may still finish this request." : err instanceof Error ? err.message : "Load failed");
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  const onReplay = async () => {
    const id = loadId.trim();
    if (!id) return;
    setLoading(true);
    setLoadingLabel("Re-running stored snapshot…");
    setError(null);
    setCompare(null);
    abortRef.current = new AbortController();
    try {
      const response = await apiFetch(`${API}/api/simulations/${encodeURIComponent(id)}/replay`, { method: "POST", signal: abortRef.current.signal });
      const loaded = (await response.json()) as ImpactReport;
      if (abortRef.current?.signal.aborted) return;
      setReport(loaded);
      setNiche(loaded.niche);
      setText(loaded.input_text ?? "");
      setTextB("");
      setPopulation(String(loaded.population ?? 100));
      setBoost(loaded.boost ?? 6);
      clearMedia();
      if (loaded.run_id) setLoadId(loaded.run_id);
    } catch (err) {
      setError(err instanceof DOMException && err.name === "AbortError" ? "Stopped waiting. The server may still finish this request." : err instanceof Error ? err.message : "Replay failed");
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  const stopWaiting = () => abortRef.current?.abort();

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[1180px] flex-1 flex-col px-8 py-6">
      <header className="flex items-end justify-between border-b border-[var(--line)] pb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[24px] font-semibold tracking-tight">Impact Simulator</h1>
          <span className="hidden text-[15px] text-[var(--muted)] sm:inline">Run report</span>
        </div>
        <Link href="/readme" className="text-[13px] text-[var(--muted)] hover:text-[var(--fg)]">About</Link>
      </header>

      <form onSubmit={onSubmit} className="flex flex-1 flex-col">
        <Section index="01" title="Input" aside="Write a draft, choose a niche, and compare its simulated response">
          <div className="border border-[var(--line)] bg-white">
            <div className="grid gap-0 md:grid-cols-[2.2fr_1.1fr_1fr]">
               <Cell label="Draft and niche">
                <select
                  aria-label="Niche"
                  value={niche}
                  onChange={(e) => setNiche(e.target.value as Niche)}
                  className="mb-2 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none"
                >
                  {NICHES.map((item) => (
                    <option key={item} value={item}>{NICHE_LABEL[item]}</option>
                  ))}
                </select>
                 <label className="block text-[12px]">Hook A
                   <textarea
                   value={text}
                   onChange={(e) => setText(e.target.value)}
                   placeholder="Hook A — caption to score"
                   maxLength={10000}
                   rows={4}
                   className="mt-1 w-full resize-y rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none placeholder:text-[var(--muted)]"
                   aria-label="Hook A caption"
                 /></label>
                 <label className="mt-2 block text-[12px]">Hook B (optional)<textarea
                   value={textB}
                   onChange={(e) => setTextB(e.target.value)}
                   placeholder="Hook B — optional second caption"
                   maxLength={10000}
                   rows={3}
                   className="mt-2 w-full resize-y rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none placeholder:text-[var(--muted)]"
                   aria-label="Hook B optional caption"
                 /></label>
                <p className="mt-2 text-[11px] leading-4 text-[var(--muted)]">{NICHE_COPY[niche]}</p>
              </Cell>
              <DropCell
                label="Optional media"
                filename={mediaLabel}
                filled={Boolean(video || images.length)}
                onClick={() => mediaInput.current?.click()}
                onDropFiles={onFiles}
                onClear={clearMedia}
              />
            <Cell label="Population">
                <select
                  id="population"
                  aria-label="Population"
                value={population}
                onChange={(e) => setPopulation(e.target.value)}
                className="w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none"
              >
                <option value="40">40 simulated agents</option>
                <option value="100">100 simulated agents</option>
                <option value="320">320 simulated agents</option>
                <option value="500">500 simulated agents</option>
              </select>
              <p className="mt-2 text-[11px] leading-4 text-[var(--muted)]">~{population} simulated agents in this run</p>
              <label className="lab-label mt-5 block" htmlFor="boost">Boost</label>
              <input
                id="boost"
                type="range"
                min={1}
                max={12}
                value={boost}
                onChange={(e) => setBoost(Number(e.target.value))}
                className="mt-2 w-full"
              />
              <p className="text-[11px] text-[var(--muted)]">{boost} seeds · round-1 initial reach</p>
            </Cell>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full border-t border-[var(--line)] bg-[var(--run)] py-3 text-[13px] font-semibold tracking-[0.28em] text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? loadingLabel : textB.trim() ? "COMPARE HOOKS" : "RUN SIMULATION"}
          </button>
          {error && (
            <p role="alert" className="border-t border-[var(--hairline)] px-3 py-2 text-[15px] text-[var(--danger)]">{error}</p>
          )}
          </div>
          <input
            ref={mediaInput}
            type="file"
            multiple
            accept="video/mp4,video/webm,video/quicktime,image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => {
              if (e.target.files?.length) onFiles(e.target.files);
              e.currentTarget.value = "";
            }}
          />
        </Section>

        <Section index="02" title="Spread" aside="Simulated agents — red solid = shared directly — grey dashed = shown by ranking policy">
          {compare ? (
            <div className="grid gap-4">
              <SpreadResult label="Hook A" report={compare.a} population={compare.a.population ?? Number(population)} />
              <SpreadResult label="Hook B" report={compare.b} population={compare.b.population ?? Number(population)} />
            </div>
          ) : (
            <SpreadView
              report={report}
              loading={loading}
              population={report?.population ?? Number(population)}
            />
          )}
          {loading ? <button type="button" onClick={stopWaiting} className="border-t border-[var(--hairline)] px-3 py-2 text-left text-[12px] underline">Stop waiting (server run may continue)</button> : null}
        </Section>

        <Section index="03" title="Verdict" aside="Comparative, not predictive">
          <VerdictPanel report={report} compare={compare} />
        </Section>
      </form>

      {report?.run_id ? (
        <Section index="04" title="Outcome" aside="Optional observed numbers for a future calibration dataset — not scored or calibrated yet">
          <OutcomePanel key={report.run_id} runId={report.run_id} onSaved={() => setHistoryVersion((value) => value + 1)} />
        </Section>
      ) : null}

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4 text-[12px] text-[var(--muted)]">
        <p>
           {(report?.population ?? Number(population))}-agent simulated population · staged spread · velocity-gated{report?.run_id ? ` · ${report.run_id}` : ""}
          {report?.parent_run_id ? ` · replay of ${report.parent_run_id}` : ""}
          {" · "}
          <a href={GITHUB_REPO} className="text-[var(--fg)] hover:underline" target="_blank" rel="noreferrer">GitHub</a>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={keyInput}
            onChange={(event) => setKeyInput(event.target.value)}
            type="password"
            spellCheck={false}
            autoComplete="off"
            aria-label="API access key"
            placeholder="API access key"
            className="w-36 rounded-none border border-[var(--line)] bg-white px-2 py-1 text-[12px] text-[var(--fg)] outline-none placeholder:text-[var(--muted)]"
          />
          <button type="button" disabled={loading} className="border border-[var(--line)] px-2 py-1 disabled:opacity-40" onClick={() => {
            const value = keyInput.trim();
            if (value) sessionStorage.setItem(ACCESS_KEY_STORAGE, value);
            else sessionStorage.removeItem(ACCESS_KEY_STORAGE);
            setApiKey(value); setRecentRuns([]); setHistoryError(null); setLoadId(""); setReport(null); setCompare(null);
            setHistoryVersion((version) => version + 1);
          }}>USE KEY</button>
          <input
            value={loadId}
            onChange={(e) => setLoadId(e.target.value)}
            onFocus={(e) => {
              e.currentTarget.select();
              const id = e.currentTarget.value.trim();
              if (id) void navigator.clipboard.writeText(id).catch(() => undefined);
            }}
            spellCheck={false}
            autoComplete="off"
            placeholder="Run id"
            className="w-40 rounded-none border border-[var(--line)] bg-white px-2 py-1 text-[12px] text-[var(--fg)] outline-none placeholder:text-[var(--muted)]"
          />
          <select aria-label="Recent runs" value={recentRuns.some((run) => run.run_id === loadId) ? loadId : ""} onChange={(e) => { if (e.target.value) setLoadId(e.target.value); }} className="w-64 max-w-full rounded-none border border-[var(--line)] bg-white px-2 py-1 text-[12px]">
            <option value="">Recent runs</option>
            {recentRuns.map((run) => <option key={run.run_id} value={run.run_id}>{new Date(run.created_at).toLocaleString()} · {run.niche} · {run.input_text.slice(0, 45) || "Media post"}{run.has_outcome ? " · outcome saved" : ""}</option>)}
          </select>
          <button type="button" className="border border-[var(--line)] px-2 py-1" onClick={() => setHistoryVersion((version) => version + 1)}>REFRESH RUNS</button>
          <button
            type="button"
            onClick={onLoad}
            disabled={loading || !loadId.trim()}
            className="border border-[var(--line)] px-2 py-1 text-[11px] font-semibold tracking-[0.12em] text-[var(--fg)] disabled:opacity-40"
          >
            LOAD
          </button>
          <button
            type="button"
            onClick={onReplay}
            disabled={loading || !loadId.trim()}
            className="border border-[var(--line)] px-2 py-1 text-[11px] font-semibold tracking-[0.12em] text-[var(--fg)] disabled:opacity-40"
          >
             RE-RUN SNAPSHOT
          </button>
        </div>
        {historyError ? <p role="status" className="w-full">Recent runs: {historyError}</p> : null}
      </footer>
    </div>
  );
}

function Section({
  index,
  title,
  aside,
  children,
}: {
  index: string;
  title: string;
  aside: string;
  children: ReactNode;
}) {
  return (
    <section className="py-5">
      <div className="mb-2.5 flex items-baseline justify-between gap-4">
        <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[var(--fg)]">
          {index} {title}
        </h2>
        <p className="max-w-2xl text-right text-[12px] leading-4 text-[var(--muted)]">{aside}</p>
      </div>
      {children}
    </section>
  );
}

function SpreadResult({
  label,
  report,
  population,
}: {
  label: string;
  report: ImpactReport;
  population: number;
}) {
  const simulation = report.simulation;
  const exposure =
    simulation.exposure_p10 != null && simulation.exposure_p90 != null
      ? `${Math.round(simulation.exposure_p10)}–${Math.round(simulation.exposure_p90)}% exposure`
      : "exposure range unavailable";
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2 border border-b-0 border-[var(--line)] bg-white px-3 py-2">
        <p className="text-[13px] font-semibold uppercase tracking-[0.08em]">{label}</p>
        <p className="text-[11px] text-[var(--muted)]">
          score p10–p90 {simulation.score_p10.toFixed(0)}–{simulation.score_p90.toFixed(0)} · {exposure}
        </p>
      </div>
      <SpreadView report={report} loading={false} population={population} />
    </div>
  );
}

function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-b border-[var(--line)] p-4 md:border-b-0 md:border-l">
      <p className="lab-label mb-2">{label}</p>
      {children}
    </div>
  );
}

function DropCell({
  label,
  filename,
  filled,
  onClick,
  onDropFiles,
  onClear,
}: {
  label: string;
  filename: string;
  filled: boolean;
  onClick: () => void;
  onDropFiles: (files: FileList | File[]) => void;
  onClear: () => void;
}) {
  return (
    <div className="p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="lab-label">{label}</p>
        {filled ? (
          <button
            type="button"
            onClick={onClear}
            className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)] hover:text-[var(--fg)]"
          >
            Clear
          </button>
        ) : null}
      </div>
      <button
        type="button"
        onClick={onClick}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          onDropFiles(e.dataTransfer.files);
        }}
        className="flex min-h-[7.25rem] w-full items-center justify-center rounded-none border border-dashed border-[var(--line)] bg-white px-3 text-center text-[13px] leading-5"
      >
        <span className={filled ? "font-medium" : "text-[var(--muted)]"}>{filename}</span>
      </button>
      <p className="mt-2 text-[11px] leading-4 text-[var(--muted)]">JPEG, PNG, WebP, GIF, MP4, WebM or MOV · one video or up to five images · total media under 3.5 MB.</p>
    </div>
  );
}

function punchline(inTarget: number, outTarget: number, reachPct: number) {
  if (reachPct < 18) return "No breakout.";
  if (outTarget === 0 && inTarget > 0) return "Niche hit.";
  if (outTarget > inTarget) return "Crossover.";
  if (inTarget > 0) return "Niche hit.";
  return "Contained spread.";
}

function signed(n: number) {
  const v = Number.isFinite(n) ? n : 0;
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}`;
}

function spreadActions(agent: { action: string; actions?: string[] }) {
  return agent.actions?.length ? agent.actions : [agent.action];
}

function humanize(value?: string | null) {
  if (!value) return "Not reported";
  return value.replaceAll("_", " ").replaceAll("-", " ");
}

function versionWithHash(version?: string, hash?: string) {
  if (!version && !hash) return null;
  return [version, hash ? hash.slice(0, 10) : null].filter(Boolean).join(" · ");
}

function VerdictPanel({ report, compare }: { report: ImpactReport | null; compare: CompareReport | null }) {
  if (!report) {
    return (
      <div className="flex h-[12.5rem] flex-col justify-center border border-[var(--line)] bg-white px-8">
        <p className="text-[18px] font-semibold">Verdict lands here.</p>
        <p className="mt-2 max-w-2xl text-[13px] leading-5 text-[var(--muted)]">
          p10–p90 of the full cascade, Niche Index, fit, risk, and rewrite suggestions render after a run.
        </p>
      </div>
    );
  }

  const people = (report.simulation.graph?.agents ?? []).filter((a) => a.cohort !== "origin");
  const shown = people.filter((a) => a.cohort !== "never_shown");
  const inTarget = shown.filter((a) => a.cohort === "in_target").length;
  const outTarget = shown.filter((a) => a.cohort === "out_of_target").length;
  const shares = shown.filter((agent) =>
    spreadActions(agent).some((action) => action === "repost" || action === "quote" || action === "share"),
  ).length;
  const depth = report.simulation.rounds.length;
  const last = report.simulation.rounds.at(-1);
  const reachPct = report.reach_pct ?? (people.length ? Math.round((shown.length / people.length) * 100) : 0);
  const sharePct = shown.length ? Math.round((shares / shown.length) * 100) : 0;
  const inShare = inTarget + outTarget === 0 ? 0 : (inTarget / (inTarget + outTarget)) * 100;
  const ofTarget = people.length ? Math.round((inTarget / people.length) * 100) : 0;
  const tag =
    outTarget === 0 && inTarget > 0
      ? "Strong in-demo, no breakout"
      : outTarget > inTarget
        ? "Crossover more than in-demo"
        : "Comparative, not predictive";
  const stages = [...new Set(report.simulation.rounds.map((r) => r.stage).filter(Boolean))].join(" → ");
  const suggestions = report.explanation.suggestions ?? [];

  return (
    <div className="border border-[var(--line)] bg-white p-5">
      <p className="text-[28px] font-semibold tracking-tight">{punchline(inTarget, outTarget, reachPct)}</p>
      <p className="mt-2 max-w-3xl text-[13px] leading-5 text-[var(--muted)]">{report.explanation.summary}</p>
      <div className="mt-5 grid border border-[var(--line)] sm:grid-cols-2 lg:grid-cols-6">
        <Metric label="Audience fit" value={`${Math.round(report.audience_fit ?? 0)}`} note="pack affinity" />
        <Metric label="Distribution" value={`${Math.round(report.distribution_potential ?? 0)}`} note="cascade depth vs cap" />
        <Metric label="Engagement quality" value={`${Math.round(report.engagement_quality ?? 0)}`} note="reply / repost / quote / share / follow" />
        <Metric label="Negative risk" value={`${Math.round(report.negative_signal_risk ?? 0)}`} note="mute / not-interested" />
        <Metric label="Niche Index" value={`${Math.round(report.niche_index ?? 0)}`} note="core-pack affinity" />
        <Metric label="Profile impact" value={`${Math.round(report.profile_impact ?? 50)}`} note="vs bland pack post" />
      </div>
      <div className="mt-4 grid border border-[var(--line)] sm:grid-cols-2 lg:grid-cols-5">
        <Metric
          label="Simulated exposure"
          value={`${Math.round(reachPct)}%`}
          note={`${shown.length} of ${people.length} simulated agents${
            report.simulation.exposure_p10 != null && report.simulation.exposure_p90 != null
              ? ` · MC p10–p90 ${Math.round(report.simulation.exposure_p10)}–${Math.round(report.simulation.exposure_p90)}%`
              : ""
          }`}
        />
        <div className="border-t border-[var(--line)] p-3 sm:border-t-0 sm:border-l">
          <p className="lab-label">% of target</p>
          <p className="mt-1 text-[22px] font-semibold">{ofTarget}/100</p>
          <span className="mt-2 flex h-1.5 overflow-hidden bg-[var(--fill)]">
            <span className="h-full bg-[var(--blue)]" style={{ width: `${inShare}%` }} />
            <span className="h-full bg-[var(--out)]" style={{ width: `${100 - inShare}%` }} />
          </span>
          <p className="mt-1 text-[11px] text-[var(--muted)]">{inTarget} in / {outTarget} out</p>
        </div>
        <Metric label="Share rate" value={`${sharePct}%`} note={`${shares} shares / ${shown.length} views`} />
        <Metric
          label="Cascade depth"
          value={`${depth} rounds`}
          note={report.stop_reason || last?.stop_reason || (last?.stopped ? "velocity-gated" : "ran to cap")}
        />
        <div className="border-t border-[var(--line)] p-3 lg:border-t-0 lg:border-l">
          <p className="lab-label">Stages</p>
          <p className="mt-2 text-[14px] font-semibold leading-5">{stages || tag}</p>
        </div>
      </div>
      <div className="mt-4 grid border border-[var(--line)] sm:grid-cols-2 lg:grid-cols-5">
        <Metric
          label="Score p10–p90"
          value={`${report.simulation.score_p10.toFixed(0)}–${report.simulation.score_p90.toFixed(0)}`}
          note={`median ${report.simulation.score_p50.toFixed(0)} · simulated cascade score`}
        />
        <Metric
          label="Exposure p10–p90"
          value={
            report.simulation.exposure_p10 != null && report.simulation.exposure_p90 != null
              ? `${Math.round(report.simulation.exposure_p10)}–${Math.round(report.simulation.exposure_p90)}%`
              : "Unavailable"
          }
          note={
            report.simulation.exposure_p50 != null
              ? `median ${Math.round(report.simulation.exposure_p50)}% · simulated population`
              : "not reported by this run"
          }
        />
        <Metric
          label="Run stability"
          value={`${Math.round(report.stability ?? report.confidence ?? 0)}/100`}
          note="Monte Carlo consistency only · not model confidence"
        />
        <Metric
          label="Evidence coverage"
          value={humanize(report.data_coverage_status)}
          note={`calibration: ${humanize(report.calibration_status)}`}
        />
        <div className="border-t border-[var(--line)] p-3 sm:border-t-0 sm:border-l lg:border-t-0">
          <p className="lab-label">Model path</p>
          <p className="mt-2 text-[12px] leading-5 text-[var(--muted)]">
            {(report.inference_path || (report.groq_used ? "groq" : "heuristic")).toUpperCase()}
            {report.calibration_version ? ` · ${report.calibration_version}` : ""}
          </p>
          <p className="mt-2 text-[12px] leading-5 text-[var(--muted)]">{report.heads_note || "No trained heads applied."}</p>
        </div>
      </div>
      <ProvenancePanel report={report} />
      {suggestions.length > 0 && (
        <div className="mt-4 border border-[var(--line)] p-3">
          <p className="lab-label">Suggestions</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] leading-5">
            {suggestions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {compare && (
        <div className="mt-4 grid border border-[var(--line)] sm:grid-cols-3">
          <Metric label="Hook A" value={compare.a.impact_score.toFixed(0)} note={`niche ${Math.round(compare.a.niche_index ?? 0)} · exposure ${Math.round(compare.a.reach_pct ?? 0)}%`} />
          <Metric label="Hook B" value={compare.b.impact_score.toFixed(0)} note={`niche ${Math.round(compare.b.niche_index ?? 0)} · exposure ${Math.round(compare.b.reach_pct ?? 0)}%`} />
          <Metric
            label="B − A"
            value={signed(compare.delta.impact_score)}
            note={`niche ${signed(compare.delta.niche_index)} · fit ${signed(compare.delta.audience_fit)} · dist ${signed(compare.delta.distribution_potential ?? 0)}`}
          />
        </div>
      )}
    </div>
  );
}

function ProvenancePanel({ report }: { report: ImpactReport }) {
  const fields = [
    ["Simulator", report.simulator_version],
    ["Persona pack", versionWithHash(report.persona_pack_version, report.persona_pack_hash)],
    ["Action model", versionWithHash(report.action_model_version, report.action_model_hash)],
    ["Calibration", report.calibration_version],
    ["X weights", versionWithHash(report.weights_version, report.weights_hash)],
    ["Dataset", versionWithHash(report.dataset_revision, report.dataset_hash)],
    ["Prompt", report.prompt_version],
    ["Configuration", report.config_version],
    ["LLM", report.llm_model],
    ["Input", report.input_hash?.slice(0, 10)],
    ["Snapshot", report.snapshot_hash?.slice(0, 10)],
    [
      "Replay contract",
      report.replay_contract_version
        ? `${report.replay_contract_version} · ${report.replay_mode ?? "original"} · ${report.replayable ? "replayable" : "not replayable"}`
        : null,
    ],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));
  const warnings = [
    ...(report.warnings ?? []),
    ...(report.fallback_reasons ?? []).map((reason) => `Fallback: ${reason}`),
    ...(report.replay_limitations ?? []).map((reason) => `Replay limitation: ${reason}`),
    report.inference_path?.toLowerCase().includes("heuristic")
      ? "Heuristic inference path used; compare this run only within the same model path."
      : null,
    report.experimental ? report.disclaimer || "Experimental simulation; not a reach forecast." : null,
    DEV_API_TOKEN ? "Browser-visible development token is active; it is not production authentication." : null,
  ].filter((item): item is string => Boolean(item));
  const uniqueWarnings = [...new Set(warnings)];

  return (
    <div className="mt-4 border border-[var(--line)]">
      <div className="grid sm:grid-cols-2 lg:grid-cols-5">
        {fields.length ? (
          fields.map(([label, value]) => <Metric key={label} label={label} value={value} note="run provenance" />)
        ) : (
          <div className="p-3 sm:col-span-2 lg:col-span-5">
            <p className="lab-label">Run provenance</p>
            <p className="mt-1 text-[12px] text-[var(--muted)]">This report did not include a version manifest.</p>
          </div>
        )}
      </div>
      <div className="border-t border-[var(--line)] p-3 text-[12px] leading-5">
        <p className="lab-label">Interpretation</p>
        <p className="mt-1 text-[var(--muted)]">
          {report.probability_semantics || "Probability semantics were not reported by this run."}
        </p>
        <p className="mt-1 text-[var(--muted)]">
          {report.uncertainty_note || "Ranges describe simulation variation, not guaranteed real-world outcomes."}
        </p>
      </div>
      {uniqueWarnings.length ? (
        <div className="border-t border-[var(--line)] bg-[#fff8ed] p-3">
          <p className="lab-label text-[var(--danger)]">Warnings and fallbacks</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] leading-5 text-[var(--fg)]">
            {uniqueWarnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </div>
      ) : null}
      {report.provenance || report.config_snapshot ? (
        <div className="grid border-t border-[var(--line)] sm:grid-cols-2">
          {report.provenance ? <MetadataDetails label="Provenance manifest" value={report.provenance} /> : null}
          {report.config_snapshot ? <MetadataDetails label="Configuration snapshot" value={report.config_snapshot} /> : null}
        </div>
      ) : null}
    </div>
  );
}

function MetadataDetails({ label, value }: { label: string; value: Record<string, unknown> }) {
  return (
    <details className="border-t border-[var(--line)] p-3 first:border-t-0 sm:border-l sm:border-t-0 sm:first:border-l-0">
      <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[0.08em]">{label}</summary>
      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all bg-[var(--fill)] p-2 text-[10px] leading-4">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

function localDateTime(value: string) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function OutcomePanel({ runId, onSaved }: { runId: string; onSaved: () => void }) {
  const [impressions, setImpressions] = useState("");
  const [likes, setLikes] = useState("");
  const [replies, setReplies] = useState("");
  const [reposts, setReposts] = useState("");
  const [follows, setFollows] = useState("");
  const [quotes, setQuotes] = useState("");
  const [shares, setShares] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [windowHours, setWindowHours] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [fetching, setFetching] = useState(true);
  const existing = useRef<OutcomeRecord | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fill = (record: OutcomeRecord) => {
      existing.current = record;
      setImpressions(record.impressions != null ? String(record.impressions) : "");
      setLikes(record.likes != null ? String(record.likes) : "");
      setReplies(record.replies != null ? String(record.replies) : "");
      setReposts(record.reposts != null ? String(record.reposts) : "");
      setFollows(record.follows != null ? String(record.follows) : "");
      setQuotes(record.quotes != null ? String(record.quotes) : "");
      setShares(record.shares != null ? String(record.shares) : "");
      setObservedAt(record.observed_at ? localDateTime(record.observed_at) : "");
      setWindowHours(record.observation_window_hours != null ? String(record.observation_window_hours) : "");
      setNote(record.note ?? "");
    };
    // A different run ID remounts this panel with empty fields and status.
    apiFetch(`${API}/api/simulations/${encodeURIComponent(runId)}/outcome`)
      .then(async (response) => {
        const record = (await response.json()) as OutcomeRecord;
        if (!cancelled) fill(record);
      })
      .catch((err) => { if (!cancelled) setStatus(err instanceof ApiError && err.status === 404 ? "No outcome recorded for this run yet." : err instanceof Error ? err.message : "Could not load outcome"); })
      .finally(() => { if (!cancelled) setFetching(false); });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const parse = (raw: string, required = false) => {
    const trimmed = raw.trim();
    if (!trimmed) return required ? undefined : null;
    if (!/^\d+$/.test(trimmed)) return undefined;
    const n = Number(trimmed);
    return Number.isSafeInteger(n) ? n : undefined;
  };

  const onSave = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const payload: OutcomeRecord = {
        ...existing.current,
        run_id: runId,
        impressions: parse(impressions, true),
        likes: parse(likes),
        replies: parse(replies),
        reposts: parse(reposts),
        follows: parse(follows),
        quotes: parse(quotes),
        shares: parse(shares),
        observed_at: observedAt
          ? existing.current?.observed_at && localDateTime(existing.current.observed_at) === observedAt
            ? existing.current.observed_at : new Date(observedAt).toISOString()
          : null,
        observation_window_hours: windowHours ? Number(windowHours) : null,
        note,
      };
      if (Object.values({ impressions: payload.impressions, likes: payload.likes, replies: payload.replies, reposts: payload.reposts, follows: payload.follows, quotes: payload.quotes, shares: payload.shares }).some((value) => value === undefined)) {
        throw new Error("Enter nonnegative whole numbers; impressions is required.");
      }
      if ([payload.likes, payload.replies, payload.reposts, payload.follows, payload.quotes, payload.shares].some((value) => value != null && value > (payload.impressions ?? 0))) {
        throw new Error("Action counts cannot exceed impressions.");
      }
      if (windowHours && (!Number.isFinite(Number(windowHours)) || Number(windowHours) <= 0 || Number(windowHours) > 8760)) throw new Error("Observation window must be greater than zero and at most 8,760 hours.");
      await apiFetch(`${API}/api/simulations/${encodeURIComponent(runId)}/outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setStatus("Saved against this run id.");
      existing.current = payload;
      onSaved();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-[var(--line)] bg-white p-4">
      <p className="mb-3 max-w-3xl text-[12px] leading-5 text-[var(--muted)]">
        These observations are stored for future evaluation only. Saving them does not recalibrate this run,
        validate its reach estimate, or establish that a caption caused the outcome.
      </p>
      <fieldset disabled={fetching || saving} className="grid gap-3 sm:grid-cols-4">
        <OutcomeField label="Impressions" value={impressions} onChange={setImpressions} />
        <OutcomeField label="Likes" value={likes} onChange={setLikes} />
        <OutcomeField label="Replies" value={replies} onChange={setReplies} />
        <OutcomeField label="Reposts" value={reposts} onChange={setReposts} />
         <OutcomeField label="Follows" value={follows} onChange={setFollows} />
         <OutcomeField label="Quotes" value={quotes} onChange={setQuotes} />
          <OutcomeField label="Shares" value={shares} onChange={setShares} />
      </fieldset>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Optional note"
        maxLength={2000}
        disabled={fetching || saving}
        className="mt-3 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none placeholder:text-[var(--muted)]"
      />
      <fieldset disabled={fetching || saving} className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block"><span className="lab-label">Observed at</span><input type="datetime-local" value={observedAt} onChange={(e) => setObservedAt(e.target.value)} className="mt-1 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px]" /></label>
        <label className="block"><span className="lab-label">Observation window (hours)</span><input type="number" min="0.01" max="8760" step="0.01" value={windowHours} onChange={(e) => setWindowHours(e.target.value)} className="mt-1 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px]" /></label>
      </fieldset>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={fetching || saving}
          className="border border-[var(--line)] px-3 py-1.5 text-[11px] font-semibold tracking-[0.12em] disabled:opacity-40"
        >
          {fetching ? "LOADING OUTCOME..." : saving ? "SAVING..." : "SAVE OUTCOME"}
        </button>
        {status ? <p role="status" className="text-[12px] text-[var(--muted)]">{status}</p> : null}
      </div>
    </div>
  );
}

function OutcomeField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="lab-label">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        inputMode="numeric"
        className="mt-1 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none"
      />
    </label>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="border-t border-[var(--line)] p-3 first:border-t-0 sm:border-t-0 sm:border-l sm:first:border-l-0">
      <p className="lab-label">{label}</p>
      <p className="mt-1 text-[22px] font-semibold">{value}</p>
      <p className="mt-1 text-[11px] text-[var(--muted)]">{note}</p>
    </div>
  );
}
