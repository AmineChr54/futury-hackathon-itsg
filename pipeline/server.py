"""EEL test-case pipeline: local server for the demo page.

    python pipeline/server.py                 → http://localhost:8787
    python pipeline/server.py --host 0.0.0.0  → reachable by the developers on your network

What it does
- serves demo/index.html (the guided demo), demo/pipeline.html at /pipeline (the live pipeline UI) and a JSON API for the "AI test pipeline" and "Developer inbox" screens;
- reads the previous spec versions in docs/law_file/ and the PDFs dropped into the page;
- diffs them section by section (or, with nothing to compare, uses the document's own change log);
- lets the AI turn each change into a spec-change JSON and test cases, with a sandboxed Python
  terminal for calculations; the chain of thought is streamed to the page and saved per test case;
- keeps test cases, examiner edits, verification and the hand-over to developers in pipeline/data/.

The API key is read from pipeline/.env or the environment (HAI_API_KEY) and never sent to the browser.
Standard library + pypdf.
"""
import argparse
import hashlib
import hmac
import secrets
import json
import os
import re
import signal
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import agent  # noqa: E402
import documents  # noqa: E402
import formula as F  # noqa: E402
import recap  # noqa: E402
from scheduler import Scheduler  # noqa: E402


def load_env():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
CFG = {"base": os.environ.get("HAI_BASE_URL", "https://hip-gw.hessian.ai/v1").rstrip("/"),
       "key": os.environ.get("HAI_API_KEY", ""),
       "model": os.environ.get("HAI_MODEL", "vllm/Kolibri-1")}
MODELS = ["vllm/Kolibri-1", "vllm/GLM-Flash:Latest"]
# Sign-in. The username decides the role. With a password set (a hosted server: it holds the API key and
# proxies /v1, so it must not be open), the Login tab asks for it and every API call needs the session token.
ACCOUNTS = {"istg": "itsg", "dev": "dev", "vendor": "vendor", "sap": "vendor", "lexware": "vendor"}
ALIASES = {"itsg": "istg", "lex": "lexware"}
VENDOR_OF = {"sap": "sap", "lexware": "lex"}  # company sign-ins; "vendor" picks its company in the page
SESSION_DAYS = float(os.environ.get("PIPELINE_SESSION_DAYS", "7"))  # a sign-in is valid this long
PASSWORDS = {u: os.environ.get(f"PIPELINE_PASSWORD_{u.upper()}") or os.environ.get("PIPELINE_PASSWORD", "") for u in ACCOUNTS}
AUTH = any(PASSWORDS.values())
LAW_DIR = os.environ.get("LAW_DIR", os.path.join(ROOT, "docs", "law_file"))
DATA = os.environ.get("PIPELINE_DATA", os.path.join(HERE, "data"))
UPLOADS = os.path.join(DATA, "uploads")
CACHE = os.path.join(DATA, "cache")
STORE_PATH = os.path.join(DATA, "store.json")
DOC_EXT = (".pdf", ".txt", ".md")
MATCH_MIN = 0.2  # heading overlap above which two documents count as versions of each other

for d in (DATA, UPLOADS, CACHE, LAW_DIR):
    os.makedirs(d, exist_ok=True)

LOCK = threading.RLock()
# AI jobs: AI_CONCURRENCY in flight against the gateway, at most AI_PER_RUN of them from one run
SCHED = Scheduler(int(os.environ.get("AI_CONCURRENCY") or 16), int(os.environ.get("AI_PER_RUN") or 6))
RUNS = {}  # run id → run (in memory; written to data/runs/, and dropped from memory when idle)
RUN_IDLE_S = 15 * 60  # a finished run nobody has polled for this long is reloaded from disk when needed


# ------------------------------------------------------------------ persistence

def _load_store():
    if os.path.exists(STORE_PATH):
        with open(STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"users": [], "testcases": [], "packages": [], "runs": []}


STORE = _load_store()
for _k in ("users", "testcases", "packages", "runs", "submissions"):
    STORE.setdefault(_k, [])
STORE.setdefault("sessions", {})
STORE.setdefault("audit", [])
for _k in ("expected", "reports", "certificates"):  # expected DTA files, test reports, certificates
    STORE.setdefault(_k, [])  # token → {user, role, t}; kept so a restart does not sign everyone out
if not any(u["name"] == "dev" for u in STORE["users"]):  # the developer account of this build: always a recipient
    STORE["users"].append({"name": "dev", "role": "dev", "since": "2025-11-01T09:00:00", "seen": None})


# Saving only marks what changed; the persister thread writes it within a second, outside the lock,
# so a busy run never makes the other requests wait for a disk write. flush_all() writes at once.
_DIRTY = {"store": False, "runs": set()}
_FLUSH = threading.Lock()  # one writer at a time


def save_store():
    with LOCK:
        _DIRTY["store"] = True


def save_run(run):
    with LOCK:
        _DIRTY["runs"].add(run["id"])


def _write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def flush_all():
    with _FLUSH:
        with LOCK:  # snapshot under the lock, write without it
            store = json.dumps(STORE, ensure_ascii=False, indent=1) if _DIRTY["store"] else None
            runs = [(rid, json.dumps({k: v for k, v in RUNS[rid].items() if k != "_seen"}, ensure_ascii=False, default=str))
                    for rid in _DIRTY["runs"] if rid in RUNS]
            _DIRTY["store"], _DIRTY["runs"] = False, set()
        try:
            if store is not None:
                _write_atomic(STORE_PATH, store)
            os.makedirs(os.path.join(DATA, "runs"), exist_ok=True)
            for rid, text in runs:
                _write_atomic(os.path.join(DATA, "runs", rid + ".json"), text)
        except OSError:
            with LOCK:  # e.g. disk full: keep it dirty and try again on the next tick
                _DIRTY["store"] = _DIRTY["store"] or store is not None
                _DIRTY["runs"].update(rid for rid, _ in runs)
            raise


def evict_idle_runs():
    cutoff = time.time() - RUN_IDLE_S
    with LOCK:
        for rid, run in list(RUNS.items()):
            busy = run.get("status") in ("running", "queued") or any(i.get("status") in ("queued", "running") for i in run["items"])
            if not busy and rid not in _DIRTY["runs"] and run.get("_seen", 0) < cutoff:
                del RUNS[rid]


def persister():
    while True:
        time.sleep(1)
        try:
            flush_all()
            evict_idle_runs()
        except Exception:  # noqa: BLE001 — log and retry on the next tick
            traceback.print_exc()


