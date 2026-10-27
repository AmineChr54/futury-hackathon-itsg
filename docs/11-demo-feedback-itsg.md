# Demo Feedback from ITSG (26.10.2026, evening)

Two back-to-back sessions where we walked an ITSG engineer through `demo/index.html`:

- **18:31–18:47:** ITSG showed us their material (the test-case description, a DTA file, the GKV
  data-exchange site), then we walked through the pipeline.
- **18:50–19:15:** how vendors actually run the tests, then feedback screen by screen.

The transcripts are rough. Both rooms were recorded on one microphone, so who said what is
inferred from context. **Gerhard** (also transcribed as "Gerald", "Geralt", "Gerhardt") is the ITSG
domain expert who works with the test data daily. He wasn't in these sessions. **Gregor** from ITSG
is on the jury.

> **Bottom line:** they liked the change detection and the click back into the spec. What they
> couldn't follow: function IDs, hashes, guards and raw bytes. They want **readable rules a human
> approves**, **one test case per rule to start**, a **pass/fail report per vendor**, and our best
> idea for **getting test input into vendor software automatically**, because manual entry is the
> real bottleneck.

---

## What we learned about the process

### Vendors enter every test case by hand

- A vendor's engineer **simulates a company** in their own payroll software and types the input
  manually, e.g. "employee is ill from 15 to 21 January". It's the real product, so there is no
  automatic input.
- So **every test case costs manual work**. 20 test cases per criterion across ~4,000 criteria is
  impossible: "they won't be able to finish this".
- Automatic input across ~100 programs isn't possible today. Each has its own platform, UI, access
  and security, and there's no standard way to enter data. An SAP engineer and a Lexware engineer
  will implement the same test case differently.
