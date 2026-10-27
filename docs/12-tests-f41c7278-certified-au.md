# Minimal Tests for Criterion `f41c7278`: Both AUs Must Be Certified

One criterion, the smallest test set that still covers it. Following ITSG's steer ("for each rule,
one test case would be enough, for the first step"), every case here is one a vendor engineer can
type into their payroll program in a few minutes.

Sources: `DTA-EEL-Beispiel_Vorerkrankung.docx` (the criterion), Verfahrensbeschreibung DTA EEL v13.4,
§3.12 (the rule it comes from). See [04-example-test-case-dbvo.md](04-example-test-case-dbvo.md) for
the full reference case.

## The criterion

| | |
|---|---|
| **UUID** | `f41c7278-b5a5-4ec3-b321-39bca5c3aeeb` |
| **Original** | *Es ist systemseitig sichergestellt, dass eine Meldung mit Abgabegrund "41" nur erzeugt werden kann, wenn sowohl die aktuelle Arbeitsunfähigkeit als auch mindestens eine vorherige Arbeitsunfähigkeit attestiert sind.* |
| **Plain English** | The payroll program must make it **impossible** to create a prior-illness request (Abgabegrund 41) unless **(A)** the current AU is certified **and (B)** at least one earlier AU is certified. |
| **Kind** | Gate check ("can only be generated if…"). It needs a positive case **and** negative cases where the program must refuse. |

**What counts as "certified" (§3.12):**

- a paper sick note (*AU-Bescheinigung*) the employer holds: *"dem Arbeitgeber … eine Arbeitsunfähigkeitsbescheinigung vorliegt"*
- an eAU record: *"Als „bescheinigte" Arbeitsunfähigkeitszeiten gelten auch die im elektronischen Arbeitsunfähigkeitsverfahren übermittelten Datensätze."*
- **not** a self-reported sick day with no note (*Kurz-AU*) under the Entgeltfortzahlungsgesetz: *"Sofern der Arbeitnehmer … sich ohne Arbeitsunfähigkeitsbescheinigung krankgemeldet hat, kann die Krankenkasse keine Beurteilung … vornehmen"*

## Why three cases are enough

The gate is `A AND B`. Covering each condition so that it alone flips the result (MC/DC) takes
exactly three cases:

| Case | A: current AU certified | B: a prior AU certified | Expected |
|---|---|---|---|
| **T1** | ✔ (eAU) | ✔ (**paper**) | 41 is created |
| **T2** | ✘ | ✔ (eAU) | **no** 41 |
| **T3** | ✔ (eAU) | ✘ (Kurz-AU) | **no** 41 |

T1 → T2 shows that A matters on its own, and T1 → T3 shows that B does. T1 also covers **both
certificate sources** at once: eAU for the current AU, paper for the prior one. A program that only
checks the eAU flag fails T1, which is the trap the reference case sets with period d.

### Keeping the other three gates out of the way

A negative case is only useful if this criterion is the **only** reason for the refusal. So all three
cases share one base setup that passes the other criteria by a wide margin:

| Other criterion | How the base setup passes it |
|---|---|
| `0cefe80e` (≤ 6 months since the last certified AU) | The prior AU ends 13.02.2026 and the current one starts 02.03.2026, **17 days** later |
| `9c8c9b58` (≥ 30 days together) | The current AU alone is **40 days**, so the gate passes whether or not the prior days count |
| `aade0289` (chain, content check) | Only one prior period, so there's nothing to chain |
| Scope (§3.12: not PKV, not marginal) | GKV member, employment subject to social insurance (*versicherungspflichtig*) |

The current AU has a **fixed end date** (10.04.2026), so the open-end rule (today + 7 days) never
applies. Dates are chosen to avoid weekends at the edges: 02.02 is a Monday, 13.02 a Friday, 02.03
a Monday and 10.04 a Friday.

**One overlap we can't remove:** in T3 there is no certified prior AU at all, so `0cefe80e`
("the last certified AU") has nothing to measure from and fails too. Both criteria say "no 41"
here, so the expected result is the same. When T3 fails, though, the report should name both
criteria.

## Base setup (shared)

- **Employer:** the vendor's standard EEL test company
- **Employee:** GKV member, employed and subject to social insurance, not marginally employed,
  employment ongoing (no end date)
- **Reporting date (*Tagesdatum*):** 23.03.2026 (Monday)
- **Current AU:** 02.03.2026 – 10.04.2026 (40 days), fixed end

## T1: Both certified → 41 is created

**Input (as a vendor engineer would enter it):**

| # | From | To | Days | Evidence |
|---|---|---|---|---|
| prior | 02.02.2026 | 13.02.2026 | 12 | **Paper** sick note held by the employer, no eAU |
| current | 02.03.2026 | 10.04.2026 | 40 | **eAU**, retrieved from the insurer |

**Action:** on 23.03.2026, create the prior-illness request for the current AU.

**Expected:** the program creates exactly **one DSLW record with Abgabegrund 41** and a DBVO block:

| Field | Expected value | Why |
|---|---|---|
| 3.1.18 Abgabegrund | `41` | prior-illness request |
| 3.12.1 GRUNDAV | `1` | AU due to illness |
| 3.12.2 AU-AB-AG | `20260302` | start of the current AU |
| 3.12.3 AU-AB-SV | `00000000` | insurer field: default value (*Grundstellung*) for the employer |
| 3.12.4 KZ-AK-AU | `0` | insurer field: default value for the employer |
| 3.12.5 12-MONATSFRIST-AB | `00000000` | insurer field: default value for the employer |
| 3.12.6 ANZAHL-AU | `01` | one prior period |
| 3.12.7 BEGINN-AU-01 | `20260202` | |
| 3.12.8 ENDE-AU-01 | `20260213` | |
| 3.12.9–3.12.14 | default values | insurer fields |

