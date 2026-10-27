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
            "reasoning": {"type": "string", "description": "One sentence: what is calculated."},
            "code": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "record_spec_change",
        "description": "Record what changed in this section (or, without an old version, which testable rule it states). Call once, before any test case.",
        "parameters": {"type": "object", "required": ["reasoning", "change_type", "summary", "new_rule", "quotes_new"], "properties": {
            "reasoning": {"type": "string", "description": "Max 2 sentences: which words/values changed and the technical effect."},
            "change_type": {"type": "string", "enum": CHANGE_TYPES},
            "summary": {"type": "string", "description": "One sentence, max 25 words: what changed (old → new value/condition) and which calculation or message field it affects."},
            "old_rule": {"type": "string", "description": "Rule before the change as 'IF <condition> THEN <consequence>' with the values (empty if no old version)."},
            "new_rule": {"type": "string", "description": "Rule after the change as 'IF <condition> THEN <consequence>' with the values."},
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
                        "from evaluate() in your terminal. Submit as many cases as the rule needs, one per distinct "
                        "situation: positive, negative, and every boundary where the change flips the result."),
        "parameters": {"type": "object", "required": ["reasoning", "title", "kind", "criterion", "preconditions", "steps", "scenario", "formula", "expected_value", "expected_outcome", "quotes"], "properties": {
            "reasoning": {"type": "string", "description": "Max 2 sentences: which boundary/branch of the new rule this case hits."},
            "title": {"type": "string", "description": "Max 10 words: situation → effect, e.g. 'Gap exactly 6 months → prior AU included'."},
            "kind": {"type": "string", "enum": ["positive", "negative", "boundary"]},
            "criterion": {"type": "string", "description": "One sentence: 'The system ensures that …'."},
            "preconditions": {"type": "array", "items": {"type": "string"}, "description": "Max 4 items, data only, e.g. 'Certified AU 01.03.2026–03.03.2026'."},
            "steps": {"type": "array", "items": {"type": "string"}, "description": "Max 6 imperative items with concrete values, e.g. 'Enter AU from 11.03.2026', 'Create request (Abgabegrund 41)'."},
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
            "expected_outcome": {"type": "string", "description": "'<result_name> = <value>' plus at most a short clause on the consequence, e.g. 'efz_end = 2026-03-27 (Krankengeld from 28.03.)'."},
            "quotes": {"type": "array", "items": {"type": "string"}, "description": "Verbatim sentences from the NEW text this case is based on."},
            "replaces": {"type": "string", "description": "Id of an earlier submission this one corrects."}}}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Call when all test cases for this section are submitted, or if the section has no testable rule.",
        "parameters": {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string", "description": "One sentence."}}}}},
]


def system_prompt(lang):
    funcs = "\n".join(f"  {k:24s} {v}" for k, v in F.FUNC_DOCS.items())
    language = "German" if lang == "de" else "English"
    return f"""You are a test-case engineer at ITSG, which certifies German payroll software for the DTA EEL
procedure (income replacement benefits, § 107 SGB IV). Zero tolerance: one wrong day or cent fails a vendor.

You receive ONE section of a specification document: the changed spots (old → new, with context) and the
new text, or, without an old version, the section's rules. Your job: state what changed as structured data
and write test cases that prove a payroll program implements the NEW rule.

Style: technical, terse, no filler. No greetings, no restating the task or the spec, no hedging. Use the
spec's terms (AU, EFZ, Abgabegrund 41, DBVO, field names) and concrete values. Every `reasoning` field is
at most 2 sentences; `summary` is one sentence. Write in {language}; quotes stay verbatim German.

Procedure:
1. Read old and new text. Call record_spec_change once. Quotes must be copied character for character.
2. If a value must be calculated (dates, deadlines, day counts, amounts, percentages), write it as ONE
   formula over named variables. Legal parameters from the text (e.g. 42 days, 6 months, 70 %) are
   variables with source "spec" and a quote; test data (dates, salaries) are variables with source "scenario".
   Never write a legal value as a literal in the expression: add_months(previous_end, gap_months), not
   add_months(previous_end, 6).
3. Check the formula in your terminal with run_python: print(evaluate("<expression>", var=value, ...)).
   Also test the boundary where the change flips the result.
4. Call submit_test_case for each case: at least one, and as many as the rule needs (positive, negative,
   each boundary). expected_value = what evaluate() printed.
   If the formula differs from the old rule, set formula_changed and give previous_expression.
5. Call finish (summary: one sentence).

You are not done until you have submitted at least one test case. Every section that states or changes
a testable rule MUST end with a test case. Test the change, not the whole section: both sides of a changed
threshold (at the boundary and one step beyond), a removed or added condition, a changed value. No
duplicate cases. Each case must still be runnable by a tester who has not read the spec: concrete data
in preconditions and steps, and an expected outcome '<result_name> = <value>'.

Do not invent rules that are not in the text. Only if the change is purely editorial and nothing can be
tested, say so in record_spec_change (change_type "editorial") and call finish.

Formula language (one expression; numbers are exact decimals; dates are 'YYYY-MM-DD'):
  + - * / // % **, comparisons, and / or / not, `a if condition else b`
  date ± whole days, date - date = days
{funcs}
Periods in months or weeks: use add_months / add_weeks, never approximate them as a number of days
(6 months is not 180 or 183 days). "not more than 6 months between end and start" is
  add_months(previous_end, 6) >= current_start
Example: sick pay ends after 42 days minus creditable prior days, counting the first day:
  add_days(au_start, efz_days - prior_days - 1)   with au_start=2026-03-11, efz_days=42, prior_days=25 → 2026-03-27
"""


def user_prompt(item, new_doc, old_doc):
    parts = [f"Document (new): {new_doc['name']} · version {new_doc.get('version') or '?'}"]
    if old_doc:
        parts.append(f"Document (previous): {old_doc['name']} · version {old_doc.get('version') or '?'}")
    parts.append(f"Section: {item['sec']} {item['title']} (page {item['page']}) · detected as: {item['kind']} · source: {item['source']}"
                 + (f" · renumbered from {item['moved_from']}" if item.get("moved_from") else ""))
    if item.get("log"):
        parts.append("Change log entries for this section:\n" + "\n".join("- " + l for l in item["log"]))
    if item["kind"] == "changed":
        hs = item.get("hunks") or documents.hunks(item["ops"], context=40)
        lines = []
        for i, h in enumerate(hs[:MAX_HUNKS], start=1):
            before, after = _sentence_start(h["before"]), _sentence_end(h["after"])
            lines.append(f"C{i} OLD: {' '.join(x for x in (before, h['old'], after) if x)}\n"
                         f"   NEW: {' '.join(x for x in (before, h['new'], after) if x)}\n"
                         f"   words: " + (f"[-{h['old']}-] " if h["old"] else "") + (f"{{+{h['new']}+}}" if h["new"] else ""))
        if len(hs) > MAX_HUNKS:
            lines.append(f"({len(hs) - MAX_HUNKS} more changes not shown)")
        n = len(hs)
        parts.append(f"WHAT CHANGED — these {n} spot(s) are the ONLY differences between the versions; every other rule in "
                     f"the section is unchanged:\n" + "\n".join(lines))
        new_text = item["new_text"]
        parts.append("SECTION TEXT, new version (context only; quotes come from here or from the sentences above):\n"
                     + (new_text if len(new_text) <= MAX_CONTEXT_CHARS else new_text[:MAX_CONTEXT_CHARS] + "\n[… rest of the section omitted]"))
        parts.append(f"Describe and test only {'C1' if n == 1 else f'C1–C{min(n, MAX_HUNKS)}'}. Rules of the section that did not change are not a change; "
                     "use them only as preconditions of your test cases.")
    elif item["kind"] == "removed":
        parts.append("This section was REMOVED. OLD TEXT:\n" + _capped(item["old_text"]))
    elif item["kind"] == "added":
        parts.append("This section is NEW. NEW TEXT:\n" + _capped(item["new_text"]))
    else:
        parts.append("No previous version is available. Test the rules this section states"
                     + (", starting with the change log entries above." if item.get("log") else ".")
                     + "\nTEXT:\n" + _capped(item["new_text"], 2))
    return "\n\n".join(parts)


def _sentence_start(text):
    """The context before a change, from the start of its sentence."""
    m = list(re.finditer(r"(?<=[a-zäöüß)]{3})[.;!?]\s+(?=[A-ZÄÖÜ\"])", text))  # not after "Abs." or "Nr."
    return text[m[-1].end():] if m else text


def _sentence_end(text):
    """The context after a change, up to the end of its sentence."""
    m = re.search(r"(?<=[a-zäöüß)]{3})[.;!?](?=\s|$)", text)
    return text[:m.end()] if m else text


def _capped(text, factor=1):
    n = MAX_CONTEXT_CHARS * factor
    return text if len(text) <= n else text[:n] + "\n[… rest of the section omitted]"


MAX_HUNKS = 15
MAX_CONTEXT_CHARS = 12000  # longer sections: the changed spots carry the context


class LLMError(RuntimeError):
    pass


class Stopped(Exception):
    """The examiner pressed Stop."""


def chat(cfg, messages, on_delta=None, should_stop=lambda: False):
    """One streamed chat completion. Returns {reasoning, content, tool_calls}.
    Raises Stopped as soon as should_stop() turns true; the stream is closed, so the
    gateway stops generating too."""
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
                if should_stop():
                    raise Stopped()
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


def _str_list(v):
    """Quotes as a list of strings, also when the model sends a single string."""
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


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


def closest_sentence(quote, text):
    """The sentence of the spec text most similar to a quote that was not found verbatim,
    so the model can copy the real wording instead of retyping its own."""
    import difflib
    sents = [s.strip() for s in re.split(r"(?<=[.;:!?])\s+", _loose(text or "")) if len(s.strip()) > 20]
    q = _loose(quote or "")
    best = max(sents, key=lambda s: difflib.SequenceMatcher(None, q, s, autojunk=False).ratio(), default="")
    return best[:400]


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


def quote_checks(sc, item):
    """G1 for a spec change: is each quote verbatim in its side of the section?"""
    return [{"quote": q, "side": "new", "ok": quote_in(q, item["new_text"])} for q in sc.get("quotes_new") or []] + \
           [{"quote": q, "side": "old", "ok": quote_in(q, item["old_text"])} for q in sc.get("quotes_old") or []]


def check_case(case, item, terminal_runs):
    """Run the five guards. Returns (guards, oracle_value)."""
    g = []
    quotes = _str_list(case.get("quotes"))
    bad = [q for q in quotes if not quote_in(q, item["new_text"], item["old_text"])]
    g.append({"id": "G1", "name": "quotes verbatim in the spec", "status": "fail" if (bad or not quotes) else "ok",
              "detail": ("not found: " + " | ".join(b[:80] for b in bad)) if bad else (f"{len(quotes)} quote(s) found" if quotes else "no quote given")})
    fm = case.get("formula") if isinstance(case.get("formula"), dict) else {}
    variables = [v for v in (fm.get("variables") or []) if isinstance(v, dict)] if isinstance(fm.get("variables"), list) else []
    oracle, types, values = None, {}, {}
    try:
        _, names = F.parse(fm.get("expression", ""))
        for v in variables:
            types[v["name"]] = v.get("type", "number")
            values[v["name"]] = v.get("value")
        missing = [n for n in names if n not in values]
        unused = [n for n in values if n not in names]
        if missing:
            raise F.FormulaError("variables not declared: " + ", ".join(missing))
        oracle = F.evaluate(fm["expression"], values, types)
        g.append({"id": "G2", "name": "formula valid", "status": "warn" if unused else "ok",
                  "detail": f"{len(names)} variable(s)" + (f"; unused: {', '.join(unused)}" if unused else "")})
    except (F.FormulaError, KeyError, TypeError, ArithmeticError) as e:
        g.append({"id": "G2", "name": "formula valid", "status": "fail", "detail": str(e) or type(e).__name__})
    ai_val = case.get("expected_value")
    if oracle is None:
        g.append({"id": "G3", "name": "oracle = AI value", "status": "fail", "detail": "formula could not be evaluated"})
    else:
        same = F.same_value(oracle, ai_val)
        g.append({"id": "G3", "name": "oracle = AI value", "status": "ok" if same else "fail",
                  "detail": f"oracle {oracle} · AI {ai_val}"})
    unsupported = []
    for v in variables:
        if v.get("source") == "spec" and v.get("type", "number") == "number":
            if not v.get("quote") or not quote_in(v["quote"], item["new_text"], item["old_text"]) or not number_in_quote(v.get("value"), v["quote"]):
                unsupported.append(v["name"])
    g.append({"id": "G4", "name": "spec parameters in their quotes", "status": "warn" if unsupported else "ok",
              "detail": ("check: " + ", ".join(unsupported)) if unsupported else "every legal parameter is quoted"})
    expr = (fm.get("expression") or "").strip() if isinstance(fm.get("expression"), str) else ""
    tried = any((expr and expr in r["code"]) or "evaluate(" in r["code"] for r in terminal_runs if r["ok"])
    g.append({"id": "G5", "name": "formula run in the terminal", "status": "ok" if tried else "warn",
              "detail": f"{sum(1 for r in terminal_runs if r['ok'])} successful terminal run(s)"})
    return g, oracle


# ------------------------------------------------------------------ the loop

# Fields of a spec change the examiner reviews and the model sees again in the "cases" step.
SPEC_FIELDS = ("change_type", "summary", "old_rule", "new_rule", "quotes_new", "quotes_old", "parameters", "formula_changed")


def run_item(cfg, item, new_doc, old_doc, emit, lang="en", should_stop=lambda: False, mode="full", approved=None):
    """Process one section. emit(type, data) streams the chain of thought. Returns
    {"spec_change": {...} | None, "cases": [...], "summary": str, "stopped": bool}.
    mode: "extract" stops once the spec change is recorded, so the examiner can approve or edit it;
    "cases" writes test cases for the `approved` spec change; "full" does both in one go.
    Stop is honoured mid-stream and between tool calls; test cases already submitted are kept."""
    state = {"spec_change": approved if mode == "cases" else None, "cases": []}
    try:
        return _run_item(cfg, item, new_doc, old_doc, emit, lang, should_stop, state, mode)
    except Stopped:
        emit("live", None)
        emit("stopped", {"kept": len(state["cases"])})
        return {"spec_change": state["spec_change"], "cases": state["cases"], "summary": "stopped by the examiner", "stopped": True}


def _run_item(cfg, item, new_doc, old_doc, emit, lang, should_stop, state, mode="full"):
    prompt = user_prompt(item, new_doc, old_doc)
    if mode == "extract":
        prompt += ("\n\nTHIS STEP: only call record_spec_change. Do not write test cases yet: the examiner "
                   "reviews your spec change first, and test cases are written in a later step.")
    elif mode == "cases":
        prompt += ("\n\nThe examiner reviewed this spec change and approved it (possibly after editing it). "
                   "It is authoritative; do not call record_spec_change again. Write the test cases for it now "
                   "(run_python, submit_test_case, finish):\n"
                   + json.dumps({k: state["spec_change"].get(k) for k in SPEC_FIELDS}, ensure_ascii=False, indent=1))
    messages = [{"role": "system", "content": system_prompt(lang)},
                {"role": "user", "content": prompt}]
    emit("context", {"chars": sum(len(m["content"]) for m in messages),
                     "sent": [item["sec"]], "old_version": bool(item["old_text"]), "mode": mode})
    spec_change, cases, summary, terminal_runs = state["spec_change"], [], "", []
    nudges, refusals = 0, 0
    force = None  # name of the tool the next turn must call

    def needs_case():  # every testable section must end with at least one test case
        if mode == "extract":
            return False
        return not cases and not (spec_change and spec_change.get("change_type") == "editorial")

    def next_required():
        return "record_spec_change" if not spec_change else "submit_test_case"

    def unfinished():
        return needs_case() or (mode == "extract" and not spec_change)

    for turn in range(MAX_TURNS):
        state["spec_change"], state["cases"] = spec_change, cases
        if should_stop():
            raise Stopped()
        if turn >= MAX_TURNS - 3 and unfinished():
            force = next_required()  # running out of turns: no more exploring, write the test case
        call_cfg = dict(cfg, tool_choice={"type": "function", "function": {"name": force}}) if force else cfg
        if force:
            emit("retry", {"message": f"the model must now call {force}"})
        failures = 0
        while True:
            try:
                resp = chat(call_cfg, messages, on_delta=lambda o: emit("live", {"reasoning": o["reasoning"], "content": o["content"],
                                                                              "tool": ", ".join(c["name"] for c in o["tool_calls"].values()) if isinstance(o["tool_calls"], dict) else ""}),
                            should_stop=should_stop)
                break
            except LLMError as e:
                if "tool_choice" in str(e) and call_cfg.get("tool_choice") != "auto":
                    # gateway/model without "required"/named support; doesn't count as a failure
                    cfg = call_cfg = dict(cfg, tool_choice="auto")
                    continue
                failures += 1
                if failures >= 2:
                    emit("error", {"message": str(e)})
                    return {"spec_change": spec_change, "cases": cases, "summary": "stopped: " + str(e), "error": str(e)}
                emit("retry", {"message": str(e)})
                time.sleep(2)
        emit("live", None)
        force = None
        if resp["reasoning"].strip():
            emit("thought", {"text": resp["reasoning"].strip(), "source": "model reasoning"})
        if resp["content"].strip():
            emit("text", {"text": resp["content"].strip()})
        calls = resp["tool_calls"]
        if not calls:
            if spec_change and not unfinished():
                break
            nudges += 1
            if nudges > 3:
                emit("error", {"message": f"the model stopped without using the tools (finish_reason: {resp.get('finish_reason')})"})
                break
            emit("retry", {"message": f"no tool call (finish_reason: {resp.get('finish_reason')}), asking the model to continue"})
            # keep its analysis so it continues instead of starting over
            carry = (resp["content"] or "") or ("My analysis so far:\n" + resp["reasoning"][-4000:] if resp["reasoning"] else "(no answer)")
            messages.append({"role": "assistant", "content": carry})
            force = next_required()
            messages.append({"role": "user", "content": f"Continue with the tools. Call {force} now."})
            continue
        messages.append({"role": "assistant", "content": resp["content"] or None,
                         "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in calls]})
        finished = False
        for c in calls:
            state["spec_change"], state["cases"] = spec_change, cases
            if should_stop():
                raise Stopped()
            try:
                args = _parse_args(c["arguments"])
                if not isinstance(args, dict):
                    raise ValueError(f"expected a JSON object, got {type(args).__name__}")
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
            elif name == "record_spec_change" and mode == "cases":
                result = "The spec change is already approved by the examiner and cannot be changed here. Continue with submit_test_case."
            elif name == "submit_test_case" and mode == "extract":
                result = "Not in this step: the examiner reviews the spec change first. Only call record_spec_change."
            elif name == "record_spec_change":
                sc = {k: args.get(k) for k in SPEC_FIELDS}
                sc["quotes_new"] = [q for q in (sc.get("quotes_new") or []) if isinstance(q, str)]
                sc["quotes_old"] = [q for q in (sc.get("quotes_old") or []) if isinstance(q, str)]
                sc["parameters"] = [p for p in (sc.get("parameters") or []) if isinstance(p, dict)]
                checks = sc["quote_checks"] = quote_checks(sc, item)
                sc.update({"section": item["sec"], "title": item["title"], "page": item["page"], "detected_as": item["kind"],
                           "source": item["source"], "document": new_doc["name"], "previous_document": old_doc["name"] if old_doc else None})
                spec_change = sc
                emit("spec_change", sc)
                bad = [x for x in checks if not x["ok"]]
                result = "recorded." + ((" These quotes are NOT verbatim in the text; in your test cases use the real wording: "
                                         + " | ".join(f"'{x['quote'][:60]}…' → \"{closest_sentence(x['quote'], item['new_text'] if x['side'] == 'new' else item['old_text'])}\"" for x in bad))
                                        if bad else " All quotes verified verbatim.")
            elif name == "submit_test_case":
                if not spec_change:
                    result = "error: call record_spec_change first."
                else:
                    guards, oracle = check_case(args, item, terminal_runs)
                    as_list = lambda v: [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])
                    case = {"title": args.get("title") or "untitled", "kind": args.get("kind", "positive"),
                            "criterion": args.get("criterion", ""), "scenario": args.get("scenario") or {},
                            "preconditions": as_list(args.get("preconditions")), "steps": as_list(args.get("steps")),
                            "formula": args.get("formula") if isinstance(args.get("formula"), dict) else {}, "previous_expression": args.get("previous_expression") or "",
                            "formula_changed": bool(args.get("formula_changed")), "ai_expected_value": args.get("expected_value"),
                            "expected_value": oracle, "expected_outcome": args.get("expected_outcome", ""),
                            "quotes": _str_list(args.get("quotes")), "guards": guards, "replaces": args.get("replaces")}
                    prev = (case["previous_expression"] or "").strip()
                    if prev and F.normalize_expression(prev) != F.normalize_expression(case["formula"].get("expression", "")):
                        case["formula_changed"] = True
                    if spec_change.get("formula_changed") or spec_change.get("change_type") == "formula":
                        case["formula_changed"] = True
                    replaced = next((x for x in cases if x["local_id"] == case["replaces"]), None) if case["replaces"] else None
                    case["fix_round"] = replaced["fix_round"] + 1 if replaced else 0
                    if replaced:
                        cases = [x for x in cases if x is not replaced]
                    case["local_id"] = f"case-{len(cases) + 1}-{int(time.time() * 1000) % 100000}"
                    cases.append(case)
                    emit("test_case", case)
                    fails = [f"{x['id']} {x['name']}: {x['detail']}" for x in guards if x["status"] == "fail"]
                    warns = [f"{x['id']} {x['name']}: {x['detail']}" for x in guards if x["status"] == "warn"]
                    unclear = [k for k in ("preconditions", "steps", "expected_outcome") if not case[k]]
                    result = f"stored as {case['local_id']}. Oracle value: {oracle}."
                    if (fails or unclear) and case["fix_round"] >= 2:
                        # don't let the model loop on the same case: the examiner decides from here
                        result += (" Checks still failing: " + "; ".join(fails + [f"missing {k}" for k in unclear])
                                   + ". The case is kept and flagged for the examiner. Do NOT resubmit it; submit a different case or call finish.")
                    else:
                        if fails:
                            result += " GUARDS FAILED: " + "; ".join(fails) + f". Fix it and call submit_test_case again with replaces='{case['local_id']}'."
                            hints = [f"'{q[:60]}…' → closest real sentence: \"{closest_sentence(q, item['new_text'])}\""
                                     for q in case["quotes"] if not quote_in(q, item["new_text"], item["old_text"])]
                            if hints:
                                result += " Copy quotes from these sentences instead of retyping them: " + " | ".join(hints)
                        if unclear:
                            result += f" The test case is not clear enough: add {', '.join(unclear)} and resubmit with replaces='{case['local_id']}'."
                    if warns:
                        result += " Warnings: " + "; ".join(warns) + "."
            elif name == "finish":
                if unfinished() and refusals < 3:
                    refusals += 1
                    force = next_required()
                    result = ("not finished: " + ("record the spec change first. " if not spec_change else "")
                              + "This section has a testable rule, so you must submit at least one clear test case "
                              "(title, preconditions, steps, expected outcome, formula) before finishing. "
                              f"Call {force} now.")
                else:
                    summary = args.get("summary", "")
                    finished = True
                    result = "ok"
            else:
                result = f"error: unknown tool {name}"
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            if name != "run_python":
                emit("tool_result", {"tool": name, "result": result})
        if finished or (mode == "extract" and spec_change):
            break
    else:
        emit("error", {"message": f"stopped after {MAX_TURNS} turns"})
    if mode == "extract":
        if not spec_change:
            emit("error", {"message": "no spec change was extracted for this section; start it again with Generate"})
        return {"spec_change": spec_change, "cases": [], "summary": "spec change extracted, waiting for the examiner" if spec_change else summary}
    if needs_case():
        emit("error", {"message": "no test case was produced for this section; start it again with Generate"})
    return {"spec_change": spec_change, "cases": cases, "summary": summary}
