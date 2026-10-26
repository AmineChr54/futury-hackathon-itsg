# Challenge Overview

Source: `hackathon-files/ITSG - The Challenge Sponsor/Futury-Hackathon-2026-Englisch.pdf`
(the slide title is "100 programs, 800 million messages, 0 errors – AI-powered system review").

## Who is ITSG?

- *Informationstechnische Servicestelle der gesetzlichen Krankenversicherung*, founded in 1996.
  Headquarters in Offenbach, branch in Berlin; 220+ employees, €46.5M revenue (2025), four of its own
  data centers.
- **Mission:** standardise and digitise data exchange in healthcare and social insurance.
- **Customers:** only its shareholders, e.g. the GKV-Spitzenverband (National Association of
  Statutory Health Insurance Funds) and its member funds.
- **Users:** anyone who exchanges data with health insurers, such as employers and health service
  providers (clinics, therapists).
- **Products:** SV-Meldeportal (social-insurance reporting portal), Systemuntersuchung (system review),
  ITSG Trust Center, ITSG Private Platform, and the health-card insurance number.

## What is a system review (*Systemuntersuchung*)?

- "Systems" means **payroll programs** (SAP, DATEV, Lexware…).
- They handle **€400bn** in social insurance contributions and **800M messages per year**: proofs of
  contribution, sick notes, registrations and deregistrations, income replacement benefits, and more.
- **Goal:** ensure that contributions are calculated correctly and that messages are transmitted
  correctly.
- The specifications are spread across **~100 documents**.
- Before a system is first approved, ITSG provides intensive consultation and tests the entire
  software. After that, there is an **annual quality-control audit**.

### Legal mandate: §95b SGB IV

1. Persons subject to reporting obligations (employers) must submit reports only from
   **system-tested programs** or system-tested electronic filling aids.
2. The system review covers advice plus the professional and technical examination of recording,
   testing, calculation, processing and transmission of data. Payroll programs must perform the
   calculations, generate the data and verify it **by machine**.
3. Hardware, operating systems and internal communication software are out of scope.
4. The review is carried out by the GKV-Spitzenverband, with pension insurance, accident insurance
   and the Federal Employment Agency participating. In practice, ITSG performs it.

## The challenge

> Design an AI solution that supports, and potentially even replaces, the testing processes.
> Focus on the **payroll process for income replacement benefits** (*Entgeltersatzleistungen*),
> e.g. maternity benefit and sickness benefit. It should automatically check whether a program meets
> all applicable specifications within this scope. The AI solution is intended to offer different
> technical approaches.

### How it could work (ITSG's suggestion)

1. **AI generates** technical test cases.
2. **Humans run** the test cases in the payroll software.
3. **AI checks** the data records generated in the process.

*Optional:* the software **vendor sets up the AI review assistant locally**, tests their own
application, and the assistant **generates a test report for the ITSG system review**.

### Objectives: what the assistant should be able to do

| # | Verb | Meaning |
|---|---|---|
| 1 | **Identify** | find the relevant requirements in the specifications |
| 2 | **Translate** | turn requirements into testable criteria |
| 3 | **Generate** | produce test cases with expected results |
| 4 | **Create** | keep a traceable test record |
| 5 | **Test & compare** | run the software with the test cases and compare actual with expected results |
| 6 | **Deliver** | produce comprehensible test reports |

### "Cherry on top"

Build a **prototype** of the concept: a code demonstrator, app, website or similar, as long as
it's clear how it supports the system review process.

## Judging (Jury Scorecard, total /20)

Source: `hackathon-files/General - Futury/Jury_Scorecard_Build_Days.pdf`

| Category | Questions the jury asks |
|---|---|
| **Idea**: innovation and creativity | Innovative? Outside the box? Different from the other teams? |
| **Execution**: quality and depth | *More than a good-looking dashboard?* Depth and substance? Thought through beyond the obvious? |
| **Relevance**: impact for ITSG | Does it really solve the challenge? Does it meet ITSG's actual needs, or did time go into gimmicks? |
| **Pitch**: presentation and clarity | Did the problem, the idea, the value and the USP come across? |

Each category is scored 1–5.

## Resources

### hessian.AI models (`chat.hessian.ai`, access until **Wed 28.10.2026 09:00 UTC+1**, unlimited tokens)

| Model | Vendor | Specs | Good for |
|---|---|---|---|
| **Kolibri-1** | Aleph Alpha (DE) | 78B MoE, 3.46B active, 512K context, text only, DE/EN, German-optimised tokenizer, tool calling, Apache 2.0 | Long-document analysis, structured extraction, knowledge assistants. **A natural fit for German specs.** |
| **GLM-5.3-Flash** | Z.ai (CN) | 320B MoE, 18B active, 512K context, text/image/video in, adjustable reasoning, MIT | Coding, long-context analysis, multi-step agent workflows |

Server and API access details: `hackathon-files/hessian.AI - Tech Sponsor/Futury_Build_Days_hessianAI_Server_Access.pdf`.

### ITSG contacts on site

- Gregor Grebe, Chief Strategy Officer
- Thorsten Müller, Group Leader Strategy
- Gerald Friedrich, System Examiner. He is the domain expert for how reviews are done today.
