"""EEL test-case pipeline: local server for the demo page.

    python pipeline/server.py                 → http://localhost:8787
    python pipeline/server.py --host 0.0.0.0  → reachable by the developers on your network

What it does
- serves demo/index.html and a JSON API for the "AI test pipeline" and "Developer inbox" screens;
- reads the previous spec versions in docs/law_file/ and the PDFs dropped into the page;
- diffs them section by section (or, with nothing to compare, uses the document's own change log);
- lets the AI turn each change into a spec-change JSON and test cases, with a sandboxed Python
  terminal for calculations; the chain of thought is streamed to the page and saved per test case;
- keeps test cases, examiner edits, verification and the hand-over to developers in pipeline/data/.

The API key is read from pipeline/.env or the environment (HAI_API_KEY) and never sent to the browser.
Standard library + pypdf.
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import agent  # noqa: E402
import documents  # noqa: E402
import formula as F  # noqa: E402


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
POOL = ThreadPoolExecutor(max_workers=2)
RUNS = {}  # run id → run (in memory; finished runs are also written to data/runs/)


# ------------------------------------------------------------------ persistence

def _load_store():
    if os.path.exists(STORE_PATH):
        with open(STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"users": [], "testcases": [], "packages": [], "runs": []}


STORE = _load_store()


def save_store():
    with LOCK:
        tmp = STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(STORE, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STORE_PATH)


def save_run(run):
    os.makedirs(os.path.join(DATA, "runs"), exist_ok=True)
    with LOCK:
        snap = json.dumps(run, ensure_ascii=False, default=str)
    with open(os.path.join(DATA, "runs", run["id"] + ".json"), "w", encoding="utf-8") as f:
        f.write(snap)


def load_run(run_id):
    if run_id in RUNS:
        return RUNS[run_id]
    path = os.path.join(DATA, "runs", re.sub(r"[^\w-]", "", run_id) + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        if run.get("status") in ("running", "queued"):
            run["status"] = "interrupted"
        RUNS[run_id] = run
        return run
    return None


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
    max_items = max(1, min(int(body.get("max_items") or 4), 20))
    if p["mode"] == "diff":
        items = documents.diff_documents(p["old"], p["new"], p["new"]["changelog"])
        if not items:
            p = {**p, "mode": "single", "old": None,
                 "reason": p["reason"] + " · no text differences found, so the document is used on its own"}
    if p["mode"] == "single":
        items = documents.single_document_items(p["new"])
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    run = {"id": run_id, "created": now(), "by": user, "status": "running", "model": model, "lang": body.get("lang", "en"),
           "plan": plan_public(p), "items": [], "events": [], "seq": 0, "live": {}, "stop": False}
    for i, it in enumerate(items[:200]):
        run["items"].append({**it, "status": "queued" if i < max_items else "candidate", "cases": [], "spec_change": None})
    RUNS[run_id] = run
    with LOCK:
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
        POOL.submit(process_item, run, it["sec"])
    if not queued:
        finish_run_if_done(run)
    return run


def finish_run_if_done(run):
    with LOCK:
        if all(i["status"] in ("done", "error", "candidate", "skipped", "stopped") for i in run["items"]) and run["status"] == "running":
            run["status"] = "stopped" if run.get("stop") else "done"
            run["seq"] += 1
            n = sum(len(i["cases"]) for i in run["items"])
            text = (f"Stopped: {n} test case(s) kept for review" if run.get("stop") else f"Finished: {n} test case(s) waiting for review")
            run["events"].append({"seq": run["seq"], "t": now(), "item": None, "type": "stage",
                                  "data": {"step": "stop" if run.get("stop") else "done", "text": text}})
    if run["status"] in ("done", "stopped"):
        save_run(run)


def process_item(run, sec):
    it = item_of(run, sec)
    if run.get("stop"):
        it["status"] = "skipped"
        finish_run_if_done(run)
        return
    it["status"] = "running"
    run["status"] = "running"
    start_seq = run["seq"]
    plan_ = run["plan"]
    new_doc = {"name": plan_["new"]["name"], "version": plan_["new"]["version"]}
    old_doc = {"name": plan_["old"]["name"], "version": plan_["old"]["version"]} if plan_["old"] else None
    emit(run, sec, "item_start", {"sec": sec, "title": it["title"], "kind": it["kind"], "source": it["source"], "model": run["model"]})
    try:
        cfg = dict(CFG, model=run["model"])
        res = agent.run_item(cfg, it, new_doc, old_doc, lambda t, d: emit(run, sec, t, d), lang=run.get("lang", "en"),
                             should_stop=lambda: run.get("stop"))
    except Exception as e:  # keep the run alive; show the error in the chain of thought
        traceback.print_exc()
        emit(run, sec, "error", {"message": f"{type(e).__name__}: {e}"})
        res = {"spec_change": None, "cases": [], "summary": "", "error": str(e)}
    with LOCK:
        cot_all = [e for e in run["events"] if e["item"] == sec and e["seq"] > start_seq]
        it["spec_change"] = res["spec_change"]
        for n, case in enumerate(res["cases"], start=1):
            tc_id = f"TC-{sec}-{run['id'][2:8]}{run['id'][-4:]}-{n}"
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
        it["status"] = "stopped" if res.get("stopped") else "error" if res.get("error") and not res["cases"] else "done"
        it["summary"] = res.get("summary", "")
        save_store()
    emit(run, sec, "item_done", {"sec": sec, "cases": it["cases"], "summary": it.get("summary", ""), "status": it["status"]})
    finish_run_if_done(run)


# ------------------------------------------------------------------ test cases

def recompute(tc):
    fm = tc.get("formula") or {}
    try:
        types = {v["name"]: v.get("type", "number") for v in fm.get("variables") or []}
        values = {v["name"]: v.get("value") for v in fm.get("variables") or []}
        tc["expected_value"] = F.evaluate(fm.get("expression", ""), values, types)
        tc["formula_error"] = None
        tc["trace"] = F.trace(fm.get("expression", ""), values, types)
    except (F.FormulaError, KeyError, TypeError) as e:
        tc["expected_value"] = None
        tc["formula_error"] = str(e)
        tc["trace"] = []


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
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def json_body(self):
        raw = self.body()
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError(400, "body is not JSON")

    @property
    def user(self):
        return urllib.parse.unquote(self.headers.get("X-User") or "") or "anonymous"

    @property
    def role(self):
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
        try:
            if path.startswith("/v1/"):
                return self.proxy(method)
            if method == "GET" and path in ("/", "/index.html", "/demo/", "/demo/index.html"):
                return self.static(os.path.join(ROOT, "demo", "index.html"), "text/html; charset=utf-8")
            if not path.startswith("/api/"):
                raise ApiError(404, "not found")
            parts = [urllib.parse.unquote(p) for p in path[5:].strip("/").split("/")]
            handler = getattr(self, f"api_{method.lower()}_{parts[0]}", None)
            if not handler:
                raise ApiError(404, f"no route {method} {path}")
            return handler(parts[1:], q)
        except ApiError as e:
            self.send_json({"error": e.message}, e.status)
        except F.FormulaError as e:
            self.send_json({"error": "formula: " + str(e)}, 400)
        except Exception as e:  # never crash the server on one request
            traceback.print_exc()
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

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
                        "functions": F.FUNC_DOCS})

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
        with open(os.path.join(folder, name), "wb") as f:
            f.write(data)
        doc = documents.load(os.path.join(folder, name), CACHE)
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
            if it["status"] in ("queued", "running"):
                raise ApiError(409, "already in progress")
            it["status"], it["cases"] = "queued", []
            run["status"], run["stop"] = "running", False
            emit(run, None, "stage", {"step": "queue", "text": f"{self.user} started §{it['sec']} by hand"})
            POOL.submit(process_item, run, it["sec"])
            return self.send_json({"ok": True})
        if parts and len(parts) == 2 and parts[1] == "stop":
            run = load_run(parts[0])
            if not run:
                raise ApiError(404, "run not found")
            run["stop"] = True
            for it in run["items"]:
                if it["status"] == "queued":
                    it["status"] = "skipped"
            emit(run, None, "stage", {"step": "stop", "text": f"{self.user} stopped the run"})
            finish_run_if_done(run)
            return self.send_json({"ok": True})
        run = start_run(self.json_body(), self.user)
        self.send_json({"id": run["id"]})

    def api_get_runs(self, parts, q):
        if not parts:
            return self.send_json(STORE["runs"][:30])
        run = load_run(parts[0])
        if not run:
            raise ApiError(404, "run not found")
        after = int((q.get("after") or ["0"])[0])
        with LOCK:
            items = [{k: v for k, v in i.items() if k not in ("old_text", "new_text")} | {"has_old": bool(i.get("old_text"))} for i in run["items"]]
            out = {k: run[k] for k in ("id", "created", "by", "status", "model", "plan", "seq")}
            out["items"] = items
            out["events"] = [e for e in run["events"] if e["seq"] > after]
            out["live"] = dict(run["live"])
        self.send_json(out)

    # ---- test cases
    def api_get_testcases(self, parts, q):
        if parts:
            tc = tc_by_id(parts[0])
            if not tc:
                raise ApiError(404, "test case not found")
            if len(parts) > 1 and parts[1] == "export":
                return self.send_json(export_case(tc))
            return self.send_json(tc)
        run = (q.get("run") or [None])[0]
        lst = [t for t in STORE["testcases"] if not run or t["run"] == run]
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
                if all(any(a["who"] == d for a in tc["acks"]) for d in tc["sent_to"]):
                    tc["status"] = "acknowledged"
                save_store()
                return self.send_json(tc)
            self.need_examiner()
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
            unverified = [c["id"] for c in cases if c["status"] not in ("verified", "sent", "acknowledged")]
            if unverified:
                raise ApiError(409, "verify these first: " + ", ".join(unverified))
            pkg = {"id": "PKG-" + time.strftime("%Y%m%d-%H%M%S"), "t": now(), "by": self.user, "to": to, "ids": ids, "note": b.get("note", "")}
            STORE["packages"].insert(0, pkg)
            for c in cases:
                c["status"] = "sent"
                c["sent_to"] = sorted(set(c["sent_to"]) | set(to))
                c["sent_at"], c["package"] = now(), pkg["id"]
                c["history"].append({"t": now(), "who": self.user, "action": "sent", "detail": "to " + ", ".join(to) + (f" · {pkg['note']}" if pkg["note"] else "")})
            save_store()
        self.send_json(pkg)

    def api_get_packages(self, parts, q):
        if parts:
            pkg = next((p for p in STORE["packages"] if p["id"] == parts[0]), None)
            if not pkg:
                raise ApiError(404, "package not found")
            return self.send_json({**pkg, "testcases": [export_case(tc_by_id(i)) for i in pkg["ids"] if tc_by_id(i)]})
        self.send_json(STORE["packages"][:50])

    def api_get_inbox(self, parts, q):
        user = (q.get("user") or [self.user])[0]
        lst = [t for t in STORE["testcases"] if user in t.get("sent_to", [])]
        self.send_json([{**{k: t.get(k) for k in ("id", "status", "title", "kind", "section", "section_title", "expected_value",
                                                  "formula_changed", "formula_edited", "sent_at", "package", "document")},
                         "my_ack": next((a for a in t.get("acks", []) if a["who"] == user), None)} for t in lst])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default=os.environ.get("PIPELINE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PIPELINE_PORT", "8787")))
    a = ap.parse_args()
    print(f"EEL pipeline on http://{'localhost' if a.host == '127.0.0.1' else a.host}:{a.port}  "
          f"(model {CFG['model']}, key {'configured' if CFG['key'] else 'MISSING'}, law files: {LAW_DIR})", file=sys.stderr)
    ThreadingHTTPServer.allow_reuse_address = False  # on Windows reuse lets two servers share a port silently
    ThreadingHTTPServer.daemon_threads = True
    try:
        srv = ThreadingHTTPServer((a.host, a.port), Handler)
    except OSError as e:
        sys.exit(f"Port {a.port} is in use ({e}). Is the pipeline already running? Use --port to pick another.")
    srv.serve_forever()


if __name__ == "__main__":
    main()
