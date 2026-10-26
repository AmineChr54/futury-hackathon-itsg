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
python pipeline/server.py                              # http://localhost:8787
python pipeline/server.py --host 0.0.0.0               # let others on your network open it too
```

3. Open `http://localhost:8787`, not `demo/index.html` as a file: the page needs the server.

If something is missing, the server says so when it starts, and the pipeline screen shows a red box with the fix (no API key, pypdf not installed); **Generate test cases** stays disabled until it is fixed.

Open `http://localhost:8787` (the demo page, served by the pipeline). Then:

1. **Inputs & archive** (role ITSG): drop the new spec PDF. Earlier versions go in `docs/law_file/`. You can also tick "next drop is a previous version".
2. Press **Generate test cases** next to the drop zone.
3. **AI test pipeline** shows the live chain of thought for each section: reasoning, terminal runs, the extracted spec-change JSON, each test case and the guard checks.
4. **Test-case review**: formulas that changed with the law are flagged **ƒ updated**. Edit the formula or the variable values (the result is recomputed live), then **Verify** and **Send to developers**.
5. Developers open the same URL, choose **Developer** and enter their name. They see the test cases sent to them and can try other variable values, read the chain of thought, accept or ask a question, and download JSON.

## Sign-in and the developer loop

The page opens with a **Login** tab: username `istg` (ITSG examiner) or `dev` (developer). On a local server no password is needed. With `PIPELINE_PASSWORD` set in `pipeline/.env` (or `PIPELINE_PASSWORD_ISTG` / `PIPELINE_PASSWORD_DEV` per account) the Login tab asks for it: the server checks it, hands out a session token, and every API call and the `/v1` AI proxy need that token. The server then takes the user and role from the token, not from what the browser sends. Hosting: `deploy/setup.sh`.

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

Roles are taken from the page (the `X-Role` header). There are no logins, so this is suitable only for a trusted local network.

## Files

| File | Purpose |
|---|---|
| `server.py` | HTTP API, run queue (2 parallel AI workers), storage in `data/store.json`, serves `demo/index.html`, `/v1` proxy |
| `documents.py` | PDF → pages → numbered sections (longest increasing heading sequence), change log, word diff |
| `agent.py` | Prompt, tools, streamed LLM loop, guards |
| `formula.py` | Safe formula evaluator, also preloaded in the AI's terminal |
| `sandbox.py` | The AI's terminal |
| `test_pipeline.py` | `python -m unittest pipeline/test_pipeline.py` |

API: `GET /api/status`, `GET /api/documents`, `POST /api/upload?name=`, `POST /api/plan`, `POST /api/runs`, `GET /api/runs/<id>?after=<seq>`, `POST /api/runs/<id>/items/<sec>/generate`, `GET|PATCH /api/testcases/<id>`, `POST /api/testcases/<id>/verify|reject|reopen|ack`, `GET /api/testcases/<id>/export`, `POST /api/evaluate`, `POST /api/send`, `GET /api/inbox?user=`, `GET /api/packages/<id>`.
