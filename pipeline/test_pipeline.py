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

    def test_number_not_in_quote_warns(self):
        c = self.case()
        c["formula"]["variables"][1]["value"] = "49"
        g, _ = agent.check_case(dict(c, expected_value="2026-04-03"), self.item, [])
        self.assertEqual(next(x for x in g if x["id"] == "G4")["status"], "warn")


if __name__ == "__main__":
    unittest.main()
