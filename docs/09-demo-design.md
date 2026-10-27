# Demo Design

The decisions behind `demo/index.html`, from the 20-question scoping round on 26.10.2026 and the
afternoon conversations with ITSG engineers ([07-itsg-meeting-notes.md](07-itsg-meeting-notes.md)).
For how to run it, see [`demo/README.md`](../demo/README.md).

## Decisions

| Area | Decision |
|---|---|
| Users | Role switch: **ITSG examiner ⇄ vendor**. The vendor signs in as SAP or Lexware and sees only its own home, test cases, results and messages. Vendors see what each test case should produce, in words with the key values (as in ITSG's Testkonstellation); the expected DTA file stays with ITSG |
| Communication | E-mail-like **Messages** inbox, one window (role switch shows the other side): threads per vendor and topic, attachments for test packages, result files (compared on arrival, verdict posted in words), reports, the certificate, rules and test cases |
| Story | Follows one sentence of §3.12 ("nicht mindestens" → "nicht mehr als 6 Monate") from the new PDF to a vendor's verdict, in four chapters: specification → requirements → testing → results. The payoff is the test whose expected result flips, computed under both versions. 15 steps, about 5 minutes |
| Presenting | Guided demo with spotlight, zoom and captions, plus a **separate presenter window** (script, speaker notes, timer, next step) synced to the projector window. While it is open, the projector shows only the chapter, the title, the ITSG objective and a short "today → with the assistant" caption; free deep-dive at any time |
| Language | DE/EN toggle; German spec quotes are always kept verbatim |
| AI | Hybrid: recorded runs by default, **live hessian.AI** (Kolibri-1 / GLM-Flash) optional |
| Trust | **The LLM only extracts parameters and picks a function; pre-written functions compute.** Every value has a provenance trail |
| Human loop | Approve, edit or decline (with a reason) the **plain-language rule text**, and confirm its numbers, once per rule; everything goes to a hash-chained audit trail |
| Domain depth | DBVO / Abgabegrund 41 in depth; 42/62 (EEL end) and 03 (maternity) shallow |
| Data | ITSG's reference case + generated employees; vendors are **SAP and Lexware as illustrative examples** (team decision, 26.10.); every result shown for them is imagined and labelled as such on each results screen |
| Style | Clean, professional tool, crimson accent, light and dark; built from tokens so it can move into Claude Design |
| Tech | One HTML file, vanilla JS, works offline; CDN only for optional extras |
| Name | **ITSG Spec Pipeline**, tagline *“From specification to certified test, in one session.”* (decided 27.10.; was the working title “EEL Review Assistant”) |

## Changes after the ITSG review (evening, 26.10.)

ITSG reviewed this demo; the full feedback and the checklist are in
[11-demo-feedback-itsg.md](11-demo-feedback-itsg.md). **These changes are built** and revise the
decisions above:

| Area | Was | Becomes |
|---|---|---|
| Human loop | Approve / reject / edit numeric parameters | Approve / **edit** / decline the **plain-language rule text**; parameters stay editable |
| Rule extraction view | Function ID, hashes and five guards up front | Readable rule first; technical details collapsed ("why you can trust this") |
| Function library | Pipeline step 4 | Moved under **Evidence**. ITSG doesn't have one and didn't follow it |
| Test cases | Full boundary set per rule (e.g. 12 for §3.12) | **One case per rule** by default, expandable; described in human words like ITSG's own |
| Compare output | Byte view with red differences | **Explained differences** (field, expected vs actual, §), decoded with the GKV dictionary; byte view as a second tab; comparison fires on upload |
| Report | Sealed report + next audit scope | Plus **pass/fail per test case and vendor**, printable and as **JSON per customer** |
| Inputs | Prepared spec sections | Visibly the **original government PDF** |
| New | — | **Automatic input proposal** (JSON import, SAP pilot) and **baseline check** of the catalogue (obsolete / missing / OK) |
| Inbox | Simulated insurer replies | Show the AG ⇄ KK exchange like ITSG's table; KK replies are input the vendor must handle |

## Final demo (27.10.)

The pitch version: four business slides, 17 steps in the app, one closing slide, about 5 minutes.
It merges Achraf's pipeline work (branch `Achraf`: change review, chain of thought, test-case
review, developer checklist with AI recap) into this app. How to run it:
[`demo/README.md`](../demo/README.md).

