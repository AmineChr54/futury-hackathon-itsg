# Demo: ITSG Spec Pipeline

← [Project README](../README.md): overview, quick start and architecture.

*From specification to certified test, in one session.*

A single-file demo (`index.html`) of the AI pipeline for ITSG's system review of income
replacement benefits (DTA EEL). It contains the business slides and the guided demo for the
5-minute pitch, and every screen can also be used freely.

`pipeline.html` is Achraf's live pipeline UI (real hessian.AI runs on any spec PDF). It needs
`pipeline/server.py`; see [../pipeline/README.md](../pipeline/README.md).

## Open it

Double-click `index.html`. Everything runs offline: no build step, no server.

Optional extras that need the internet:
- **Fonts:** IBM Plex, from Google Fonts. Without a connection, system fonts are used instead.
- **Certificate PDF:** html2pdf.js from cdnjs. Offline, the button opens the print dialog
  instead (choose "Save as PDF").
- **PDF upload:** reading your own spec PDF loads pdf.js from cdnjs.
- **Live AI mode:** calls hessian.AI (see below).

With the server running (`python pipeline/server.py`, then http://localhost:8787), the same page
is served at `/`, and the Changes and Test-case review screens get a **Live AI pipeline ↗** link
to `/pipeline`.

## Presenting

| Key | What it does |
|---|---|
| **D**, the **Demo** button or **Start guided demo** | Start from slide 1: slides 1–4, then 17 steps in the app, then the closing slide |
| **→** / **Space** · **←** | Next / previous beat, across slides and steps. Arrows also work while the demo is typing |
| **P** (or **Narrator** in the bar) | Open the **narrator window**: current beat, what is on screen, 2–3 speaker notes, the next beat, a timer, and ‹ › buttons that drive the main window. While it is open, the projector shows only the sentence |
| **T** | Text only by hand: hides the step counter and the buttons |
| **Esc** | End the demo |
| `index.html#demo=9` | Open the demo at beat 9 (1–22). Useful to rehearse or to resume |

Put the narrator window on your laptop screen and the main window on the projector. If nothing
opens, the browser blocked the pop-up: allow pop-ups for this file (Firefox shows a yellow bar at
the top), then press **P** again.

During the demo the bottom bar shows **one sentence** per step. A spotlight frames what the
sentence is about (with a slight zoom) and keeps following it while the page scrolls or changes.
Each step sets up its own state, so stepping back and forth is safe, and each one plays its action
once (approve, ask the AI, send, upload…).

**Animations in Firefox.** If the zoom, the smooth scrolling or the flashing quote don't move, your
system asks apps to reduce motion. The demo still frames every step, just without animation. To
turn the animations on, use either of these:
- Windows: **Settings → Accessibility → Visual effects → Animation effects: On**, then restart
  Firefox.
- Firefox only: open `about:config`, search `ui.prefersReducedMotion`, create it as a **Number**
  with value **0** (1 = reduce, 0 = allow).
- Smooth scrolling is a separate switch: **Firefox Settings → General → Browsing → Use smooth
  scrolling**.

| # | Beat | What happens on screen |
|---|---|---|
| 1 | Slide | ITSG logo, **ITSG Spec Pipeline**, tagline |
| 2 | Slide | Patrick: "400 pages. Every year. By hand." |
| 3 | Slide | Read the spec → extract rules → write test cases → dev types them in; "Every year. By hand. Zero error tolerance." |
| 4 | Slide | The name, the tagline, three promises |
| 5 | Step 1 | The pipeline in eight stages: Import · Index & highlight · Detect changes · Understand & approve · Generate test cases · Hand over · Compare · Report & certify |
| 6 | Step 2 | The original v13.4 PDF is imported (168 pages, 220 sections); the archive sits next to it |
| 7 | Step 3 | The full specification: § index left, §3.12 right with the AI's highlights; the changed sentence flashes |
| 8 | Step 4 | Changes: the log calls §3.12 editorial; the AI finds the 6-month rule flipped (Achraf's change card) |
| 9 | Step 5 | The examiner edits the AI's reading ("More than 6 months stops it.") and approves |
| 10 | Step 6 | The reasoning opens: what was sent to the model, its reasoning, a check in the terminal, the extracted change. The demo types a question into the chat; the answer streams back with the quote |
| 11 | Step 7 | Create test cases: the AI writes 5 cases, grouped by the rule they test |
| 12 | Step 8 | The case we follow (TC-3.12-B-01, ITSG's reference employee) is highlighted and opened |
| 13 | Step 9 | Send to developers: SAP's team is ticked, Send |
| 14 | Step 10 | SAP's side: the notification, then the package e-mail in Messages |
| 15 | Step 11 | The checklist: the AI recap (what changed, what to do) |
| 16 | Step 12 | Run each test: the developer opens each case, **How to run it** (preconditions, steps), **What should happen** (in words, with the key values), then **Works as expected** |
| 17 | Step 13 | Upload the DTA file: sent to ITSG by automatic e-mail and compared at once |
| 18 | Step 14 | The inbox: 1 of 5 failed. SAP's screen looked right, but the exported file still has the 2024 period |
| 19 | Step 15 | The developer asks why the file differs from the screen; ITSG answers with the quote |
| 20 | Step 16 | “Two days later” with a clock: the fixed file passes, 5 of 5 |
| 21 | Step 17 | Report & certificate: passed, e-mailed to SAP, **Download PDF** |
| 22 | Slide | Before (tired guy) → after (happy squirrel), "Thank you!" |

- **ITSG / Vendor** (top right) switches the role; **EN / DE** the language (recorded AI output
  in the story screens is English).
- Every underlined value on the older screens opens its **provenance trail**.

## Screens

| Screen | What it shows |
|---|---|
| Overview | The eight-stage pipeline; outside the demo also KPIs, today vs. with the assistant, ITSG's reference case |
| 1 Inputs & archive | Import the original v13.4 PDF (simulated drop, or a real file via pdf.js); the archive |
| 2 Specification | All 220 sections of the real v13.4 PDF (full text), changed sections marked, AI highlights |
| 3 Changes & review | Change list (log + diff); Achraf's change card (before → now, numbers, evidence) with approve / edit / decline; the AI's reasoning and a chat underneath |
| 4 Test-case review | Achraf's review list, **grouped by rule**; detail with preconditions, steps, expected result, formula, variables, checks G1–G5; verify / reject; send to developers |
| 5 Messages | E-mail-like inbox: threads per vendor, attachments, result files compared on arrival |
| 6 Report & certificate | Final report for SAP, issue the certificate by e-mail, download it as a PDF |
| Rules, Test catalogue, Publish, Compare output, On-site audit, Audit report, Coverage check | The earlier, deeper screens (rule approval with two AI runs, catalogue and variants, byte view, audit checklist, all-vendors report) |
| Evidence | Function library, change impact (diff), coverage by §, audit trail |

**Vendor role** (SAP or Lexware, illustrative examples; every result shown for them is imagined):
Home · **1 Messages** · **2 Checklist** (AI recap; per case: how to run it, what should happen, works as expected; upload) · My test cases · 3 Upload & compare ·
4 My results · Specification.

## What's real and what's simulated

| Real | Simulated or illustrative |
|---|---|
| The full text of all 220 sections of the Verfahrensbeschreibung v13.4, extracted from the original PDF; page numbers; the change log | The v13.3 wording (reconstructed from the change log; labelled in the UI) |
| The §3.12 boundary flip, checked by the rule functions; the real inconsistency on p. 136 (the insurer's paragraph still says "nicht mindestens") | The AI's recorded reasoning, chat answers, spec-change JSON, test cases and recap (in the same shapes as Achraf's pipeline API; live mode makes real calls) |
| ITSG's reference case (Peter Mustermann), its criteria, the sample file `TEEL0-Test1-DBVO` | The broken result file (derived from the real one) and all vendor results |
| Expected values computed by tested code; quote checks against the full v13.4 text | The test catalogue (46-row subset) and the historic ALT-… rows |

## Live AI

- **Full live pipeline:** `python pipeline/server.py` (needs `HAI_API_KEY` in `pipeline/.env`),
  then http://localhost:8787/pipeline. See [../pipeline/README.md](../pipeline/README.md).
- **Live chat and live rule extraction in this page:** run the proxy and switch **⚙ AI settings**
  to Live:

  ```powershell
  $env:HAI_API_KEY = "<your team key>"   # never commit this
  python demo/proxy.py                    # serves http://localhost:8787/v1
  ```

  Base URL `http://localhost:8787/v1`, model `vllm/Kolibri-1` or `vllm/GLM-Flash:Latest`. The chat
  in step 6 then sends the question with the section text and the extracted change to the model
  (`chatAnswer()`); if a call fails, the recorded answer is used. Inside a published claude.ai
  artifact, live calls are blocked by the sandbox.

## Source structure

`index.html` is one file:

1. **Design tokens and CSS.** Colours, type and spacing on `:root`, light and dark modes.
2. **CORE.** Spec excerpts, the rule function library, guards, the diff, the DTA parser, the test
   generator and the self-tests. No DOM access, so it runs in Node too:

   ```bash
   node -e "const s=require('fs').readFileSync('demo/index.html','utf8');const c=s.slice(s.indexOf('/*CORE-START*/'),s.indexOf('/*CORE-END*/'));const C=new Function(c+';return CORE')();const t=C.selfTest(C.PARAMS_DEFAULT);console.log(t.filter(x=>x.ok).length+'/'+t.length)"
   ```
3. **SPEC_FULL and IMAGES.** The full v13.4 text and the slide images, generated by
   `python demo/embed.py` from the PDF in `hackathon-files/` and the files in `images/`. Re-run it
   after changing either; it rewrites only the marker blocks.
4. **APP.** All screens and actions. The **STORY SCREENS** section holds the demo's change review,
   chat, test-case review, checklist and certificate; it reuses the renderers of Achraf's
   `pipeline.html` with recorded data in the same JSON shapes as his API.
5. **TOUR.** Slides, steps, speaker notes, the one-sentence bar, the spotlight, the narrator window (`#presenter`) and the keys.

`node demo/test_demo.cjs` runs the regression checks of Achraf's pipeline UI (`pipeline.html`).