**Fails if:** no 41 is created (the program ignores paper notes), or the prior period is missing from
the DBVO.

## T2: Current AU not certified → no 41

**Input:** the same dates as T1, but the evidence changes:

| # | From | To | Evidence |
|---|---|---|---|
| prior | 02.02.2026 | 13.02.2026 | **eAU** |
| current | 02.03.2026 | 10.04.2026 | **None.** The employee called in sick and gave the expected end date by phone. The eAU retrieval found no record, and there's no paper note. |

**Action:** on 23.03.2026, try to create the prior-illness request.

**Expected:**

- **No** record with Abgabegrund 41 is created or queued for sending.
- The program tells the user why (e.g. "no sick note for the current AU").
- "Systemseitig sichergestellt" means the program has to **block** this. A warning the user can
  click past doesn't count.

**Evidence the vendor returns:** a screenshot or log of the refusal, plus the outgoing file for the
day showing no 41 for this employee.

## T3: No certified prior AU → no 41

**Input:**

| # | From | To | Days | Evidence |
|---|---|---|---|---|
| prior | 10.02.2026 | 12.02.2026 | 3 | **None:** short sick leave the employee reported themselves (*Kurz-AU*), with no certified AU following straight after |
| current | 02.03.2026 | 10.04.2026 | 40 | **eAU** |

**Action:** on 23.03.2026, try to create the prior-illness request.

**Expected:** the same as T2 (no 41, a reason shown, a hard block). The program must **not** treat the
3 Kurz-AU days as a certified prior illness.

**Fails if:** a 41 is created, especially one with the Kurz-AU period 10.02–12.02.2026 in the DBVO.

## Machine-readable input (proposal)

The same three cases in the demo's proposed import format `itsg-eel-testinput/0.1` (see
[09-demo-design.md](09-demo-design.md)). Vendors don't offer an import like this today, so it would
need a change to the specification.

```json
[
  {
    "schema": "itsg-eel-testinput/0.1", "test_case": "T1", "rule": "f41c7278-b5a5-4ec3-b321-39bca5c3aeeb",
    "reference_date": "2026-03-23",
    "employee": { "health_insurance": "GKV", "marginal_employment": false },
    "absences": [ { "from": "2026-02-02", "to": "2026-02-13", "certified": true, "evidence": "paper" } ],
    "current_au": { "from": "2026-03-02", "to": "2026-04-10", "certified": true, "evidence": "eAU" },
    "employment_end": null,
    "expected": { "message": "41", "dbvo": { "GRUNDAV": "1", "AU-AB-AG": "20260302", "ANZAHL-AU": "01",
      "periods": [ { "BEGINN-AU": "20260202", "ENDE-AU": "20260213" } ] } }
  },
  {
    "schema": "itsg-eel-testinput/0.1", "test_case": "T2", "rule": "f41c7278-b5a5-4ec3-b321-39bca5c3aeeb",
    "reference_date": "2026-03-23",
    "employee": { "health_insurance": "GKV", "marginal_employment": false },
    "absences": [ { "from": "2026-02-02", "to": "2026-02-13", "certified": true, "evidence": "eAU" } ],
    "current_au": { "from": "2026-03-02", "to": "2026-04-10", "certified": false, "evidence": "none" },
    "employment_end": null,
    "expected": { "message": null, "dbvo": null }
  },
  {
    "schema": "itsg-eel-testinput/0.1", "test_case": "T3", "rule": "f41c7278-b5a5-4ec3-b321-39bca5c3aeeb",
    "reference_date": "2026-03-23",
    "employee": { "health_insurance": "GKV", "marginal_employment": false },
    "absences": [ { "from": "2026-02-10", "to": "2026-02-12", "certified": false, "evidence": "none" } ],
    "current_au": { "from": "2026-03-02", "to": "2026-04-10", "certified": true, "evidence": "eAU" },
    "employment_end": null,
    "expected": { "message": null, "dbvo": null }
  }
]
```

## Deliberately left out

Each of these belongs to another criterion, or adds manual effort for little extra coverage:

- **A Kurz-AU followed straight away by a certified AU** (it counts as a prior illness then). That
  is a question of what goes into the request, so it belongs to `aade0289` and the Kurz-AU rule.
- **A mix of certified and uncertified priors.** B is already true as soon as one certified prior
  exists, so the mix tests which periods are *listed*, again `aade0289`.
- **The sick note arriving later** (T2 followed by "the eAU now arrives → 41 is allowed"). A good
  follow-up once input is automated, not needed for minimal coverage.
- **PKV or marginal employment.** That's the scope rule, not this criterion.

## Open questions for ITSG

1. Is a **warning the user can override** acceptable for "systemseitig sichergestellt", or must it
   be a hard block? These tests assume a hard block.
2. Does a **paper note that has been recorded** but not sent to the insurer count as "attestiert"
   for the employer's gate? §3.12 and the reference case (period d) suggest yes. T1 relies on that.
3. For the negative cases, what evidence do vendors usually send: a screenshot, a log, or just the
   empty outgoing file?
