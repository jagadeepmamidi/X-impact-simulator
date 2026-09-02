import Link from "next/link";
import { GITHUB_REPO } from "@/lib/repo";

export const metadata = {
  title: "About · Impact Simulator",
  description: "How the experimental X-inspired audience simulator works.",
};

export default function ReadmePage() {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-[720px] flex-1 flex-col px-8 py-6">
      <header className="flex items-end justify-between border-b border-[var(--line)] pb-4">
        <h1 className="text-[24px] font-semibold tracking-tight">About</h1>
        <Link href="/" className="text-[13px] text-[var(--muted)] hover:text-[var(--fg)]">Simulator</Link>
      </header>

      <article className="flex-1 py-8 text-[15px] leading-6">
        <p className="text-[var(--muted)]">Experimental X-inspired audience and distribution simulator. Comparative, not predictive. Not X production. No live X feed.</p>
        <p className="mt-4">A creator submits a draft (caption, up to 5 images, or a short video). Fifteen niche archetypes emit Phoenix-style P(action) probabilities. Python scores them with public RankingScorer weights from xai-org/x-algorithm, then runs a Monte Carlo spread. Groq never emits the impact score.</p>

        <h2 className="mt-8 text-[13px] font-semibold uppercase tracking-[0.08em]">What you can do</h2>
        <ul className="mt-3 list-disc space-y-1 pl-5">
          <li>Score a hook against tech, fitness, finance, or comedy packs (15 archetypes, cloned to 40 / 100 / 320 agents).</li>
          <li>Optional Hook B compare on the same media and seed.</li>
          <li>Verdict with p10–p90, Niche Index, audience fit, negative risk, confidence, and rewrite suggestions.</li>
          <li>Save every run and replay by id.</li>
          <li>BluePrint heads blend favorite (75%) and retweet (35%) only.</li>
        </ul>

        <h2 className="mt-8 text-[13px] font-semibold uppercase tracking-[0.08em]">Local run</h2>
        <p className="mt-3">Python 3.11+, Node 20+, Groq key in <code className="text-[13px]">.env</code>. Backend on :8000, frontend on :3000. Full commands live in the GitHub README.</p>

        <h2 className="mt-8 text-[13px] font-semibold uppercase tracking-[0.08em]">Disclaimer</h2>
        <p className="mt-3 text-[var(--muted)]">Uncalibrated research prototype. Ranking weights follow a public snapshot of X&apos;s RankingScorer, not the production stack. Treat ranges as comparative, not forecasts.</p>
      </article>

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4 text-[12px] text-[var(--muted)]">
        <p>Source on GitHub</p>
        <a href={GITHUB_REPO} className="text-[var(--fg)] hover:underline" target="_blank" rel="noreferrer">jagadeepmamidi/X-impact-simulator</a>
      </footer>
    </div>
  );
}
