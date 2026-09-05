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
        <p className="mt-4">A creator submits a draft (caption, up to 5 images, or a short video). Fifteen curated behavior profiles emit Phoenix-style affinities, which Python maps onto assumed per-impression priors. Public RankingScorer defaults and synthetic candidate-slate competition then drive a Monte Carlo spread. The headline blends 35% persona prior with 65% median sampled population/ranking outcome; Groq never emits it.</p>

        <h2 className="mt-8 text-[13px] font-semibold uppercase tracking-[0.08em]">What you can do</h2>
        <ul className="mt-3 list-disc space-y-1 pl-5">
          <li>Score a hook against tech, fitness, finance, or comedy packs, sampled into 40 / 100 / 320 / 500 coherent audience members.</li>
          <li>Optional Hook B compare on the same media and seed.</li>
          <li>Verdict with full-cascade p10–p90, Niche Index, audience fit, negative risk, stability, and rewrite suggestions.</li>
          <li>Save owner-isolated runs with verified provenance/config hashes and replay stored probabilities by id.</li>
          <li>Optional cluster-aware BluePrint heads apply persona-preserving favorite (40%) and retweet (25%) log-odds lifts.</li>
          <li>Compatible actions are sampled independently; the shown graph is the run nearest median exposure and score.</li>
        </ul>

        <h2 className="mt-8 text-[13px] font-semibold uppercase tracking-[0.08em]">Local run</h2>
        <p className="mt-3">Python 3.11+, Node 20+, Groq key in <code className="text-[13px]">.env</code>. Backend on :8000, frontend on :3000. Full commands live in the GitHub README.</p>

        <h2 className="mt-8 text-[13px] font-semibold uppercase tracking-[0.08em]">Disclaimer</h2>
        <p className="mt-3 text-[var(--muted)]">Prior-mapped research prototype, not empirically calibrated. Ranking weights follow public X defaults, not runtime experiments or the full production stack. p10–p90 measure variation across full-cascade simulator runs, not model confidence. Treat ranges as comparative scenarios, not forecasts.</p>
      </article>

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4 text-[12px] text-[var(--muted)]">
        <p>Source on GitHub</p>
        <a href={GITHUB_REPO} className="text-[var(--fg)] hover:underline" target="_blank" rel="noreferrer">jagadeepmamidi/X-impact-simulator</a>
      </footer>
    </div>
  );
}
