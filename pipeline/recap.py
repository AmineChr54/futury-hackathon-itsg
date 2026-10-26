"""AI briefing for a developer checklist: what changed in the spec, what to do, what to verify.

The briefing is written from the redacted test cases only (criterion, set-up, steps, spec change),
so it never contains the values ITSG verified: developers calculate those themselves. As a second
line of defence, any text that mentions an expected value is replaced by the plain summary.
"""
import json
import re
import urllib.request

PROMPT = """You brief a payroll software developer who received test cases from ITSG for a new version of the
DTA EEL specification (German continued-pay / sickness-benefit procedure). Write a short, concrete recap so
the developer knows what changed and what to do. Plain English, no marketing, no German unless quoting a term.

Answer with ONE JSON object and nothing else:
{"changed": "2-3 sentences: what changed in the spec and why it matters for their program",
 "todo": ["3-5 short imperative steps: what to change in their program, then test each case and tick it off in the checklist"],
 "verify": ["2-4 things in their program that these cases check, e.g. a rule or a boundary"],
 "rows": {"<test case id>": "one sentence: what this case checks and which value to look at"}}

Rules: never state or calculate the result of a test case (no resulting dates, numbers, true/false or
allowed/refused answers; write "check whether ..." instead);
the developer must calculate them in their own program. Use the ids exactly as given."""


def brief_input(pkg, rows, cases):
    """The facts the AI may use: no expected values, no trace, no chain of thought."""
    changes, seen = [], set()
    for tc in cases:
        sc = tc.get("spec_change") or {}
        key = (tc.get("section"), sc.get("summary"))
        if key not in seen:
            seen.add(key)
            changes.append({"section": tc.get("section"), "section_title": tc.get("section_title"),
                            **{k: sc.get(k) for k in ("change_type", "summary", "old_rule", "new_rule") if sc.get(k)}})
    return {"package": pkg.get("note") or pkg["id"], "from": pkg.get("by"),
            "version": next((r.get("version") for r in rows if r.get("version")), None),
            "previous_version": next(((tc.get("previous_document") or {}).get("version") for tc in cases if tc.get("previous_document")), None),
            "spec_changes": changes,
            "test_cases": [{"id": r["id"], "title": r.get("title"), "kind": r.get("kind"), "section": r.get("section"),
                            "criterion": r.get("criterion"), "preconditions": r.get("preconditions"), "steps": r.get("steps"),
                            "value_to_report": r.get("result_name"), "value_type": r.get("result_type")} for r in rows]}


def fallback(pkg, rows, cases):
    """A plain summary from the test cases themselves, used when the AI is unavailable."""
    info = brief_input(pkg, rows, cases)
    ch = [c for c in info["spec_changes"] if c.get("summary")]
    ver = info["version"]
    changed = " ".join(f"§{c['section']}: {c['summary']}" for c in ch[:3]) or "ITSG verified new test cases for this spec version."
    if ver:
        changed = f"Spec version {ver}" + (f" (was {info['previous_version']})" if info["previous_version"] else "") + ". " + changed
    sections = sorted({r.get("section") for r in rows if r.get("section")})
    return {"changed": changed,
            "todo": ["Open each row and set up the data listed under “How to run it”.",
                     "Run the steps in your payroll program for this spec version.",
                     "Check the value your program calculates against the rule in the spec.",
                     "Tick the case in the checklist once you have tested it."],
            "verify": [f"§{s}: " + next((r.get("criterion") or "" for r in rows if r.get("section") == s), "") for s in sections][:4],
            "rows": {r["id"]: (r.get("criterion") or r.get("title") or "") + (f" Report {r['result_name']}." if r.get("result_name") else "") for r in rows}}


def _json_object(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    return json.loads(m.group(0)) if m else None


def _leaks(text, secrets):
    """True when the text gives away a result: an expected date or number, or a yes/no answer."""
    return any(s and s in text for s in secrets) or bool(re.search(r"\b(true|false)\b", text, flags=re.I))


def secrets_of(cases):
    """Expected values in the forms a recap could spell them (ISO and German dates, numbers)."""
    out = set()
    for tc in cases:
        v = str(tc.get("expected_value") or "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            y, m, d = v.split("-")
            out |= {v, f"{d}.{m}.{y}", f"{d}.{m}.", f"{int(d)}.{int(m)}.{y}"}
        elif re.fullmatch(r"-?\d+(\.\d+)?", v) and len(v) > 1:
            out.add(v)
    return out


def generate(cfg, pkg, rows, cases, timeout=120):
    """Returns a recap dict. Falls back to the plain summary, field by field, when the AI fails."""
    base = fallback(pkg, rows, cases)
    body = {"model": cfg["model"], "temperature": 0.2, "max_tokens": 4000, "stream": False,
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": json.dumps(brief_input(pkg, rows, cases), ensure_ascii=False)}]}
    req = urllib.request.Request(cfg["base"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["key"]})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        msg = (json.loads(resp.read().decode("utf-8"))["choices"][0].get("message") or {})
    got = _json_object(msg.get("content") or "")
    if not isinstance(got, dict):
        raise ValueError("the model did not return a JSON recap")
    secrets = secrets_of(cases)
    clean = lambda s: isinstance(s, str) and s.strip() and not _leaks(s, secrets)
    out = {"changed": got["changed"].strip() if clean(got.get("changed")) else base["changed"]}
    for k in ("todo", "verify"):
        items = [s.strip() for s in got.get(k) or [] if clean(s)] if isinstance(got.get(k), list) else []
        out[k] = items[:6] or base[k]
    rws = got.get("rows") if isinstance(got.get("rows"), dict) else {}
    out["rows"] = {r["id"]: rws[r["id"]].strip() if clean(rws.get(r["id"])) else base["rows"][r["id"]] for r in rows}
    return out
