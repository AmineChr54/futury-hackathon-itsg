# Problem and Solution at a Glance

Background: [01-challenge-overview.md](01-challenge-overview.md), [07-itsg-meeting-notes.md](07-itsg-meeting-notes.md),
[06-solution-concept.md](06-solution-concept.md).

## The problem

Every payroll program in Germany (~100 of them) has to be certified by ITSG every year before it may
send reports to the social insurers. ITSG checks each one against **~3,000 test cases that are
written and maintained by hand** from **~1,000 pages of German specification**. The specs change
every half year, often arriving in December and taking effect on 1 January. The tolerance for error
is **zero**: one wrong field or one wrong cent, and the software is off the market.

### How it works today

```mermaid
flowchart LR
    GOV["Authorities publish specs<br/>(PDF, German, ~1,000 pages)<br/>often in December"]
    READ["ITSG experts read the specs<br/>and 'think about it'"]
    TC["~600-page sheet<br/>~3,000 test cases<br/>written by hand"]
    VEND["Vendor enters each scenario<br/>in their payroll software<br/>(SAP, DATEV, Lexware … ×100)"]
    MSG["Software produces<br/>DTA data files"]
    DEV["ITSG testing device<br/>compares with known solutions<br/>(monthly, automated)"]
    AUDIT["Yearly on-site inspection<br/>'show me in your program…'"]
    CERT{"All cases pass?"}
    OK["Certified:<br/>may transmit for the year"]
    NO["Not certified:<br/>software offline"]

    GOV --> READ --> TC --> VEND --> MSG --> DEV --> CERT
    TC --> AUDIT --> CERT
    CERT -- yes --> OK
    CERT -- "no (even 1 error)" --> NO

    classDef pain fill:#fde2e2,stroke:#c0392b,color:#000;
    class READ,TC,AUDIT pain;
```

Red marks the manual steps that hurt most.

### Where it hurts

```mermaid
flowchart TD
    P1["Manual test design<br/>no method for turning a spec clause into a test"]
    P2["Spec changes every half year<br/>find and adapt affected cases by hand"]
    P3["Late specs<br/>December → 1 January<br/>weeks, not months"]
    P4["Zero tolerance<br/>1 cent wrong = software off the market<br/>800M messages a year"]
    P5["Gaming risk<br/>vendors can fit messages<br/>to the known solutions"]
    P6["~100 different programs<br/>UI automation not realistic"]

    P1 --> CORE(("Test creation and maintenance<br/>is the bottleneck"))
    P2 --> CORE
    P3 --> CORE
    P4 --> CORE
    P5 --> CORE
    P6 --> CORE
```

## The solution: an AI review assistant

**Core idea: use the LLM where understanding is needed, and deterministic code where proof is
needed.** The AI reads the specs and drafts rules, each with a citation. A person approves each rule
once. From then on, code generates the test cases, computes the expected results and checks the
vendor's output. The LLM never decides whether something passes.

### End-to-end pipeline

```mermaid
flowchart LR
    subgraph IN["1 · Specs"]
        S["Verfahrensbeschreibung<br/>GG · Circulars · Beispielpapier"]
    end

    subgraph AI["2 · AI extraction"]
        X1["LLM extraction A"]
        X2["LLM extraction B<br/>(other model or prompt)"]
        CMP{"A = B?"}
    end

    subgraph HUMAN["3 · Human sign-off"]
        H["Examiner approves rule<br/>once, not 3,000 cases"]
    end

    subgraph CAT["4 · Criteria catalogue"]
        C["Rule · §-citation · UUID<br/>gate / content / format<br/>executable check"]
    end

    subgraph GEN["5 · Test generation"]
        G["Scenarios: positive,<br/>negative, boundary"]
        O["Deterministic oracle<br/>computes expected records"]
    end

    subgraph RUN["6 · Vendor"]
        V["Runs cases in payroll SW<br/>→ DTA files"]
    end

    subgraph VAL["7 · Validation"]
        P["Fixed-width parser"]
        R["Rule engine +<br/>expected vs. actual diff"]
    end

    subgraph OUT["8 · Report"]
        REP["Traceable report<br/>criterion → test → field →<br/>verdict → § citation<br/>+ product and version ID"]
    end

    S --> X1 & X2 --> CMP
    CMP -- yes --> H
    CMP -- "no: flag" --> H
    H --> C --> G --> O --> V --> P --> R --> REP
    O -. expected .-> R
```

### Killer feature 1: spec change → updated test cases

When a new spec version arrives, we don't start over. We work out what changed, and only that goes
to a person.

```mermaid
flowchart LR
    OLD["Spec v13.3"]
    NEW["Spec v13.4"]
    DIFF["Diff per section<br/>+ official change log<br/>(Änderungsübersicht)"]
    SEC["Changed sections<br/>e.g. §3.12 DBVO,<br/>§3.1.18 Abgabegrund"]
    CRIT["Affected criteria"]
    TESTS["Affected test cases<br/>(out of ~3,000)"]
    REGEN["Re-extract rules →<br/>human reviews delta only →<br/>regenerate cases"]
    READY["Updated test suite<br/>in hours, not weeks"]

    OLD --> DIFF
    NEW --> DIFF
    DIFF --> SEC --> CRIT --> TESTS --> REGEN --> READY
```

