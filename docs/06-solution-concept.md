# Solution Concept (draft for team discussion)

## Core idea

**An LLM where understanding is needed, deterministic code where proof is needed.**

An auditor can't sign off on "the AI thinks it's fine." The assistant should use the LLM to read
~1,000 pages of German spec and turn them into **explicit, citable, executable rules**. Checking the
actual output files should then be **deterministic and reproducible**, with every verdict traceable
back to a spec paragraph. This is what earns the jury's "more than a dashboard" and "depth" points.

## What ITSG told us changes the focus

See [07-itsg-meeting-notes.md](07-itsg-meeting-notes.md). In short:

- **The pain is test-case creation and maintenance.** That's ~3,000 cases by hand, adapted every
  half year to spec changes. Checking messages is already partly automated by their testing device.
- **Zero failure tolerance.** One wrong cent fails the software.
- **Vendors may fit their answers** to the known monthly test solutions.
- **UI automation of 100 programs is not realistic.** Use the message channel instead.

So the centre of gravity moves **left in the pipeline**, onto spec → criteria → test cases and
spec change → affected test cases. Validation stays, but as a supporting piece.

> **Update (afternoon, 26.10.):** the follow-up talks sharpened three points, and the demo is built
> on them. See [09-demo-design.md](09-demo-design.md).
> 1. **The LLM only extracts parameters, with verbatim quotes, and picks a pre-written function.**
>    The functions compute. Five deterministic guards check every answer.
> 2. **Change detection uses the change log *and* a section diff against last year's spec**,
>    because the government doesn't always ship a change log.
> 3. **The next audit scope is failed + changed + new.** Criteria are checked on site and recorded
>    as a pass/fail checklist.

> **Update (evening, 26.10.):** ITSG reviewed the demo. See
> [11-demo-feedback-itsg.md](11-demo-feedback-itsg.md).
> 1. **The real bottleneck is manual input.** Vendor engineers type every test case into their own
>    software. So: **one test case per rule to start**, and more only once input is automated.
> 2. **Proposal: automatic test input.** Vendors import test cases as JSON; the output stays DTA.
>    This needs a **spec change**. Pilot with **SAP**.
> 3. **Rules must be readable.** Show a plain-language rule between spec and test case, which the
>    examiner approves, edits or declines. Function IDs, hashes and guards stay behind the scenes.
> 4. **Baseline check:** check the ~4,000 historically grown test scenarios against the current spec
>    and flag obsolete and missing ones. Start from the **original government PDF**.
> 5. **Our comparison stays.** ITSG has its own comparator but would replace it with ours "if it's
>    better". Differences must be explained in words, not bytes.

## Pipeline

```
 Specs (PDF)                 Criteria catalogue              Test cases                 Vendor runs           Validation               Report
┌────────────┐  extract   ┌──────────────────────┐ gen  ┌─────────────────────┐  in   ┌──────────────┐ parse ┌────────────────┐     ┌────────────────┐
│ Verfahrens-│──(LLM)───▶ │ ID, spec ref (§3.12),│────▶ │ scenario (AU dates, │─────▶ │ payroll SW   │─────▶ │ fixed-width    │───▶ │ criterion →    │
│ beschreib. │  + human   │ rule text, type      │(LLM+ │ employee, …)        │ their │ produces     │       │ parser + rule  │     │ test → field → │
│ GG, GR,    │  review    │ (gate/content),      │solver)│ + EXPECTED records  │ tool  │ DTA files    │       │ engine; diff   │     │ pass/fail →    │
│ Beispiel-  │            │ fields, executable   │      │ + negative cases    │       │              │       │ expected vs    │     │ spec citation  │
│ papier     │            │ check                │      │                     │       │              │       │ actual         │     │ (PDF/HTML)     │
└────────────┘            └──────────────────────┘      └─────────────────────┘       └──────────────┘       └────────────────┘     └────────────────┘
```

1. **Spec ingestion.** Convert the PDFs to text, chunk them by section number (§3.12.7…), and parse
   the field tables (position, length, type, M/m) into a machine-readable **schema** for each record
   and block.
