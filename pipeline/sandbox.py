"""The AI's terminal: runs a short Python calculation script in a separate process.

Guard rails (this runs model-written code on your machine, so keep them):
- the script is checked before it runs: only calculation modules may be imported, and file,
  process, network and introspection built-ins are refused;
- it runs with `python -I` in an empty temporary folder, with a minimal environment and a
  10 s timeout; output is capped.
The formula evaluator (formula.py) is prepended, so `evaluate(expr, **variables)` is available
and gives exactly the result the pipeline's oracle will compute.
"""
import ast
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_IMPORTS = {"math", "datetime", "decimal", "fractions", "statistics", "calendar", "json",
                   "itertools", "functools", "re", "dataclasses", "typing", "collections"}
BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "globals",
                "locals", "vars", "getattr", "setattr", "delattr", "help", "exit", "quit", "memoryview",
                "__builtins__", "__loader__", "__spec__"}
TIMEOUT_S = 10
MAX_OUTPUT = 20000


def check(code):
    """Return None if the script may run, else the reason it is refused."""
    if len(code) > 20000:
        return "script too long"
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    return f"import not allowed: {a.name} (allowed: {', '.join(sorted(ALLOWED_IMPORTS))})"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                return f"import not allowed: {node.module}"
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            return f"name not allowed: {node.id}"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return f"attribute not allowed: {node.attr}"
    return None


def run(code):
    """Run a script. Returns {ok, stdout, stderr, exit_code, ms, refused}."""
    reason = check(code)
    if reason:
        return {"ok": False, "stdout": "", "stderr": reason, "exit_code": None, "ms": 0, "refused": True}
    with open(os.path.join(HERE, "formula.py"), encoding="utf-8") as f:
        prelude = f.read()
    script = prelude + "\n# ---- AI script ----\n" + code + "\n"
    with tempfile.TemporaryDirectory(prefix="eel-calc-") as tmp:
        path = os.path.join(tmp, "calc.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
        env = {"PYTHONIOENCODING": "utf-8", "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "PATH": ""}
        t0 = time.time()
        try:
            # -X utf8: -I ignores PYTHONIOENCODING, and Windows would otherwise print umlauts in cp1252
            p = subprocess.run([sys.executable, "-I", "-S", "-X", "utf8", path], cwd=tmp, env=env, capture_output=True,
                               timeout=TIMEOUT_S, text=True, encoding="utf-8", errors="replace",
                               stdin=subprocess.DEVNULL)
            out, err, code_ = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired:
            out, err, code_ = "", f"timeout after {TIMEOUT_S} s", None
        ms = int((time.time() - t0) * 1000)
    offset = script[:script.index("# ---- AI script ----")].count("\n") + 1
    err = re.sub(r'File "[^"]*calc\.py", line (\d+)',
                 lambda m: f'File "calc.py", line {int(m.group(1)) - offset}', err)
    return {"ok": code_ == 0, "stdout": out[:MAX_OUTPUT], "stderr": err[-MAX_OUTPUT:], "exit_code": code_,
            "ms": ms, "refused": False}
