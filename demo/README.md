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
| **D** or the **Demo** button | Start the guided demo (13 steps with spotlight and zoom) |
| **→** / **Space** · **←** | Next / previous step |
| **P** | Open the presenter window: speaker notes, timer, next step, synced with the main window |
| **Esc** | End the demo, close the drawer |

Put the presenter window on your laptop screen and the main window on the projector. If the
browser blocks pop-ups, the speaker notes appear in the demo card instead.

- **ITSG / Vendor** (top right) switches the role.
- **EN / DE** switches the language.
- Every underlined value opens its **provenance trail**.

## What's real and what's simulated

| Real | Simulated or illustrative |
|---|---|
| Spec excerpts, page numbers and change log of the Verfahrensbeschreibung v13.4 | The v13.3 wording (reconstructed from the change log; labelled in the UI) |
| ITSG's reference case (Peter Mustermann), its 4 criteria and UUIDs, the message chain | The test catalogue (46-row EEL subset) and vendors (fictional) |
| The sample file `TEEL0-Test1-DBVO`, parsed with the spec's field offsets | The broken file variants (derived from the real file) |
| Rule functions, guards, diff, parser, SHA-256: all running code with 26 unit tests | AI extraction runs (recorded; live mode makes real calls) |

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
3. **APP.** The screens, the provenance drawer and all actions.
4. **TOUR.** The guided demo and the presenter window.

Run the upload and rerun regression checks with `node demo/test_demo.cjs`.
When the pipeline server is connected, PDF uploads use its text extraction and
do not need the pdf.js CDN. Completed sections have a **Run tests again** action
in the AI test pipeline.