2. **Requirement extraction (LLM).** For a chosen area, extract the rules into a **criteria
   catalogue**: ID, source citation, rule in plain language, kind (*gate*: "may only be generated
   if"; *content*: "field X must…"; *format*), and the fields involved. A human reviews and approves
   each entry. ITSG's 4 DBVO criteria are our gold standard for checking the extraction.
3. **Test-case generation.** For each criterion, generate scenarios: a positive case, a negative
   case (the software must refuse to produce the message), and boundary cases (exactly 6 months,
   exactly 30 days, open-ended AU = today + 7 days). Each comes with **expected output records**,
   computed by deterministic code rather than the LLM, so the expected results are guaranteed
   correct.
4. **Execution (human).** The vendor enters each scenario in their payroll software and uploads the
   resulting DTA file(s). Each case is typed in by hand today, which is why ITSG wants few cases
   per rule until there is an import interface (see the evening update above).
5. **Validation.**
   - Parse the file against the schema: format errors, wrong default values, field lengths.
   - Run the rule engine: e.g. periods newest-first, gaps ≤ 6 months, insurer-only fields at their
     default value, ≥ 30 days.
   - Diff expected against actual, field by field.
   - Check the message sequence across files (41 → 61 → 01 → 88 → 01, REF-ID and DSID-UR linkage).
   - The LLM is used **only to explain** failures in plain German or English, with spec quotes.
6. **Report.** A traceable test record: criterion → test case → record and field → expected vs.
   actual → verdict → spec citation, plus the software's PRODUKT-IDENTIFIER and version. Exportable
   for the ITSG review.

### Cross-cutting pieces (from the ITSG conversation)

- **Spec change → impact.** Given a new spec version, diff it against the old one. Use the
  Verfahrensbeschreibung's change log (*Änderungsübersicht*) plus a text diff per section to get:
  changed sections → affected criteria → affected test cases → regenerated cases. A human reviews
  only the delta.
- **Zero-tolerance safeguards.**
  - The LLM never computes expected values; deterministic code does.
  - Run two independent extractions (e.g. two models or two prompts) of each rule, and send any
    disagreement to a human.
  - A human approves each rule once.
  - Each generated test case is replayed through the oracle, so it is consistent by construction.
- **Fresh variants against gaming.** Each criterion is a parameterised template. Every cycle (or
  every vendor) gets new concrete data, e.g. other AU dates or other gap lengths, still at the
  boundaries. The expected result is recomputed each time, so vendors can't fit outputs to answers
  they've never seen.
- **Coverage matrix.** Every spec clause is mapped to its criteria and their test cases, with
  uncovered clauses flagged. This gives evidence for "100% covered".

## MVP for the hackathon (vertical slice)

Build one complete slice end to end, using **DBVO / Abgabegrund 41**:

In priority order, re-weighted after the ITSG conversation:

- [ ] **LLM extraction:** feed §3.12 → produce criteria → compare with ITSG's 4 criteria (shows the
      extraction generalises)
- [ ] **The 4 DBVO criteria** encoded as executable checks, linked to their UUIDs and §3.12
- [ ] **Test-case generator:** positive, negative and boundary scenarios plus expected DBVO output,
      computed by the deterministic oracle
- [ ] **Fresh-variant mode:** the same criteria regenerated with new data, to show the anti-gaming
      idea
- [ ] **Spec-change demo:** use the v13.4 change log (e.g. its §3.12 DBVO entry) to show "this
      section changed → these criteria and test cases are affected → here are the updated cases"
- [ ] **Parser and validator** for DSLW + DBVO (+ DBNA, DBID), with the sample file passing and
      synthetic broken files failing (wrong order, missing period, insurer field filled,
      gap > 6 months…)
- [ ] **Report and coverage view** (web UI): clause → criteria → tests, pass/fail, field-level diff,
      citations
- [ ] Stretch: the message-sequence check (61 / 88 / 01 / 62 chain) and a second area (e.g.
      Abgabegrund 03, maternity benefit)
- [ ] *(From the demo review)* **Readable rule text** with approve / edit / decline, one default
      test case per rule, field-level explanations of differences, and a per-vendor pass/fail report
      (print and JSON). Full list: [11-demo-feedback-itsg.md](11-demo-feedback-itsg.md)
- [ ] *(From the demo review)* **Automatic input proposal** (JSON import, SAP pilot) and a
      **baseline check** of the existing catalogue against the current spec

## Pitch angles (USP)

- **From spec change to updated tests in hours, not weeks:** this directly addresses the
  "specs in December, effective 1 January" crunch.
- **Can't be gamed:** fresh variants each cycle mean vendors can't fit their outputs to known answers.
- **Trustworthy:** deterministic verdicts and citations to the exact paragraph, so it's audit-grade.
- **Spec-change resilient:** a new spec version means re-running the extraction and diffing the
  criteria catalogue, which shows which tests are affected.
- **Vendor self-service:** it runs locally at the vendor (data protection: real employee data never
  leaves the premises), and ITSG receives the report.
- **Sovereign AI:** it can run on Kolibri-1 (German, open weights, self-hostable).
- **Removes the manual-input bottleneck:** test cases ship as importable JSON, so vendors stop
  typing scenarios in by hand. This is a proposed spec change, piloted with SAP.
- **Cleans up 30 years of test history:** a baseline check flags obsolete and missing tests
  against the current law.

## Open questions

- [ ] Team size and skills, and the tech stack (Python backend + web UI?)
- [ ] Must we use the hessian.AI models, or can we also use other LLMs?
- [ ] Ask ITSG: can we get the **record description** (Datensatzbeschreibung) with the full VOSZ,
      DSKO, NCSZ and DBNA layouts and the DSLW flags 206–224?
- [ ] Ask ITSG: what does "Daumenkriterium" mean? Is it the key criterion?
- [ ] Ask ITSG: more sample output files, especially the KK replies (61, 62) and the 01 pay
      certificate?
- [ ] Ask ITSG: how are test results documented today (format of the current test record)?
- [ ] Ask Gerhard (ITSG): where do the ~4,000 test scenarios live, and does the reworked
      rule-extraction screen make sense to him?
- [ ] Would ITSG support a spec change that requires vendors to accept JSON test input?
- [x] ~~Do we need to re-implement DTA comparison?~~ ITSG has a comparator, but ours may replace it,
      so keep it
