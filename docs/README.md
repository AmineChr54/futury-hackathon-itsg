# ITSG Challenge: AI Review Assistant for System Review

**Futury Build Days #3, 26–27 Oct 2026.** Challenge sponsor: ITSG GmbH. Tech sponsor: hessian.AI.

## TL;DR

Every payroll program in Germany (SAP, DATEV, Lexware, ~100 in total) must be **system-tested** by ITSG before it may send reports to the social insurance institutions (§95b SGB IV). 
Today that testing is manual, and the rules are spread across ~100 specification documents.

**We are building an AI review assistant** for the area of **income replacement benefits**
(*Entgeltersatzleistungen*, EEL), such as sickness benefit and maternity benefit. It should:

1. read the specs and **identify** the requirements,
2. **translate** them into testable criteria,
3. **generate** test cases with expected results,
4. **check** the data records the payroll software actually produces,
5. produce a **traceable test report** for the ITSG system review.

A working prototype is optional but strongly encouraged.

## Docs

| File | What's in it |
|---|---|
| [01-challenge-overview.md](01-challenge-overview.md) | Who ITSG is, what a system review is, the challenge, judging, resources |
| [02-glossary.md](02-glossary.md) | German↔English terms, submission-reason codes, record and block names |
| [03-source-documents.md](03-source-documents.md) | What each provided file is and when to use it |
| [04-example-test-case-dbvo.md](04-example-test-case-dbvo.md) | The one fully worked reference test case (prior-illness request) |
| [05-data-format.md](05-data-format.md) | The fixed-width DTA EEL file format, with an annotated sample file |
| [06-solution-concept.md](06-solution-concept.md) | Proposed architecture, MVP scope, open questions |
| [07-itsg-meeting-notes.md](07-itsg-meeting-notes.md) | What the ITSG team told us: how testing works today, constraints, what to focus on |
| [08-problem-and-solution.md](08-problem-and-solution.md) | **Start here:** the problem and our solution, explained with diagrams |
| [09-demo-design.md](09-demo-design.md) | The demo: decisions, inputs/workflow/outputs, trust architecture, change detection, traceability |
| [10-hessian-ai-api.md](10-hessian-ai-api.md) | The hessian.AI inference API (endpoint, models, auth), without the key |
| [11-demo-feedback-itsg.md](11-demo-feedback-itsg.md) | ITSG's feedback on the demo (evening 26.10.): how vendors really test, and the list of UI changes |

**The demo:** [`demo/index.html`](../demo/index.html) is a single file that opens offline.
[`demo/README.md`](../demo/README.md) explains how to present it and how to use the live AI mode.

Source files live in `hackathon-files/`.
