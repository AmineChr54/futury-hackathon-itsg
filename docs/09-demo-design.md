# Demo Design

The decisions behind `demo/index.html`, from the 20-question scoping round on 26.10.2026 and the
afternoon conversations with ITSG engineers ([07-itsg-meeting-notes.md](07-itsg-meeting-notes.md)).
For how to run it, see [`demo/README.md`](../demo/README.md).

## Decisions

| Area | Decision |
|---|---|
| Users | Role switch: **ITSG examiner ⇄ vendor** |
| Story | Starts with ITSG's biggest pain (spec change → affected tests), with the full pipeline one click away |
| Presenting | Guided demo with spotlight, zoom and captions, plus a **separate presenter window** (speaker notes, timer, next step) synced to the projector window; free deep-dive at any time |
| Language | DE/EN toggle; German spec quotes are always kept verbatim |
| AI | Hybrid: recorded runs by default, **live hessian.AI** (Kolibri-1 / GLM-Flash) optional |
| Trust | **The LLM only extracts parameters and picks a function; pre-written functions compute.** Every value has a provenance trail |
| Human loop | Approve, edit or decline (with a reason) the **plain-language rule text**, and confirm its numbers, once per rule; everything goes to a hash-chained audit trail |
| Domain depth | DBVO / Abgabegrund 41 in depth; 42/62 (EEL end) and 03 (maternity) shallow |
| Data | ITSG's reference case + generated employees; fictional vendors only |
| Style | Clean, professional tool, crimson accent, light and dark; built from tokens so it can move into Claude Design |
| Tech | One HTML file, vanilla JS, works offline; CDN only for optional extras |
| Name | Open: working title "EEL Review Assistant", tracked as a GitHub issue |

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
- **31 self-tests run in the browser** (and in Node). They include ITSG's reference case:
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
