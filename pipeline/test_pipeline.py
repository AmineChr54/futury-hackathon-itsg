"""Unit tests for the deterministic parts: python -m unittest pipeline/test_pipeline.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent  # noqa: E402
import documents as D  # noqa: E402
import formula as F  # noqa: E402
import sandbox  # noqa: E402


class FormulaTests(unittest.TestCase):
    def test_itsg_reference_sick_pay_end(self):
        # ITSG reference case: 42 days minus 25 creditable prior days from 11.03.2026 → 27.03.2026
        expr = "add_days(au_start, efz_days - prior_days - 1)"
        self.assertEqual(F.evaluate(expr, {"au_start": "2026-03-11", "efz_days": 42, "prior_days": 25}), "2026-03-27")
        self.assertEqual(F.evaluate(expr, {"au_start": "11.03.2026", "efz_days": "42", "prior_days": "22"}), "2026-03-30")

    def test_thirty_day_gate(self):
        expr = "prior_days + days_inclusive(au_start, au_end) >= min_days"
        v = {"prior_days": 25, "au_start": "2026-03-11", "au_end": "2026-03-20", "min_days": 30}
        self.assertEqual(F.evaluate(expr, v), "true")
        self.assertEqual(F.evaluate(expr, dict(v, au_end="2026-03-14")), "false")

    def test_exact_decimals_and_commercial_rounding(self):
        self.assertEqual(F.evaluate("round(brutto * 70 / 100 / 30, 2)", {"brutto": "3000.10"}), "70")
        self.assertEqual(F.evaluate("round(x, 2)", {"x": "2.345"}), "2.35")  # half up, not banker's rounding
        self.assertEqual(F.evaluate("0.1 + 0.2"), "0.3")
        self.assertEqual(F.evaluate("percent(2500, 90)"), "2250")

    def test_months_and_conditionals(self):
        self.assertEqual(F.evaluate("add_months(d, 6)", {"d": "2025-08-31"}), "2026-02-28")
        self.assertEqual(F.evaluate("days_between(a, b) <= 183 if certified else False",
                                    {"a": "2025-12-03", "b": "2026-03-11", "certified": True}, {"certified": "bool"}), "true")

    def test_rejects_code(self):
        for bad in ["__import__('os').system('dir')", "open('x')", "(lambda: 1)()", "x.__class__", "[1,2]", "eval('1')"]:
            with self.assertRaises(F.FormulaError, msg=bad):
                F.evaluate(bad, {"x": 1})

    def test_missing_variable(self):
        with self.assertRaises(F.FormulaError):
            F.evaluate("a + b", {"a": 1})

    def test_same_value(self):
        self.assertTrue(F.same_value("2026-03-27", "27.03.2026"))
        self.assertTrue(F.same_value("17", "17.00"))
        self.assertFalse(F.same_value("17", "18"))

    def test_trace(self):
        steps = F.trace("add_days(au_start, efz_days - prior_days - 1)", {"au_start": "2026-03-11", "efz_days": 42, "prior_days": 25})
        self.assertEqual(steps[-1], ["add_days(au_start, efz_days - prior_days - 1)", "2026-03-27"])


class SandboxTests(unittest.TestCase):
    def test_runs_and_has_evaluate(self):
        r = sandbox.run("print(evaluate('add_days(d, 16)', d='2026-03-11'))\nimport math\nprint(math.floor(2.7))")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["stdout"].split(), ["2026-03-27", "2"])

    def test_umlauts_survive_the_terminal(self):
        r = sandbox.run("print('Arbeitsunfähigkeit für Prüfung')")
        self.assertEqual(r["stdout"].strip(), "Arbeitsunfähigkeit für Prüfung")

    def test_refuses_dangerous_code(self):
        for code in ["import os\nos.listdir('.')", "open('x','w')", "import subprocess", "().__class__.__bases__",
                     "from socket import socket", "getattr(1, 'real')"]:
            r = sandbox.run(code)
            self.assertTrue(r["refused"], code)

    def test_error_line_numbers_refer_to_the_script(self):
        r = sandbox.run("x = 1\ny = x / 0")
        self.assertFalse(r["ok"])
        self.assertIn('line 2', r["stderr"])


OLD = """Seite 1 von 3
1. Einleitung
Dies ist die Einleitung.
Seite 2 von 3
3.12 Datenbaustein DBVO – Vorerkrankungszeiten
Eine Anfrage ist nur zulässig, wenn zwischen dem Beginn der aktuellen AU und dem Ende der letzten AU
nicht mindestens 6 Monate liegen. Die Summe muss 30 Tage betragen.
3.12.9 „Kennzeichen Nachweis“ übermittelt.
3.13 Datenbaustein DBHE
Unverändert bleibt dieser Text.
"""
NEW = OLD.replace("nicht mindestens 6 Monate", "nicht mehr als 6 Monate")


class DocumentTests(unittest.TestCase):
    def test_sections_ignore_cross_references(self):
        secs, _ = D.split_sections([OLD])
        self.assertEqual([s["sec"] for s in secs], ["1", "3.12", "3.13"])
        self.assertIn("3.12.9 „Kennzeichen", secs[1]["text"])

    def test_toc_and_overview_lists_do_not_win(self):
        toc = "Inhalt\n1 Einleitung ........ 1\n3.12 Datenbaustein DBVO ....... 2\n3.12 DBVO – Vorerkrankungszeiten\n3.13 DBHE\n"
        secs, _ = D.split_sections([toc, OLD])
        s312 = next(s for s in secs if s["sec"] == "3.12")
        self.assertIn("nicht mindestens", s312["text"])

    def test_diff_finds_the_flipped_boundary(self):
        old = {"sections": D.split_sections([OLD])[0]}
        new = {"sections": D.split_sections([NEW])[0]}
        ch = D.diff_documents(old, new)
        self.assertEqual([c["sec"] for c in ch], ["3.12"])
        self.assertIn(["-", "mindestens"], ch[0]["ops"])
        self.assertIn(["+", "mehr als"], ch[0]["ops"])
        self.assertEqual(ch[0]["source"], "diff-only")

    def test_changelog(self):
        page = ("Änderungsübersicht\nVersion Datum Änderung\n13.3 01.02.2026 3.12 „Datenbaustein DBVO“ – Anpassung\n"
                "13.4 10.03.2026 3.12.7 „Arbeitsunfähigkeit Zeitraum-Beginn“ und\n3.13 „Datenbaustein DBHE“ – Klarstellung\n")
        rows = D.parse_changelog([page])
        self.assertEqual([r["version"] for r in rows], ["13.3", "13.4"])
        self.assertEqual(rows[1]["refs"], ["3.12.7", "3.13"])
        doc = {"changelog": rows, "sections": D.split_sections([OLD])[0]}
        items = D.single_document_items(doc)
        self.assertEqual(sorted(i["sec"] for i in items), ["3.12", "3.13"])  # 3.12.7 maps to its block 3.12


class GuardTests(unittest.TestCase):
    item = {"new_text": "Es dürfen nicht mehr als 6 Monate zwischen dem Ende der letzten AU und dem Beginn liegen. "
                        "Der Anspruch auf Entgeltfortzahlung besteht für sechs Wochen.", "old_text": ""}

    def case(self, **kw):
        c = {"quotes": ["nicht mehr als 6 Monate zwischen dem Ende"],
             "formula": {"expression": "add_days(au_start, efz_days - prior_days - 1)", "result_name": "efz_end", "variables": [
                 {"name": "au_start", "type": "date", "value": "2026-03-11", "source": "scenario"},
                 {"name": "efz_days", "type": "number", "value": "42", "source": "spec", "quote": "für sechs Wochen"},
                 {"name": "prior_days", "type": "number", "value": "25", "source": "scenario"}]},
             "expected_value": "2026-03-27"}
        c.update(kw)
        return c

    def test_all_guards_pass(self):
        g, oracle = agent.check_case(self.case(), self.item, [{"code": "print(evaluate('...'))", "ok": True}])
        self.assertEqual(oracle, "2026-03-27")
        self.assertEqual({x["id"]: x["status"] for x in g}, {"G1": "ok", "G2": "ok", "G3": "ok", "G4": "ok", "G5": "ok"})

    def test_wrong_ai_value_and_paraphrase_fail(self):
        g, _ = agent.check_case(self.case(expected_value="2026-03-28", quotes=["höchstens sechs Monate"]), self.item, [])
        st = {x["id"]: x["status"] for x in g}
        self.assertEqual((st["G1"], st["G3"], st["G5"]), ("fail", "fail", "warn"))

    def test_quote_with_lost_line_break_hyphenation(self):
        text = "Dies bedeutet, dass möglichst alle Vorerkrankungen über-\nmittelt werden, bei welchen"
        self.assertTrue(agent.quote_in("möglichst alle Vorerkrankungen über- mittelt werden", text))
        self.assertTrue(agent.quote_in("möglichst alle Vorerkrankungen übermittelt werden", text))
        self.assertTrue(agent.quote_in("Dies bedeutet, … übermittelt werden", text))

    def test_closest_sentence_points_to_the_real_wording(self):
        text = ("Relevant für die Beurteilung sind alle Erkrankungen, bei welchen nicht mindestens 6 Monate vergangen sind. "
                "Hierbei ist bis zur erstmalig bescheinigten Erkrankung zurückzugehen.")
        hint = agent.closest_sentence("Relevant für die Beurteilung sind alle Erkrankungen, bei welchen nicht mehr als 6 Monate vergangen sind.", text)
        self.assertIn("nicht mindestens 6 Monate", hint)

    def test_number_not_in_quote_warns(self):
        c = self.case()
        c["formula"]["variables"][1]["value"] = "49"
        g, _ = agent.check_case(dict(c, expected_value="2026-04-03"), self.item, [])
        self.assertEqual(next(x for x in g if x["id"] == "G4")["status"], "warn")


class RobustnessTests(unittest.TestCase):
    """Malformed model output, odd arithmetic and server restarts must not crash the pipeline."""
    item = {"sec": "3.12", "title": "DBVO", "page": 1, "kind": "rule", "source": "test", "ops": [], "log": [],
            "new_text": "Der Anspruch auf Entgeltfortzahlung besteht für sechs Wochen.", "old_text": ""}

    def test_arithmetic_errors_are_formula_errors(self):
        for expr, v in [("0/0", {}), ("x ** 50", {"x": "1e999999"}), ("round(x, 99)", {"x": 1}),
                        ("add_days(d, 5)", {"d": "9999-12-31"})]:
            with self.assertRaises(F.FormulaError, msg=expr):
                F.evaluate(expr, v)

    def test_guards_survive_malformed_cases(self):
        for case in [{"formula": "add_days(a, 1)", "quotes": "für sechs Wochen", "expected_value": "x"},
                     {"formula": {"expression": "a + 1", "variables": ["a"]}, "expected_value": 1},
                     {"formula": {"expression": "a + 1", "variables": "a"}, "quotes": None}]:
            g, oracle = agent.check_case(case, self.item, [])
            self.assertEqual(next(x for x in g if x["id"] == "G2")["status"], "fail")
            self.assertIsNone(oracle)
        g, _ = agent.check_case({"quotes": "Entgeltfortzahlung besteht für sechs Wochen"}, self.item, [])
        self.assertEqual(next(x for x in g if x["id"] == "G1")["status"], "ok")  # a single string counts as one quote

    def test_empty_formula_was_not_run_in_the_terminal(self):
        g, _ = agent.check_case({"formula": {"expression": ""}}, self.item, [{"code": "print(1)", "ok": True}])
        self.assertEqual(next(x for x in g if x["id"] == "G5")["status"], "warn")

    def _fake_chat(self, script):
        calls = iter(script)

        def chat(cfg, messages, on_delta=None, should_stop=lambda: False):
            step = next(calls)
            if isinstance(step, Exception):
                raise step
            return {"reasoning": "", "content": "", "finish_reason": "tool_calls",
                    "tool_calls": [{"id": f"c{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(step)]}
        return chat

    def _run(self, script):
        real = agent.chat, agent.time.sleep
        agent.chat, agent.time.sleep = self._fake_chat(script), lambda s: None
        events = []
        try:
            res = agent.run_item({"model": "m", "key": "k", "base": "b"}, self.item, {"name": "n"}, None,
                                 lambda t, d: events.append((t, d)))
        finally:
            agent.chat, agent.time.sleep = real
        return res, events

    editorial = [("record_spec_change", '{"change_type": "editorial", "summary": "wording"}'), ("finish", '{"summary": "done"}')]

    def test_tool_choice_fallback_after_a_network_retry(self):
        # previously the retry loop ran out after the fallback and reused a stale (or unbound) response
        res, events = self._run([agent.LLMError("network: reset"), agent.LLMError("HTTP 400: tool_choice not supported"),
                                 self.editorial])
        self.assertEqual(res["summary"], "done")
        self.assertEqual(res["spec_change"]["change_type"], "editorial")

    def _run_mode(self, script, **kw):
        real = agent.chat, agent.time.sleep
        sent = []
        fake = self._fake_chat(script)

        def chat(cfg, messages, **k):
            sent.append(messages[1]["content"])
            return fake(cfg, messages, **k)
        agent.chat, agent.time.sleep = chat, lambda s: None
        try:
            res = agent.run_item({"model": "m", "key": "k", "base": "b"}, self.item, {"name": "n"}, None, lambda t, d: None, **kw)
        finally:
            agent.chat, agent.time.sleep = real
        return res, sent

    def test_extract_mode_stops_after_the_spec_change(self):
        change = ('{"change_type": "parameter", "summary": "six weeks", "new_rule": "42 days", '
                  '"quotes_new": ["Entgeltfortzahlung besteht für sechs Wochen"]}')
        res, sent = self._run_mode([[("record_spec_change", change)]], mode="extract")
        self.assertEqual(len(sent), 1)  # no second call: test cases wait for the examiner
        self.assertEqual(res["cases"], [])
        self.assertEqual(res["spec_change"]["summary"], "six weeks")
        self.assertTrue(res["spec_change"]["quote_checks"][0]["ok"])
        self.assertIn("only call record_spec_change", sent[0])

    def test_cases_mode_uses_the_approved_change_and_keeps_it(self):
        approved = {"change_type": "parameter", "summary": "edited by the examiner", "new_rule": "42 days"}
        case = ('{"title": "t", "kind": "positive", "preconditions": ["p"], "steps": ["s"], "expected_outcome": "o", '
                '"quotes": ["Entgeltfortzahlung besteht für sechs Wochen"], "expected_value": "2", '
                '"formula": {"expression": "1 + 1", "variables": []}}')
        res, sent = self._run_mode([[("record_spec_change", '{"change_type": "editorial", "summary": "AI overrides"}'),
                                     ("submit_test_case", case), ("finish", '{"summary": "ok"}')]], mode="cases", approved=approved)
        self.assertIn("edited by the examiner", sent[0])
        self.assertEqual(res["spec_change"]["summary"], "edited by the examiner")  # the model cannot overwrite it
        self.assertEqual(len(res["cases"]), 1)

    def test_non_object_arguments_are_sent_back(self):
        res, events = self._run([[("record_spec_change", "[1, 2]")], self.editorial])
        self.assertTrue(any(t == "tool_error" and "JSON object" in d["message"] for t, d in events))
        self.assertEqual(res["summary"], "done")


class ChangelogDiffTests(unittest.TestCase):
    def test_field_level_refs_mark_their_section_as_logged(self):
        old = {"sections": D.split_sections([OLD])[0]}
        new = {"sections": D.split_sections([NEW])[0]}
        log = [{"version": "13.4", "date": "10.03.2026", "text": "3.12.7 „AU-Beginn“", "refs": ["3.12.7"]}]
        ch = D.diff_documents(old, new, log)
        self.assertEqual(ch[0]["sec"], "3.12")
        self.assertEqual(ch[0]["source"], "log+diff")
        self.assertEqual(ch[0]["log"], ["3.12.7 „AU-Beginn“"])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp()
        os.environ["PIPELINE_DATA"] = cls.tmp
        os.environ["LAW_DIR"] = os.path.join(cls.tmp, "law")
        import server
        cls.S = server

    def run_with(self, n_cases):
        S = self.S
        run = {"id": "20261026-120000-abcd", "model": "m", "lang": "en", "seq": 0, "events": [], "live": {}, "stop": False,
               "status": "running", "plan": {"new": {"name": "n.pdf", "version": "1"}, "old": None},
               "items": [{"sec": "3.12", "title": "DBVO", "page": 1, "kind": "rule", "source": "t", "status": "queued", "cases": []}]}
        S.RUNS[run["id"]] = run
        real = S.agent.run_item
        S.agent.run_item = lambda *a, **k: {"spec_change": None, "summary": "", "cases": [
            {"local_id": f"case-{i}", "title": "t", "formula": {"expression": "1 + 1", "variables": []}} for i in range(n_cases)]}
        try:
            S.process_item(run, "3.12", "cases")
            S.item_of(run, "3.12")["status"] = "done"
            S.process_item(run, "3.12", "cases")  # "Generate" again on the same section
        finally:
            S.agent.run_item = real
        return [t["id"] for t in S.STORE["testcases"] if t["run"] == run["id"]]

    def test_developer_history_is_seeded_once_and_hidden_from_itsg(self):
        S = self.S
        from unittest import mock
        with mock.patch.object(S, "start_recap", lambda pkg: None):  # no AI in unit tests
            S.seed_history("Kim B.")
            S.seed_history("Kim B.")  # second sign-in: nothing new
        pkgs = [p for p in S.STORE["packages"] if p.get("mock") and "Kim B." in p["to"]]
        self.assertEqual(len(pkgs), len(S.MOCK_HISTORY))
        self.assertEqual([p["t"] for p in pkgs], [h["t"] for h in S.MOCK_HISTORY])  # the mock dates are kept
        cases = [S.tc_by_id(i) for p in pkgs for i in p["ids"]]
        self.assertTrue(all(c["mock"] and c["expected_value"] not in (None, "") and not c.get("formula_error") for c in cases))
        self.assertTrue(all(c["acks"][0]["who"] == "Kim B." for c in cases))
        self.assertEqual(sum(len(p["coverage"]["Kim B."]) for p in pkgs), sum(len(h["covered"]) for h in S.MOCK_HISTORY))

    def test_default_package_title(self):
        cases = [{"document": {"version": "13.4"}, "section": "3.12.5"}, {"document": {"version": "13.4"}, "section": "3.12"}]
        self.assertEqual(self.S.default_note(cases), "EEL 13.4 — §3.12, §3.12.5")

    def test_generate_again_does_not_reuse_test_case_ids(self):
        ids = self.run_with(2)
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 4)

    def _http(self, method, path, body=None, role="itsg"):
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Role": role, "X-User": "Examiner"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_examiner_reviews_spec_changes_before_test_cases(self):
        import threading
        from http.server import ThreadingHTTPServer
        S = self.S

        class Now:  # run queued work right away instead of in the thread pool
            def submit(self, fn, *a):
                fn(*a)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        self.port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        calls = []

        def fake_run_item(cfg, item, new_doc, old_doc, emit, mode="full", approved=None, **kw):
            calls.append((item["sec"], mode, approved))
            emit("thought", {"text": f"{mode} §{item['sec']}", "source": "model reasoning"})
            if mode == "extract":
                return {"spec_change": {"change_type": "parameter", "summary": "6 → 7 months", "new_rule": "7 months",
                                        "quotes_new": ["nicht mehr als 7 Monate"], "parameters": [{"name": "gap_months", "new_value": "7"}]},
                        "cases": [], "summary": ""}
            return {"spec_change": approved, "summary": "", "cases": [
                {"local_id": "case-1", "title": "boundary", "formula": {"expression": "1 + 1", "variables": []}}]}
        real_run_item, real_pool = S.agent.run_item, S.POOL
        S.agent.run_item, S.POOL = fake_run_item, Now()
        try:
            run = {"id": "20261026-130000-beef", "model": "m", "lang": "en", "seq": 0, "events": [], "live": {}, "stop": False,
                   "status": "running", "plan": {"new": {"name": "n.pdf", "version": "1"}, "old": None},
                   "items": [{"sec": s, "title": "T" + s, "page": 1, "kind": "rule", "source": "t", "status": "queued", "cases": [],
                              "new_text": "Es dürfen nicht mehr als 7 Monate vergangen sein.", "old_text": ""} for s in ("1", "2", "3")]}
            S.RUNS[run["id"]] = run
            for s in ("1", "2", "3"):
                S.process_item(run, s)  # step 1: the AI only extracts
            self.assertEqual([i["status"] for i in run["items"]], ["review"] * 3)
            self.assertEqual({m for _, m, _ in calls}, {"extract"})
            self.assertFalse([t for t in S.STORE["testcases"] if t["run"] == run["id"]])
            base = f"/api/runs/{run['id']}"

            # nothing approved yet; developers may not decide
            self.assertEqual(self._http("POST", base + "/cases", {})[0], 409)
            self.assertEqual(self._http("POST", base + "/decide", {"secs": ["1"], "decision": "approved"}, role="dev")[0], 403)

            # edit §1: a quote that is not in the text is flagged, an unknown change type is refused
            self.assertEqual(self._http("PATCH", base + "/items/1/change", {"change_type": "nonsense"})[0], 400)
            st, r = self._http("PATCH", base + "/items/1/change", {"summary": "Gap extended to 7 months",
                                                                   "quotes_new": ["nicht mehr als 7 Monate", "erfundener Satz hier"]})
            self.assertEqual(st, 200)
            self.assertEqual(r["changes"], ["summary", "quotes_new"])
            self.assertEqual([q["ok"] for q in r["spec_change"]["quote_checks"]], [True, False])

            # select-all approve, then decline §3
            self.assertEqual(self._http("POST", base + "/decide", {"decision": "approved"})[1]["changed"], ["1", "2", "3"])
            self.assertEqual(self._http("POST", base + "/decide", {"secs": ["3"], "decision": "declined"})[0], 200)
            st, r = self._http("POST", base + "/cases", {})
            self.assertEqual((st, r["queued"]), (200, ["1", "2"]))

            # step 2 got the edited, approved spec change; declined §3 was not sent
            sent = {sec: a for sec, m, a in calls if m == "cases"}
            self.assertEqual(sorted(sent), ["1", "2"])
            self.assertEqual(sent["1"]["summary"], "Gap extended to 7 months")
            self.assertEqual([i["status"] for i in run["items"]], ["done", "done", "review"])
            tc = next(t for t in S.STORE["testcases"] if t["run"] == run["id"] and t["section"] == "1")
            self.assertEqual(tc["spec_change"]["summary"], "Gap extended to 7 months")
            texts = [e["data"].get("text") for e in tc["cot"] if e["type"] == "thought"]
            self.assertEqual(texts, ["extract §1", "cases §1"])  # the extraction reasoning stays with the case
            self.assertTrue(any(e["type"] == "change_edited" for e in tc["cot"]))
        finally:
            S.agent.run_item, S.POOL = real_run_item, real_pool
            srv.shutdown()

    def test_interrupted_run_can_be_generated_again(self):
        import json
        S = self.S
        os.makedirs(os.path.join(self.tmp, "runs"), exist_ok=True)
        with open(os.path.join(self.tmp, "runs", "r1.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "r1", "status": "running", "items": [{"sec": "1", "status": "running"}, {"sec": "2", "status": "done"}]}, f)
        run = S.load_run("r1")
        self.assertEqual(run["status"], "interrupted")
        self.assertEqual([i["status"] for i in run["items"]], ["error", "done"])

    def test_bad_pdf_does_not_replace_a_valid_document_or_poison_planning(self):
        import io
        from unittest.mock import Mock
        from pypdf import PdfWriter
        S = self.S
        path = os.path.join(S.UPLOADS, "keep.pdf")
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buf = io.BytesIO()
        writer.write(buf)
        original = buf.getvalue()
        with open(path, "wb") as f:
            f.write(original)
        handler = object.__new__(S.Handler)
        handler.body = lambda: b"%PDF-1.7\nbroken"
        handler.send_json = Mock()
        with self.assertRaises(S.ApiError) as err:
            handler.api_post_upload([], {"name": ["keep.pdf"]})
        self.assertEqual(err.exception.status, 400)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), original)
        with self.assertRaises(S.ApiError):
            handler.api_post_upload([], {"name": ["bad.pdf"]})
        self.assertFalse(os.path.exists(os.path.join(S.UPLOADS, "bad.pdf")))

    def test_pdf_without_text_is_rejected_without_leaving_an_upload(self):
        import io
        from unittest.mock import Mock
        from pypdf import PdfWriter
        S = self.S
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buf = io.BytesIO()
        writer.write(buf)
        handler = object.__new__(S.Handler)
        handler.body = buf.getvalue
        handler.send_json = Mock()
        with self.assertRaises(S.ApiError) as err:
            handler.api_post_upload([], {"name": ["scan.pdf"]})
        self.assertEqual(err.exception.status, 400)
        self.assertIn("OCR", err.exception.message)
        self.assertFalse(os.path.exists(os.path.join(S.UPLOADS, "scan.pdf")))


class RecapTests(unittest.TestCase):
    CASES = [{"id": "A", "section": "3.12.5", "expected_value": "2026-03-27", "spec_change": {"summary": "Only confirmed days count."}},
             {"id": "B", "section": "3.12", "expected_value": "true", "spec_change": {"summary": "30-day minimum."}}]
    ROWS = [{"id": "A", "section": "3.12.5", "criterion": "EFZ ends after 42 days minus confirmed prior days.", "result_name": "efz_end", "result_type": "date"},
            {"id": "B", "section": "3.12", "criterion": "Request 41 needs 30 days.", "result_name": "request_allowed", "result_type": "bool"}]

    def fake_model(self, content):
        import io
        import json
        from unittest import mock
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        return mock.patch("urllib.request.urlopen", return_value=mock.MagicMock(__enter__=lambda s: io.BytesIO(body), __exit__=lambda *a: False))

    def test_answers_never_reach_the_developer(self):
        import json
        import recap
        leaky = {"changed": "EFZ now ends on 27.03.2026.", "todo": ["Run the cases"], "verify": ["The 30-day gate"],
                 "rows": {"A": "efz_end should be 2026-03-27", "B": "request_allowed true at 35 days"}}
        with self.fake_model("<think>x</think>" + json.dumps(leaky)):
            out = recap.generate({"base": "http://x", "key": "k", "model": "m"}, {"id": "P"}, self.ROWS, self.CASES)
        text = json.dumps(out)
        for secret in ("2026-03-27", "27.03.2026", "true"):
            self.assertNotIn(secret, text)
        self.assertEqual(out["todo"], ["Run the cases"])  # clean fields are kept

    def test_fallback_without_ai(self):
        import recap
        out = recap.fallback({"id": "P"}, self.ROWS, self.CASES)
        self.assertIn("Only confirmed days count.", out["changed"])
        self.assertEqual(set(out["rows"]), {"A", "B"})
        self.assertTrue(out["todo"] and out["verify"])


if __name__ == "__main__":
    unittest.main()
