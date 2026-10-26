# Source Documents

All files are in `hackathon-files/ITSG - The Challenge Sponsor/` unless noted. All specs are in German.

## The specifications (rules the software must follow)

| File                                                                                       | Pages | What it is                                                                                                                                                                                                                       | When to use it                                                                                                                |
| ------------------------------------------------------------------------------------------ | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `2026_03_10_Endfassung_Verfahrensbeschreibung <br>_DTA_EEL_Version_13.4_ab_01.01.2027.pdf` | 168   | **Procedure description, v13.4, valid from 01.01.2027.** Defines every record (DSLW) and data block (DBxx) field by field: position, length, type, mandatory or optional, allowed values, and the business rules for filling it. | **Primary spec.** The source for parsing and for most testable rules. §3.1 DSLW, §3.12 DBVO (prior illness), etc.             |
| `2026_03_10_Endfassung_Beispielpapier_DTA_ <br>EEL_Version_13.3_gueltig_ab_01.01.2027.pdf` | 161   | **Example paper, v13.3.** Worked scenarios with filled-in records.                                                                                                                                                               | Expected results and test oracles; a template for generated test cases.                                                       |
| `GG_EEL_V13.1_06.05.2025.pdf`                                                              | 16    | **Common principles (Gemeinsame Grundsätze), v13.1, valid from 01.01.2026.** The legally approved framework: which messages exist, by Abgabegrund, and who sends what when.                                                      | High-level process rules: §2.1.2 request for prior illness (41), §2.2.1 prior-illness procedure (61), §2.5 cancellation (88). |

## The joint circulars (legal interpretation and benefit rules)

| File                                                                     | Pages | Topic                                                                                                                                             |
| ------------------------------------------------------------------------ | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `2024_12_11_…_Aktualisierung_der_GR_zu_Entgeltersatzleistungen_Anl3.pdf` | 406   | Circular on sickness benefit (*Krankengeld*) and its duration. Substantive benefit law, e.g. how long benefits run and how prior illnesses count. |
| `2025_12_10_…_Aktualisierung_der_GR_zu_EEL_Anl1.pdf`                     | 162   | Circular on income replacement benefits (update of 13.03.2024). Calculation rules and practical clarifications.                                   |
| `2025_12_10_…_Aktualisierung_der_GR_zu_EEL_Anl2.pdf`                     | 140   | Circular on benefits during pregnancy and maternity (*Mutterschaftsgeld*).                                                                        |

These explain *why* the fields have the values they do. They are good RAG material for explaining
test results, but they're less directly testable than the Verfahrensbeschreibung.

## The worked example (how ITSG expects a test case to look)

| File                                                            | What it is                                                                                            |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `DTA-EEL-Beispiel_Vorerkrankung.docx`                           | Test scenario "DBVO": the requirement, **4 testable criteria with UUIDs**, and the expected result    |
| `Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx` | The test setup: sick-leave periods, employment end, the expected message sequence, and the IDs to use |
| `TEEL0-Test1-DBVO`                                              | **A real output file** produced by payroll software for this case (fixed-width, ISO-8859-1, CRLF)     |

See [04-example-test-case-dbvo.md](04-example-test-case-dbvo.md) and [05-data-format.md](05-data-format.md).

## Other

| File | What it is |
|---|---|
| `2026-10-26 Translation Assistance.pdf` | German↔English glossary from ITSG. Merged into [02-glossary.md](02-glossary.md). |
| `Futury-Hackathon-2026-Englisch.pdf` | The challenge slides. Summarised in [01-challenge-overview.md](01-challenge-overview.md). |
| `../General - Futury/Jury_Scorecard_Build_Days.pdf` | Judging criteria |
| `../hessian.AI - Tech Sponsor/*` | Model info (Kolibri-1, GLM-5.3-Flash) and server access |

## Version note

The Verfahrensbeschreibung and Beispielpapier are valid **from 01.01.2027**, while the GG is v13.1
(valid from 01.01.2026). The assistant should track which spec version each rule comes from,
because the rules change every year.

## Document structure (what makes deterministic retrieval possible)

These are findings from analysing the PDFs with `pdftotext` and `pdftohtml`.

- **Numbered sections everywhere.** In the Verfahrensbeschreibung, records and blocks are §3.x and
  fields are §3.x.y (e.g. §3.12.7 "Arbeitsunfähigkeit Zeitraum-Beginn nn"). The table of contents
  gives page numbers.
- **Internal hyperlinks.** The v13.4 Verfahrensbeschreibung contains **3,528 internal links**. Every
  cross-reference such as "siehe 3.12.7" is a clickable link to its target page. A § index (number →
  title → page → text span → outgoing links) can therefore be built **deterministically**, with no
  fuzzy embedding search.
- **Field tables follow a fixed pattern:**
  `position-from – length – type (n/an) – M/m – FIELD-NAME – description`, followed by the business
  rules. For example `031- 002 n M ANZAHL-AU`. These lines can be parsed into a machine-readable
  record schema. The DBVO and DSLW offsets parsed this way match the real sample file byte for byte
  (see [05-data-format.md](05-data-format.md)).
- **Page furniture to strip** before diffing: headers like "Datenbaustein DBVO – Vorerkrankungszeiten"
  and footers like "Stand: 10.03.2026 Seite 135 von 168 Version 13.4".
- Text extraction is **ISO-8859-1** / Windows-1252. Convert to UTF-8 so umlauts survive.

## Change logs (where "what changed" lives)

| Document | Location | Format |
|---|---|---|
| Verfahrensbeschreibung DTA EEL v13.4 | "Änderungsübersicht", pp. 2–4 | Table: **version \| date \| change**. Each change names § numbers with quoted titles, e.g. `3.12 „Datenbaustein DBVO – Vorerkrankungszeiten" – redaktionelle Anpassung bei einer Aussage zur 6-Monatsfrist` |
| GR Krankengeld (Anl3, 11.12.2024) | "1. Änderungsübersicht", **pp. 17–20** | Table: **date \| change**. Each entry lists **hyperlinked** § numbers with quoted titles, then " – " and a description |
| GR EEL (Anl1), GR Mutterschaft (Anl2) | Near the start (Vorwort / change overview) | Same family as Anl3 |

**Examples from the v13.4 change log (useful for the demo):**

| § | What changed |
|---|---|
| 3.12 DBVO | Editorial adjustment of a statement on the **6-month period** |
| 3.7.3 Ende der EEL | Note added: the EEL end may **only be confirmed up to the end of employment** |
| 3.1.10 BBNR-VU | Clarification: a reply must contain the BBNR-VU sent by the employer |
| 3.20 DBSD | On cancellation, the first and family name of the record being cancelled must be given |
| 3.5.5 SV-Bruttoarbeitsentgelt | Hourly-paid staff: use actual hours × hourly wage, not the estimate |
| 3.1.18 Abgabegrund | Explanation added for co-admission certificates (reasons "02"/"04") |

**Important:** the government **doesn't always provide a change log** (ITSG engineer, 26.10.2026).
The assistant therefore also diffs the new spec against the previous version section by section;
see [09-demo-design.md](09-demo-design.md).

**What we're missing:** the **previous version (v13.3) of the Verfahrensbeschreibung**, needed for
a real diff. We should ask ITSG for it.