The government doesn't always ship a change log, so both sources run, and every change gets a
source badge:

```mermaid
flowchart LR
    LOG["Change log<br/>(parsed by code)"] --> REC{"Reconcile<br/>per § section"}
    DIF["Section diff<br/>v13.3 vs v13.4"] --> REC
    REC --> A["in log + diff<br/>confirmed"]
    REC --> B["diff only<br/>NOT in change log<br/>shown first"]
    REC --> C["log only<br/>no text change<br/>check tables/annex"]
    classDef bad fill:#fde2e2,stroke:#c0392b,color:#000;
    class B bad;
```

### Next audit scope: failed + changed + new

ITSG doesn't re-check all ~3,000 criteria every year (ITSG engineer, 26.10.2026).

```mermaid
flowchart LR
    PREV["Last report<br/>e.g. 2 of 3,000 failed"] --> SCOPE["Next audit scope"]
    CHG["Criteria touched<br/>by spec changes"] --> SCOPE
    NEWC["New criteria"] --> SCOPE
    SCOPE --> VISIT["On-site checklist"] --> REP["Sealed report<br/>pass/fail per criterion"]
    REP -. failed items carry over .-> PREV
```

### Killer feature 2: fresh variants against gaming

Each criterion is a **template**, not a fixed answer. Every test cycle, or every vendor, gets new
concrete data that still sits on the boundaries. The expected result is recomputed each time.

```mermaid
flowchart TD
    T["Criterion template<br/>'prior AUs included only if gap ≤ 6 months'"]
    T --> V1["Cycle Jan<br/>gap = 5 months 30 days<br/>expect: included"]
    T --> V2["Cycle Feb<br/>gap = 6 months 1 day<br/>expect: excluded"]
    T --> V3["Vendor X<br/>total = 29 days<br/>expect: no request 41"]
    T --> V4["Vendor Y<br/>total = 30 days, open-ended AU<br/>expect: request 41"]
    V1 & V2 & V3 & V4 --> ORA["Oracle computes expected<br/>result for each variant"]
    ORA --> NOFIT["Vendors can't fit outputs<br/>to answers they've never seen"]
```

### Worked example: the prior-illness request (DBVO, Abgabegrund 41)

This is the one case ITSG worked out for us ([04-example-test-case-dbvo.md](04-example-test-case-dbvo.md)).
It shows how a single spec section becomes a gate check and content checks, and then a verdict on
the real sample file.

```mermaid
flowchart TD
    SPEC["§3.12 DBVO<br/>Prior illness periods"]
    SPEC --> G1{"Current AU<br/>certified?"}
    G1 -- no --> NOREQ["Software must NOT<br/>produce request 41"]
    G1 -- yes --> G2{"Certified AU in the<br/>6 months before?"}
    G2 -- no --> NOREQ
    G2 -- yes --> G3{"Prior days + current<br/>≥ 30 days?<br/>(open end = today + 7)"}
    G3 -- no --> NOREQ
    G3 -- yes --> REQ["Produce DSLW, Abgabegrund 41<br/>+ DBVO block"]
    REQ --> C1["All chained AUs<br/>(gaps ≤ 6 months)"]
    REQ --> C2["Newest first"]
    REQ --> C3["Insurer-only fields<br/>at default value"]
    C1 & C2 & C3 --> FILE["Check TEEL0-Test1-DBVO:<br/>4 periods, newest first,<br/>2+17+3+3+10 = 35 days<br/>✔ PASS"]
```

### How a test flows between the parties

```mermaid
sequenceDiagram
    participant ITSG as ITSG examiner
    participant AI as AI review assistant
    participant V as Vendor (payroll SW)
    participant KK as Health insurer (simulated)

    ITSG->>AI: New spec version
    AI->>AI: Diff, extract rules (A/B), flag conflicts
    AI->>ITSG: Changed rules for sign-off
    ITSG->>AI: Approve
    AI->>V: Fresh test cases (scenario data only)
    V->>V: Enter scenarios, run payroll
    V->>AI: DTA files (e.g. Abgabegrund 41)
    AI->>KK: Simulated reply (61: period not on file)
    KK-->>V: Reply message
    V->>AI: Follow-up messages (01, 88, 01)
    AI->>AI: Parse, check rules, diff with oracle
    AI->>ITSG: Traceable report + coverage matrix
    ITSG->>V: Certify or reject
```

## Why this fits what ITSG asked for

| ITSG objective | How we cover it |
|---|---|
| Identify requirements | LLM extraction from the specs, two independent runs, with citations |
| Translate into testable criteria | Criteria catalogue: gate, content and format checks, executable |
| Generate test cases with expected results | Generator plus deterministic oracle; positive, negative and boundary cases; fresh variants |
| Create a traceable test record | Every verdict linked to criterion, test case, field and § citation |
| Test and compare | Fixed-width parser, rule engine, and field-level diff of expected vs. actual |
| Deliver comprehensible reports | Report and coverage view; the LLM explains failures in plain language |
| *(From the meeting)* Spec changes | Diff → affected criteria → affected tests → regenerated tests |
| *(From the meeting)* Zero tolerance | LLM never decides a pass; dual extraction; human sign-off per rule |
| *(From the meeting)* Gaming | Fresh variants each cycle |
