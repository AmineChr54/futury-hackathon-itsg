# Reference Test Case: DBVO (Prior-Illness Request)

This is the **one fully worked example** ITSG gave us. It shows exactly what the chain from
requirement → criteria → test setup → expected messages → actual output file looks like. Everything
our assistant generates should follow this shape.

Sources: `DTA-EEL-Beispiel_Vorerkrankung.docx`, `Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx`,
Verfahrensbeschreibung §3.12, and `TEEL0-Test1-DBVO`.

## Business background (why this matters)

Under §3 EntgFG, an employer pays **up to 6 weeks of sick pay** (EFZ) per illness. If the employee
was already off sick **with the same illness** in the past, those earlier days count against the 6
weeks. After that, the health insurer pays sickness benefit (*Krankengeld*).

The employer doesn't know the diagnoses, so it **asks the health insurer** which earlier periods of
sick leave count. That is the **prior-illness request**: a DSLW record with **Abgabegrund 41** and a
**DBVO** block listing the candidate periods. The insurer replies with **Abgabegrund 61** and marks
each period as creditable or not.

## The requirement (Verfahrensbeschreibung §3.12)

The employer may only trigger a request with Abgabegrund 41 if **all** of the following hold:

1. The employer has a **sick note for the current AU** (an eAU counts as certified).
2. **In the 6 months before the current AU started**, there is **at least one certified** potential
   prior illness on file.
3. The **cumulative days of all potential prior illnesses in the last 12 months plus the current AU**
   are **≥ 30 days** at the time of reporting.
   - If the system stores absences with an **open end**, evaluate the current AU as lasting until
     **today + 7 days**.

What to include in the request:

- **As many potential prior illnesses as possible**, and at least one.
- **Chain backwards:** include each earlier AU as long as the gap between it and the next one is
  **no more than 6 months**. Go back to the first AU that has no predecessor within 6 months. There is
  no time limit on this chain for the request; the insurer's reply looks back at most 12 months.
- **Exclude short uncertified sick leave** (self-reported days with no doctor's note), unless a
  certified AU follows seamlessly.
- List the periods **chronologically, newest first** (§3.12.7).
- The transmitted periods don't themselves need to add up to 30 days. Only the system-side check
  does.

Exclusions: no request for **privately insured** or **marginally employed** (*geringfügig*) employees.

## The 4 testable criteria (with ITSG UUIDs)

| UUID | Criterion (translated) |
|---|---|
| `f41c7278-b5a5-4ec3-b321-39bca5c3aeeb` | The system ensures a report with Abgabegrund "41" can only be generated if **both the current AU and at least one previous AU are certified**. |
| `0cefe80e-4fd9-41e1-be4f-3ae1ecbde646` | The system ensures a report with Abgabegrund "41" can only be generated if **no more than 6 months lie between the start of the current AU and the end of the last certified AU**. |
| `aade0289-e8f9-4e12-9c49-464cf6cd0789` **("Daumenkriterium")** | AU periods before the current AU are **only included** in the "41" report if **no more than 6 months lie between the start of each AU period and the end of the previous one**. |
| `9c8c9b58-4d0f-4066-98ac-973095418d63` | The system ensures a report with Abgabegrund "41" can only be generated if the **prior-illness periods on file plus the current AU total at least 30 days**. |

**Expected result:** a test case that produces a correct prior-illness request in the payroll
program, which is then transmitted to the responsible health insurer.

> Note the two kinds of criteria: **gate checks** ("may only be generated if…") need *negative*
> test cases as well, where the software must refuse to produce a 41. **Content checks** ("only
> included if…") can be verified on the output file.

## Test setup

**AU periods on file:**

| # | From | To | Days | Note |
|---|---|---|---|---|
| a | 14.07.2025 | 15.07.2025 | 2 | |
| b | 01.10.2025 | 17.10.2025 | 17 | |
| c | 01.12.2025 | 03.12.2025 | 3 | |
| d | 01.03.2026 | 03.03.2026 | 3 | The employer has a **paper** note only (no eAU), so the insurer doesn't have it yet |
| **current** | **11.03.2026** | initially 20.03.2026, finally **10.04.2026** | | |

Employment ends **31.03.2026**.

**Checking the criteria against this data:**

- Current AU certified, plus prior AUs certified ✔
- Gap from d (03.03.26) to the current AU (11.03.26) is 8 days, well under 6 months ✔
- Chain: a→b (2.5 months), b→c (1.5 months), c→d (3 months), d→current (8 days). All gaps are ≤ 6
  months, so **all 4 periods go into the DBVO** ✔
- 30-day rule: 2 + 17 + 3 + 3 = 25 prior days, plus the current AU (11.03–20.03 = 10 days) =
  **35 ≥ 30** ✔. Without the current AU it would be only 25 days, so the current AU is what tips it
  over.

## Expected message sequence

| Step | From | Abgabegrund | Cancel? | DSID | DSID-UR | REF-ID | AZVU | 12-month period from | End EEL | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | AG | **41** prior-illness request | N | `11111111-2222-AAAA-EEEE-111111111111` | | | 1234-5678-007 | | | |
| 2 | KK | **61** reply: period d marked **"4 = AU not on file"** | N | | | `11111111-…-111111111111` | 1234-5678-007 | 14.07.2025 | | |
| 3 | AG | **01** pay certificate (sick pay ends **30.03.2026**) | N | `AAAAAAAA-EEEE-2222-4444-BBBBBBBBBBBB` | | | 1234-5678-007 | | | |
| 4 | KK | **61** corrected reply, sent proactively after the employee hands in the paper note for d | N | | | `11111111-…-111111111111` | 1234-5678-007 | 14.07.2025 | | |
| 5 | AG | **88** cancellation of step 3 | **J** | `BBBBBBBB-8888-5555-CCCC-121212121212` | `AAAAAAAA-…-BBBBBBBBBBBB` | | 1234-5678-007 | | | |
| 6 | AG | **01** new pay certificate (sick pay now ends **27.03.2026**) | N | `11112222-FFFF-3333-5555-CCCCCCCCCCCC` | | | 1234-5678-007 | | | |
| 7 | KK | **62** end of income replacement benefit | N | | | `11112222-…-CCCCCCCCCCCC` | 1234-5678-007 | | **31.03.2026** | 99 |

**Why the sick-pay end moves.** EFZ = 42 days minus creditable prior days.
- Insurer knows a + b + c (22 days): 42 − 22 = 20 days → 11.03 + 19 = **30.03.2026**
- After d is confirmed (25 days): 42 − 25 = 17 days → **27.03.2026**

(This assumes all prior periods are the same illness, which the 12-month period starting 14.07.2025
implies.)

The benefit ends on 31.03.2026, when the employment ends, so the reason is "99".

## Things we noticed

- The Hinweise doc says "die AU vom **01.03.2025** bis 03.03.2026". That's a typo for
  **01.03.2026**.
- **The KK replies (61, 62) are given input, not output.** The software under test doesn't produce
  them; it has to handle them. The IDs only show the vendor where its DSID reappears in the reply
  (as REF-ID). ITSG, evening of 26.10.2026; see [11-demo-feedback-itsg.md](11-demo-feedback-itsg.md).
- ITSG's own verdict on this document: hard to understand, "forget about it… automatic test cases
  might be better than that."
- The sample file `TEEL0-Test1-DBVO` covers **step 1 only** (the AG 41 request). See
  [05-data-format.md](05-data-format.md).
- The sample file's creation timestamp is **14.02.2026**, before the AU it reports (11.03.2026).
  This is presumably a test-environment artefact, but it's the kind of plausibility check a
  validator could flag.
