# Source Documents

All files are in `hackathon-files/ITSG - The Challenge Sponsor/` unless noted. All specs are in German.

## The specifications (rules the software must follow)

| File                                                                                  | Pages | What it is                                                                                                                                                                                                                       | When to use it                                                                                                                |
| ------------------------------------------------------------------------------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf` | 168   | **Procedure description, v13.4, valid from 01.01.2027.** Defines every record (DSLW) and data block (DBxx) field by field: position, length, type, mandatory or optional, allowed values, and the business rules for filling it. | **Primary spec.** The source for parsing and for most testable rules. §3.1 DSLW, §3.12 DBVO (prior illness), etc.             |
| `2026_03_10_Endfassung_Beispielpapier_DTA_EEL_Version_13.3_gueltig_ab_01.01.2027.pdf` | 161   | **Example paper, v13.3.** Worked scenarios with filled-in records.                                                                                                                                                               | Expected results and test oracles; a template for generated test cases.                                                       |
| `GG_EEL_V13.1_06.05.2025.pdf`                                                         | 16    | **Common principles (Gemeinsame Grundsätze), v13.1, valid from 01.01.2026.** The legally approved framework: which messages exist, by Abgabegrund, and who sends what when.                                                      | High-level process rules: §2.1.2 request for prior illness (41), §2.2.1 prior-illness procedure (61), §2.5 cancellation (88). |

## The joint circulars (legal interpretation and benefit rules)

| File | Pages | Topic |
|---|---|---|
| `2024_12_11_…_Aktualisierung_der_GR_zu_Entgeltersatzleistungen_Anl3.pdf` | 406 | Circular on sickness benefit (*Krankengeld*) and its duration. Substantive benefit law, e.g. how long benefits run and how prior illnesses count. |
| `2025_12_10_…_Aktualisierung_der_GR_zu_EEL_Anl1.pdf` | 162 | Circular on income replacement benefits (update of 13.03.2024). Calculation rules and practical clarifications. |
| `2025_12_10_…_Aktualisierung_der_GR_zu_EEL_Anl2.pdf` | 140 | Circular on benefits during pregnancy and maternity (*Mutterschaftsgeld*). |

These explain *why* the fields have the values they do. They are good RAG material for explaining
test results, but they're less directly testable than the Verfahrensbeschreibung.

## The worked example (how ITSG expects a test case to look)

| File | What it is |
|---|---|
| `DTA-EEL-Beispiel_Vorerkrankung.docx` | Test scenario "DBVO": the requirement, **4 testable criteria with UUIDs**, and the expected result |
| `Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx` | The test setup: sick-leave periods, employment end, the expected message sequence, and the IDs to use |
| `TEEL0-Test1-DBVO` | **A real output file** produced by payroll software for this case (fixed-width, ISO-8859-1, CRLF) |

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
