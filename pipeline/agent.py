"""The AI step: one changed spec section in → spec-change JSON + test cases out.

The model works through tool calls and explains every step (its chain of thought is shown to
the examiner and saved with each test case):

    run_python          the AI's terminal, for working out and checking a formula
    record_spec_change  what changed, as JSON, with verbatim quotes
    submit_test_case    a scenario + a formula in named variables + the expected value
    finish

The model's expected value is never trusted on its own. Deterministic guards re-check every
submission (quotes verbatim in the spec, formula valid, oracle evaluation equals the model's
value, numbers appear in their quotes, the formula was tried in the terminal) and the result is
sent back to the model so it can fix its answer.
"""
import json
import re
import socket
import time
import urllib.error
import urllib.request

import documents
import formula as F
import sandbox

MAX_TURNS = 16
CHANGE_TYPES = ["parameter", "condition", "formula", "new_rule", "removed_rule", "format", "clarification", "editorial"]

TOOLS = [
    {"type": "function", "function": {
        "name": "run_python",
        "description": ("Your terminal. Runs a short Python 3 script and returns stdout/stderr. Use it for every "
                        "calculation (dates, day counts, amounts). Allowed imports: math, datetime, decimal, "
                        "fractions, statistics, calendar, json, itertools, functools, re. The pipeline's formula "
                        "evaluator is preloaded: evaluate(expression, **variables) returns exactly what the "
                        "oracle will compute for your test case, so call it on your final formula. Print your results."),
        "parameters": {"type": "object", "required": ["reasoning", "code"], "properties": {
            "reasoning": {"type": "string", "description": "What you are calculating and why (shown to the examiner)."},
            "code": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "record_spec_change",
        "description": "Record what changed in this section (or, without an old version, which testable rule it states). Call once, before any test case.",
        "parameters": {"type": "object", "required": ["reasoning", "change_type", "summary", "new_rule", "quotes_new"], "properties": {
            "reasoning": {"type": "string", "description": "How you compared old and new text, step by step."},
            "change_type": {"type": "string", "enum": CHANGE_TYPES},
            "summary": {"type": "string", "description": "One or two sentences: what changed and what it means for payroll software."},
            "old_rule": {"type": "string", "description": "The rule before the change, in plain words (empty if no old version)."},
            "new_rule": {"type": "string", "description": "The rule after the change, in plain words."},
            "quotes_new": {"type": "array", "items": {"type": "string"}, "description": "Sentences copied character for character from the NEW text."},
            "quotes_old": {"type": "array", "items": {"type": "string"}, "description": "Sentences copied character for character from the OLD text."},
            "parameters": {"type": "array", "description": "Every number or limit that changed or that the rule depends on.", "items": {
                "type": "object", "required": ["name", "new_value"], "properties": {
                    "name": {"type": "string", "description": "snake_case, reused as a formula variable name"},
                    "old_value": {"type": "string"}, "new_value": {"type": "string"}, "unit": {"type": "string"},
                    "quote": {"type": "string", "description": "Verbatim sentence that contains the value."}}}},
            "formula_changed": {"type": "boolean", "description": "True if the way a value is calculated changed."}}}}},
    {"type": "function", "function": {
        "name": "submit_test_case",
        "description": ("Submit one test case. The scenario must be concrete (real dates and amounts). The expected "
                        "result is defined by `formula` over `variables`; `expected_value` must be the value you got "
                        "from evaluate() in your terminal. Submit 1-3 cases: positive, negative, and a boundary case "
                        "where the change flips the result."),
        "parameters": {"type": "object", "required": ["reasoning", "title", "kind", "criterion", "scenario", "formula", "expected_value", "quotes"], "properties": {
            "reasoning": {"type": "string", "description": "Why this case tests the change and how the expected value follows."},
            "title": {"type": "string"},
            "kind": {"type": "string", "enum": ["positive", "negative", "boundary"]},
            "criterion": {"type": "string", "description": "Testable criterion, in the style 'The system ensures that …'."},
            "scenario": {"type": "object", "description": "The employee / absence / payroll situation the tester enters, as key-value pairs.", "additionalProperties": True},
            "formula": {"type": "object", "required": ["expression", "result_name", "variables"], "properties": {
                "expression": {"type": "string", "description": "One expression in the formula language (see the system prompt)."},
                "result_name": {"type": "string"}, "result_unit": {"type": "string"},
                "variables": {"type": "array", "items": {"type": "object", "required": ["name", "type", "value"], "properties": {
                    "name": {"type": "string"}, "type": {"type": "string", "enum": ["number", "date", "bool"]},
                    "value": {"type": "string", "description": "number as text, date as YYYY-MM-DD, bool as true/false"},
                    "unit": {"type": "string"}, "description": {"type": "string"},
                    "source": {"type": "string", "enum": ["spec", "scenario"], "description": "spec = a legal parameter from the text, scenario = test data"},
                    "quote": {"type": "string", "description": "for spec parameters: the verbatim sentence it comes from"}}}}}},
            "previous_expression": {"type": "string", "description": "The formula under the OLD version, if it was different."},
            "formula_changed": {"type": "boolean"},
            "expected_value": {"type": "string", "description": "The value evaluate() printed in your terminal."},
            "expected_outcome": {"type": "string", "description": "What the payroll software must do or report, in words."},
            "quotes": {"type": "array", "items": {"type": "string"}, "description": "Verbatim sentences from the NEW text this case is based on."},
            "replaces": {"type": "string", "description": "Id of an earlier submission this one corrects."}}}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Call when all test cases for this section are submitted, or if the section has no testable rule.",
        "parameters": {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string"}}}}},
]


def system_prompt(lang):
    funcs = "\n".join(f"  {k:24s} {v}" for k, v in F.FUNC_DOCS.items())
    language = "German" if lang == "de" else "English"
    return f"""You are a test-case engineer at ITSG, which certifies German payroll software for the DTA EEL
procedure (income replacement benefits, § 107 SGB IV). Zero tolerance: one wrong day or cent fails a vendor.

You receive ONE section of a specification document in its new version and, if available, its previous
version with a word diff. Your job: find what changed, describe it as structured data, and write test
cases that prove a payroll program implements the NEW rule.

Work step by step and think aloud. The examiner reads your reasoning, so put it in the `reasoning`
argument of every tool call. Write your reasoning in {language}; keep quotes from the spec verbatim in German.

Procedure:
1. Read old and new text. Call record_spec_change once. Quotes must be copied character for character.
2. If a value must be calculated (dates, deadlines, day counts, amounts, percentages), write it as ONE
   formula over named variables. Legal parameters from the text (e.g. 42 days, 6 months, 70 %) are
   variables with source "spec" and a quote; test data (dates, salaries) are variables with source "scenario".
3. Check the formula in your terminal with run_python: print(evaluate("<expression>", var=value, ...)).
   Also test the boundary where the change flips the result.
4. Call submit_test_case for each case (1-3 cases). expected_value = what evaluate() printed.
   If the formula differs from the old rule, set formula_changed and give previous_expression.
5. Call finish.

Do not invent rules that are not in the text. If the change is purely editorial and nothing can be tested,
say so in record_spec_change (change_type "editorial") and call finish.

Formula language (one expression; numbers are exact decimals; dates are 'YYYY-MM-DD'):
  + - * / // % **, comparisons, and / or / not, `a if condition else b`
  date ± whole days, date - date = days
{funcs}
Example: sick pay ends after 42 days minus creditable prior days, counting the first day:
  add_days(au_start, efz_days - prior_days - 1)   with au_start=2026-03-11, efz_days=42, prior_days=25 → 2026-03-27
"""


def user_prompt(item, new_doc, old_doc):
    parts = [f"Document (new): {new_doc['name']} · version {new_doc.get('version') or '?'}"]
    if old_doc:
        parts.append(f"Document (previous): {old_doc['name']} · version {old_doc.get('version') or '?'}")
    parts.append(f"Section: {item['sec']} {item['title']} (page {item['page']}) · detected as: {item['kind']} · source: {item['source']}")
    if item.get("log"):
        parts.append("Change log entries for this section:\n" + "\n".join("- " + l for l in item["log"]))
    if item["kind"] == "changed":
        red = []
        for op, text in item["ops"]:
            if op == "=":
                w = text.split(" ")
                red.append(text if len(w) <= 24 else " ".join(w[:10]) + " […] " + " ".join(w[-10:]))
            else:
                red.append(("[-" if op == "-" else "{+") + text + ("-]" if op == "-" else "+}"))
        parts.append("WORD DIFF ([-removed-] {+added+}):\n" + " ".join(red))
        parts.append("OLD TEXT:\n" + item["old_text"])
        parts.append("NEW TEXT:\n" + item["new_text"])
    elif item["kind"] == "removed":
        parts.append("This section was REMOVED. OLD TEXT:\n" + item["old_text"])
    elif item["kind"] == "added":
        parts.append("This section is NEW. NEW TEXT:\n" + item["new_text"])
    else:
        parts.append("No previous version is available. Derive test cases from the rules this section states"
                     + (" and from the change log entries above." if item.get("log") else ".")
                     + "\nTEXT:\n" + item["new_text"])
    return "\n\n".join(parts)


class LLMError(RuntimeError):
    pass


def chat(cfg, messages, on_delta=None):
    """One streamed chat completion. Returns {reasoning, content, tool_calls}."""
    body = {"model": cfg["model"], "messages": messages, "tools": TOOLS, "tool_choice": cfg.get("tool_choice", "required"),
            "temperature": 0, "max_tokens": 16000, "stream": True}
    req = urllib.request.Request(cfg["base"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["key"],
                                          "Accept": "text/event-stream"})
    out = {"reasoning": "", "content": "", "tool_calls": {}, "finish_reason": None}
    last = 0.0
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise LLMError(str(chunk["error"]))
                for ch in chunk.get("choices") or []:
                    d = ch.get("delta") or ch.get("message") or {}
                    out["finish_reason"] = ch.get("finish_reason") or out["finish_reason"]
                    out["reasoning"] += d.get("reasoning") or d.get("reasoning_content") or ""
                    out["content"] += d.get("content") or ""
                    for tc in d.get("tool_calls") or []:
                        slot = out["tool_calls"].setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                        slot["id"] = tc.get("id") or slot["id"]
                        fn = tc.get("function") or {}
                        slot["name"] += fn.get("name") or ""
                        slot["arguments"] += fn.get("arguments") or ""
                if on_delta and time.time() - last > 0.25:
                    last = time.time()
                    on_delta(out)
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        raise LLMError(f"network: {e}")
    calls = [out["tool_calls"][k] for k in sorted(out["tool_calls"])]
    for i, c in enumerate(calls):
        c["id"] = c["id"] or f"call_{int(time.time() * 1000)}_{i}"
    out["tool_calls"] = calls
    if on_delta:
        on_delta(out)
    return out


def _parse_args(raw):
    if isinstance(raw, dict):
        return raw
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group(0))
        raise


# ------------------------------------------------------------------ guards (deterministic)

NUMBER_WORDS = {"ein": 1, "eine": 1, "einen": 1, "einem": 1, "einer": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
                "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "zwanzig": 20,
                "dreißig": 30, "vierzig": 40, "fünfzig": 50, "hundert": 100}


def _loose(s):
    # also join hyphenation whose line break the PDF text lost: "über- mittelt" = "übermittelt"
    return re.sub(r"(\w)- (?=[a-zäöüß])", r"\1", documents.normalize_text(s))


def quote_in(quote, *texts):
    """A quote is verbatim if every part between ellipses is in the text (whitespace/hyphenation-insensitive)."""
    q = _loose(quote or "").strip(" „“\"'")
    if len(q) < 8:
        return False
    hay = [_loose(t) for t in texts if t]
    parts = [p.strip() for p in re.split(r"\s*(?:\.\.\.|…|\[…\]|\[\.\.\.\])\s*", q) if p.strip()]
    return bool(parts) and any(all(p in h for p in parts) for h in hay)


def number_in_quote(value, quote):
    try:
        v = F._num(value)
    except F.FormulaError:
        return False
    q = (quote or "").lower()
    nums = [F._num(x.replace(".", "").replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)*", q)]
    if v in nums:
        return True
    words = re.findall(r"[a-zäöüß]+", q)
    if any(NUMBER_WORDS.get(w) == v for w in words):
        return True
    if any(w.startswith("woche") for w in words) and (v / 7 in nums or any(NUMBER_WORDS.get(w) == v / 7 for w in words)):
        return True  # "sechs Wochen" = 42 days
    return False


def check_case(case, item, terminal_runs):
    """Run the five guards. Returns (guards, oracle_value)."""
    g = []
    quotes = case.get("quotes") or []
    bad = [q for q in quotes if not quote_in(q, item["new_text"], item["old_text"])]
    g.append({"id": "G1", "name": "quotes verbatim in the spec", "status": "fail" if (bad or not quotes) else "ok",
              "detail": ("not found: " + " | ".join(b[:80] for b in bad)) if bad else (f"{len(quotes)} quote(s) found" if quotes else "no quote given")})
    fm = case.get("formula") or {}
    oracle, types, values = None, {}, {}
    try:
        _, names = F.parse(fm.get("expression", ""))
        for v in fm.get("variables") or []:
            types[v["name"]] = v.get("type", "number")
            values[v["name"]] = v.get("value")
        missing = [n for n in names if n not in values]
        unused = [n for n in values if n not in names]
        if missing:
            raise F.FormulaError("variables not declared: " + ", ".join(missing))
        oracle = F.evaluate(fm["expression"], values, types)
        g.append({"id": "G2", "name": "formula valid", "status": "warn" if unused else "ok",
                  "detail": f"{len(names)} variable(s)" + (f"; unused: {', '.join(unused)}" if unused else "")})
    except (F.FormulaError, KeyError, TypeError) as e:
        g.append({"id": "G2", "name": "formula valid", "status": "fail", "detail": str(e)})
    ai_val = case.get("expected_value")
    if oracle is None:
        g.append({"id": "G3", "name": "oracle = AI value", "status": "fail", "detail": "formula could not be evaluated"})
    else:
        same = F.same_value(oracle, ai_val)
        g.append({"id": "G3", "name": "oracle = AI value", "status": "ok" if same else "fail",
                  "detail": f"oracle {oracle} · AI {ai_val}"})
    unsupported = []
    for v in fm.get("variables") or []:
        if v.get("source") == "spec" and v.get("type", "number") == "number":
            if not v.get("quote") or not quote_in(v["quote"], item["new_text"], item["old_text"]) or not number_in_quote(v.get("value"), v["quote"]):
                unsupported.append(v["name"])
    g.append({"id": "G4", "name": "spec parameters in their quotes", "status": "warn" if unsupported else "ok",
              "detail": ("check: " + ", ".join(unsupported)) if unsupported else "every legal parameter is quoted"})
    tried = any(fm.get("expression", "#") in r["code"] or "evaluate(" in r["code"] for r in terminal_runs if r["ok"])
    g.append({"id": "G5", "name": "formula run in the terminal", "status": "ok" if tried else "warn",
              "detail": f"{sum(1 for r in terminal_runs if r['ok'])} successful terminal run(s)"})
    return g, oracle


# ------------------------------------------------------------------ the loop

def run_item(cfg, item, new_doc, old_doc, emit, lang="en", should_stop=lambda: False):
    """Process one section. emit(type, data) streams the chain of thought. Returns
    {"spec_change": {...} | None, "cases": [...], "summary": str}."""
    messages = [{"role": "system", "content": system_prompt(lang)},
                {"role": "user", "content": user_prompt(item, new_doc, old_doc)}]
    emit("context", {"chars": sum(len(m["content"]) for m in messages),
                     "sent": [item["sec"]], "old_version": bool(item["old_text"])})
    spec_change, cases, summary, terminal_runs = None, [], "", []
    nudges = 0
    for turn in range(MAX_TURNS):
        if should_stop():
            emit("stopped", {})
            break
        for attempt in range(2):
            try:
                resp = chat(cfg, messages, on_delta=lambda o: emit("live", {"reasoning": o["reasoning"], "content": o["content"],
                                                                         "tool": ", ".join(c["name"] for c in o["tool_calls"].values()) if isinstance(o["tool_calls"], dict) else ""}))
                break
            except LLMError as e:
                if "tool_choice" in str(e) and cfg.get("tool_choice") != "auto":
                    cfg = dict(cfg, tool_choice="auto")  # gateway/model without "required" support
                    continue
                if attempt:
                    emit("error", {"message": str(e)})
                    return {"spec_change": spec_change, "cases": cases, "summary": "stopped: " + str(e), "error": str(e)}
                emit("retry", {"message": str(e)})
                time.sleep(2)
        emit("live", None)
        if resp["reasoning"].strip():
            emit("thought", {"text": resp["reasoning"].strip(), "source": "model reasoning"})
        if resp["content"].strip():
            emit("text", {"text": resp["content"].strip()})
        calls = resp["tool_calls"]
        if not calls:
            if spec_change and cases:
                break
            nudges += 1
            if nudges > 2:
                emit("error", {"message": f"the model stopped without using the tools (finish_reason: {resp.get('finish_reason')})"})
                break
            emit("retry", {"message": f"no tool call (finish_reason: {resp.get('finish_reason')}), asking the model to continue"})
            # keep its analysis so it continues instead of starting over
            carry = (resp["content"] or "") or ("My analysis so far:\n" + resp["reasoning"][-4000:] if resp["reasoning"] else "(no answer)")
            messages.append({"role": "assistant", "content": carry})
            messages.append({"role": "user", "content": "Use the tools: record_spec_change first, then run_python and submit_test_case, then finish."})
            continue
        messages.append({"role": "assistant", "content": resp["content"] or None,
                         "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in calls]})
        finished = False
        for c in calls:
            try:
                args = _parse_args(c["arguments"])
            except (json.JSONDecodeError, ValueError) as e:
                result = f"error: arguments are not valid JSON ({e}). Send the call again."
                emit("tool_error", {"tool": c["name"], "message": result})
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
                continue
            if args.get("reasoning"):
                emit("thought", {"text": args["reasoning"], "source": c["name"]})
            name = c["name"]
            if name == "run_python":
                code = args.get("code", "")
                r = sandbox.run(code)
                terminal_runs.append({"code": code, "ok": r["ok"]})
                emit("terminal", {"code": code, **r})
                result = (r["stdout"] or "") + (("\n[stderr]\n" + r["stderr"]) if r["stderr"] else "")
                result = result.strip() or "(no output: print your results)"
            elif name == "record_spec_change":
                sc = {k: args.get(k) for k in ("change_type", "summary", "old_rule", "new_rule", "quotes_new", "quotes_old", "parameters", "formula_changed")}
                sc["quotes_new"] = [q for q in (sc.get("quotes_new") or []) if isinstance(q, str)]
                sc["quotes_old"] = [q for q in (sc.get("quotes_old") or []) if isinstance(q, str)]
                sc["parameters"] = [p for p in (sc.get("parameters") or []) if isinstance(p, dict)]
                checks = [{"quote": q, "side": "new", "ok": quote_in(q, item["new_text"])} for q in sc["quotes_new"]] + \
                         [{"quote": q, "side": "old", "ok": quote_in(q, item["old_text"])} for q in sc["quotes_old"]]
                sc["quote_checks"] = checks
                sc.update({"section": item["sec"], "title": item["title"], "page": item["page"], "detected_as": item["kind"],
                           "source": item["source"], "document": new_doc["name"], "previous_document": old_doc["name"] if old_doc else None})
                spec_change = sc
                emit("spec_change", sc)
                bad = [x["quote"][:80] for x in checks if not x["ok"]]
                result = "recorded." + (f" These quotes are NOT verbatim in the text, fix them in your test cases: {bad}" if bad else " All quotes verified verbatim.")
            elif name == "submit_test_case":
                if not spec_change:
                    result = "error: call record_spec_change first."
                else:
                    guards, oracle = check_case(args, item, terminal_runs)
                    case = {"title": args.get("title") or "untitled", "kind": args.get("kind", "positive"),
                            "criterion": args.get("criterion", ""), "scenario": args.get("scenario") or {},
                            "formula": args.get("formula") or {}, "previous_expression": args.get("previous_expression") or "",
                            "formula_changed": bool(args.get("formula_changed")), "ai_expected_value": args.get("expected_value"),
                            "expected_value": oracle, "expected_outcome": args.get("expected_outcome", ""),
                            "quotes": args.get("quotes") or [], "guards": guards, "replaces": args.get("replaces")}
                    prev = (case["previous_expression"] or "").strip()
                    if prev and F.normalize_expression(prev) != F.normalize_expression(case["formula"].get("expression", "")):
                        case["formula_changed"] = True
                    if spec_change.get("formula_changed") or spec_change.get("change_type") == "formula":
                        case["formula_changed"] = True
                    if case["replaces"]:
                        cases = [x for x in cases if x["local_id"] != case["replaces"]]
                    case["local_id"] = f"case-{len(cases) + 1}-{int(time.time() * 1000) % 100000}"
                    cases.append(case)
                    emit("test_case", case)
                    fails = [f"{x['id']} {x['name']}: {x['detail']}" for x in guards if x["status"] == "fail"]
                    warns = [f"{x['id']} {x['name']}: {x['detail']}" for x in guards if x["status"] == "warn"]
                    result = f"stored as {case['local_id']}. Oracle value: {oracle}."
                    if fails:
                        result += " GUARDS FAILED: " + "; ".join(fails) + f". Fix it and call submit_test_case again with replaces='{case['local_id']}'."
                    if warns:
                        result += " Warnings: " + "; ".join(warns) + "."
            elif name == "finish":
                summary = args.get("summary", "")
                finished = True
                result = "ok"
            else:
                result = f"error: unknown tool {name}"
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            if name != "run_python":
                emit("tool_result", {"tool": name, "result": result})
        if finished:
            if not spec_change and nudges < 2:
                nudges += 1
                messages.append({"role": "user", "content": "You must call record_spec_change before finishing."})
                continue
            break
    else:
        emit("error", {"message": f"stopped after {MAX_TURNS} turns"})
    return {"spec_change": spec_change, "cases": cases, "summary": summary}