- **Ideas discussed:**
  - **Start with SAP.** Many of ITSG's customers use it, so it's the natural priority. ("The idea
    is not bad, and you can go to SAP and sell it, maybe.")
  - **Define a JSON input interface.** Vendors would have to implement an import for test input,
    and output stays the standard DTA file. This would be **a change to the specification**,
    because vendors currently aren't required to accept test input.
- ITSG's steer: **"we shouldn't do many tests, we should work on the idea of how to do this
  automatically, the input."** Until input is automated, keep the number of test cases low. Once
  it is automated, "more is better".

### How test cases are made today

- The baseline example is
  `hackathon-files/ITSG - The Challenge Sponsor/Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx`
  ("Hinweise zur Testkonstellation EEL-Anwendungsprogramme"). It's a description **in human words**:
  - four previous AU periods are in the system (14.07.2025–15.07.2025, 01.10.–17.10.2025,
    01.12.–03.12.2025, and 01.03.–03.03.2026 on paper only, no eAU);
  - the current AU starts 11.03.2026, first until 20.03.2026, finally until 10.04.2026;
  - employment ends 31.03.2026.
- **The expected dataset is made by hand.** Sometimes the case adds details such as "earns €3,000,
  has two children / no children", which change the expected output values.
- Test cases come from **people talking to each other**: "somebody has the idea, we have to test
  this". That description goes to the vendor's engineer, who builds the company with that
  employee. "There's nothing more we do."
- **Nothing checks that a test case fits the spec.** The computer produces its output, ITSG writes
  its expected output "from thinking about it", and the two are compared. Today they "generate the
  test, give it to the software developer and wait to see if they shout that a test is wrong.
  This is not very good, I have to admit."
- **Worked example (§3.12, the 6-month rule):** the law says the employer may not send a prior-illness
  request if more than six months lie between the current and the earlier illness. Test case: an
  illness period here, the current illness there, more than six months apart → **expected: no
  message is created**.
- **Maintenance:** one person owns the document and updates it every year, e.g. moving the illness
  dates to the new year.
- ITSG on their own document: "Everything is technical words. There's nothing to get from this.
  I would say forget about it… If you have a better solution, for example automatic test cases,
  … all of them might be better than that."

### The AG ⇄ KK dialogue (table on page 2 of the example)

- The table shows the **exchange between the employer (AG) and the health insurer (KK)**:
  - AG sends **Abgabegrund 41** (prior-illness request) with its own DSID.
  - KK answers with **Abgabegrund 61**. Its **REF-ID is the DSID of the AG's message**, and it
    carries the **Beginn 12-Monatsfrist** (14.07.2025).
  - Later rows show 01 (EEL), 88 (cancellation, Stornierung = J, with DSID-UR pointing to the
    cancelled message) and the KK's 62 (EEL end 31.03.2026, reason 99).
- **The KK answer is given, not produced by the software under test.** The vendor's software has to
  *handle* the answer it receives.
- Example from ITSG: SAP sells its software to Mercedes-Benz. A Mercedes worker gets ill, so ITSG
  expects SAP-at-Mercedes to create the 41 message. Mercedes gets the KK answer back and must deal
  with it.
- The IDs in the table are only examples, showing the vendor where an ID they sent reappears in
  the answer.
- In our pipeline this belongs to **"generate tests"**.

### Comparison already exists, but ours may replace it

- Vendors upload their DTA file to **ITSG's existing comparator**, built over three decades by
  Gerhard's team, which parses the fields and compares them with the expected solution. "We don't
  need to reimplement it."
- They first said we could remove our comparison, then corrected that: **"Leave it in. We can
  replace our software, which creates a solution, with yours, if it's better."**
- Reading a difference today needs **deep technical knowledge**. You take the red-highlighted part,
  look the record and field up in the dictionary, and work out what it means (e.g. find the
  submission reason, which should be 41). "If it's automatically created it could be very helpful,
  **but there mustn't be any errors.**"

### More documentation exists than we were given

- ITSG showed us the **GKV data-exchange site** (*GKV-Datenaustausch*), section
  *Entgeltersatzleistungen*. It has **many more documents than the challenge SharePoint**.
- One of them is a **data dictionary**: every short form (VOSZ, DSKO…) with its record, position in
  the file, type (alphanumeric or integer), and whether it's mandatory. It's "a lookup table" if we
  come across field names, and we can summarise it for the AI.
- The DTA file is the same format for all ~100 programs, because every health insurer has to parse
  it.

### Start from the government PDF, and check the old tests

- ITSG asked whether we start from **their prepared document** (with GUIDs and split cases) or from
  the **original 600-page government PDF**. They prefer the **original law documents**, "from
  scratch".
- **New idea: a baseline check.** The ~4,000 test scenarios grew over 30 years. Laws sometimes
  *remove* rules or matching criteria, so the catalogue may still contain **obsolete tests**, and
  may be **missing** some. ITSG would like an **initial check of the existing test scenarios against
  the current specification**.
- The 4,000 test scenarios aren't in the department of the engineer we spoke to. **Gerhard knows
  where they are**, and they'll ask him.

### Terminology

- What we call **rules**, ITSG calls **questions**, criteria or requirements: "it's just
  terminology". Flow: specification → rules (criteria) → test cases.

---

## Feedback screen by screen

| Demo view | What they said | Verdict |
|---|---|---|
| Pipeline overview | Followed it: new spec → detect changes → extract rules → human approves → generate tests → publish to vendors → vendors upload DTA → automatic comparison → certification | ✓ keep |
| ITSG / vendor role switch | Matches reality: ITSG has a view, each vendor's engineers have a view | ✓ keep |
| **2 · Change impact** | The AI summary of each change (e.g. §3.12 "mindestens" → "mehr als 6 Monate") was "pretty cool". Clicking back to the original spec: "This is great". The examiner sees what the AI saw and can confirm it | ✓ keep, strongest screen |
| **3 · Rule extraction** | They saw rule IDs (3.12-A, 3.12-B…) but **not the rule text**: "You can't see the text. That would be helpful." The hashes, "function picked by the model" and the five guards were not understandable: "this is in detail on the details", ask Gerhard | ✕ rework |
| **4 · Function library** | "The AI should return a function ID… do you have a function library?" ITSG: **no**. "Okay, we can remove this." | ✕ hide from main flow |
| **5 · Test cases** | "Cool test cases", and the AU timelines covering possible cases were understood. But **12 cases for one rule is "a bit much"** while input is manual. **"For each rule, one test case would be enough. For the first step."** | ~ reduce default |
| **7 · Compare output** | Keep it; it may replace their comparator. The byte view's red highlights are only readable by experts | ~ add explanations |
| **9 · Report** | Wants: how many passed, how many failed, every test case ("everything passes except this one"), **printable or JSON, per customer** | ~ extend |

---

## Changes to make in the demo

Ordered by how directly ITSG asked for them. **Status (26.10.2026, night):** built in
`demo/index.html`, except the two items left open below. See
[09-demo-design.md](09-demo-design.md) and [`demo/README.md`](../demo/README.md).

### 1. Readable rules between spec and test cases (rule extraction)

- [x] Make the **rule text in plain language** the main content of each rule (DE and EN), e.g.
      *"The employer may only send request 41 if the gap between the end of the last certified AU
      and the start of the current one is not more than 6 months."*
- [x] Show **spec quote → readable rule → its test case(s)** as one visible chain, so the examiner
      can "explain to the software what it should do".
- [x] Examiner actions on the **text itself**: **approve, edit, decline**. The current approve/reject
      only works on numeric parameters.
- [x] Move function ID, SHA-256, the guard list and run A / run B into a collapsed
      **"Technical details / why you can trust this"** section. They stay available for the jury's
      trust story, but they aren't the first thing an examiner reads.
- [x] Use ITSG's words in labels: "rule (criterion)", or "Prüfkriterium".

### 2. Function library out of the main pipeline

- [x] Remove "4 · Function library" from the numbered pipeline steps. ITSG doesn't have one and
      doesn't think in these terms.
- [x] Keep it reachable under **Evidence** (next to Coverage and Audit trail) as proof that
      expected values are computed, not generated.
- **Open:** our trust architecture still relies on pre-written functions (see
  [09-demo-design.md](09-demo-design.md)). Hiding them in the UI is fine; dropping them from the
  design is not decided. We need a one-sentence explanation an examiner understands, e.g. *"the
  expected result is calculated by tested code, not written by the AI"*.

### 3. One test case per rule by default (test cases)

- [x] Default: **one representative test case per rule**, with a control to **expand to the full
      boundary set** (positive, negative, edges). Label it with ITSG's reasoning: *manual entry
      today → few cases; automatic input → as many as you like.*
- [x] Show each test case like ITSG's own: a **description in human words** ("The following AU
      periods are stored… the current AU starts…"), plus the expected dataset next to it.
- [x] Every test case links to **its rule text and spec quote**, which closes the "how do we know
      the test case fits the spec?" gap ITSG admitted to.
- [x] Add the §3.12 **"> 6 months → no message created"** case as an explicit negative example. It
      is the exact example ITSG used.
- [ ] Optional scenario details that change expected values (salary, number of children) should
      be visible on the case. *Not yet: none of the demo's EEL rules depends on them.*

### 4. Automatic test input: make it the headline idea

- [x] Add a step or panel **"Automatic input (proposal)"**: export each test case as a **JSON
      input file** the vendor's software imports. The output stays the standard DTA file.
- [x] Frame it honestly: it **requires a specification change** (vendors must offer an import
      interface). **Pilot with SAP first.**
- [x] On the vendor side, show "import test package" next to "enter manually", to make the time
      saved visible.

### 5. Explain differences instead of showing bytes (compare output)

- [x] For every red difference, add a **plain-language line**: record, field name, position,
      expected vs actual, and the § it comes from. In the screenshot from this session, the DBVO
      block has a different period count and an extra period 01.11.2024–05.11.2024. That should
      read like *"ANZAHL-AU: expected 4, got 5 — the period 01.11.2024–05.11.2024 should not be
      included because the gap is more than 6 months (§3.12)."*
- [ ] Decode fields using the **GKV data dictionary** (name, position, type, mandatory), so nobody
      has to look them up by hand. *Partly: meanings and types come from the record tables we
      have; the GKV dictionary (with mandatory flags) still needs to be downloaded.*
- [x] Keep the byte view, but as a secondary tab.
- [x] Vendor uploads its DTA → **comparison starts automatically** (no extra click).

### 6. Report: pass/fail per vendor (report & next scope)

- [x] Summary per vendor: **N passed, M failed**, and the failing test cases listed by name and
      rule ("everything passes except EEL-3.12-007").
- [x] Full list of every test case with its result.
- [x] **Print view** and **JSON export, per customer/vendor**.
- [x] Keep the "next audit scope = failed + changed + new" logic from the earlier meeting.

### 7. Start from the original government PDF (inputs & archive)

- [x] Make it obvious that the input is the **raw government PDF** (Verfahrensbeschreibung, from
      GKV-Datenaustausch), not ITSG's prepared document. They asked this directly.
- [x] Mention that the GKV site holds more documents (data dictionary, record descriptions) that we
      can pull in.

### 8. New feature: baseline check of the existing catalogue

- [x] Add a view (or a mode in Coverage): **check the existing test catalogue against the current
      spec**.
  - **Obsolete:** the test cites a rule that no longer exists in the spec.
  - **Missing:** a rule in the spec with no test.
  - **OK:** the test maps to a current rule.
- [x] Demo with our 46-row subset, plus one or two deliberately obsolete rows.

### 9. AG ⇄ KK dialogue (inbox)

- [x] Show the message exchange the way ITSG's table does: **AG 41 → KK 61** (REF-ID = AG's DSID,
      Beginn 12-Monatsfrist), then 01, cancellation 88, and KK 62.
- [x] Label the KK replies as **given input the vendor's software must handle**, not something it
      produces. Our simulated insurer already plays this role; make the REF-ID → DSID link visible.

---

## Open questions and follow-ups

- [ ] **Ask Gerhard** whether the rule-extraction screen makes sense to someone who works with the
      data daily, once it's been reworked to show readable rules.
- [ ] **Ask Gerhard where the ~4,000 test scenarios live.** We need real rows for the baseline check.
- [ ] Download the **GKV-Datenaustausch EEL documents**, especially the field dictionary, into
      `hackathon-files/` and list them in [03-source-documents.md](03-source-documents.md).
- [ ] Which field and record was ITSG pointing at when decoding the example? The transcript
      garbles it ("LB", "GD = 41"); it is probably the submission reason (Abgabegrund) 41 in the
      DSLW/DBVO record.
- [x] How do we explain the function library in one sentence (see change 2), or do we drop it?
      → Kept, under Evidence: *"Every expected result is calculated by tested code, not written by
      the AI."*
- [ ] Would ITSG back a **spec change for a JSON input interface**? Who decides that, and could SAP
      be a pilot?