| Area | Decision |
|---|---|
| Name | **ITSG Spec Pipeline** |
| Language | English on the slides and in the bar; German spec quotes verbatim |
| Slides | Same file. Demo button → slides 1–4 → steps → closing slide. 1: ITSG logo, name, tagline. 2: Patrick meme, “400 pages. Every year. By hand.” 3: the four manual steps with their cost, “Every year. By hand. Zero error tolerance.” 4: name, tagline, three promises (AI reads · you approve · every value traces to a §). 5: tired guy → happy squirrel, “Thank you!” |
| Bottom bar | One sentence per step plus `n/17 ‹ › Narrator ✕`. No timeline, chapters or objectives. **T** hides the controls (text only) |
| Narrator | **P** opens a narrator pop-up (same file, `#presenter`): beat, on-screen sentence, 2–3 speaker notes, next beat, timer, ‹ › synced to the main window. While it is open the projector shows only the sentence. Synced by `opener.postMessage` (works on `file://` in Firefox) plus BroadcastChannel |
| Overview | Only the pipeline: eight cards with a one-line explanation each (Import · Index & highlight · Detect changes · Understand & approve · Generate test cases · Hand over · Compare · Report & certify). No emojis, no deterministic / AI / human labels |
| Import | A simulated drop of the original v13.4 PDF (no file dialog on stage); a real file still works |
| Specification | All 220 sections of the real PDF, full text (`demo/embed.py`), §3.12 preselected |
| Changes | Change list left, Achraf's change card right (approve / edit / decline). Step 5 shows an edit of the AI's reading before approving. The AI's reasoning sits underneath, collapsed in step 4 and opened in step 6 with a chat. The demo types the question; the answer is scripted, and `chatAnswer()` calls the live model in Live mode |
| Test cases | Achraf's review list, grouped by the rule they test. Step 7 highlights the case we follow (TC-3.12-B-01) |
| Developer | SAP's developer: Achraf's notification → our Messages inbox → Achraf's checklist with AI recap → **runs each test case**: opens it, “How to run it” (preconditions, steps), “What should happen” (in words, with the key values), then “Works as expected” → upload (automatic e-mail). No positive/negative labels |
| What the developer knows | ITSG's `Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx` gives the vendor the key results in prose (which periods go into the DBVO, EFZ end 30.03 → 27.03.2026, the message order 41 → 01 → 88 → 01, the DSIDs to use), but not the file field by field. So the checklist shows the expected behaviour; ITSG compares the exact file |
| Failure | SAP's screen showed 4 periods, but the exported file still has 5. Verdict mail “1 of 5 failed” in words → the developer asks why the file differs from the screen → ITSG answers with the quote. Then “two days later” (a clock overlay), the fixed file passes 5/5. The comparison view (byte view) is no longer a demo step; it is still on the Compare output screen |
| Certificate | Report & certificate screen; issued by e-mail; real PDF via html2pdf.js, print fallback |
| Live vs. recorded | Recorded by default, in the JSON shapes of Achraf's API. His full live UI stays as `demo/pipeline.html`, served at `/pipeline` |

**The story case.** ITSG's reference employee (Peter Mustermann) plus one older sick period,
01.11.–05.11.2024. More than 6 months lie between it and 14.07.2025, so request 41 must list
exactly 4 periods. SAP's screen gets it right, but its export writes every period on file: the first file still includes it (the existing “gap” variant), so it fails
with “Period 01.11.2024–05.11.2024 should not be in the request …” and “ANZAHL-AU expected 04,
got 05”. The fixed file is ITSG's real `TEEL0-Test1-DBVO`.

**Found while extracting the full text:**
- The real v13.4 is inconsistent. The employer paragraph of §3.12 (p. 135) says “nicht mehr als 6
  Monate”, the insurer paragraph (p. 136) still says “nicht mindestens 6 Monate”. The AI's
  reasoning in step 6 flags this for ITSG.
- The three maternity quotes (“beginnt 6 Wochen vor …”, “Sie endet 8 Wochen …”, “12 Wochen nach
  der Entbindung”) are in §3.11.5 “Ende Beschäftigungsverhältnis zum”, not in §3.11.1. The
  highlights now point there.
- Field-level headings carry no number in the PDF text; their numbers come from their order under
  the parent (3.12 → 3.12.1 … 3.12.14), which matches the spec's own cross references.

## Inputs → workflow → outputs

**Inputs**
- The yearly government spec PDFs. This is the only external input. The change log is included
  when the government provides one.
- From our own archive:
  - last year's spec version,
  - the existing test catalogue,
  - last year's audit reports.
- From vendors: their DTA output files. Each file carries the product and modification IDs.

**Workflow**
0. **Baseline check (once).** Match the existing catalogue against the current spec: obsolete
   tests (rule or wording removed) and missing tests (statement without a test).
1. **Ingest.** Build the § index from the original PDF's structure.
2. **Detect changes.** Parse the change log and diff the sections.
3. **Impact.** Find the affected catalogue rows.
4. **Extract.** The LLM extracts the parameters and drafts the rule in plain language.
5. **Approve.** An examiner approves, edits or declines each rule.
6. **Generate.** One representative test case per rule, in human words; functions compute the
   expected output. The full boundary set and fresh variants are one click away.
7. **Publish.** Send the test package to vendors, also as importable JSON (proposal).
8. **Compare.** Check vendor files against the expected output; explain each difference in words.
9. **Audit and report.** Run the on-site checklist, then produce the per-vendor report, its seal
   and the next audit scope.

