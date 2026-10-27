import Image from "next/image";
import { Suspense } from "react";
import { QrCard, QrSkeleton } from "./qr-card";
import { StatusChip } from "./status-chip";

const TRY = [
  {
    href: "/demo/#demo", kicker: "5 minutes", title: "Guided demo",
    text: "The pitch as we present it: four slides, then 17 steps through the app with recorded data. Press D, or the Demo button, to start; → and ← step through.",
  },
  {
    href: "/app", kicker: "Live AI", title: "Live app",
    text: "The same app on the server's data with the real AI: drop a spec PDF, approve, send, certify. Sign in as istg (ITSG examiner), sap or lexware (vendors).",
  },
  {
    href: "/ITSG-Spec-Pipeline.pdf", kicker: "PDF", title: "Pitch deck",
    text: "The five slides from the pitch, with speaker notes.",
  },
];

const PIPELINE = [
  ["Import", "Drop the government's new spec PDF."],
  ["Index & highlight", "§ index from the PDF's own headings and links."],
  ["Detect changes", "Change log + section diff against last year."],
  ["Understand & approve", "AI drafts each rule; the examiner approves."],
  ["Generate test cases", "In plain words; tested code computes the values."],
  ["Hand over", "Checklist and AI recap for each vendor's developer."],
  ["Compare", "Vendor file vs. expected, every difference in words."],
  ["Report & certify", "Sealed report, certificate, next audit scope."],
];

const GUARDS = [
  ["G1", "Every quote appears verbatim in the spec"],
  ["G2", "The formula parses in a small, safe language"],
  ["G3", "Our oracle's result equals the AI's own value"],
  ["G4", "Every legal number appears in its quote (sechs Wochen = 42 days)"],
  ["G5", "The formula was actually run"],
];

export default function Home() {
  return (
    <main>
      <header className="top">
        <Image src="/ITSG-logo.png" alt="ITSG" width={681} height={293} className="logo" priority />
        <StatusChip />
      </header>

      <section className="hero">
        <div className="hero-text">
          <span className="kicker">Futury Build Days 2026 · ITSG challenge</span>
          <h1>§pecs</h1>
          <p className="tagline">From specification to certified test, in one session.</p>
          <p className="lede">
            Every December a new ~400-page specification lands, and ITSG rewrites 3,000–4,000 test cases by hand.
            Our pipeline reads the spec, finds what changed, drafts the rules for an examiner to approve and turns them
            into test cases. <b>Every expected value traces back to a sentence in the spec.</b>
          </p>
          <div className="actions">
            <a className="btn primary" href="/demo/#demo">Open the guided demo</a>
            <a className="btn" href="/app">Live app</a>
          </div>
        </div>
        <Suspense fallback={<QrSkeleton />}>
          <QrCard />
        </Suspense>
      </section>

      <section>
        <h2>Try it</h2>
        <div className="cards three">
          {TRY.map(t => (
            <a key={t.href} href={t.href} className="card link">
              <span className="kicker">{t.kicker}</span>
              <h3>{t.title} <span aria-hidden="true">→</span></h3>
              <p>{t.text}</p>
            </a>
          ))}
        </div>
      </section>

      <section>
        <h2>Data · Model · Logic</h2>
        <div className="cards three">
          <article className="card">
            <span className="kicker">Data</span>
            <h3>Real ITSG documents</h3>
            <ul>
              <li>The government&apos;s <b>DTA EEL Verfahrensbeschreibung v13.4</b> PDF: all 220 sections, full text.</li>
              <li>Last year&apos;s <b>v13.3</b> from the archive, for the diff.</li>
              <li>ITSG&apos;s reference case (prior-illness request) and its real <span className="mono">TEEL0-Test1-DBVO</span> file, which our expected output matches byte for byte.</li>
            </ul>
          </article>
          <article className="card">
            <span className="kicker">Model</span>
            <h3>Kolibri-1 on hessian.AI</h3>
            <ul>
              <li><b>Aleph Alpha&apos;s Kolibri-1</b> through the hessian.AI OpenAI-compatible gateway, with tool calls.</li>
              <li>It gets one § section, the sections it links to and the old version. Never the whole archive.</li>
              <li>It extracts parameters with <b>verbatim German quotes</b> and writes the formula. It never decides an expected value on its own.</li>
            </ul>
          </article>
          <article className="card">
            <span className="kicker">Logic</span>
            <h3>Deterministic guards</h3>
            <ul className="guards">
              {GUARDS.map(([id, text]) => <li key={id}><span className="mono">{id}</span>{text}</li>)}
            </ul>
            <p className="small">Failed guards go back to the AI. An examiner approves every rule. The value a developer receives always comes from tested code.</p>
          </article>
        </div>
      </section>

      <section>
        <h2>The pipeline</h2>
        <ol className="pipe">
          {PIPELINE.map(([title, text], i) => (
            <li key={title}><span className="n mono">{String(i + 1).padStart(2, "0")}</span><b>{title}</b><span>{text}</span></li>
          ))}
        </ol>
        <p className="trail mono">
          spec § → AI reads (quotes + formula) → 5 guards → examiner approves → tested function → expected value → vendor check
        </p>
      </section>

      <footer>
        <span>Futury Build Days · 26–27 Oct 2026 · ITSG challenge</span>
        <a href="https://github.com/AmineChr54/futury-hackathon-itsg">Source on GitHub</a>
      </footer>
    </main>
  );
}
