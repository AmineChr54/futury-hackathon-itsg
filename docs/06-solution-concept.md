# Solution Concept (draft for team discussion)

## Core idea

**An LLM where understanding is needed, deterministic code where proof is needed.**

An auditor can't sign off on "the AI thinks it's fine." The assistant should use the LLM to read
~1,000 pages of German spec and turn them into **explicit, citable, executable rules**. Checking the
actual output files should then be **deterministic and reproducible**, with every verdict traceable
back to a spec paragraph. This is what earns the jury's "more than a dashboard" and "depth" points.

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
   resulting DTA file(s).
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

## MVP for the hackathon (vertical slice)

Build one complete slice end to end, using **DBVO / Abgabegrund 41**:

- [ ] Parser for DSLW + DBVO (+ DBNA, DBID), with the sample file parsing correctly
- [ ] The 4 DBVO criteria encoded as executable checks, linked to their UUIDs and §3.12
- [ ] Test-case generator: positive, negative and boundary scenarios plus expected DBVO output
- [ ] Synthetic "broken" files (wrong order, missing period, insurer field filled, gap > 6 months…)
      to show the validator catching errors
- [ ] LLM demo: feed §3.12 → produce criteria → compare with ITSG's 4 criteria (shows the extraction
      generalises)
- [ ] Report view (web UI) with pass/fail, field-level diff and spec citations
- [ ] Stretch: the message-sequence check (61 / 88 / 01 / 62 chain) and a second area (e.g.
      Abgabegrund 03, maternity benefit)

## Pitch angles (USP)

- **Trustworthy:** deterministic verdicts and citations to the exact paragraph, so it's audit-grade.
- **Spec-change resilient:** a new spec version means re-running the extraction and diffing the
  criteria catalogue, which shows which tests are affected.
- **Vendor self-service:** it runs locally at the vendor (data protection: real employee data never
  leaves the premises), and ITSG receives the report.
- **Sovereign AI:** it can run on Kolibri-1 (German, open weights, self-hostable).

## Open questions

- [ ] Team size and skills, and the tech stack (Python backend + web UI?)
- [ ] Must we use the hessian.AI models, or can we also use other LLMs?
- [ ] Ask ITSG: can we get the **record description** (Datensatzbeschreibung) with the full VOSZ,
      DSKO, NCSZ and DBNA layouts and the DSLW flags 206–224?
- [ ] Ask ITSG: what does "Daumenkriterium" mean? Is it the key criterion?
- [ ] Ask ITSG: more sample output files, especially the KK replies (61, 62) and the 01 pay
      certificate?
- [ ] Ask ITSG: how are test results documented today (format of the current test record)?
