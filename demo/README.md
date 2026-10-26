# Demo: EEL Review Assistant

A single-file demo (`index.html`) of the AI review assistant for ITSG's system review of
income replacement benefits (DTA EEL). "EEL Review Assistant" is a working title; the final
name is tracked in a GitHub issue.

## Open it

Double-click `index.html`. Everything runs offline: no build step, no server.

Optional extras that need the internet:
- **Fonts:** IBM Plex, from Google Fonts. Without a connection, system fonts are used instead.
- **PDF upload:** reading a spec PDF loads pdf.js from cdnjs.
- **Live AI mode:** calls hessian.AI (see below).

## Presenting

| Key | What it does |
|---|---|
| **D** or the **Demo** button | Start the guided demo (18 steps with spotlight and zoom, including the vendor side and Messages) |
| **→** / **Space** · **←** | Next / previous step |
| **N** | Show or hide the speaker notes in the demo bar at the bottom |
| **P** | Open the presenter window: speaker notes, timer, next step, synced with the main window |
| **Esc** | End the demo, close the drawer |

Put the presenter window on your laptop screen and the main window on the projector. If the
browser blocks pop-ups, press **N** to open the notes in the demo bar instead (collapsed by
default, so the bar stays slim).

- **ITSG / Vendor** (top right) switches the role.
- **EN / DE** switches the language.
- Every underlined value opens its **provenance trail**.

## Screens

Reworked after ITSG's review on 26.10.2026 ([docs/11-demo-feedback-itsg.md](../docs/11-demo-feedback-itsg.md)).

| Screen | What it shows |
|---|---|
| Overview | The pipeline, today vs. with the assistant, ITSG's reference case |
| 1 Inputs & archive | The original government PDF as the only external input, plus our archive |
| Baseline check | Existing tests vs. the current spec: obsolete (rule or wording removed) and missing (statement without a test) |
| Specification | AI highlights; each lists the tests that cover it |
| 2 Change impact | Change log + section diff, reconciled |
| 3 Rules (criteria) | Spec quote → rule in plain language → its test case; approve, edit or decline. Function, five checks and both AI runs sit in a collapsed "Technical details" fold |
| 4 Test cases | **Per rule** (default): one case per rule in human words, expected result, JSON download, expandable boundary set. Also: catalogue, fresh variants, ITSG reference case |
| 5 Publish | Publish the package (sent through Messages); **automatic input proposal** (JSON import, SAP pilot); the AG ⇄ KK dialogue as ITSG's table |
| 6 Compare output | Differences **in words** (field, expected vs actual, §), checks; bytes in a second tab. Uploading a file runs the comparison |
| 7 On-site audit · Report | Audit checklist; all vendors at a glance, summary in words, print and JSON per vendor |
| Messages | E-mail-like inbox: folders, one thread per vendor and topic, reply box with attachments (test package, result files, reports, certificate, rules, test cases). Result files are compared on arrival and the verdict is posted in words. ITSG quick actions: send report, request fix & resend, issue certificate (only when nothing failed) |
| Evidence | Function library, coverage, audit trail |

**Vendor role.** Switching to *Vendor* asks which company you are (SAP or Lexware — illustrative
examples; every result shown for them is imagined, and the screens say so). A vendor sees only
its own data:

| Screen | What it shows |
|---|---|
| Home | Progress (package → entered → results sent → ITSG review → certificate), next step, days left until 31.12.2026, what ITSG will check on site, latest messages |
| Messages | Its own threads with ITSG |
| 1 My test cases | Each case in words; mark as entered or import all (JSON); send a result file (demo picker: real or broken file, or from disk); "Ask ITSG". Expected results are never shown |
| 2 Upload & compare | Compare any file, then send it to ITSG |
| 3 My results | Own result files and own audit report only |
| Specification | The public spec |

## What's real and what's simulated

| Real | Simulated or illustrative |
|---|---|
| Spec excerpts, page numbers and change log of the Verfahrensbeschreibung v13.4 | The v13.3 wording (reconstructed from the change log; labelled in the UI) |
| ITSG's reference case (Peter Mustermann), its 4 criteria and UUIDs, the message chain | The test catalogue (46-row EEL subset), the three historic ALT-… rows in the baseline check, and all vendor results (SAP and Lexware are illustrative; results imagined) |
| ITSG's negative example from the review (earlier illness > 6 months back → no 41) | The JSON test-input format (a proposal; no vendor imports it yet) |
| The sample file `TEEL0-Test1-DBVO`, parsed with the spec's field offsets | The broken file variants (derived from the real file) |
| Rule functions, guards, diff, parser, difference explainer, baseline check, SHA-256: all running code with 31 unit tests | AI extraction runs and rule wording (recorded; live mode makes real calls) |

## Live AI mode (hessian.AI)

The gateway rejects direct browser calls (a CORS preflight returns 403), so use the local proxy:

```powershell
$env:HAI_API_KEY = "<your team key>"   # never commit this
python demo/proxy.py                    # serves http://localhost:8787/v1
```

Then in the demo, open **⚙ AI settings**, choose **Live** and set the base URL to
`http://localhost:8787/v1`, with model `vllm/Kolibri-1` or `vllm/GLM-Flash:Latest`.

Live answers go through the same deterministic guards as the recorded ones. If a call fails,
the demo says so and keeps the recorded runs. Inside a published claude.ai artifact, live calls
are blocked by the sandbox; recorded mode still works there.

## Source structure

`index.html` is one file in four sections:

1. **Design tokens and CSS.** Colours, type and spacing are defined on `:root`, with
   light and dark modes. This is the part to bring into Claude Design.
2. **CORE.** Spec data, the rule function library, guards, the diff, the DTA parser, the
   test generator and the self-tests. It has no DOM access, so it runs in Node too:

   ```bash
   node -e "const s=require('fs').readFileSync('demo/index.html','utf8');const c=s.slice(s.indexOf('/*CORE-START*/'),s.indexOf('/*CORE-END*/'));const C=new Function(c+';return CORE')();const t=C.selfTest(C.PARAMS_DEFAULT);console.log(t.filter(x=>x.ok).length+'/'+t.length)"
   ```
3. **APP.** The screens, the provenance drawer and all actions. `ruleCase()` defines the one
   representative test case per rule; `describeCase()` writes a scenario in human words.
4. **TOUR.** The guided demo and the presenter window.
