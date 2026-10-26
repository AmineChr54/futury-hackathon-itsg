# Notes from Talking to the ITSG Team (26.10.2026)

Summarised from our transcript of the conversation with the ITSG system review team. The
transcription is rough, and some names and terms were garbled.

## How testing works today

**The test-case base**
- ITSG keeps a **~600-page sheet with ~3,000 test cases** (5–6 per page), all **written and
  maintained by hand**.
- Testers read the specs and "think about it". There is no formal method for turning a spec clause
  into a test case.
- Test cases are **employee scenarios**: age, sex, married/divorced/single, number of children,
  income above or below thresholds, and so on. Each has a hand-computed expected result.

**When the spec changes (every half year)**
- ITSG doesn't rewrite everything. They **look only at what changed since the last version, find
  the affected test cases and adapt them**.
- This is the step they called "the start of the process". In their words, reviewing ~600 pages
  of spec manually and working out which test scenarios are needed is "a nightmare".

**Monthly tests (partly automated)**
- ITSG gives the vendors test cases.
- Vendors send the resulting messages to ITSG's **electronic testing device**, which compares them
  automatically against ITSG's solutions.
- **Their worry:** vendors may **fit the messages to the known solutions** instead of letting
  their program generate them.

**Yearly inspection (the main event)**
- Every vendor needs a **new certificate every year**. Without the 2027 certificate, software
  cannot transmit anything from 01.01.2027.
- An ITSG examiner visits the vendor and asks them to *"show me in your program that when an
  employee is ill, you produce this message."*
- **All 3,000–5,000 test cases must pass. One error and the software doesn't go to market.**

## Hard constraints

- **Zero failure tolerance.** "This is nothing of a 90/10." Even one cent wrong is a failure. With
  800M transactions a year, a 1% error rate means millions of records corrected by hand.
- **~100 programs, all certified the same way.** 5–6 programs produce over 80% of all messages, but
  a program sending 10 messages a year must also be certified.
- **The specs arrive late.** The authorities often publish them **in December, sometimes with
  hundreds of changes, effective 1 January**. Vendors and ITSG get weeks, not months, to adapt.
  **Speed of turning spec changes into updated test cases is critical.**
- **UI automation is probably out of reach.** There are 100 different programs (web, desktop,
  different OSes). ITSG doubts entering test data into them can be automated ("surprise us").
- **ITSG is not a software vendor.** They define and check tests; the vendors build the programs.

## Useful facts

- Every certified program gets a **product identifier and a modification identifier**, sent in every
  message. These are DSLW fields 135–141 and 142–149; see [05-data-format.md](05-data-format.md). An
  error in live traffic can be traced to the exact program version.
- **Where specs come from:** they are published by a body one level below the government. ITSG takes
  part in the specification process a little and is told when specs change. The specs are public,
  and vendors build against them.
- ITSG said openly: *"We won't show you our solution, because we do it wrong. It's how it works
  today. Maybe you can provide a better one."* They are open to process changes, not just tooling.
- **Availability:** the ITSG team is on site until about 18:00–19:00 today and from about 08:00
  tomorrow.

## What this means for us

1. **The biggest pain is test-case creation and maintenance, not checking.** The checking is
   already partly automated by their testing device. Generating and updating ~3,000 test cases from
   the specs is still fully manual.
2. **The killer feature is turning a spec change into its affected test cases.** Every half year
   (and again in late December) they need: *what changed → which criteria are affected → which test
   cases must be updated → the updated cases.* The Verfahrensbeschreibung already has a **change
   log** (*Änderungsübersicht*) listing the changed sections per version (e.g. v13.4: §3.12 DBVO,
   §3.1.18 Abgabegrund…), which makes a concrete demo.
3. **Zero tolerance means the LLM must never be the oracle.** Expected results must come from
   deterministic code, cross-checked by a second independent extraction or implementation.
   Disagreements go to a human. Humans approve the extracted rules once, rather than checking 3,000
   cases.
4. **Use fresh test variants against gaming.** Generate **new random variants of each test case
   every cycle**: the same criterion, different data. Vendors can't fit outputs to answers they've
   never seen. This directly addresses ITSG's stated fear.
5. **Plug into their existing message channel, not the UIs.** Our output is test cases plus
   expected messages that feed into the existing testing device. We don't drive SAP or Lexware
   screens.
6. **Show coverage.** "100% covered" needs evidence. Build a matrix of every spec clause against
   the test cases that cover it, and flag clauses with no test.

## Questions to ask while they're here

- [ ] Can we see **a page of the 600-page test-case sheet**? We want to match its format.
- [ ] What does the **electronic testing device** compare: whole message, field by field, or
      selected fields? What's its input format?
- [ ] Do the 3,000 test cases cover all procedures? How many are for **EEL** specifically?
- [ ] Is the **change log** in the Verfahrensbeschreibung what they use to find changes today, or do
      they diff the documents?
- [ ] For the monthly tests, how are test cases handed to vendors, and could ITSG send per-vendor
      randomised variants?
- [ ] What does "Daumenkriterium" mean in the DBVO example?
- [ ] Can we get the record description (Datensatzbeschreibung) for VOSZ, DSKO and NCSZ, and DSLW
      positions 206–224?
