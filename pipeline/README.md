# AI test-case pipeline

Turns a new spec PDF into reviewed test cases for developers:

```
PDF drop + docs/law_file/ ─▶ sections ─▶ diff / change log ─▶ AI per changed section ─▶ examiner review ─▶ developers
                             (pypdf)     (deterministic)       spec-change JSON          formula + variables   inbox + JSON
                                                               test cases                edit, verify
                                                               terminal calculations
                                                               chain of thought
```

## Run it

On a fresh clone (Python 3.10+ needed):

1. **API key.** `pipeline/.env` is not in git (it holds the team's hessian.AI key). Copy `pipeline/.env.example` to `pipeline/.env` and put the key after `HAI_API_KEY=`. Ask a teammate for the key, privately.
2. **Start.** Windows: double-click `pipeline/start.cmd`. Mac/Linux: `sh pipeline/start.sh`. Both create `.env` from the template if it is missing and install `pypdf`. By hand:

```
python -m pip install -r pipeline/requirements.txt    # python3 on Mac/Linux
python pipeline/server.py                              # http://localhost:8787/pipeline
python pipeline/server.py --host 0.0.0.0               # let others on your network open it too
```

3. Open `http://localhost:8787/pipeline` (the live app; `http://localhost:8787/` is the team's guided demo with slides). Don't open the HTML files directly: the app needs the server.

If something is missing, the server says so when it starts, and the pipeline screen shows a red box with the fix (no API key, pypdf not installed); **Generate test cases** stays disabled until it is fixed.

Open `http://localhost:8787/pipeline` (the live app, served by the pipeline). Then:

1. **Inputs & archive** (role ITSG): drop the new spec PDF. Earlier versions go in `docs/law_file/`. You can also tick "next drop is a previous version".
2. Press **Generate test cases** next to the drop zone.
3. **AI test pipeline** shows the live chain of thought for each section: reasoning, terminal runs, the extracted spec-change JSON, each test case and the guard checks.
4. **Test-case review**: formulas that changed with the law are flagged **ƒ updated**. Edit the formula or the variable values (the result is recomputed live), then **Verify** and **Send to developers**.
5. Developers open the same URL, choose **Developer** and enter their name. They see the test cases sent to them and can try other variable values, read the chain of thought, accept or ask a question, and download JSON.

## Sign-in and the developer loop

The page opens with a **Login** tab: username `istg` (ITSG examiner) or `dev` (developer). On a local server no password is needed. With `PIPELINE_PASSWORD` set in `pipeline/.env` (or `PIPELINE_PASSWORD_ISTG` / `PIPELINE_PASSWORD_DEV` per account) the Login tab asks for it: the server checks it, hands out a session token, and every API call and the `/v1` AI proxy need that token. The server then takes the user and role from the token, not from what the browser sends.

## Hosting

With Docker (one container, data in the `eel-data` volume): put `HAI_API_KEY` and `PIPELINE_PASSWORD` in `pipeline/.env`, then

```
bash deploy/docker.sh 8787        # builds the image and (re)starts the container "eel" on that port
docker logs -f eel                # what the server is doing
```

Without Docker: `deploy/setup.sh`.

Many people can run the AI at the same time. All runs share `AI_CONCURRENCY` AI workers (default 16), and one run has at most `AI_PER_RUN` of them (default 6). Free workers take sections round-robin across the runs (`scheduler.py`), so a run of 100 sections never holds up the person who starts after it, and a queued section shows how many runs go first. When the gateway is busy (HTTP 429/502/503/504) a call waits and tries again (2 → 30 s) instead of failing the section. Saves are written by a background thread within a second, and `docker stop` writes what is still unsaved before the server exits.

| | ITSG | Developer |
|---|---|---|
| Screens | everything above, plus **Test validation** | **Checklist**, **Results**, test-case details |
| Demo button | the guided ITSG demo | the developer demo below |
| Notifications | "Dev test results are here!" | "New test cases have been created", "ITSG validated your results" |

1. On **Test-case review** ITSG ticks test cases (one by one or **Select all**) and either deletes them or sends them (**Send to developers**, enabled once one is ticked; sending a case that is not verified yet counts as the examiner's verification and is recorded in its history; rejected cases cannot be sent; a deleted case also leaves the developers' checklists; the developer `dev` is always listed, an empty note becomes e.g. "EEL 13.4 — §3.12.5"). The developer gets "ITSG sent you new test cases" within seconds and a **checklist**: one row per test case with what to check and how to run it. The developer ticks each case once they have covered it in their program. A tick tracks coverage only, not pass/fail; ticks are saved per developer (`POST /api/checklists/<id>/coverage`) and the progress bar, the package list and the nav badge show what is still open.
   Above the table, an **AI recap** (`pipeline/recap.py`, written when the package is sent) says what changed in the spec, what to do and what the tests verify, and each row gets a one-line note on what it checks. It is written from the redacted test cases only; any text that names an expected value or a true/false answer is replaced by a plain summary, which is also used when the AI is unavailable. `POST /api/checklists/<id>/recap` writes it again.
2. *(Older flow, still served for existing submissions: the developer submitted values.)* ITSG gets "Dev test results are here!". **Test validation** shows the developer's values, **Fetch expected values** loads the values verified for that spec version, and each row is compared (pass / fail, editable with a comment). **Confirm & share** sends the verdicts back.
3. The developer sees the last passed and failed tests under **Results**.

Each developer also sees the packages ITSG sent before this build, with their original (mock) dates and ticks, under **Shared earlier** and in **Test cases from ITSG** (`MOCK_HISTORY` in `server.py`, created once per developer on first sign-in). They are marked `mock` and never appear in ITSG's own lists.

Developers never receive ITSG's expected values before validation: the server strips them, including from the AI's chain of thought. The developer demo seeds a checklist from ITSG's reference case (`POST /api/demo`), so it works without the AI.

## ITSG and the vendors (Messages)

Vendors sign in as `sap` or `lexware`; their company is fixed by the sign-in (`vendor` signs in without a company and picks one; per-account passwords: `PIPELINE_PASSWORD_SAP`, `PIPELINE_PASSWORD_LEXWARE`). The conversations, result files, the published test package, certificates and each vendor's per-case progress live on the server (`STORE["exchange"]`, files in `pipeline/data/exchange/`), so ITSG and each vendor see the same state from different machines; the page polls every 4 seconds.

- **ITSG → vendor:** *New message* (to SAP or Lexware) or a reply in a conversation, with attachments (test package, report, rules, test cases); *Publish* sends the package; *Issue certificate* once nothing failed. The vendor gets "New message from ITSG".
- **Vendor → ITSG:** result files from *My test cases* (*Send result file*) or attached in Messages: `.dat .dta .txt .edi` (DTA output) and `.xml .csv .json .zip .pdf`, up to 10 MB, sent as the original bytes. DTA files are compared at once against ITSG's expected result (the verdict is posted in the conversation); other formats arrive as files for the examiner. ITSG gets "SAP sent a result file", can download it and opens DTA files in *Compare output*.
- **Who sees what:** ITSG sees all vendors; a vendor only its own conversations, files, certificate and progress (the server checks each request, not the page). Only ITSG publishes and certifies; only the vendor records its progress.
- The opening conversations are written once by the first page that finds the exchange empty. The guided demo (Demo button) plays its story in the page only and never writes to the server; afterwards the page shows the server's state again.

API: `GET /api/exchange`, `POST /api/exchange/threads` (new conversation), `POST /api/exchange/threads/<id>/messages`, `POST /api/exchange/threads/<id>/read`, `POST /api/exchange/files?name=…&rule=…` (raw bytes), `GET /api/exchange/files/<key>`, `PATCH /api/exchange` (`publishedTo`, `certs` by ITSG; `vwork` by the vendor), `POST /api/session/vendor`. Every change is in the shared audit trail (`GET /api/audit`, hash-chained).

## Expected DTA files, test reports and certificates

> The vendor's standardized output file is compared field by field with the expected output, as soon as it is uploaded. Every difference is explained in words, with its field and §. ITSG has its own comparator; our expected file uses the same DTA format, and ITSG said ours could replace theirs if it is better.

1. **Send to developers** (Test-case review) also writes the package's **expected DTA files** with ITSG's oracle: ITSG's sample envelope with the DBVO block the oracle computes for each message test case (TC-3.12-001 ITSG's reference case, EEL-3.12-006 the 6-month boundary v13.4 flipped). For the reference case the file is ITSG's own `TEEL0-Test1-DBVO` byte for byte. ITSG gets **"Your .DTA file is ready"**.
2. **Compare output**: choose the expected file (the new ones are added automatically), then the vendor's file — dropped, uploaded, or one the vendor sent in Messages ("Received: SAP · …"). The vendor is recognised from PRODUKT-IDENTIFIER. **Create test report** saves the result: verdict, every check, every difference in words with field and §, the SHA-256 of both files, sealed.
3. **Reports & certificates** keeps every test report per vendor. When the latest report for each expected file of the latest package passes, **Issue certificate** creates a sealed certificate (it lists the reports it rests on; a report changed after sealing blocks it), delivers it in the vendor's Messages, and offers **E-mail** (HTML attachment with the seal) and **Download**.

E-mail is sent by the server when `SMTP_HOST` (and `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`) are set in `pipeline/.env`; without them the page downloads the certificate and opens your mail program with the text, to attach it.

API (ITSG only): `GET/POST /api/expected`, `GET /api/expected/<id>`, `GET/POST /api/reports`, `GET /api/reports/<id>`, `GET/POST /api/certificates`, `GET /api/certificates/<id>/html`, `POST /api/certificates/<id>/email`. The comparison runs in the page (the same oracle and comparator as Compare output); the server stores, seals and certifies.

## What is compared with what

| Documents | Mode |
|---|---|
| Dropped PDF + a matching version in `docs/law_file/` | **diff**: section by section; changes not in the change log are flagged |
| Dropped PDF only, or no matching version (< 20 % heading overlap) | **single document**: its own change log for the latest version, or else the sections with the most rule signals |
| Nothing dropped, 2+ matching files in `docs/law_file/` | diff of the newest against the previous |
| Nothing dropped, one file in `docs/law_file/` | single document |

You can override the pairing under **Options**.

## Trust model

The AI explains each step and does the arithmetic in its terminal. Its answers are still not taken on trust:

- **G1**: every quote must appear verbatim in the spec (whitespace- and hyphenation-insensitive).
- **G2**: the formula must parse in a small safe language (`formula.py`): exact decimals, dates, a fixed set of functions.
- **G3**: the oracle evaluates the formula, and the result must equal the AI's own terminal value.
- **G4**: each legal parameter (e.g. 42 days) must appear in its quote ("sechs Wochen" counts as 42).
- **G5**: the formula must have been run in the terminal.

Failed guards go back to the AI, which corrects itself. Verifying a case with a failed guard needs a written reason. The expected value a developer receives always comes from the oracle.

The terminal (`sandbox.py`) runs the AI's Python in a separate process with an import allow-list, banned file/process/introspection built-ins, an empty temp folder and a 10 s timeout. It is a guard rail for a local prototype, not a security boundary for hostile input.

Without `PIPELINE_PASSWORD`, roles are taken from the page (the `X-Role` header), so a server without a password is suitable only for a trusted local network.

## Files

| File | Purpose |
|---|---|
| `server.py` | HTTP API, runs on the shared AI workers, storage in `data/store.json`, serves `demo/index.html`, `/v1` proxy |
| `scheduler.py` | Fair queue for the AI workers: round-robin across runs, a cap per run, Stop drops a run's queued sections |
| `documents.py` | PDF → pages → numbered sections (longest increasing heading sequence), change log, word diff |
| `agent.py` | Prompt, tools, streamed LLM loop, guards |
| `formula.py` | Safe formula evaluator, also preloaded in the AI's terminal |
| `sandbox.py` | The AI's terminal |
| `test_pipeline.py` | `python -m unittest pipeline/test_pipeline.py` |

API: `GET /api/status`, `GET /api/documents`, `POST /api/upload?name=`, `POST /api/plan`, `POST /api/runs`, `GET /api/runs/<id>?after=<seq>`, `POST /api/runs/<id>/items/<sec>/generate`, `GET|PATCH /api/testcases/<id>`, `POST /api/testcases/<id>/verify|reject|reopen|ack`, `GET /api/testcases/<id>/export`, `POST /api/evaluate`, `POST /api/send`, `GET /api/inbox?user=`, `GET /api/packages/<id>`.