def load_run(run_id):
    with LOCK:  # two requests for an evicted run must get the same object
        if run_id in RUNS:
            return RUNS[run_id]
        path = os.path.join(DATA, "runs", re.sub(r"[^\w-]", "", run_id) + ".json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        run["_seen"] = time.time()
        if run.get("status") in ("running", "queued"):
            run["status"] = "interrupted"
        for it in run.get("items", []):  # the server restarted mid-run: these can be generated again
            if it.get("status") in ("running", "queued"):
                it["status"] = "error"
                it["summary"] = "interrupted (server restarted)"
        RUNS[run_id] = run
        return run


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def tc_by_id(tc_id):
    return next((t for t in STORE["testcases"] if t["id"] == tc_id), None)


# ------------------------------------------------------------------ documents

def list_docs():
    def entries(folder, kind):
        out = []
        for name in sorted(os.listdir(folder)):
            p = os.path.join(folder, name)
            if os.path.isfile(p) and name.lower().endswith(DOC_EXT) and not name.lower().startswith("readme"):
                st = os.stat(p)
                out.append({"name": name, "kind": kind, "size": st.st_size, "mtime": st.st_mtime})
        return out
    law = entries(LAW_DIR, "law_file")
    # also accept files next to the folder named law_file*, e.g. docs/law_file.pdf
    law += [d for d in entries(os.path.dirname(LAW_DIR), "law_file") if d["name"].lower().startswith("law_file") and d["name"] not in {x["name"] for x in law}]
    return {"law_files": law, "uploads": sorted(entries(UPLOADS, "upload"), key=lambda d: -d["mtime"]),
            "law_dir": os.path.relpath(LAW_DIR, ROOT).replace("\\", "/")}


def doc_path(kind, name):
    name = os.path.basename(name or "")
    folder = LAW_DIR if kind == "law_file" else UPLOADS
    p = os.path.join(folder, name)
    if kind == "law_file" and not os.path.isfile(p) and name.lower().startswith("law_file"):
        p = os.path.join(os.path.dirname(LAW_DIR), name)
    if not name or not os.path.isfile(p):
        raise ApiError(404, f"document not found: {kind}/{name}")
    return p


def load_doc(ref):
    doc = documents.load(doc_path(ref["kind"], ref["name"]), CACHE)
    doc["kind"] = ref["kind"]
    return doc


def plan(new_ref=None, old_ref=None):
    """Decide what to compare. Returns {mode, new, old, similarity, reason}."""
    docs = list_docs()
    law, ups = docs["law_files"], docs["uploads"]
    if new_ref and new_ref.get("name"):
        new = load_doc(new_ref)
        if old_ref is not None:  # explicit choice, also "none"
            old = load_doc(old_ref) if old_ref.get("name") else None
            sim = documents.similarity(old, new) if old else None
            return {"mode": "diff" if old else "single", "new": new, "old": old, "similarity": sim,
                    "reason": "chosen by you"}
        cands = [load_doc(d) for d in law if not (d["name"] == new["name"] and new_ref["kind"] == "law_file")]
    elif ups:
        new = load_doc(ups[0])
        cands = [load_doc(d) for d in law]
    elif len(law) >= 2:
        loaded = [load_doc(d) for d in law]
        best = max(((documents.similarity(a, b), a, b) for i, a in enumerate(loaded) for b in loaded[i + 1:]), key=lambda x: x[0])
        if best[0] >= MATCH_MIN:
            n, o = documents.newer_first(best[1], best[2])
            return {"mode": "diff", "new": n, "old": o, "similarity": best[0],
                    "reason": f"no PDF dropped: compared the two matching versions in {docs['law_dir']}"}
        new = max(loaded, key=lambda d: documents._version_key(d.get("version")))
        return {"mode": "single", "new": new, "old": None, "similarity": best[0],
                "reason": f"no PDF dropped and the files in {docs['law_dir']} are different documents: using the newest on its own"}
    elif law:
        return {"mode": "single", "new": load_doc(law[0]), "old": None, "similarity": None,
                "reason": f"only one document ({docs['law_dir']}): nothing to compare with, using it on its own"}
    else:
        raise ApiError(400, f"no document yet: drop a PDF or put one into {docs['law_dir']}")
    cands = [c for c in cands if c["sha256"] != new["sha256"]] or cands
    if not cands:
        return {"mode": "single", "new": new, "old": None, "similarity": None,
                "reason": f"no earlier version in {docs['law_dir']}: using the dropped document on its own"}
    scored = sorted(((documents.similarity(c, new), c) for c in cands), key=lambda x: -x[0])
    sim, old = scored[0]
    if sim < MATCH_MIN:
        return {"mode": "single", "new": new, "old": None, "similarity": sim,
                "reason": f"no matching earlier version in {docs['law_dir']} (best: {old['name']}, {sim:.0%} heading overlap): using the dropped document on its own"}
    if old["sha256"] == new["sha256"]:
        return {"mode": "single", "new": new, "old": None, "similarity": 1.0,
                "reason": f"{old['name']} is the same file: nothing changed, using the document on its own"}
    return {"mode": "diff", "new": new, "old": old, "similarity": sim,
            "reason": f"matched with {old['name']} ({sim:.0%} heading overlap)"}


def plan_public(p):
    return {"mode": p["mode"], "reason": p["reason"], "similarity": p["similarity"],
            "new": documents.summary(p["new"]) | {"kind": p["new"]["kind"]},
            "old": (documents.summary(p["old"]) | {"kind": p["old"]["kind"]}) if p["old"] else None}


# ------------------------------------------------------------------ runs

def emit(run, item_sec, typ, data):
    with LOCK:
        if typ == "live":
            if data is None:
                run["live"].pop(item_sec, None)
            else:
                run["live"][item_sec] = {"reasoning": data["reasoning"][-6000:], "content": data["content"][-3000:], "tool": data.get("tool", "")}
            return
        run["seq"] += 1
        run["events"].append({"seq": run["seq"], "t": now(), "item": item_sec, "type": typ, "data": data})


def item_of(run, sec):
    return next((i for i in run["items"] if i["sec"] == sec), None)


def start_run(body, user):
    p = plan(body.get("new"), body.get("old"))
    model = body.get("model") or CFG["model"]
    max_items = int(body.get("max_items") or 0)  # optional; by default every changed section is processed
    if p["mode"] == "diff":
        items = documents.diff_documents(p["old"], p["new"], p["new"]["changelog"])
        if not items:
            p = {**p, "mode": "single", "old": None,
                 "reason": p["reason"] + " · no text differences found, so the document is used on its own"}
    if p["mode"] == "single":
        items = documents.single_document_items(p["new"])
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    run = {"id": run_id, "created": now(), "by": user, "status": "running", "model": model, "lang": body.get("lang", "en"),
           "plan": plan_public(p), "items": [], "events": [], "seq": 0, "live": {}, "stop": False, "_seen": time.time()}
    for i, it in enumerate(items[:200]):
        run["items"].append({**it, "status": "queued" if not max_items or i < max_items else "candidate", "cases": [], "spec_change": None})
    with LOCK:
        RUNS[run_id] = run
        STORE["runs"].insert(0, {"id": run_id, "created": run["created"], "by": user, "mode": p["mode"],
                                 "new": p["new"]["name"], "old": p["old"]["name"] if p["old"] else None})
        save_store()
    n_changed = len(items)
    emit(run, None, "stage", {"step": "ingest", "text": f"Read {p['new']['name']}: {p['new']['pages']} pages, {len(p['new']['sections'])} numbered sections"
                              + (f", change log with {len(p['new']['changelog'])} rows" if p['new']['changelog'] else "")})
    if p["old"]:
        emit(run, None, "stage", {"step": "ingest", "text": f"Read {p['old']['name']}: {p['old']['pages']} pages, {len(p['old']['sections'])} numbered sections"})
    emit(run, None, "stage", {"step": "plan", "text": p["reason"]})
    if p["mode"] == "diff":
        kinds = {k: sum(1 for i in items if i["kind"] == k) for k in ("changed", "added", "removed")}
        emit(run, None, "stage", {"step": "diff", "text": f"Section diff: {kinds['changed']} changed, {kinds['added']} added, {kinds['removed']} removed"
                                  + f" · {sum(1 for i in items if i['source'] == 'diff-only')} not mentioned in the change log"})
    else:
        emit(run, None, "stage", {"step": "select", "text": f"{n_changed} candidate sections ({items[0]['source'] if items else 'none'})"})
    queued = [i for i in run["items"] if i["status"] == "queued"]
    emit(run, None, "stage", {"step": "queue", "text": f"AI processes the top {len(queued)}: " + ", ".join("§" + i["sec"] for i in queued)
                              + (f" · {len(run['items']) - len(queued)} more can be started by hand" if len(run["items"]) > len(queued) else "")})
    if not CFG["key"]:
        emit(run, None, "error", {"message": "HAI_API_KEY is not set (pipeline/.env)"})
    for it in queued:
        enqueue(run, it["sec"], "extract")
    if not queued:
        finish_run_if_done(run)
    return run


def enqueue(run, sec, phase):
    """Hand one section to the AI workers; runs share them fairly (scheduler.py)."""
    SCHED.submit(run["id"], (run["id"], sec, phase), process_item, run, sec, phase)


def finish_run_if_done(run):
    with LOCK:
        if all(i["status"] in ("done", "error", "candidate", "skipped", "stopped", "review") for i in run["items"]) and run["status"] == "running":
            run["status"] = "stopped" if run.get("stop") else "done"
            run["seq"] += 1
            n = sum(len(i["cases"]) for i in run["items"])
            waiting = sum(1 for i in run["items"] if i["status"] == "review" and not i.get("decision"))
            text = (f"Stopped: {n} test case(s) kept for review" if run.get("stop")
                    else f"Spec changes extracted: {waiting} waiting for your approval in “Review changes”" if waiting
                    else f"Finished: {n} test case(s) waiting for review")
            run["events"].append({"seq": run["seq"], "t": now(), "item": None, "type": "stage",
                                  "data": {"step": "stop" if run.get("stop") else "done", "text": text}})
    if run["status"] in ("done", "stopped"):
        save_run(run)


def process_item(run, sec, phase="extract"):
    """phase "extract": the AI records the spec change, which then waits for the examiner (status "review").
    phase "cases": the AI writes test cases for the approved spec change."""
    it = item_of(run, sec)
    with LOCK:
        stopped = run.get("stop")
        if stopped:
            it["status"] = "skipped" if phase == "extract" else "review"
        else:
            it["status"], it["phase"], run["status"] = "running", phase, "running"
            start_seq = run["seq"]
    if stopped:
        finish_run_if_done(run)
        return
    plan_ = run["plan"]
    new_doc = {"name": plan_["new"]["name"], "version": plan_["new"]["version"]}
    old_doc = {"name": plan_["old"]["name"], "version": plan_["old"]["version"]} if plan_["old"] else None
    emit(run, sec, "item_start", {"sec": sec, "title": it["title"], "kind": it["kind"], "source": it["source"], "model": run["model"], "phase": phase})
    approved = {k: v for k, v in (it.get("spec_change") or {}).items()} if phase == "cases" else None
    try:
        cfg = dict(CFG, model=run["model"])
        res = agent.run_item(cfg, it, new_doc, old_doc, lambda t, d: emit(run, sec, t, d), lang=run.get("lang", "en"),
                             should_stop=lambda: run.get("stop"), mode=phase, approved=approved)
    except Exception as e:  # keep the run alive; show the error in the chain of thought
        traceback.print_exc()
        emit(run, sec, "error", {"message": f"{type(e).__name__}: {e}"})
        res = {"spec_change": approved, "cases": [], "summary": "", "error": str(e)}
    if phase == "extract":
        with LOCK:
            it["spec_change"] = res["spec_change"]
            it["decision"], it["decided_by"], it["change_edited"] = None, None, False
            it["extract_seq"] = [start_seq, run["seq"]]  # its chain of thought, kept with the test cases later
            it["status"] = ("stopped" if res.get("stopped") and not res["spec_change"]
                            else "review" if res["spec_change"] else "error")
            it["summary"] = res.get("summary", "")
        emit(run, sec, "item_done", {"sec": sec, "cases": [], "summary": it["summary"], "status": it["status"], "phase": phase})
        finish_run_if_done(run)
        save_run(run)
        return
    with LOCK:
        lo, hi = it.get("extract_seq") or [start_seq, start_seq]
        # the AI's extraction, then the examiner's edits and decisions on it, then this test-case run
        extraction = [e for e in run["events"] if e["item"] == sec and (lo < e["seq"] <= hi
                      or (hi < e["seq"] <= start_seq and e["type"] in ("change_edited", "decision")))]
        cot_all = extraction + [e for e in run["events"] if e["item"] == sec and e["seq"] > start_seq]
        it["spec_change"] = res["spec_change"]
        prefix = f"TC-{sec}-{run['id'][2:8]}{run['id'][-4:]}-"
        # "Generate" again on the same section must not reuse the ids of the earlier attempt
        n0 = max((int(t["id"][len(prefix):]) for t in STORE["testcases"]
                  if t["id"].startswith(prefix) and t["id"][len(prefix):].isdigit()), default=0)
        for n, case in enumerate(res["cases"], start=n0 + 1):
            tc_id = f"{prefix}{n}"
            # the chain of thought up to this case's submission and the guard feedback on it
            upto = next((e["seq"] for e in cot_all if e["type"] == "test_case" and e["data"].get("local_id") == case["local_id"]), None)
            if upto is not None:
                upto = next((e["seq"] for e in cot_all if e["seq"] > upto and e["type"] == "tool_result"), upto)
            tc = {"id": tc_id, "run": run["id"], "created": now(), "status": "draft", "model": run["model"],
                  "section": sec, "section_title": it["title"], "page": it["page"], "change_kind": it["kind"],
                  "change_source": it["source"], "document": new_doc, "previous_document": old_doc,
                  "spec_change": res["spec_change"], **{k: v for k, v in case.items() if k not in ("local_id", "replaces")},
                  "cot": [e for e in cot_all if upto is None or e["seq"] <= upto],
                  "history": [{"t": now(), "who": "AI " + run["model"], "action": "created", "detail": f"from run {run['id']}"}],
                  "sent_to": [], "acks": []}
            recompute(tc)
            STORE["testcases"].insert(0, tc)
            it["cases"].append(tc_id)
        # without test cases the approved change goes back to review, so it can be sent to the AI again
        editorial = (res["spec_change"] or {}).get("change_type") == "editorial"
        it["status"] = "done" if it["cases"] or editorial else "review"
        it["summary"] = res.get("summary", "")
        save_store()
    emit(run, sec, "item_done", {"sec": sec, "cases": it["cases"], "summary": it.get("summary", ""), "status": it["status"], "phase": phase})
    finish_run_if_done(run)
    save_run(run)


# ------------------------------------------------------------------ test cases

def recompute(tc):
    fm = tc.get("formula") or {}
    try:
        types = {v["name"]: v.get("type", "number") for v in fm.get("variables") or []}
        values = {v["name"]: v.get("value") for v in fm.get("variables") or []}
        tc["expected_value"] = F.evaluate(fm.get("expression", ""), values, types)
        tc["formula_error"] = None
        tc["trace"] = F.trace(fm.get("expression", ""), values, types)
    except (F.FormulaError, KeyError, TypeError, AttributeError) as e:
        tc["expected_value"] = None
        tc["formula_error"] = str(e)
        tc["trace"] = []


def redact_for_dev(tc):
    """Developers compute the expected values themselves and ITSG verifies them, so a developer
    never receives ITSG's values: not as fields, not inside the AI's chain of thought."""
    out = {k: v for k, v in tc.items() if k not in ("expected_value", "ai_expected_value", "trace", "dev_results")}
    out["guards"] = [{**g, "detail": re.sub(r"oracle \S+ · AI \S+", "values hidden", g.get("detail", ""))} for g in tc.get("guards", [])]
    cot = []
    for e in tc.get("cot", []):
        d = e.get("data")
        if e["type"] == "terminal":
            d = {**d, "stdout": "(output hidden from developers)", "stderr": ""}
        elif e["type"] == "test_case":
            d = {k: v for k, v in d.items() if k not in ("expected_value", "ai_expected_value")}
        elif e["type"] in ("tool_result", "thought", "text") and isinstance(d, dict):
            d = {**d, **{k: re.sub(r"(Oracle value|oracle|expected[_ ]value)[:=]?\s*\S+", r"\1: (hidden)", d[k], flags=re.I) for k in ("result", "text") if isinstance(d.get(k), str)}}
        cot.append({**e, "data": d})
    out["cot"] = cot
    out["redacted"] = True
    return out


def result_type(value):
    if value in ("true", "false"):
        return "bool"
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return "date"
    return "number"


def checklist_row(tc):
    fm = tc.get("formula") or {}
    return {"id": tc["id"], "title": tc.get("title"), "kind": tc.get("kind"), "section": tc.get("section"),
            "section_title": tc.get("section_title"), "criterion": tc.get("criterion"), "preconditions": tc.get("preconditions", []),
            "steps": tc.get("steps", []), "expected_outcome_hint": fm.get("result_name"), "result_name": fm.get("result_name"),
            "result_unit": fm.get("result_unit"), "result_type": result_type(tc.get("expected_value")),
            "version": (tc.get("document") or {}).get("version"), "demo": tc.get("demo", False)}


def public_submission(sub, with_expected):
    """A developer's submitted values; with_expected adds the values ITSG verified for this spec version."""
    out = {k: sub[k] for k in ("id", "package", "by", "t", "status")}
    rows = []
    for r in sub["rows"]:
        tc = tc_by_id(r["id"]) or {}
        row = {**r, "title": tc.get("title"), "section": tc.get("section"), "kind": tc.get("kind"),
               "result_name": (tc.get("formula") or {}).get("result_name"), "result_unit": (tc.get("formula") or {}).get("result_unit"),
               "version": (tc.get("document") or {}).get("version"), "document": (tc.get("document") or {}).get("name")}
        if with_expected:
            row["expected"] = tc.get("expected_value")
            row["verified_by"], row["verified_at"] = tc.get("verified_by"), tc.get("verified_at")
            row["auto_verdict"] = "pass" if r["value"] and F.same_value(r["value"], tc.get("expected_value")) else "fail"
        rows.append(row)
    out["rows"] = rows
    if sub.get("validation"):
        v = {x["id"]: x for x in sub["validation"]["rows"]}
        for row in rows:
            if row["id"] in v:
                row["verdict"], row["comment"] = v[row["id"]]["verdict"], v[row["id"]]["comment"]
                if not with_expected:  # the developer sees ITSG's value once the result is shared
                    row["expected"] = v[row["id"]]["expected"]
        out["validation"] = {"by": sub["validation"]["by"], "t": sub["validation"]["t"],
                             "passed": sum(1 for x in sub["validation"]["rows"] if x["verdict"] == "pass"),
                             "failed": sum(1 for x in sub["validation"]["rows"] if x["verdict"] == "fail")}
    return out


def start_recap(pkg):
    """Write the developer briefing for a package in the background; the checklist shows it when ready."""
    cases = [tc for tc in (tc_by_id(i) for i in pkg["ids"]) if tc]
    rows = [checklist_row(tc) for tc in cases]
    pkg["recap"] = {"status": "pending", "t": now()}

    def work():
        try:
            if not CFG["key"]:
                raise RuntimeError("HAI_API_KEY is not set")
            out = {"status": "done", "source": "ai", "model": CFG["model"], **recap.generate(CFG, pkg, rows, cases)}
        except Exception as e:  # noqa: BLE001 — any failure falls back to the plain summary
            out = {"status": "done", "source": "summary", "error": str(e)[:200], **recap.fallback(pkg, rows, cases)}
        with LOCK:
            pkg["recap"] = {**out, "t": now()}
            save_store()
    threading.Thread(target=work, daemon=True).start()


DEMO_CASES = [
    # ITSG reference case (Peter Mustermann, DBVO / Abgabegrund 41) and its neighbours
    {"title": "End of sick pay with 25 creditable prior days", "kind": "positive", "section": "3.12.5",
     "change": ("condition", "Only prior-illness periods the insurer confirmed as creditable (reply 61) now reduce the 42-day continued-pay period.", "All prior AU periods reported by the employer reduced the 42 days.", "Only periods confirmed by the insurer (reply 61) reduce the 42 days; unconfirmed periods are ignored."),
     "criterion": "The system ensures that continued pay (EFZ) ends after 42 days minus all creditable prior-illness days.",
     "preconditions": ["Employee Peter Mustermann, statutory health insurance", "Prior AUs (same illness): 14.07.–15.07.2025, 01.10.–17.10.2025, 01.12.–03.12.2025, 01.03.–03.03.2026 (25 days)", "Insurer confirmed all four periods as creditable (reply 61)"],
     "steps": ["Enter the current AU from 11.03.2026", "Import the insurer's reply 61", "Run the payroll for March 2026", "Read the last day of continued pay (EFZ)"],
     "expression": "add_days(au_start, efz_days - prior_days - 1)", "result_name": "efz_end",
     "variables": [("au_start", "date", "2026-03-11", "scenario"), ("efz_days", "number", "42", "spec"), ("prior_days", "number", "25", "scenario")],
     "outcome": "Continued pay ends on 27.03.2026; sickness benefit starts the next day."},
    {"title": "End of sick pay while one prior AU is not yet confirmed", "kind": "boundary", "section": "3.12.5",
     "change": ("condition", "Only prior-illness periods the insurer confirmed as creditable (reply 61) now reduce the 42-day continued-pay period.", "All prior AU periods reported by the employer reduced the 42 days.", "Only periods confirmed by the insurer (reply 61) reduce the 42 days; unconfirmed periods are ignored."),
     "criterion": "The system ensures that only prior days confirmed by the insurer reduce the 42 days.",
     "preconditions": ["Same employee and AUs as above", "The insurer marked 01.03.–03.03.2026 as 'AU not on file' (KZ-NACHWEIS 4)"],
     "steps": ["Enter the current AU from 11.03.2026", "Import the first reply 61 (22 creditable days)", "Run the payroll", "Read the last day of continued pay"],
     "expression": "add_days(au_start, efz_days - prior_days - 1)", "result_name": "efz_end",
     "variables": [("au_start", "date", "2026-03-11", "scenario"), ("efz_days", "number", "42", "spec"), ("prior_days", "number", "22", "scenario")],
     "outcome": "Continued pay ends on 30.03.2026."},
    {"title": "Request 41 with 25 prior days + current AU 11.–20.03.2026", "kind": "positive", "section": "3.12",
     "change": ("parameter", "Request 41 (prior illnesses) may only be generated when prior illnesses plus the current AU total at least 30 days.", "No minimum duration was required before generating request 41.", "Request 41 needs at least 30 days of prior illnesses plus the current AU."),
     "criterion": "The system ensures that request 41 can only be generated if prior illnesses plus the current AU total at least 30 days.",
     "preconditions": ["Certified prior AUs with 25 days in the last 12 months", "Current AU 11.03.–20.03.2026 (certified)"],
     "steps": ["Enter the current AU 11.03.–20.03.2026", "Open the prior-illness request (Abgabegrund 41)", "Check whether the program allows sending it"],
     "expression": "prior_days + days_inclusive(au_start, au_end) >= min_days", "result_name": "request_allowed",
     "variables": [("prior_days", "number", "25", "scenario"), ("au_start", "date", "2026-03-11", "scenario"), ("au_end", "date", "2026-03-20", "scenario"), ("min_days", "number", "30", "spec")],
     "outcome": "The request may be generated (35 ≥ 30 days)."},
    {"title": "Request 41 with 15 prior days + current AU 11.–14.03.2026", "kind": "negative", "section": "3.12",
     "change": ("parameter", "Request 41 (prior illnesses) may only be generated when prior illnesses plus the current AU total at least 30 days.", "No minimum duration was required before generating request 41.", "Request 41 needs at least 30 days of prior illnesses plus the current AU."),
     "criterion": "The system ensures that request 41 is refused below 30 days.",
     "preconditions": ["Certified prior AUs with 15 days in the last 12 months", "Current AU 11.03.–14.03.2026"],
     "steps": ["Enter the current AU 11.03.–14.03.2026", "Try to create the prior-illness request (Abgabegrund 41)"],
     "expression": "prior_days + days_inclusive(au_start, au_end) >= min_days", "result_name": "request_allowed",
     "variables": [("prior_days", "number", "15", "scenario"), ("au_start", "date", "2026-03-11", "scenario"), ("au_end", "date", "2026-03-14", "scenario"), ("min_days", "number", "30", "spec")],
     "outcome": "The program refuses the request (19 < 30 days)."},
    {"title": "Prior AU with a gap of exactly 6 months", "kind": "boundary", "section": "3.12",
     "change": ("condition", "The 6-month gap rule was inverted: prior AUs now count if NO MORE than 6 months lie between them (was: at least 6 months).", "AU periods were included if at least 6 months lay between the end of one AU and the start of the next.", "AU periods are included if no more than 6 months lie between the end of one AU and the start of the next."),
     "criterion": "AU periods are included if no more than 6 months lie between the end of one AU and the start of the next.",
     "preconditions": ["Prior certified AU ending 11.09.2025", "Current AU starting 11.03.2026"],
     "steps": ["Enter both AUs", "Create the prior-illness request (Abgabegrund 41)", "Check whether the prior AU is listed in the DBVO block"],
     "expression": "add_months(previous_end, gap_months) >= current_start", "result_name": "prior_au_included",
     "variables": [("previous_end", "date", "2025-09-11", "scenario"), ("current_start", "date", "2026-03-11", "scenario"), ("gap_months", "number", "6", "spec")],
     "outcome": "The prior AU is included in the request."},
]


SECTION_TITLES = {"3.12": "DBVO – Vorerkrankungszeiten", "3.12.5": "Entgeltfortzahlung"}
DOC = "Verfahrensbeschreibung DTA EEL"


def ref_package(defs, user, t, version, prev, note, pkg_id, tag, by="ITSG examiner", mock=False):
    """A package of ITSG reference cases sent to one developer (the demo and the mock history)."""
    ids = []
    for n, d in enumerate(defs, start=1):
        tc = {"id": f"TC-{d['section']}-{tag}-{n}", "run": "demo", "created": t, "status": "sent", "model": "ITSG reference case",
              "demo": True, "mock": mock, "section": d["section"], "section_title": SECTION_TITLES.get(d["section"], ""),
              "page": 135, "change_kind": "changed", "change_source": "demo",
              "document": {"name": DOC, "version": version}, "previous_document": {"name": DOC, "version": prev},
              "spec_change": dict(zip(("change_type", "summary", "old_rule", "new_rule"), d["change"])),
              "title": d["title"], "kind": d["kind"], "criterion": d["criterion"], "preconditions": d["preconditions"], "steps": d["steps"],
              "scenario": {v[0]: v[2] for v in d["variables"] if v[3] == "scenario"},
              "formula": {"expression": d["expression"], "result_name": d["result_name"],
                          "variables": [{"name": a, "type": b, "value": c, "source": s} for a, b, c, s in d["variables"]]},
              "formula_changed": False, "expected_outcome": d["outcome"], "quotes": [],
              "guards": [{"id": "G2", "name": "formula valid", "status": "ok", "detail": "reference case"}],
              "cot": [], "verified_by": by, "verified_at": t, "sent_to": [user], "sent_at": t, "acks": [], "package": pkg_id,
              "history": [{"t": t, "who": by, "action": "verified", "detail": "ITSG reference case"},
                          {"t": t, "who": by, "action": "sent", "detail": f"to {user}"}]}
        recompute(tc)
        if mock:
            STORE["testcases"].append(tc)  # old cases: at the end, never on top of the examiner's lists
        else:
            STORE["testcases"].insert(0, tc)
        ids.append(tc["id"])
    return {"id": pkg_id, "t": t, "by": by, "to": [user], "ids": ids, "note": note, "demo": True, "mock": mock}


def seed_demo(user):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    pkg = ref_package(DEMO_CASES, user, now(), "13.4", "13.3", "EEL 13.4 — prior-illness request and continued pay (demo)",
                      "PKG-" + stamp, "DEMO" + stamp[-6:])
    STORE["packages"].insert(0, pkg)
    start_recap(pkg)
    return pkg


def _case(title, kind, section, criterion, pre, steps, expression, result_name, variables, outcome, change):
    return {"title": title, "kind": kind, "section": section, "criterion": criterion, "preconditions": pre, "steps": steps,
            "expression": expression, "result_name": result_name, "variables": variables, "outcome": outcome, "change": change}


_COUNT = ("clarification", "AU days are counted inclusively: the first and the last day of an AU both count.",
          "The spec did not say whether the first and the last day of an AU count.", "Both the first and the last day of an AU count.")
_EFZ = ("parameter", "Continued pay (EFZ) lasts 42 calendar days from the first day of incapacity, minus creditable prior days.",
        "Continued pay lasted six weeks; the counting of calendar days was not defined.", "Continued pay lasts 42 calendar days minus creditable prior days.")
_WINDOW = ("condition", "Only prior AUs that ended within the last 12 months before the current AU are counted.",
           "Prior AUs were counted without a time limit.", "Prior AUs count only if they ended within 12 months before the current AU.")

# Packages ITSG sent before this build (mock dates), newest first: each developer sees them as their history.
MOCK_HISTORY = [
    {"t": "2026-03-02T09:40:00", "version": "13.3", "prev": "13.2", "note": "EEL 13.3 corrigendum — 12-month look-back for prior illnesses",
     "covered": {1: "2026-03-04T16:12:00"},
     "cases": [
         _case("Prior AU that ended 13 months before the current AU", "negative", "3.12", "The system ensures that prior AUs older than 12 months are not counted.",
               ["Prior certified AU ending 01.02.2025", "Current AU starting 11.03.2026"], ["Enter both AUs", "Open the prior-illness request (Abgabegrund 41)", "Check whether the prior AU is listed"],
               "add_months(previous_end, lookback_months) >= current_start", "prior_in_window",
               [("previous_end", "date", "2025-02-01", "scenario"), ("current_start", "date", "2026-03-11", "scenario"), ("lookback_months", "number", "12", "spec")],
               "The prior AU is not counted.", _WINDOW),
         _case("Prior AU that ended 11 months before the current AU", "positive", "3.12", "The system ensures that prior AUs within 12 months are counted.",
               ["Prior certified AU ending 15.04.2025", "Current AU starting 11.03.2026"], ["Enter both AUs", "Open the prior-illness request (Abgabegrund 41)", "Check whether the prior AU is listed"],
               "add_months(previous_end, lookback_months) >= current_start", "prior_in_window",
               [("previous_end", "date", "2025-04-15", "scenario"), ("current_start", "date", "2026-03-11", "scenario"), ("lookback_months", "number", "12", "spec")],
               "The prior AU is counted.", _WINDOW)]},
    {"t": "2026-01-21T14:05:00", "version": "13.3", "prev": "13.2", "note": "EEL 13.3 — end of continued pay (EFZ)",
     "covered": {1: "2026-01-26T10:31:00", 2: "2026-01-26T11:02:00", 3: "2026-01-27T09:15:00"},
     "cases": [
         _case("End of sick pay without prior illnesses", "positive", "3.12.5", "The system ensures that continued pay ends after 42 calendar days.",
               ["Employee without prior AUs in the last 12 months", "Current AU from 05.01.2026, open-ended"], ["Enter the current AU", "Run the payroll for January and February 2026", "Read the last day of continued pay (EFZ)"],
               "add_days(au_start, efz_days - 1)", "efz_end",
               [("au_start", "date", "2026-01-05", "scenario"), ("efz_days", "number", "42", "spec")], "Continued pay ends after 42 days.", _EFZ),
         _case("End of sick pay with 10 creditable prior days", "positive", "3.12.5", "The system ensures that creditable prior days shorten continued pay.",
               ["Prior AU (same illness) of 10 days, confirmed by the insurer", "Current AU from 05.01.2026"], ["Enter the prior and the current AU", "Import the reply 61 of the insurer", "Read the last day of continued pay (EFZ)"],
               "add_days(au_start, efz_days - prior_days - 1)", "efz_end",
               [("au_start", "date", "2026-01-05", "scenario"), ("efz_days", "number", "42", "spec"), ("prior_days", "number", "10", "scenario")],
               "Continued pay ends 10 days earlier.", _EFZ),
         _case("Sick pay already used up by prior illnesses", "negative", "3.12.5", "The system ensures that no continued pay is due when prior days reach 42.",
               ["Prior AUs (same illness) of 45 days, confirmed by the insurer", "Current AU from 05.01.2026"], ["Enter the prior and the current AU", "Import the reply 61 of the insurer", "Check whether continued pay is still due"],
               "prior_days >= efz_days", "efz_exhausted",
               [("prior_days", "number", "45", "scenario"), ("efz_days", "number", "42", "spec")], "No continued pay is due.", _EFZ)]},
    {"t": "2025-11-14T10:20:00", "version": "13.2", "prev": "13.1", "note": "EEL 13.2 — counting days of prior illnesses",
     "covered": {1: "2025-11-17T13:44:00", 2: "2025-11-17T15:20:00", 3: "2025-11-18T09:05:00"},
     "cases": [
         _case("Days of a single AU from 01.10. to 17.10.2025", "positive", "3.12", "The system counts AU days inclusively.",
               ["Certified AU 01.10.–17.10.2025"], ["Enter the AU", "Open the prior-illness overview", "Read the number of AU days"],
               "days_inclusive(au_start, au_end)", "au_days", [("au_start", "date", "2025-10-01", "scenario"), ("au_end", "date", "2025-10-17", "scenario")],
               "The AU counts with all its days.", _COUNT),
         _case("Prior days from two AUs in the last 12 months", "positive", "3.12", "The system adds up the days of all prior AUs.",
               ["Certified AU 14.07.–15.07.2025", "Certified AU 01.10.–17.10.2025"], ["Enter both AUs", "Open the prior-illness overview", "Read the total of prior days"],
               "days_inclusive(a_start, a_end) + days_inclusive(b_start, b_end)", "prior_days",
               [("a_start", "date", "2025-07-14", "scenario"), ("a_end", "date", "2025-07-15", "scenario"), ("b_start", "date", "2025-10-01", "scenario"), ("b_end", "date", "2025-10-17", "scenario")],
               "Both AUs are added up.", _COUNT),
         _case("One-day AU on a Sunday", "boundary", "3.12", "The system counts a one-day AU as one day, also on a non-working day.",
               ["Certified AU on Sunday 02.11.2025 only"], ["Enter the AU", "Open the prior-illness overview", "Read the number of AU days"],
               "days_inclusive(au_start, au_end)", "au_days", [("au_start", "date", "2025-11-02", "scenario"), ("au_end", "date", "2025-11-02", "scenario")],
               "The AU counts as one day.", _COUNT)]},
]


def seed_history(user):
    """Give a developer the packages ITSG sent before this build, once, so the checklist has a history."""
    seeded = STORE.setdefault("history_seeded", [])
    if user in seeded:
        return
    tag = re.sub(r"\W", "", user)[:12] or "dev"
    for h in MOCK_HISTORY:
        stamp = h["t"].replace("-", "").replace(":", "").replace("T", "-")
        pkg = ref_package(h["cases"], user, h["t"], h["version"], h["prev"], h["note"], f"PKG-{stamp}-{tag}", f"H{stamp[2:8]}{tag}", mock=True)
        pkg["coverage"] = {user: {pkg["ids"][n - 1]: t for n, t in h["covered"].items()}}
        for tc_id in pkg["ids"]:  # the developer accepted these back then
            tc = tc_by_id(tc_id)
            tc["acks"], tc["status"] = [{"who": user, "t": h["t"], "comment": "", "state": "accepted"}], "acknowledged"
        STORE["packages"].append(pkg)
        start_recap(pkg)
    seeded.append(user)
    save_store()


def default_note(cases):
    """A package title when the examiner leaves the note empty: document version and sections."""
    doc = next((c.get("document") or {} for c in cases if c.get("document")), {})
    secs = sorted({c.get("section") for c in cases if c.get("section")})
    head = "EEL " + doc["version"] if doc.get("version") else (doc.get("name") or "Test cases")
    return f"{head} — " + ", ".join("§" + s for s in secs) if secs else head


# ------------------------------------------------------------------ audit trail (shared, hash-chained)

AUDIT_KEEP = 5000  # older entries are dropped from the front; the rest of the chain stays verifiable


def _audit_hash(prev, e):
    body = json.dumps({k: e[k] for k in ("seq", "t", "who", "role", "action", "detail")}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()


def audit(who, role, action, detail=""):
    """Append one entry. Each entry carries the previous entry's hash, so editing or removing one breaks the chain."""
    with LOCK:
        log = STORE["audit"]
        prev = log[-1]["hash"] if log else "0" * 64
        e = {"seq": log[-1]["seq"] + 1 if log else 1, "t": now(), "who": who, "role": role, "action": action,
             "detail": str(detail or "")[:300], "prev": prev}
        e["hash"] = _audit_hash(prev, e)
        log.append(e)
        if len(log) > AUDIT_KEEP:
            del log[:len(log) - AUDIT_KEEP]
        save_store()
    return e


def audit_chain(log):
    """(True, None) when every entry links to the one before and its hash matches; else (False, first bad seq)."""
    for i, e in enumerate(log):
        if (i and e["prev"] != log[i - 1]["hash"]) or _audit_hash(e["prev"], e) != e["hash"]:
            return False, e["seq"]
    return True, None


def describe_change(method, parts, b):
    """What a successful change request means, in words for the audit trail; None for requests not worth logging."""
    r, rest = parts[0], parts[1:]
    act = rest[-1] if rest else ""
    if r in ("users", "plan", "evaluate", "status"):
        return None
    if r == "login":
        return "signed in", ""
    if r == "logout":
        return "signed out", ""
    if r == "upload":
        return ("removed document" if method == "DELETE" else "uploaded document"), (rest[0] if rest else "")
    if r == "runs":
        if not rest:
            return "started AI run", ""
        named = {"stop": "stopped AI run", "generate": "generated test cases", "decide": "decided on spec changes",
                 "cases": "approved spec changes for test cases", "change": "edited a spec change"}
        sec = rest[2] if len(rest) > 2 else ", ".join(b.get("secs") or [])
        return named.get(act, "updated AI run"), f"{rest[0]}" + (f" · §{sec}" if sec else "") + (f" · {b['decision']}" if act == "decide" and b.get("decision") else "")
    if r == "testcases":
        tid = rest[0] if rest else ""
        if method == "DELETE":
            return "deleted test case", tid
        if method == "PATCH":
            return "edited test case", tid
        named = {"verify": "verified test case", "reject": "rejected test case", "reopen": "reopened test case",
                 "reply": "answered a question", "ack": "asked a question" if b.get("state") == "question" else "accepted test case"}
        return named.get(act, act), tid
    if r == "send":
        return "sent test cases", f"{', '.join(b.get('ids') or [])} → {', '.join(b.get('to') or [])}"
    if r == "checklists":
        if act == "coverage":
            return ("ticked" if b.get("done") else "unticked") + " a test case as tested", b.get("id", "")
        return {"recap": "rewrote the AI recap", "submit": "submitted values"}.get(act, act), rest[0] if rest else ""
    if r == "submissions":
        return "validated developer results", rest[0] if rest else ""
    if r == "demo":
        return "started the developer demo", ""
    if r == "session":
        return "chose vendor company", b.get("vendor", "")
    if r == "expected":
        return "prepared expected DTA files", f"{b.get('package') or ''} · {', '.join(f.get('name', '') for f in (b.get('files') or []) if isinstance(f, dict))}"
    if r == "reports":
        return "saved a test report", f"{b.get('vendor') or ''} · {(b.get('file') or {}).get('name') or ''} → {b.get('verdict') or ''}"
    if r == "certificates":
        return ("e-mailed a certificate", f"{rest[0]} → {b.get('to') or ''}") if act == "email" else ("issued a certificate", b.get("vendor", ""))
    if r == "exchange":
        what = rest[0] if rest else ""
        if what == "seed" or act == "read":
            return None
        if what == "files":
            return "sent a result file", ""
        if what == "threads" and len(rest) == 1:
            return "started a conversation", f"{b.get('vendor') or ''} · {b.get('subject') if isinstance(b.get('subject'), str) else ''}"
        if act == "messages":
            return ("posted a comparison verdict" if b.get("from") == "system" else "sent a message"), rest[1] if len(rest) > 1 else ""
        if method == "PATCH":
            return ("published the test package" if "publishedTo" in b else "issued a certificate" if "certs" in b else "recorded test progress"), ""
        return None
    return f"{method.lower()} {r}", "/".join(rest)


# ------------------------------------------------------------------ ITSG's view of what was sent

def open_question(tc):
    """The last message on a test case is a developer's question: ITSG has not answered yet."""
    th = [m for m in tc.get("thread") or [] if m["role"] == "itsg" or m.get("kind") == "question"]
    return bool(th) and th[-1]["role"] == "dev"


def tracking(pkg):
    """A package as ITSG follows it: per developer how far they are, and per test case ticks, answers and questions."""
    cases = [tc for tc in (tc_by_id(i) for i in pkg["ids"]) if tc]
    cov = pkg.get("coverage") or {}
    progress = {u: {"covered": sum(1 for tc in cases if tc["id"] in cov.get(u, {})), "total": len(cases),
                    "last": max(cov.get(u, {}).values(), default=None),
                    "accepted": sum(1 for tc in cases if any(a["who"] == u and a["state"] == "accepted" for a in tc.get("acks", [])))}
                for u in pkg["to"]}
    rows = [{"id": tc["id"], "title": tc.get("title"), "section": tc.get("section"), "kind": tc.get("kind"), "status": tc.get("status"),
             "expected_value": tc.get("expected_value"), "result_name": (tc.get("formula") or {}).get("result_name"),
             "ticked": {u: cov.get(u, {}).get(tc["id"]) for u in pkg["to"]},
             "acks": {a["who"]: a["state"] for a in tc.get("acks", [])},
             "thread": tc.get("thread", []), "open_question": open_question(tc)} for tc in cases]
    return {**{k: pkg.get(k) for k in ("id", "t", "by", "to", "note")}, "progress": progress, "cases": rows,
            "open_questions": sum(1 for r in rows if r["open_question"])}


# ------------------------------------------------------------------ ITSG ⇄ vendor exchange (Messages)

# The payroll vendors of the demo (the page's C.VENDORS). A vendor account sees only its own company's data.
VENDORS = {"sap": "SAP", "lex": "Lexware"}
EXCHANGE_DIR = os.path.join(DATA, "exchange")
# DTA output files and the other formats vendors send test results in
RESULT_EXT = (".dat", ".dta", ".txt", ".edi", ".xml", ".csv", ".json", ".zip", ".pdf")
DTA_EXT = (".dat", ".dta", ".txt", ".edi")
MAX_FILE = 10 * 1024 * 1024
ATTACH_TYPES = {"package", "report", "rule", "case", "crit", "dta", "file", "verdict", "certificate"}


def exchange():
    x = STORE.setdefault("exchange", {})
    for k, v in (("threads", []), ("files", {}), ("certs", {}), ("publishedTo", []), ("vwork", {})):
        x.setdefault(k, v)
    return x


def text_of(v, limit=20000):
    """Message bodies and subjects: a string, or {en, de} for the seeded texts."""
    if isinstance(v, dict):
        return {k: str(v.get(k) or "")[:limit] for k in ("en", "de")}
    return str(v or "")[:limit]


def exchange_for(role, vendor):
    """What one side may see: ITSG everything, a vendor only its own threads, files, certificate and results."""
    x = exchange()
    if role == "itsg":
        return x
    if role != "vendor" or vendor not in VENDORS:
        raise ApiError(403, "sign in as ITSG or as a vendor")
    return {"threads": [t for t in x["threads"] if t["vendor"] == vendor],
            "files": {k: f for k, f in x["files"].items() if f["vendor"] == vendor},
            "certs": {vendor: x["certs"][vendor]} if vendor in x["certs"] else {},
            "publishedTo": [vendor] if vendor in x["publishedTo"] else [],
            "published": vendor in x["publishedTo"],
            "vwork": {vendor: x["vwork"][vendor]} if vendor in x["vwork"] else {}}


def check_attach(attach, role, vendor):
    out = []
    for a in attach if isinstance(attach, list) else []:
        if not isinstance(a, dict) or a.get("type") not in ATTACH_TYPES:
            raise ApiError(400, "unknown attachment")
        if a["type"] == "certificate" and role != "itsg":
            raise ApiError(403, "only ITSG issues certificates")
        if a["type"] in ("dta", "file"):
            f = exchange()["files"].get(str(a.get("ref")))
            if not f or (role == "vendor" and f["vendor"] != vendor):
                raise ApiError(400, "attached file not found")
        out.append({k: a[k] for k in ("type", "ref") if k in a})
    return out


def new_message(th, frm, body, attach, msg_id=None):
    m = {"id": str(msg_id or f"{th['id']}-{len(th['msgs']) + 1}")[:80], "from": frm, "t": now(),
         "at": int((time.time() + time.localtime().tm_gmtoff) // 60), "body": text_of(body), "attach": attach}
    th["msgs"].append(m)
    if frm == "itsg":
        th["read"]["itsg"] = len(th["msgs"])
    elif frm != "system":
        th["read"]["vendor"] = len(th["msgs"])
    return m


# ------------------------------------------------------------------ expected DTA files, test reports, certificates
# The expected files and the field-by-field comparison come from ITSG's oracle in the page (the same code that
# reproduces ITSG's own TEEL0 file byte for byte); the server keeps them, seals them and issues certificates.

SMTP = {k: os.environ.get("SMTP_" + k.upper(), "") for k in ("host", "port", "user", "password", "from")}
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def seal_of(record):
    """SHA-256 over the canonical record: any later change to a report or certificate is detectable."""
    body = {k: v for k, v in record.items() if k not in ("seal", "emailed")}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def certificate_html(c):
    rows = "".join(f"<tr><td>{html_esc(r['scenario_id'])}</td><td>{html_esc(r['expected_name'])}</td><td>{html_esc(r['file'])}</td>"
                   f"<td>PASS</td><td style='font:11px monospace'>{r['seal'][:16]}…</td></tr>" for r in c["reports"])
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Zertifikat {html_esc(c['id'])}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:760px;margin:40px auto;color:#111}}h1{{font-size:26px;margin:0}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left;font-size:13px}}
.seal{{font:12px monospace;word-break:break-all;background:#f4f4f4;padding:8px}}</style></head><body>
<p style="letter-spacing:.1em;text-transform:uppercase;color:#a00;font-weight:700">ITSG · Systemuntersuchung DTA EEL</p>
<h1>Zertifikat / Certificate {html_esc(c['id'])}</h1>
<p><b>{html_esc(c['vendor_name'])}</b> {html_esc(c.get('product_name') or '')} {html_esc(c.get('release') or '')}<br>
Produkt-ID <code>{html_esc(c.get('product') or '—')}</code> · Modifikation <code>{html_esc(c.get('modification') or '—')}</code></p>
<p>Gültig / valid {html_esc(c['valid_from'])} – {html_esc(c['valid_to'])} · ausgestellt / issued {html_esc(c['issued'][:10])} von / by {html_esc(c['by'])}</p>
<p>Alle Ausgabedateien stimmen Feld für Feld mit der erwarteten Ausgabe überein. / Every output file matches the expected output field by field.</p>
<table><tr><th>Testfall</th><th>Erwartete Datei</th><th>Herstellerdatei</th><th>Ergebnis</th><th>Bericht-Siegel</th></tr>{rows}</table>
<p>Siegel / seal (SHA-256):</p><div class="seal">{c['seal']}</div></body></html>"""


def html_esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def send_certificate_mail(c, to):
    """Send the certificate by e-mail when the server has an SMTP account (SMTP_HOST, SMTP_PORT, SMTP_USER,
    SMTP_PASSWORD, SMTP_FROM in pipeline/.env)."""
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = f"Zertifikat DTA EEL {c['vendor_name']} · {c['id']}"
    msg["From"] = SMTP["from"] or SMTP["user"]
    msg["To"] = to
    msg.set_content(f"{c['vendor_name']}: Zertifikat {c['id']}, gültig {c['valid_from']} – {c['valid_to']}.\n"
                    f"Siegel (SHA-256): {c['seal']}\n\nDas Zertifikat liegt als HTML-Datei bei.\nITSG Systemuntersuchung")
    msg.add_attachment(certificate_html(c).encode("utf-8"), maintype="text", subtype="html", filename=f"{c['id']}.html")
    port = int(SMTP["port"] or 587)
    with (smtplib.SMTP_SSL(SMTP["host"], port, timeout=20) if port == 465 else smtplib.SMTP(SMTP["host"], port, timeout=20)) as s:
        if port != 465:
            s.starttls()
        if SMTP["user"]:
            s.login(SMTP["user"], SMTP["password"])
        s.send_message(msg)


def export_case(tc):
    """The hand-over format for developers."""
    fm = tc.get("formula") or {}
    return {
        "id": tc["id"], "status": tc["status"], "title": tc.get("title"), "kind": tc.get("kind"),
        "criterion": tc.get("criterion"),
        "preconditions": tc.get("preconditions", []), "steps": tc.get("steps", []),
        "source": {"document": tc["document"], "previous_document": tc.get("previous_document"),
                   "section": tc["section"], "section_title": tc["section_title"], "page": tc.get("page"),
                   "quotes": tc.get("quotes", [])},
        "spec_change": {k: (tc.get("spec_change") or {}).get(k) for k in ("change_type", "summary", "old_rule", "new_rule", "parameters", "quotes_new", "quotes_old")},
        "scenario": tc.get("scenario"),
        "formula": {"expression": fm.get("expression"), "result_name": fm.get("result_name"), "result_unit": fm.get("result_unit"),
                    "variables": fm.get("variables", []), "changed": tc.get("formula_changed"),
                    "previous_expression": tc.get("previous_expression") or None},
        "expected": {"value": tc.get("expected_value"), "outcome": tc.get("expected_outcome")},
        "verification": {"guards": tc.get("guards", []), "verified_by": tc.get("verified_by"), "verified_at": tc.get("verified_at"),
                         "override_reason": tc.get("override_reason")},
        "chain_of_thought": [{"t": e["t"], "type": e["type"], **({"text": e["data"].get("text")} if isinstance(e["data"], dict) and "text" in e["data"] else {"data": e["data"]})} for e in tc.get("cot", [])],
        "history": tc.get("history", []),
    }


def edit_spec_change(it, body):
    """Apply the examiner's edits to an item's spec change. Returns (new spec change, list of changes)."""
    old = it["spec_change"]
    sc = dict(old)
    text = lambda v: str(v).strip() if v is not None else ""
    strings = lambda v: [s.strip() for s in v if isinstance(s, str) and s.strip()] if isinstance(v, list) else None
    if "change_type" in body:
        if body["change_type"] not in agent.CHANGE_TYPES:
            raise ApiError(400, "unknown change type: " + str(body["change_type"]))
        sc["change_type"] = body["change_type"]
    for k in ("summary", "old_rule", "new_rule"):
        if k in body:
            sc[k] = text(body[k])
    for k in ("quotes_new", "quotes_old"):
        if k in body:
            v = strings(body[k])
            if v is None:
                raise ApiError(400, k + " must be a list of strings")
            sc[k] = v
    if "parameters" in body:
        if not isinstance(body["parameters"], list):
            raise ApiError(400, "parameters must be a list")
        params = []
        for p in body["parameters"]:
            if not isinstance(p, dict) or not text(p.get("name")):
                continue  # an empty row in the editor
            params.append({k: text(p.get(k)) for k in ("name", "old_value", "new_value", "unit", "quote") if text(p.get(k))})
        sc["parameters"] = params
    if "formula_changed" in body:
        sc["formula_changed"] = bool(body["formula_changed"])
    sc["quote_checks"] = agent.quote_checks(sc, it)
    changes = [k for k in agent.SPEC_FIELDS if sc.get(k) != old.get(k)]
    return sc, changes


def edit_case(tc, body, user):
    if tc["status"] in ("sent", "acknowledged"):
        raise ApiError(409, "already sent to developers: reopen it first")
    changes = []
    for k in ("title", "criterion", "expected_outcome", "kind"):
        if k in body and body[k] != tc.get(k):
            changes.append(f"{k}: {tc.get(k)!r} → {body[k]!r}")
            tc[k] = body[k]
    for k in ("preconditions", "steps"):
        if isinstance(body.get(k), list):
            new = [str(x).strip() for x in body[k] if str(x).strip()]
            if new != tc.get(k, []):
                changes.append(f"{k} edited")
                tc[k] = new
    if "scenario" in body and isinstance(body["scenario"], dict) and body["scenario"] != tc.get("scenario"):
        changes.append("scenario edited")
        tc["scenario"] = body["scenario"]
    if "formula" in body:
        new_f = body["formula"]
        old_f = tc.get("formula") or {}
        if new_f.get("expression") is not None and new_f["expression"] != old_f.get("expression"):
            F.parse(new_f["expression"])  # reject invalid formulas before storing
            changes.append(f"formula: {old_f.get('expression')} → {new_f['expression']}")
            tc.setdefault("ai_expression", old_f.get("expression"))
            old_f["expression"] = new_f["expression"]
            tc["formula_edited"] = True
        if isinstance(new_f.get("variables"), list):
            before = {v["name"]: v.get("value") for v in old_f.get("variables") or []}
            clean = []
            for v in new_f["variables"]:
                if not re.fullmatch(r"[A-Za-z_]\w{0,40}", str(v.get("name", ""))):
                    raise ApiError(400, f"invalid variable name: {v.get('name')!r}")
                clean.append({k: v.get(k) for k in ("name", "type", "value", "unit", "description", "source", "quote") if k in v})
                if before.get(v["name"]) != v.get("value"):
                    changes.append(f"{v['name']}: {before.get(v['name'])} → {v.get('value')}")
            old_f["variables"] = clean
        tc["formula"] = old_f
    before_val = tc.get("expected_value")
    recompute(tc)
    if tc.get("expected_value") != before_val:
        changes.append(f"expected value: {before_val} → {tc.get('expected_value')}")
    if changes:
        if tc["status"] == "verified":
            tc["status"] = "draft"
            changes.append("verification withdrawn (edited)")
        tc["history"].append({"t": now(), "who": user, "action": "edited", "detail": "; ".join(changes)})
    return changes


# ------------------------------------------------------------------ HTTP

PIPELINE_PAGES = ("/pipeline", "/pipeline.html", "/demo/pipeline.html")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    server_version = "EELPipeline/1.0"

    def log_message(self, fmt, *args):
        if not (len(args) > 1 and str(args[1]) == "200" and "/api/runs/" in str(args[0])):
            sys.stderr.write("pipeline: " + (fmt % args) + "\n")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-User, X-Role")

    def send_json(self, obj, status=200):
        self._status = status
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        # read once and keep it: route() drains it before any early error reply, otherwise Windows
        # resets the connection and the browser sees a network error instead of the message
        if not hasattr(self, "_raw"):
            n = int(self.headers.get("Content-Length") or 0)
            self._raw = self.rfile.read(n) if n else b""
        return self._raw

    def json_body(self):
        raw = self.body()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(400, "body is not JSON")

    @property
    def session(self):
        tok = self.headers.get("X-Token") or ""
        s = STORE["sessions"].get(tok) if tok else None
        if s and time.time() - time.mktime(time.strptime(s["t"], "%Y-%m-%dT%H:%M:%S")) > SESSION_DAYS * 86400:
            with LOCK:
                STORE["sessions"].pop(tok, None)
            return None
        return s

    @property
    def user(self):
        if AUTH:  # who is signed in, not what the browser claims
            return (self.session or {}).get("user", "anonymous")
        return urllib.parse.unquote(self.headers.get("X-User") or "") or "anonymous"

    @property
    def role(self):
        if AUTH:
            return (self.session or {}).get("role", "")
        return (self.headers.get("X-Role") or "").lower()

    def need_examiner(self):
        if self.role not in ("itsg", "examiner"):
            raise ApiError(403, "only an ITSG examiner can do this")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PATCH(self):
        self.route("PATCH")

    def do_DELETE(self):
        self.route("DELETE")

    def route(self, method):
        url = urllib.parse.urlparse(self.path)
        path, q = url.path, urllib.parse.parse_qs(url.query)
        self.body()
        try:
            public = path in ("/", "/index.html", "/demo/", "/demo/index.html", *PIPELINE_PAGES, "/api/status", "/api/login")
            if AUTH and not public and not self.session:
                raise ApiError(401, "sign in first")
            if path.startswith("/v1/"):
                return self.proxy(method)
            if method == "GET" and path in ("/", "/index.html", "/demo/", "/demo/index.html"):
                return self.static(os.path.join(ROOT, "demo", "index.html"), "text/html; charset=utf-8")
            if method == "GET" and path in PIPELINE_PAGES:  # the full live pipeline UI (Achraf's app)
                return self.static(os.path.join(ROOT, "demo", "pipeline.html"), "text/html; charset=utf-8")
            if not path.startswith("/api/"):
                raise ApiError(404, "not found")
            parts = [urllib.parse.unquote(p) for p in path[5:].strip("/").split("/")]
            handler = getattr(self, f"api_{method.lower()}_{parts[0]}", None)
            if not handler:
                raise ApiError(404, f"no route {method} {path}")
            who, role = self.user, self.role  # before the handler: logout removes the session
            handler(parts[1:], q)
            if method != "GET" and getattr(self, "_status", 500) < 400:
                self.log_change(method, parts, who, role)
        except ApiError as e:
            self.send_json({"error": e.message}, e.status)
        except F.FormulaError as e:
            self.send_json({"error": "formula: " + str(e)}, 400)
        except Exception as e:  # never crash the server on one request
            traceback.print_exc()
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def log_change(self, method, parts, who, role):
        """Every successful change goes into the shared audit trail."""
        try:
            b = self.json_body() if (self.headers.get("Content-Type") or "").startswith("application/json") else {}
        except ApiError:
            b = {}
        d = describe_change(method, parts, b if isinstance(b, dict) else {})
        if not d:
            return
        if parts[0] == "login":
            name = (b.get("name") or "").strip().lower()
            who = ALIASES.get(name, name)
            role = ACCOUNTS.get(who, "")
        audit(who, role, *d)

    def static(self, path, mime):
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def proxy(self, method):
        """OpenAI-compatible pass-through for the demo's older 'Live' extraction mode."""
        req = urllib.request.Request(CFG["base"] + self.path[3:], data=self.body() or None, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {CFG['key']}")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                status, data = resp.status, resp.read()
        except urllib.error.HTTPError as err:
            status, data = err.code, err.read()
        except Exception as err:
            status, data = 502, json.dumps({"error": str(err)}).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- status, users
    def api_get_status(self, parts, q):
        self.send_json({"ok": True, "model": CFG["model"], "models": MODELS, "key_configured": bool(CFG["key"]),
                        "base": CFG["base"], "law_dir": os.path.relpath(LAW_DIR, ROOT).replace("\\", "/"),
                        "functions": F.FUNC_DOCS, "auth": AUTH, "problems": setup_problems(), "queue": SCHED.stats()})

    def api_post_login(self, parts, q):
        b = self.json_body()
        name = (b.get("name") or "").strip().lower()
        name = ALIASES.get(name, name)
        if name not in ACCOUNTS:
            raise ApiError(401, "unknown user: sign in as istg, dev, sap, lexware or vendor")
        if AUTH and not hmac.compare_digest(str(b.get("password") or "").encode(), PASSWORDS[name].encode()):
            time.sleep(0.5)  # slows down guessing
            raise ApiError(401, "wrong password")
        tok = secrets.token_urlsafe(24)
        with LOCK:
            STORE["sessions"][tok] = {"user": name, "role": ACCOUNTS[name], "t": now(), "vendor": VENDOR_OF.get(name), "fixed": name in VENDOR_OF}
            if len(STORE["sessions"]) > 500:  # keep the newest
                for k in sorted(STORE["sessions"], key=lambda k: STORE["sessions"][k]["t"])[:-500]:
                    STORE["sessions"].pop(k)
            save_store()
        self.send_json({"token": tok, "user": name, "role": ACCOUNTS[name], "vendor": VENDOR_OF.get(name)})

    def api_post_logout(self, parts, q):
        with LOCK:
            STORE["sessions"].pop(self.headers.get("X-Token") or "", None)
            save_store()
        self.send_json({"ok": True})

    def api_get_users(self, parts, q):
        self.send_json(STORE["users"])

    def api_post_users(self, parts, q):
        b = self.json_body()
        name, role = (b.get("name") or "").strip()[:60], b.get("role")
        if not name or role not in ("itsg", "dev", "vendor"):
            raise ApiError(400, "name and role (itsg | dev | vendor) required")
        with LOCK:
            u = next((u for u in STORE["users"] if u["name"].lower() == name.lower()), None)
            if u:
                u["role"], u["seen"] = role, now()
            else:
                u = {"name": name, "role": role, "since": now(), "seen": now()}
                STORE["users"].append(u)
            save_store()
        self.send_json(u)

    # ---- documents
    def api_get_documents(self, parts, q):
        self.send_json(list_docs())

    def api_post_upload(self, parts, q):
        name = os.path.basename((q.get("name") or [""])[0])
        if not name.lower().endswith(DOC_EXT):
            raise ApiError(400, "only .pdf (or .txt) files")
        data = self.body()
        if not data:
            raise ApiError(400, "empty file")
        if name.lower().endswith(".pdf") and not data.startswith(b"%PDF"):
            raise ApiError(400, "this is not a PDF")
        target = (q.get("target") or ["upload"])[0]
        folder = LAW_DIR if target == "law_file" else UPLOADS
        # Parse before replacing an existing document. A rejected upload must not
        # remain in the archive and break every subsequent automatic plan.
        staged = None
        try:
            with tempfile.NamedTemporaryFile(dir=DATA, suffix=os.path.splitext(name)[1], delete=False) as f:
                staged = f.name
                f.write(data)
            try:
                doc = documents.load(staged, CACHE)
            except (ValueError, UnicodeError) as e:
                raise ApiError(400, f"could not read {name}: {e}")
            except Exception as e:
                from pypdf.errors import PyPdfError
                if isinstance(e, PyPdfError):
                    raise ApiError(400, f"could not read {name}: {e}")
                raise
            if not doc["chars"]:
                raise ApiError(400, "PDF has no readable text. Upload a text-based PDF or run OCR first.")
            os.replace(staged, os.path.join(folder, name))
            doc["name"] = name
        finally:
            if staged and os.path.exists(staged):
                os.remove(staged)
        self.send_json({"ok": True, "kind": "law_file" if target == "law_file" else "upload", **documents.summary(doc)})

    def api_delete_upload(self, parts, q):
        p = doc_path("upload", parts[0] if parts else "")
        os.remove(p)
        self.send_json({"ok": True})

    def api_post_plan(self, parts, q):
        b = self.json_body()
        self.send_json(plan_public(plan(b.get("new"), b.get("old"))))

    # ---- runs
    def api_post_runs(self, parts, q):
        self.need_examiner()
        if parts and len(parts) >= 4 and parts[1] == "items" and parts[3] == "generate":
            run = load_run(parts[0])
            if not run:
                raise ApiError(404, "run not found")
            it = item_of(run, parts[2])
            if not it:
                raise ApiError(404, "section not in this run")
            with LOCK:
                if it["status"] in ("queued", "running"):
                    raise ApiError(409, "already in progress")
                # extract the spec change again; it goes back to the examiner before any test case is written
                it["status"], it["cases"], it["decision"] = "queued", [], None
                run["status"], run["stop"] = "running", False
            emit(run, None, "stage", {"step": "queue", "text": f"{self.user} started §{it['sec']} by hand"})
            enqueue(run, it["sec"], "extract")
            return self.send_json({"ok": True})
        if parts and len(parts) == 2 and parts[1] == "stop":
            run = load_run(parts[0])
            if not run:
                raise ApiError(404, "run not found")
            SCHED.cancel(run["id"])  # frees the queue at once; running sections stop at their next check
            with LOCK:
                run["stop"] = True
                for it in run["items"]:
                    if it["status"] == "queued":
                        it["status"] = "review" if it.get("phase") == "cases" else "skipped"
            emit(run, None, "stage", {"step": "stop", "text": f"{self.user} stopped the run"})
            finish_run_if_done(run)
            return self.send_json({"ok": True})
        if parts and len(parts) == 2 and parts[1] == "decide":
            run = self._run(parts[0])
            b = self.json_body()
            decision = b.get("decision")
            if decision not in ("approved", "declined", None):
                raise ApiError(400, "decision must be approved, declined or null")
            with LOCK:
                items = self._review_items(run, b.get("secs"))
                for it in items:
                    it["decision"], it["decided_by"], it["decided_at"] = decision, self.user if decision else None, now() if decision else None
                    emit(run, it["sec"], "decision", {"decision": decision, "by": self.user})
            save_run(run)
            return self.send_json({"ok": True, "changed": [i["sec"] for i in items]})
        if parts and len(parts) == 2 and parts[1] == "cases":
            run = self._run(parts[0])
            b = self.json_body()
            with LOCK:
                items = [i for i in self._review_items(run, b.get("secs")) if i.get("decision") == "approved"]
                if not items:
                    raise ApiError(409, "approve at least one spec change first")
                for it in items:
                    it["status"], it["cases"], it["phase"] = "queued", [], "cases"
                run["status"], run["stop"] = "running", False
            emit(run, None, "stage", {"step": "queue", "text": f"{self.user} approved {len(items)} spec change(s): the AI writes test cases for "
                                      + ", ".join("§" + i["sec"] for i in items)})
            for it in items:
                enqueue(run, it["sec"], "cases")
            return self.send_json({"ok": True, "queued": [i["sec"] for i in items]})
        run = start_run(self.json_body(), self.user)
        self.send_json({"id": run["id"]})

    def _run(self, run_id):
        run = load_run(run_id)
        if not run:
            raise ApiError(404, "run not found")
        return run

    @staticmethod
    def _review_items(run, secs):
        """The items waiting for the examiner, optionally limited to the given sections."""
        items = [i for i in run["items"] if i["status"] == "review" and i.get("spec_change")]
        if secs is not None:
            if not isinstance(secs, list):
                raise ApiError(400, "secs must be a list")
            items = [i for i in items if i["sec"] in secs]
        return items

    def api_patch_runs(self, parts, q):
        """The examiner edits an extracted spec change before approving it."""
        self.need_examiner()
        if len(parts) != 4 or parts[1] != "items" or parts[3] != "change":
            raise ApiError(404, "no such route")
        run = self._run(parts[0])
        b = self.json_body()
        with LOCK:
            it = item_of(run, parts[2])
            if not it or it["status"] != "review" or not it.get("spec_change"):
                raise ApiError(409, "this spec change is not waiting for review")
            sc, changes = edit_spec_change(it, b)
            if changes:
                it["spec_change"], it["change_edited"] = sc, True
                it["decision"] = "approved" if b.get("approve") else None  # an edit needs a fresh approval
                it["decided_by"] = self.user if b.get("approve") else None
                emit(run, it["sec"], "change_edited", {"by": self.user, "changes": changes})
            elif b.get("approve"):
                it["decision"], it["decided_by"] = "approved", self.user
        save_run(run)
        self.send_json({"ok": True, "changes": changes, "spec_change": it["spec_change"], "decision": it.get("decision")})

    def api_get_runs(self, parts, q):
        if not parts:
            return self.send_json(STORE["runs"][:30])
        run = load_run(parts[0])
        if not run:
            raise ApiError(404, "run not found")
        after = int((q.get("after") or ["0"])[0])
        with LOCK:
            run["_seen"] = time.time()
            items =[{k: v for k, v in i.items() if k not in ("old_text", "new_text")} | {"has_old": bool(i.get("old_text"))} for i in run["items"]]
            out = {k: run[k] for k in ("id", "created", "by", "status", "model", "plan", "seq")}
            out["items"] = items
            out["events"] = [e for e in run["events"] if e["seq"] > after]
            out["live"] = dict(run["live"])
        out["queue"] = SCHED.position(run["id"])
        self.send_json(out)

    # ---- test cases
    def api_get_testcases(self, parts, q):
        if parts:
            tc = tc_by_id(parts[0])
            if not tc:
                raise ApiError(404, "test case not found")
            dev = self.role == "dev"
            if len(parts) > 1 and parts[1] == "export":
                return self.send_json(export_case(redact_for_dev(tc) if dev else tc))
            return self.send_json(redact_for_dev(tc) if dev else tc)
        run = (q.get("run") or [None])[0]
        lst = [t for t in STORE["testcases"] if (not run or t["run"] == run) and not t.get("mock")]
        self.send_json([{k: t.get(k) for k in ("id", "run", "status", "title", "kind", "section", "section_title", "expected_value",
                                                 "formula_changed", "formula_edited", "created", "sent_to", "guards", "change_kind")} for t in lst])

    def api_patch_testcases(self, parts, q):
        self.need_examiner()
        tc = tc_by_id(parts[0] if parts else "")
        if not tc:
            raise ApiError(404, "test case not found")
        with LOCK:
            changes = edit_case(tc, self.json_body(), self.user)
            save_store()
        self.send_json({"ok": True, "changes": changes, "testcase": tc})

    def api_post_testcases(self, parts, q):
        tc = tc_by_id(parts[0] if parts else "")
        if not tc or len(parts) < 2:
            raise ApiError(404, "test case not found")
        action, b = parts[1], self.json_body()
        with LOCK:
            if action == "ack":
                if self.user not in tc["sent_to"]:
                    raise ApiError(403, "this test case was not sent to you")
                tc["acks"] = [a for a in tc["acks"] if a["who"] != self.user] + [{"who": self.user, "t": now(), "comment": b.get("comment", ""), "state": b.get("state", "accepted")}]
                tc["history"].append({"t": now(), "who": self.user, "action": "developer: " + b.get("state", "accepted"), "detail": b.get("comment", "")})
                if b.get("state") == "question" or (b.get("comment") or "").strip():
                    tc.setdefault("thread", []).append({"t": now(), "who": self.user, "role": "dev", "kind": b.get("state", "accepted"),
                                                        "text": (b.get("comment") or "").strip()[:2000] or "(question without text)"})
                if all(any(a["who"] == d for a in tc["acks"]) for d in tc["sent_to"]):
                    tc["status"] = "acknowledged"
                save_store()
                return self.send_json(tc)
            self.need_examiner()
            if action == "reply":
                text = (b.get("text") or "").strip()
                if not text:
                    raise ApiError(400, "write an answer")
                tc.setdefault("thread", []).append({"t": now(), "who": self.user, "role": "itsg", "kind": "answer", "text": text[:2000]})
                tc["history"].append({"t": now(), "who": self.user, "action": "answered", "detail": text[:200]})
                save_store()
                return self.send_json(tc)
            if action == "verify":
                recompute(tc)
                if tc.get("formula_error"):
                    raise ApiError(400, "the formula does not evaluate: " + tc["formula_error"])
                failing = [g for g in tc.get("guards", []) if g["status"] == "fail" and not (g["id"] == "G3" and tc.get("formula_edited"))]
                if failing and not (b.get("override_reason") or "").strip():
                    raise ApiError(409, "guards failed (" + ", ".join(g["id"] for g in failing) + "): give a reason to verify anyway")
                tc["status"], tc["verified_by"], tc["verified_at"] = "verified", self.user, now()
                tc["override_reason"] = (b.get("override_reason") or "").strip() or None
                tc["history"].append({"t": now(), "who": self.user, "action": "verified",
                                      "detail": f"expected value {tc.get('expected_value')}" + (f" · override: {tc['override_reason']}" if tc["override_reason"] else "")})
            elif action == "reject":
                if not (b.get("reason") or "").strip():
                    raise ApiError(400, "a reason is required")
                tc["status"] = "rejected"
                tc["history"].append({"t": now(), "who": self.user, "action": "rejected", "detail": b["reason"].strip()})
            elif action == "reopen":
                tc["status"] = "draft"
                tc["history"].append({"t": now(), "who": self.user, "action": "reopened", "detail": b.get("reason", "")})
            else:
                raise ApiError(404, "unknown action")
            save_store()
        self.send_json(tc)

    def api_post_evaluate(self, parts, q):
        b = self.json_body()
        vars_ = b.get("variables") or []
        types = {v["name"]: v.get("type", "number") for v in vars_}
        values = {v["name"]: v.get("value") for v in vars_}
        try:
            _, names = F.parse(b.get("expression", ""))
            value = F.evaluate(b.get("expression", ""), values, types)
            self.send_json({"ok": True, "value": value, "names": names, "trace": F.trace(b["expression"], values, types)})
        except F.FormulaError as e:
            names = []
            try:
                _, names = F.parse(b.get("expression", ""))
            except F.FormulaError:
                pass
            self.send_json({"ok": False, "error": str(e), "names": names})

    # ---- hand-over to developers
    def api_post_send(self, parts, q):
        self.need_examiner()
        b = self.json_body()
        ids, to = b.get("ids") or [], [t for t in (b.get("to") or []) if isinstance(t, str) and t.strip()]
        if not ids or not to:
            raise ApiError(400, "choose test cases and at least one developer")
        with LOCK:
            cases = [tc_by_id(i) for i in ids]
            missing = [i for i, c in zip(ids, cases) if not c]
            if missing:
                raise ApiError(404, "not found: " + ", ".join(missing))
            rejected = [c["id"] for c in cases if c["status"] == "rejected"]
            if rejected:
                raise ApiError(409, "rejected test cases cannot be sent: " + ", ".join(rejected))
            pkg = {"id": "PKG-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4], "t": now(), "by": self.user, "to": to, "ids": ids, "note": (b.get("note") or "").strip() or default_note(cases)}
            STORE["packages"].insert(0, pkg)
            start_recap(pkg)
            for c in cases:
                if c["status"] not in ("verified", "sent", "acknowledged"):  # sending is the examiner's approval
                    c["verified_by"], c["verified_at"] = self.user, now()
                    c["history"].append({"t": now(), "who": self.user, "action": "verified", "detail": "on sending"})
                c["status"] = "sent"
                c["sent_to"] = sorted(set(c["sent_to"]) | set(to))
                c["sent_at"], c["package"] = now(), pkg["id"]
                c["history"].append({"t": now(), "who": self.user, "action": "sent", "detail": "to " + ", ".join(to) + (f" · {pkg['note']}" if pkg["note"] else "")})
            save_store()
        self.send_json(pkg)

    def api_delete_testcases(self, parts, q):
        """Delete a test case: it also leaves the developers' checklists it was sent in."""
        self.need_examiner()
        tc = tc_by_id(parts[0] if parts else "")
        if not tc:
            raise ApiError(404, "test case not found")
        with LOCK:
            STORE["testcases"].remove(tc)
            for p in STORE["packages"]:
                if tc["id"] in p["ids"]:
                    p["ids"].remove(tc["id"])
                    for mine in (p.get("coverage") or {}).values():
                        mine.pop(tc["id"], None)
            STORE["packages"] = [p for p in STORE["packages"] if p["ids"]]
            run = load_run(tc.get("run") or "")
            if run:  # the pipeline screen lists the run's cases
                for it in run.get("items") or []:
                    if tc["id"] in (it.get("cases") or []):
                        it["cases"].remove(tc["id"])
                save_run(run)
            save_store()
        self.send_json({"deleted": tc["id"]})

    # ---- ITSG ⇄ vendor exchange: conversations, result files, package, certificates, the vendor's progress
    @property
    def vendor(self):
        """This request's vendor company: from the sign-in, or (local server without passwords) the page's choice."""
        s = self.session
        if s and s.get("vendor"):
            return s["vendor"]
        if not AUTH:
            v = (self.headers.get("X-Vendor") or "").strip()
            return v if v in VENDORS else None
        return None

    def side(self):
        if self.role == "itsg":
            return "itsg"
        if self.role == "vendor" and self.vendor in VENDORS:
            return "vendor"
        raise ApiError(403, "sign in as ITSG or as a vendor")

    def api_post_session(self, parts, q):
        """A generic vendor sign-in picks its company; a company sign-in (sap, lexware) cannot switch."""
        if parts != ["vendor"]:
            raise ApiError(404, "unknown action")
        v = (self.json_body().get("vendor") or "").strip()
        if v not in VENDORS:
            raise ApiError(400, "unknown vendor")
        if self.role != "vendor":
            raise ApiError(403, "only a vendor sign-in has a company")
        s = self.session
        if s:
            if s.get("fixed") and s.get("vendor") != v:
                raise ApiError(403, f"you are signed in as {VENDORS[s['vendor']]}")
            with LOCK:
                s["vendor"] = v
                save_store()
        self.send_json({"vendor": v, "name": VENDORS[v]})

    def api_get_exchange(self, parts, q):
        side = self.side()
        if parts and parts[0] == "files" and len(parts) == 2:
            f = exchange()["files"].get(parts[1])
            if not f or (side == "vendor" and f["vendor"] != self.vendor):
                raise ApiError(404, "file not found")
            with open(os.path.join(EXCHANGE_DIR, f["key"] + ".bin"), "rb") as fh:
                data = fh.read()
            self._status = 200
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(f["name"]))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if parts:
            raise ApiError(404, "unknown exchange resource")
        self.send_json(exchange_for(self.role, self.vendor))

    def api_post_exchange(self, parts, q):
        side, me = self.side(), self.vendor
        x = exchange()
        what = parts[0] if parts else ""
        if what == "files":  # a result file from a vendor: raw bytes, any of the usual test formats
            if side != "vendor":
                raise ApiError(403, "vendors send result files")
            name = os.path.basename((q.get("name") or [""])[0]).strip()[:120]
            if not name.lower().endswith(RESULT_EXT):
                raise ApiError(400, "send a test result file: " + ", ".join(RESULT_EXT))
            data = self.body()
            if not data:
                raise ApiError(400, "empty file")
            if len(data) > MAX_FILE:
                raise ApiError(413, f"files up to {MAX_FILE // (1024 * 1024)} MB")
            key = re.sub(r"[^\w-]", "", (q.get("key") or [""])[0])[:40] or "F" + uuid.uuid4().hex[:10]
            with LOCK:
                if key in x["files"]:
                    raise ApiError(409, "file key already used")
                os.makedirs(EXCHANGE_DIR, exist_ok=True)
                with open(os.path.join(EXCHANGE_DIR, key + ".bin"), "wb") as fh:
                    fh.write(data)
                f = {"key": key, "name": name, "vendor": me, "by": self.user, "t": now(), "size": len(data),
                     "sha256": hashlib.sha256(data).hexdigest(), "rule": (q.get("rule") or [None])[0],
                     "format": "dta" if name.lower().endswith(DTA_EXT) else os.path.splitext(name)[1].lstrip(".").lower()}
                x["files"][key] = f
                save_store()
            return self.send_json(f)
        if what == "seed":  # the opening conversations, written once by the first page that finds the exchange empty
            b = self.json_body()
            with LOCK:
                if x["threads"]:
                    return self.send_json({"seeded": False})
                for t in (b.get("threads") or [])[:50]:
                    if not isinstance(t, dict) or t.get("vendor") not in VENDORS:
                        continue
                    th = {"id": str(t.get("id"))[:40], "vendor": t["vendor"], "subject": text_of(t.get("subject"), 300), "kind": str(t.get("kind") or "")[:20],
                          "msgs": [], "read": {"itsg": 0, "vendor": 0}}
                    for m in (t.get("msgs") or [])[:20]:
                        if m.get("from") in ("itsg", "system"):
                            new_message(th, m["from"], m.get("body"), [a for a in (m.get("attach") or []) if isinstance(a, dict) and a.get("type") in ("crit", "rule", "case")])
                    x["threads"].append(th)
                save_store()
            return self.send_json({"seeded": True})
        if what == "threads" and len(parts) == 1:
            b = self.json_body()
            vendor = b.get("vendor") if side == "itsg" else me
            if vendor not in VENDORS:
                raise ApiError(400, "unknown vendor")
            tid = re.sub(r"[^\w-]", "", str(b.get("id") or ""))[:40] or "T" + uuid.uuid4().hex[:10]
            with LOCK:
                th = next((t for t in x["threads"] if t["id"] == tid), None)
                if th and th["vendor"] != vendor:
                    raise ApiError(409, "conversation id already used")
                if not th:
                    th = {"id": tid, "vendor": vendor, "subject": text_of(b.get("subject"), 300) or "(no subject)",
                          "kind": str(b.get("kind") or "")[:20], "msgs": [], "read": {"itsg": 0, "vendor": 0}}
                    x["threads"].append(th)
                    save_store()
            return self.send_json(th)
        if what == "threads" and len(parts) == 3:
            th = next((t for t in x["threads"] if t["id"] == parts[1]), None)
            if not th or (side == "vendor" and th["vendor"] != me):
                raise ApiError(404, "conversation not found")
            b = self.json_body()
            if parts[2] == "read":
                with LOCK:
                    th["read"][side] = max(th["read"][side], min(int(b.get("n") or len(th["msgs"])), len(th["msgs"])))
                    save_store()
                return self.send_json({"ok": True})
            if parts[2] != "messages":
                raise ApiError(404, "unknown action")
            attach = check_attach(b.get("attach"), side, me)
            frm = b.get("from")
            if frm == "system":  # the automatic comparison posts its verdict
                if not attach or any(a["type"] != "verdict" for a in attach):
                    raise ApiError(400, "system messages carry comparison verdicts only")
            else:
                frm = "itsg" if side == "itsg" else th["vendor"]
            with LOCK:
                mid = str(b.get("id") or "")
                if mid and any(m["id"] == mid for m in th["msgs"]):
                    return self.send_json(th)  # sent twice (retry): keep one
                new_message(th, frm, b.get("body"), attach, mid or None)
                save_store()
            return self.send_json(th)
        raise ApiError(404, "unknown exchange resource")

    def api_patch_exchange(self, parts, q):
        """Shared state: ITSG publishes the package and issues certificates; a vendor records its own progress."""
        side, me, b, x = self.side(), self.vendor, self.json_body(), exchange()
        with LOCK:
            if side == "itsg":
                if "publishedTo" in b:
                    x["publishedTo"] = [v for v in b.get("publishedTo") or [] if v in VENDORS]
                for v, c in (b.get("certs") or {}).items():
                    if v in VENDORS and isinstance(c, dict):
                        x["certs"][v] = {"seal": str(c.get("seal") or "")[:128], "t": now(), "by": self.user}
                if "vwork" in b:
                    raise ApiError(403, "the vendor records its own progress")
            else:
                if "publishedTo" in b or "certs" in b:
                    raise ApiError(403, "only ITSG publishes packages and issues certificates")
                w = (b.get("vwork") or {}).get(me)
                if isinstance(w, dict):
                    if len(json.dumps(w)) > 200000:
                        raise ApiError(413, "progress record too large")
                    x["vwork"][me] = w
            save_store()
        self.send_json(exchange_for(self.role, me))

    # ---- expected DTA files (built when ITSG sends a package), test reports, certificates
    def api_get_expected(self, parts, q):
        self.need_examiner()
        if parts:
            e = next((x for x in STORE["expected"] if x["id"] == parts[0]), None)
            if not e:
                raise ApiError(404, "expected file not found")
            return self.send_json(e)
        pkg = (q.get("package") or [None])[0]
        self.send_json([{k: v for k, v in e.items() if k != "text"} for e in STORE["expected"] if not pkg or e["package"] == pkg])

    def api_post_expected(self, parts, q):
        self.need_examiner()
        b = self.json_body()
        files = [f for f in (b.get("files") or []) if isinstance(f, dict)][:20]
        if not files:
            raise ApiError(400, "no expected files")
        out = []
        with LOCK:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            for n, f in enumerate(files, start=1):
                name = os.path.basename(str(f.get("name") or ""))[:120]
                text = str(f.get("text") or "")
                if not name.lower().endswith((".dta", ".dat")) or not text.strip():
                    raise ApiError(400, "expected files are .dta files with content")
                e = {"id": f"EXP-{stamp}-{n}-{uuid.uuid4().hex[:4]}", "package": str(b.get("package") or "")[:80], "note": str(b.get("note") or "")[:200],
                     "name": name, "scenario_id": str(f.get("scenario_id") or "")[:60], "title": str(f.get("title") or "")[:200],
                     "rule": str(f.get("rule") or "")[:40], "scenario": f.get("scenario") if isinstance(f.get("scenario"), dict) else None,
                     "text": text[:200000], "size": len(text), "created": now(), "by": self.user}
                e["sha256"] = hashlib.sha256(text.encode("latin-1", "replace")).hexdigest()
                out.append(e)
            STORE["expected"][0:0] = out  # newest package first, its files in their order
            save_store()
        out = [{k: v for k, v in e.items() if k != "text"} for e in out]
        self.send_json(out)

    def api_get_reports(self, parts, q):
        self.need_examiner()
        if parts:
            r = next((x for x in STORE["reports"] if x["id"] == parts[0]), None)
            if not r:
                raise ApiError(404, "report not found")
            return self.send_json(r)
        vendor = (q.get("vendor") or [None])[0]
        self.send_json([r for r in STORE["reports"] if not vendor or r["vendor"] == vendor][:500])

    def api_post_reports(self, parts, q):
        """A test report: one vendor file compared field by field with one expected file."""
        self.need_examiner()
        b = self.json_body()
        if b.get("vendor") not in VENDORS:
            raise ApiError(400, "choose the vendor the file comes from")
        if b.get("verdict") not in ("pass", "fail"):
            raise ApiError(400, "verdict must be pass or fail")
        f = b.get("file") if isinstance(b.get("file"), dict) else {}
        clean = lambda items, keys: [{k: x.get(k) for k in keys if k in x} for x in (items or [])[:200] if isinstance(x, dict)]
        r = {"id": f"REP-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}", "created": now(), "by": self.user,
             "vendor": b["vendor"], "vendor_name": VENDORS[b["vendor"]],
             "expected_id": str(b.get("expected_id") or "builtin")[:60], "expected_name": str(b.get("expected_name") or "")[:120],
             "expected_sha256": str(b.get("expected_sha256") or "")[:64], "scenario_id": str(b.get("scenario_id") or "")[:60],
             "package": str(b.get("package") or "")[:80],
             "file": {"name": str(f.get("name") or "")[:120], "sha256": str(f.get("sha256") or "")[:64], "size": int(f.get("size") or 0)},
             "product": str(b.get("product") or "")[:20], "modification": str(b.get("modification") or "")[:20],
             "abgabegrund": str(b.get("abgabegrund") or "")[:4], "spec": str(b.get("spec") or "")[:80],
             "checks": clean(b.get("checks"), ("id", "ok", "sec", "msg")),
             "findings": clean(b.get("findings"), ("en", "de", "field", "sec", "kind", "expected", "actual")),
             "passed": sum(1 for c in b.get("checks") or [] if isinstance(c, dict) and c.get("ok")),
             "total": len(b.get("checks") or []), "verdict": b["verdict"]}
        r["seal"] = seal_of(r)
        with LOCK:
            STORE["reports"].insert(0, r)
            save_store()
        self.send_json(r)

    def api_get_certificates(self, parts, q):
        self.need_examiner()
        if len(parts) == 2 and parts[1] == "html":
            c = next((x for x in STORE["certificates"] if x["id"] == parts[0]), None)
            if not c:
                raise ApiError(404, "certificate not found")
            data = certificate_html(c).encode("utf-8")
            self._status = 200
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_json(STORE["certificates"])

    def api_post_certificates(self, parts, q):
        self.need_examiner()
        b = self.json_body()
        if parts and len(parts) == 2 and parts[1] == "email":
            c = next((x for x in STORE["certificates"] if x["id"] == parts[0]), None)
            if not c:
                raise ApiError(404, "certificate not found")
            to = str(b.get("to") or "").strip()
            if not EMAIL_RE.match(to):
                raise ApiError(400, "enter a valid e-mail address")
            if not SMTP["host"]:
                raise ApiError(501, "e-mail is not configured on this server (SMTP_HOST in pipeline/.env)")
            try:
                send_certificate_mail(c, to)
            except Exception as e:  # noqa: BLE001 — report the mail server's answer
                raise ApiError(502, f"the mail server refused: {e}")
            with LOCK:
                c.setdefault("emailed", []).append({"to": to, "t": now(), "by": self.user})
                save_store()
            return self.send_json(c)
        vendor = b.get("vendor")
        if vendor not in VENDORS:
            raise ApiError(400, "unknown vendor")
        ids = [i for i in (b.get("reports") or []) if isinstance(i, str)]
        reps = [next((r for r in STORE["reports"] if r["id"] == i), None) for i in ids]
        if not reps or any(r is None for r in reps):
            raise ApiError(400, "certify on the basis of saved test reports")
        if any(r["vendor"] != vendor for r in reps):
            raise ApiError(400, "every report must be for this vendor")
        failed = [r["id"] for r in reps if r["verdict"] != "pass"]
        if failed:
            raise ApiError(409, "not every test passed: " + ", ".join(failed))
        if any(r["seal"] != seal_of(r) for r in reps):
            raise ApiError(409, "a test report was changed after it was sealed")
        c = {"id": f"CERT-{time.strftime('%Y%m%d-%H%M%S')}-{vendor.upper()}", "vendor": vendor, "vendor_name": VENDORS[vendor],
             "product": reps[0]["product"], "modification": reps[0]["modification"],
             "product_name": str(b.get("product_name") or "")[:80], "release": str(b.get("release") or "")[:20],
             "issued": now(), "by": self.user, "valid_from": str(b.get("valid_from") or "2027-01-01")[:10], "valid_to": str(b.get("valid_to") or "2027-12-31")[:10],
             "reports": [{"id": r["id"], "scenario_id": r["scenario_id"], "expected_name": r["expected_name"], "file": r["file"]["name"], "seal": r["seal"]} for r in reps]}
        c["seal"] = seal_of(c)
        with LOCK:
            STORE["certificates"].insert(0, c)
            save_store()
        self.send_json(c)

    def api_get_audit(self, parts, q):
        self.need_examiner()
        log = STORE["audit"]
        ok, bad = audit_chain(log)
        n = min(int((q.get("limit") or ["300"])[0]), 2000)
        self.send_json({"entries": log[::-1][:n], "total": len(log), "chain_ok": ok, "broken_at": bad})

    def api_get_tracking(self, parts, q):
        """ITSG: the packages sent to developers, with their progress, answers and questions."""
        self.need_examiner()
        pkgs = sorted((p for p in STORE["packages"] if not p.get("mock")), key=lambda p: p.get("t") or "", reverse=True)
        self.send_json([tracking(p) for p in pkgs[:100]])

    def api_get_packages(self, parts, q):
        if parts:
            pkg = next((p for p in STORE["packages"] if p["id"] == parts[0]), None)
            if not pkg:
                raise ApiError(404, "package not found")
            fix = redact_for_dev if self.role == "dev" else (lambda t: t)
            return self.send_json({**pkg, "testcases": [export_case(fix(tc_by_id(i))) for i in pkg["ids"] if tc_by_id(i)]})
        self.send_json([p for p in STORE["packages"] if not p.get("mock")][:50])

    def api_get_inbox(self, parts, q):
        user = (q.get("user") or [self.user])[0]
        if self.role == "dev":
            with LOCK:
                seed_history(user)
        lst = sorted((t for t in STORE["testcases"] if user in t.get("sent_to", [])), key=lambda t: t.get("sent_at") or "", reverse=True)
        self.send_json([{**{k: t.get(k) for k in ("id", "status", "title", "kind", "section", "section_title",
                                                  "formula_changed", "formula_edited", "sent_at", "package", "document")},
                         "my_ack": next((a for a in t.get("acks", []) if a["who"] == user), None),
                         "last_answer": next((m["t"] for m in reversed(t.get("thread", [])) if m["role"] == "itsg"), None)} for t in lst])

    # ---- developer checklist → submission → ITSG validation → results back to the developer
    def api_get_checklists(self, parts, q):
        user = (q.get("user") or [self.user])[0]
        with LOCK:
            seed_history(user)
        out = []
        for p in STORE["packages"]:
            if user not in p["to"]:
                continue
            if not p.get("recap"):  # packages sent before briefings existed
                with LOCK:
                    start_recap(p)
            sub = next((s for s in STORE["submissions"] if s["package"] == p["id"] and s["by"] == user), None)
            out.append({**{k: v for k, v in p.items() if k != "coverage"}, "covered": (p.get("coverage") or {}).get(user, {}),
                        "rows": [checklist_row(tc_by_id(i)) for i in p["ids"] if tc_by_id(i)],
                        "submission": public_submission(sub, with_expected=False) if sub else None})
        out.sort(key=lambda p: p.get("t") or "", reverse=True)  # newest first: the mock history sits below the new packages
        self.send_json(out)

    def api_post_checklists(self, parts, q):
        if len(parts) != 2 or parts[1] not in ("submit", "recap", "coverage"):
            raise ApiError(404, "unknown action")
        pkg = next((p for p in STORE["packages"] if p["id"] == parts[0]), None)
        if not pkg:
            raise ApiError(404, "checklist not found")
        if self.user not in pkg["to"]:
            raise ApiError(403, "this checklist was not sent to you")
        if parts[1] == "coverage":  # the developer's own tracking: "I have covered this case", not pass/fail
            b = self.json_body()
            if b.get("id") not in pkg["ids"]:
                raise ApiError(404, "test case not in this checklist")
            with LOCK:
                mine = pkg.setdefault("coverage", {}).setdefault(self.user, {})
                if b.get("done"):
                    mine[b["id"]] = now()
                else:
                    mine.pop(b["id"], None)
                save_store()
            return self.send_json(mine)
        if parts[1] == "recap":  # write the briefing again
            with LOCK:
                if (pkg.get("recap") or {}).get("status") != "pending":
                    start_recap(pkg)
            return self.send_json(pkg["recap"])
        rows = [r for r in (self.json_body().get("rows") or []) if isinstance(r, dict) and r.get("id") in pkg["ids"]]
        if not rows or not any(str(r.get("value", "")).strip() for r in rows):
            raise ApiError(400, "enter at least one value")
        with LOCK:
            if any(s["package"] == pkg["id"] and s["by"] == self.user and s["status"] == "validated" for s in STORE["submissions"]):
                raise ApiError(409, "ITSG has already validated this checklist")
            STORE["submissions"] = [s for s in STORE["submissions"] if not (s["package"] == pkg["id"] and s["by"] == self.user)]
            sub = {"id": "SUB-" + time.strftime("%Y%m%d-%H%M%S"), "package": pkg["id"], "by": self.user, "t": now(), "status": "submitted",
                   "rows": [{"id": r["id"], "value": str(r.get("value", "")).strip(), "note": str(r.get("note", "")).strip()[:500]} for r in rows]}
            STORE["submissions"].insert(0, sub)
            for r in sub["rows"]:
                tc = tc_by_id(r["id"])
                tc["history"].append({"t": now(), "who": self.user, "action": "developer result submitted", "detail": f"value {r['value'] or '—'}"})
            save_store()
        self.send_json(public_submission(sub, with_expected=False))

    def api_get_submissions(self, parts, q):
        self.need_examiner()
        if not parts:
            return self.send_json([{k: s[k] for k in ("id", "package", "by", "t", "status")} | {"n": len(s["rows"]), "seen": s.get("seen", False)}
                                   for s in STORE["submissions"]])
        sub = next((s for s in STORE["submissions"] if s["id"] == parts[0]), None)
        if not sub:
            raise ApiError(404, "submission not found")
        with_expected = (q.get("expected") or ["0"])[0] == "1" or sub["status"] == "validated"
        if not sub.get("seen"):
            sub["seen"] = True
            save_store()
        self.send_json(public_submission(sub, with_expected))

    def api_post_submissions(self, parts, q):
        self.need_examiner()
        sub = next((s for s in STORE["submissions"] if s["id"] == (parts[0] if parts else "")), None)
        if not sub or len(parts) < 2 or parts[1] != "validate":
            raise ApiError(404, "submission not found")
        verdicts = {r.get("id"): r for r in (self.json_body().get("rows") or []) if isinstance(r, dict)}
        with LOCK:
            full = public_submission(sub, with_expected=True)
            rows = []
            for r in full["rows"]:
                v = verdicts.get(r["id"], {})
                verdict = v.get("verdict") if v.get("verdict") in ("pass", "fail") else r["auto_verdict"]
                rows.append({"id": r["id"], "expected": r["expected"], "value": r["value"], "auto_verdict": r["auto_verdict"],
                             "verdict": verdict, "comment": str(v.get("comment", "")).strip()[:500]})
                tc = tc_by_id(r["id"])
                tc.setdefault("dev_results", []).append({"dev": sub["by"], "t": now(), "value": r["value"], "verdict": verdict})
                tc["history"].append({"t": now(), "who": self.user, "action": f"developer result {verdict}",
                                      "detail": f"{sub['by']}: {r['value'] or '—'} vs expected {r['expected']}"})
            sub["validation"] = {"by": self.user, "t": now(), "rows": rows}
            sub["status"] = "validated"
            save_store()
        self.send_json(public_submission(sub, with_expected=True))

    def api_get_results(self, parts, q):
        """What a developer sees after ITSG validated: last passed and failed tests."""
        user = (q.get("user") or [self.user])[0]
        out = []
        for s in STORE["submissions"]:
            if s["by"] != user or s["status"] != "validated":
                continue
            for r in s["validation"]["rows"]:
                tc = tc_by_id(r["id"]) or {}
                out.append({"id": r["id"], "title": tc.get("title"), "section": tc.get("section"), "package": s["package"],
                            "value": r["value"], "expected": r["expected"], "verdict": r["verdict"], "comment": r["comment"],
                            "validated_by": s["validation"]["by"], "t": s["validation"]["t"], "version": (tc.get("document") or {}).get("version")})
        self.send_json(out)

    def api_post_demo(self, parts, q):
        """Seed a demo checklist (ITSG reference case) for a developer, so the demo never depends on the AI."""
        user = (self.json_body().get("user") or self.user).strip()
        if not user or user == "anonymous":
            raise ApiError(400, "log in first")
        with LOCK:
            pkg = seed_demo(user)
            save_store()
        self.send_json(pkg)


def setup_problems():
    """What stops the pipeline from running on a fresh clone, with the fix (shown at start and on the page)."""
    out = []
    if not CFG["key"]:
        out.append("No API key: copy pipeline/.env.example to pipeline/.env and set HAI_API_KEY (ask a teammate for the key).")
    try:
        import pypdf  # noqa: F401
    except ImportError:
        out.append(f"pypdf is not installed: run  {os.path.basename(sys.executable)} -m pip install -r pipeline/requirements.txt")
    return out


def warm_cache():
    """Parse the archived spec versions at start-up, so the first runs do not wait for pypdf."""
    for d in list_docs()["law_files"]:
        try:
            load_doc(d)
        except Exception as e:  # noqa: BLE001 — a broken file is reported when someone uses it
            print(f"  ! could not read {d['name']}: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default=os.environ.get("PIPELINE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PIPELINE_PORT", "8787")))
    a = ap.parse_args()
    print(f"EEL pipeline on http://{'localhost' if a.host == '127.0.0.1' else a.host}:{a.port}  "
          f"(model {CFG['model']}, key {'configured' if CFG['key'] else 'MISSING'}, law files: {LAW_DIR})", file=sys.stderr)
    for problem in setup_problems():
        print("  ! " + problem, file=sys.stderr)
    # on Windows reuse lets two servers share a port silently; on Linux it only lets a restart bind while the
    # old connections are still closing (TIME_WAIT), so keep it there
    ThreadingHTTPServer.allow_reuse_address = os.name != "nt"
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.request_queue_size = 128  # a room full of phones polling at once
    try:
        srv = ThreadingHTTPServer((a.host, a.port), Handler)
    except OSError as e:
        sys.exit(f"Port {a.port} is in use ({e}). Is the pipeline already running? Use --port to pick another.")
    threading.Thread(target=persister, name="persister", daemon=True).start()
    threading.Thread(target=warm_cache, name="warm-cache", daemon=True).start()
    # docker stop sends SIGTERM: stop serving, then write what is still unsaved (shutdown() must not run on this thread)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown).start())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        flush_all()
        print("EEL pipeline stopped, data saved", file=sys.stderr)


if __name__ == "__main__":
    main()