**Outputs**
- **Test package:** test cases in words, expected DTA files, criteria checklist, and the same
  cases as JSON test input (`itsg-eel-testinput/0.1`, a proposal that needs a spec change).
- **Comparison results**, with every difference explained in words.
- **Sealed report per vendor** (print and JSON), an all-vendors overview, and the **next audit
  scope**: failed + changed + new.
- **Updated catalogue** and **baseline check** as CSV.

## The trust architecture

```
spec § section ──structural retrieval──▶ LLM ──JSON tool call──▶ 5 guards ──▶ examiner ──▶ rule function ──▶ expected value
                                         reads numbers,           1 quote is verbatim in the spec
                                         picks function_id        2 number appears in the quote (Woche = 7 Tage …)
                                         + verbatim quotes        3 parameter exists and is in range
                                                                  4 run A = run B
                                                                  5 function unit tests pass
```

- **The LLM never computes.** Expected values come from pre-written, versioned, hashed and
  unit-tested functions such as `dbvo.gates`, `dbvo.chain`, `efz.end` and `eel.confirmedEnd`.
- **The guards are deterministic.** A paraphrased quote, or a number that isn't in its quote, is
  rejected mechanically. The demo shows both cases: run B paraphrases one quote in R-3.12-A, and
  reads 14 weeks from a "12 Wochen" quote in R-3.11.1.
- **In the UI this sits one level down.** ITSG couldn't follow function IDs and hashes, so the
  Rules screen leads with spec quote → plain-language rule → test case. The function, the five
  guards and both AI runs are in a collapsed "Technical details" fold; the function library
  moved to the Evidence group.
- **32 self-tests run in the browser** (and in Node). They include ITSG's reference case:
  - 35 days,
  - sick pay ending 30.03 → 27.03.2026,
  - the expected DBVO block matching the real `TEEL0-Test1-DBVO` file **byte for byte**.

## Spec change detection

- **Two deterministic sources:**
  - the official change log, parsed with a regex over § numbers and quoted titles;
  - a section-by-section word diff of the old and new text.
- **Reconciliation** gives each change one source badge:
  - **in log + diff**: confirmed.
  - **diff only**: not in the change log. These are shown first, because they're the riskiest.
  - **log only, no text change**: the change is probably in a table or annex.
  - **log only, text not loaded**: the demo only embeds some sections.
- **Classification:**
  - *Type* is the only AI judgement. The examiner confirms it.
  - *Test impact* is counted from the catalogue's § references.
  - *Risk* follows a fixed rule from type and impact:
    - high: a condition, parameter or format change with affected tests;
    - medium: a new or removed rule;
    - low: editorial.
- **Demo highlight.** The change log calls the §3.12 change *editorial*. The (illustrative) diff
  shows "nicht **mindestens** 6 Monate" → "nicht **mehr als** 6 Monate". At exactly six months the
  result flips, so the boundary test's expected value changes.
  > Interesting detail in the real v13.4: the employer paragraph says "nicht mehr als", while the
  > insurer paragraph a page later still says "nicht mindestens". That's worth asking ITSG about.

## Retrieval and context discipline

- **Retrieval is structural, not embedding similarity.** It uses numbered §-headings, the table
  of contents with page numbers, and the 3,528 internal links in the v13.4 PDF. A retrieved span
  must start with its expected heading.
- **Each LLM call gets only:**
  - the target § section,
  - the sections it links to directly (depth 1),
  - the old version of the same section.
- **The archive is never sent in bulk.** A context meter shows what was sent.

## Traceability: why a linear trail

The primary traceability view is a **linear provenance trail**, opened from any value or verdict:

> German quote → extracted parameter → function@version (+ tests) → inputs → step-by-step
> calculation → result → where it's used

People read top to bottom, while node graphs are hard to read on a projector. Each supporting
view answers one question:

| View | Question it answers |
|---|---|
| **Coverage matrix** | Is everything covered? |
| **Byte view** in the comparator | Which bytes are wrong? |
| **Audit trail** | Who did what, and when? Entries are hash-chained. |

## Known limits of the demo

- **No real v13.3 text yet.** The old wording is reconstructed from the change log and labelled.
- **Partial record layouts.** VOSZ, DSKO, NCSZ and DSLW positions 206–224 aren't fully specified
  in the documents we have.
- **Field dictionary.** Difference explanations use field meanings from the record tables we
  have; the full GKV-Datenaustausch dictionary (incl. mandatory flags) is not imported yet.
- **Simulated data:**
  - the catalogue is a 46-row EEL subset, and the baseline check adds three simulated historic rows;
  - the JSON import on the vendor side is simulated (no vendor offers an import interface);
  - the vendors and their previous audit results are fictional;
  - the KK replies are simulated.
- **Live mode needs the local proxy.** It is blocked inside a published artifact.
