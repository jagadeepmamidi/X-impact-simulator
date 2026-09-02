"use client";

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { NICHES, NICHE_COPY, type CompareReport, type ImpactReport, type Niche, type OutcomeRecord } from "@/lib/types";
import { GITHUB_REPO } from "@/lib/repo";
import { SpreadView } from "./spread";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
const SIM_API_KEY = process.env.NEXT_PUBLIC_SIM_API_KEY ?? "";

function apiHeaders(init?: HeadersInit) {
  const headers = new Headers(init);
  if (SIM_API_KEY) headers.set("X-API-Key", SIM_API_KEY);
  return headers;
}

async function apiFetch(url: string, init?: RequestInit) {
  const response = await fetch(url, { ...init, headers: apiHeaders(init?.headers) });
  if (response.status === 401) throw new Error("API key required or invalid");
  if (response.status === 429) throw new Error("Too many runs. Wait and try again.");
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const message = typeof detail.detail === "string" ? detail.detail : `Request failed (${response.status})`;
    throw new Error(message);
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
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [compare, setCompare] = useState<CompareReport | null>(null);
  const mediaInput = useRef<HTMLInputElement>(null);

  const mediaLabel = video?.name
    ?? (images.length > 1 ? `${images.length} images selected` : images[0]?.name)
    ?? "Drop a video or images here, or click to choose.";

  const onFiles = (list: FileList | File[]) => {
    const files = [...list];
    const vid = files.find((f) => f.type.startsWith("video/"));
    const pics = files.filter((f) => f.type.startsWith("image/")).slice(0, 5);
    if (vid) setVideo(vid);
    if (pics.length) setImages(pics);
  };

  const onSubmit = async (event?: FormEvent) => {
    event?.preventDefault();
    setLoading(true);
    setError(null);
    setCompare(null);
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
      const response = await apiFetch(`${API}${comparing ? "/api/compare" : "/api/simulate"}`, { method: "POST", body });
      if (comparing) {
        const result = (await response.json()) as CompareReport;
        setCompare(result);
        setReport(result.a);
        if (result.a.run_id) setLoadId(result.a.run_id);
      } else {
        const loaded = (await response.json()) as ImpactReport;
        setReport(loaded);
        if (loaded.run_id) setLoadId(loaded.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setLoading(false);
    }
  };

  const onLoad = async () => {
    const id = loadId.trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    setCompare(null);
    try {
      const response = await apiFetch(`${API}/api/simulations/${encodeURIComponent(id)}`);
      const loaded = (await response.json()) as ImpactReport;
      setReport(loaded);
      setNiche(loaded.niche);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  };

  const onReplay = async () => {
    const id = loadId.trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    setCompare(null);
    try {
      const response = await apiFetch(`${API}/api/simulations/${encodeURIComponent(id)}/replay`, { method: "POST" });
      const loaded = (await response.json()) as ImpactReport;
      setReport(loaded);
      setNiche(loaded.niche);
      if (loaded.run_id) setLoadId(loaded.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Replay failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[1180px] flex-1 flex-col px-8 py-6">
      <header className="flex items-end justify-between border-b border-[var(--line)] pb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[24px] font-semibold tracking-tight">Impact Simulator</h1>
          <span className="text-[15px] text-[var(--muted)]">Run report</span>
        </div>
        <Link href="/readme" className="text-[13px] text-[var(--muted)] hover:text-[var(--fg)]">About</Link>
      </header>

      <form onSubmit={onSubmit} className="flex flex-1 flex-col">
        <Section index="01" title="Input" aside="Drop video or images, pick a target demographic, run">
          <div className="border border-[var(--line)] bg-white">
            <div className="grid gap-0 md:grid-cols-[2.05fr_0.62fr_0.55fr_8.75rem]">
              <DropCell
                label="Video or images"
                filename={mediaLabel}
                filled={Boolean(video || images.length)}
                onClick={() => mediaInput.current?.click()}
                onDropFiles={onFiles}
              />
              <Cell label="Target demographic">
                <select
                  value={niche}
                  onChange={(e) => setNiche(e.target.value as Niche)}
                  className="mb-2 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none"
                >
                  {NICHES.map((item) => (
                    <option key={item} value={item}>{NICHE_LABEL[item]}</option>
                  ))}
                </select>
                <input
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Hook A — caption to score"
                  className="w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none placeholder:text-[var(--muted)]"
                />
                <input
                  value={textB}
                  onChange={(e) => setTextB(e.target.value)}
                  placeholder="Hook B — optional second caption"
                  className="mt-2 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none placeholder:text-[var(--muted)]"
                />
                <p className="mt-2 text-[11px] leading-4 text-[var(--muted)]">{NICHE_COPY[niche]}</p>
              </Cell>
            <Cell label="Population">
              <select
                id="population"
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
            <button
              id="run-sim"
              type="submit"
              disabled={loading}
              className="flex min-h-[9.5rem] items-center justify-center rounded-none bg-[var(--run)] text-[13px] font-semibold tracking-[0.28em] text-white disabled:cursor-not-allowed disabled:opacity-50 md:min-h-full md:border-l md:border-[var(--line)]"
              style={{ writingMode: "vertical-rl" }}
            >
              {loading ? "RUNNING..." : textB.trim() ? "COMPARE" : "RUN"}
            </button>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full border-t border-[var(--line)] bg-[var(--run)] py-3 text-[13px] font-semibold tracking-[0.28em] text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "RUNNING..." : textB.trim() ? "COMPARE HOOKS" : "RUN SIMULATION"}
          </button>
          {error && (
            <p className="border-t border-[var(--hairline)] px-3 py-2 text-[15px] text-[var(--danger)]">{error}</p>
          )}
          </div>
          <input
            ref={mediaInput}
            type="file"
            multiple
            accept="video/mp4,video/webm,video/quicktime,image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => e.target.files && onFiles(e.target.files)}
          />
        </Section>

        <Section index="02" title="Spread" aside={compare ? "Hook A map — red solid = shared directly — grey dashed = shown by algo — nodes are simulated agents" : "Simulated agents — red solid = shared directly — grey dashed = shown by algo"}>
          <SpreadView
            report={report}
            loading={loading}
            population={Number(population)}
          />
        </Section>

        <Section index="03" title="Verdict" aside="Comparative, not predictive">
          <VerdictPanel report={report} compare={compare} />
        </Section>
      </form>

      {report?.run_id ? (
        <Section index="04" title="Outcome" aside="Optional live numbers for later calibration — not scored yet">
          <OutcomePanel runId={report.run_id} />
        </Section>
      ) : null}

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4 text-[12px] text-[var(--muted)]">
        <p>
          {population}-agent simulated population · staged spread · velocity-gated{report?.run_id ? ` · ${report.run_id}` : ""}
          {report?.parent_run_id ? ` · replay of ${report.parent_run_id}` : ""}
          {" · "}
          <a href={GITHUB_REPO} className="text-[var(--fg)] hover:underline" target="_blank" rel="noreferrer">GitHub</a>
        </p>
        <div className="flex items-center gap-2">
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
            REPLAY
          </button>
        </div>
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
}: {
  label: string;
  filename: string;
  filled: boolean;
  onClick: () => void;
  onDropFiles: (files: FileList | File[]) => void;
}) {
  return (
    <div className="p-4">
      <p className="lab-label mb-2">{label}</p>
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
      <p className="mt-2 text-[11px] leading-4 text-[var(--muted)]">Videos and images run through the media pipeline on Run.</p>
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
  const shares = shown.filter((a) => a.action === "repost" || a.action === "quote" || a.action === "share").length;
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
            report.simulation.exposure_p10 != null
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
        <Metric label="p10" value={report.simulation.score_p10.toFixed(0)} note="cascade score, low" />
        <Metric label="p50" value={report.simulation.score_p50.toFixed(0)} note="median cascade" />
        <Metric label="p90" value={report.simulation.score_p90.toFixed(0)} note="cascade score, high" />
        <Metric
          label="Stability"
          value={`${Math.round(report.stability ?? report.confidence ?? 0)}`}
          note="tighter p10–p90"
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

function OutcomePanel({ runId }: { runId: string }) {
  const [impressions, setImpressions] = useState("");
  const [likes, setLikes] = useState("");
  const [replies, setReplies] = useState("");
  const [reposts, setReposts] = useState("");
  const [follows, setFollows] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fill = (record: OutcomeRecord) => {
      setImpressions(record.impressions != null ? String(record.impressions) : "");
      setLikes(record.likes != null ? String(record.likes) : "");
      setReplies(record.replies != null ? String(record.replies) : "");
      setReposts(record.reposts != null ? String(record.reposts) : "");
      setFollows(record.follows != null ? String(record.follows) : "");
      setNote(record.note ?? "");
    };
    fetch(`${API}/api/simulations/${encodeURIComponent(runId)}/outcome`)
      .then(async (response) => {
        if (!response.ok || cancelled) return;
        fill((await response.json()) as OutcomeRecord);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const parse = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : null;
  };

  const onSave = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const payload: OutcomeRecord = {
        run_id: runId,
        impressions: parse(impressions),
        likes: parse(likes),
        replies: parse(replies),
        reposts: parse(reposts),
        follows: parse(follows),
        note,
      };
      await apiFetch(`${API}/api/simulations/${encodeURIComponent(runId)}/outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setStatus("Saved against this run id.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-[var(--line)] bg-white p-4">
      <div className="grid gap-3 sm:grid-cols-5">
        <OutcomeField label="Impressions" value={impressions} onChange={setImpressions} />
        <OutcomeField label="Likes" value={likes} onChange={setLikes} />
        <OutcomeField label="Replies" value={replies} onChange={setReplies} />
        <OutcomeField label="Reposts" value={reposts} onChange={setReposts} />
        <OutcomeField label="Follows" value={follows} onChange={setFollows} />
      </div>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Optional note"
        className="mt-3 w-full rounded-none border border-[var(--line)] bg-white px-2 py-1.5 text-[13px] outline-none placeholder:text-[var(--muted)]"
      />
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="border border-[var(--line)] px-3 py-1.5 text-[11px] font-semibold tracking-[0.12em] disabled:opacity-40"
        >
          {saving ? "SAVING..." : "SAVE OUTCOME"}
        </button>
        {status ? <p className="text-[12px] text-[var(--muted)]">{status}</p> : null}
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
