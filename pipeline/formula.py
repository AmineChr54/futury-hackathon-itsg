"""Safe formula language for test-case calculations.

A formula is one expression over named variables, e.g.

    add_days(au_start, efz_days - prior_days - 1)

Numbers are exact decimals (no float rounding: one wrong cent fails a vendor). Dates are
ISO strings ("2026-03-11") converted to dates. Only the functions in FUNCS are callable; any
other Python construct is rejected before evaluation.

This file is also copied verbatim in front of every script the AI runs in its terminal, so
the AI can check a formula with exactly the same evaluator: evaluate(expr, **variables).
Standard library only.
"""
import ast
import datetime as _dt
import math as _math
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING, InvalidOperation, getcontext

getcontext().prec = 34


class FormulaError(ValueError):
    pass


def _num(x):
    if isinstance(x, bool):
        raise FormulaError("expected a number, got a boolean")
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, float):
        return Decimal(repr(x))
    if isinstance(x, str):
        try:
            return Decimal(x.strip().replace(",", "."))
        except InvalidOperation:
            raise FormulaError(f"not a number: {x!r}")
    raise FormulaError(f"expected a number, got {type(x).__name__}")


def _int(x):
    n = _num(x)
    if n != n.to_integral_value():
        raise FormulaError(f"expected a whole number, got {n}")
    return int(n)


def _date(x):
    if isinstance(x, _dt.date):
        return x
    if isinstance(x, str):
        s = x.strip()
        try:
            if len(s) == 8 and s.isdigit():  # jhjjmmtt, as in DTA records
                return _dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
            if len(s) == 10 and s[2] == "." and s[5] == ".":  # German 11.03.2026
                return _dt.date(int(s[6:]), int(s[3:5]), int(s[:2]))
            return _dt.date.fromisoformat(s)
        except ValueError:
            pass
    raise FormulaError(f"not a date: {x!r} (use YYYY-MM-DD)")


def _add_months(d, n):
    d, n = _date(d), _int(n)
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return _dt.date(y, m, min(d.day, last))


def _round(x, places=0):
    q = Decimal(1).scaleb(-_int(places))
    return _num(x).quantize(q, rounding=ROUND_HALF_UP)


def _minmax(fn):
    def f(*args):
        if not args:
            raise FormulaError(f"{fn.__name__} needs arguments")
        if all(isinstance(a, _dt.date) for a in args):
            return fn(args)
        return fn(_num(a) for a in args)
    return f


FUNCS = {
    # dates
    "date": lambda s: _date(s),
    "add_days": lambda d, n: _date(d) + _dt.timedelta(days=_int(n)),
    "add_weeks": lambda d, n: _date(d) + _dt.timedelta(days=7 * _int(n)),
    "add_months": _add_months,
    "days_between": lambda a, b: Decimal((_date(b) - _date(a)).days),
    "days_inclusive": lambda a, b: Decimal((_date(b) - _date(a)).days + 1),
    "weekday": lambda d: Decimal(_date(d).isoweekday()),  # 1 = Monday … 7 = Sunday
    # numbers
    "min": _minmax(min),
    "max": _minmax(max),
    "abs": lambda x: abs(_num(x)),
    "round": _round,  # commercial rounding (half up), as in German payroll
    "floor": lambda x: _num(x).to_integral_value(rounding=ROUND_FLOOR),
    "ceil": lambda x: _num(x).to_integral_value(rounding=ROUND_CEILING),
    "percent": lambda x, p: _num(x) * _num(p) / Decimal(100),
}
FUNC_DOCS = {
    "date(s)": "date from 'YYYY-MM-DD', 'DD.MM.YYYY' or 'YYYYMMDD'",
    "add_days(d, n)": "date d plus n days",
    "add_weeks(d, n)": "date d plus 7*n days",
    "add_months(d, n)": "date d plus n calendar months (end of month clamped)",
    "days_between(a, b)": "b - a in days",
    "days_inclusive(a, b)": "days from a to b counting both (b - a + 1)",
    "weekday(d)": "1 = Monday … 7 = Sunday",
    "min(...), max(...)": "numbers or dates",
    "abs(x), floor(x), ceil(x)": "",
    "round(x, places)": "commercial rounding, half up",
    "percent(x, p)": "p percent of x",
}

_BINOPS = {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow}
_CMPOPS = {ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE}


def parse(expression):
    """Parse and validate; returns (tree, sorted variable names)."""
    if not isinstance(expression, str) or not expression.strip():
        raise FormulaError("empty formula")
    if len(expression) > 2000:
        raise FormulaError("formula too long")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"syntax error: {e.msg}")
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.Load, ast.operator, ast.cmpop, ast.boolop, ast.unaryop)):
            continue
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            continue
        if isinstance(node, ast.Compare) and all(type(o) in _CMPOPS for o in node.ops):
            continue
        if isinstance(node, (ast.BoolOp, ast.IfExp)):
            continue
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Not)):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool)):
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS or node.keywords:
                raise FormulaError(f"function not allowed: {ast.unparse(node.func)}")
            continue
        if isinstance(node, ast.Name):
            if node.id not in FUNCS and node.id not in ("True", "False"):
                names.add(node.id)
            continue
        raise FormulaError(f"not allowed in a formula: {type(node).__name__}")
    return tree, sorted(names)


def coerce(value, typ):
    """Turn a stored variable value into its runtime type."""
    if typ == "date":
        return _date(value)
    if typ == "bool":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("true", "1", "ja", "yes", "j"):
            return True
        if str(value).strip().lower() in ("false", "0", "nein", "no", "n"):
            return False
        raise FormulaError(f"not a boolean: {value!r}")
    if typ == "text":
        return str(value)
    return _num(value)


def _guess(value):
    if isinstance(value, (bool, Decimal, _dt.date)):
        return value
    if isinstance(value, (int, float)):
        return _num(value)
    if isinstance(value, str):
        try:
            return _date(value)
        except FormulaError:
            pass
        try:
            return _num(value)
        except FormulaError:
            return value
    raise FormulaError(f"unsupported value {value!r}")


def _eval(node, env):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return _num(v)
        return v
    if isinstance(node, ast.Name):
        if node.id in ("True", "False"):
            return node.id == "True"
        if node.id not in env:
            raise FormulaError(f"variable has no value: {node.id}")
        return env[node.id]
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not v
        return -_num(v) if isinstance(node.op, ast.USub) else _num(v)
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, env), _eval(node.right, env)
        op = type(node.op)
        if isinstance(a, _dt.date) or isinstance(b, _dt.date):
            if op is ast.Sub and isinstance(a, _dt.date) and isinstance(b, _dt.date):
                return Decimal((a - b).days)
            if op in (ast.Add, ast.Sub) and isinstance(a, _dt.date) and not isinstance(b, _dt.date):
                n = _int(b)
                return a + _dt.timedelta(days=n if op is ast.Add else -n)
            raise FormulaError("dates only support date ± days and date - date; use add_days / days_between")
        a, b = _num(a), _num(b)
        try:
            if op is ast.Add: return a + b
            if op is ast.Sub: return a - b
            if op is ast.Mult: return a * b
            if op is ast.Div: return a / b
            if op is ast.FloorDiv: return a // b
            if op is ast.Mod: return a % b
            if op is ast.Pow:
                if abs(b) > 100: raise FormulaError("exponent too large")
                return a ** b
        except ZeroDivisionError:
            raise FormulaError("division by zero")
        except ArithmeticError as e:  # decimal overflow, invalid operation (e.g. 0/0, (-8) ** 0.5)
            raise FormulaError(f"arithmetic error: {type(e).__name__}")
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, env)
            if isinstance(left, _dt.date) != isinstance(right, _dt.date):
                raise FormulaError("cannot compare a date with a number")
            if not isinstance(left, (_dt.date, bool, str)):
                left, right = _num(left), _num(right)
            ok = {ast.Eq: left == right, ast.NotEq: left != right, ast.Lt: left < right,
                  ast.LtE: left <= right, ast.Gt: left > right, ast.GtE: left >= right}[type(op)]
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = (_eval(v, env) for v in node.values)
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.IfExp):
        return _eval(node.body, env) if _eval(node.test, env) else _eval(node.orelse, env)
    if isinstance(node, ast.Call):
        args = [_eval(a, env) for a in node.args]
        try:
            return FUNCS[node.func.id](*args)
        except TypeError as e:
            raise FormulaError(f"{node.func.id}: {e}")
        except (ArithmeticError, OverflowError) as e:  # e.g. round(x, 50), a date past year 9999
            raise FormulaError(f"{node.func.id}: {type(e).__name__}")
    raise FormulaError(f"cannot evaluate {type(node).__name__}")


def fmt(value):
    """Canonical text form of a result, used to compare AI and oracle values."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, _dt.datetime):
        value = value.date()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, (int, float, Decimal)):
        d = _num(value)
        if d == d.to_integral_value():
            return str(d.quantize(Decimal(1)))
        return format(d.normalize(), "f")
    return str(value)


def same_value(a, b):
    """True if two results are the same value (2026-03-27 == 27.03.2026, 17 == 17.00)."""
    if a is None or b is None:
        return False
    sa, sb = fmt(_guess(a) if isinstance(a, str) else a), fmt(_guess(b) if isinstance(b, str) else b)
    if sa == sb:
        return True
    try:
        return _num(sa) == _num(sb)
    except FormulaError:
        return sa.strip().lower() == sb.strip().lower()


def evaluate(expression, variables=None, types=None, **kw):
    """Evaluate a formula. variables: {name: value}; types: {name: number|date|bool|text}.
    Returns the result in canonical text form (see fmt)."""
    variables = dict(variables or {}, **kw)
    types = types or {}
    tree, names = parse(expression)
    env = {}
    for k, v in variables.items():
        env[k] = coerce(v, types[k]) if k in types else _guess(v)
    missing = [n for n in names if n not in env]
    if missing:
        raise FormulaError("variables have no value: " + ", ".join(missing))
    return fmt(_eval(tree, env))


def trace(expression, variables=None, types=None):
    """Step-by-step evaluation of every sub-expression, for the provenance view."""
    variables = variables or {}
    types = types or {}
    tree, names = parse(expression)
    env = {k: (coerce(v, types[k]) if k in types else _guess(v)) for k, v in variables.items()}
    steps, seen = [], set()

    def visit(node):
        for child in ast.iter_child_nodes(node):
            visit(child)
        if isinstance(node, (ast.BinOp, ast.Call, ast.Compare, ast.IfExp, ast.BoolOp)):
            src = ast.unparse(node)
            if src not in seen:
                seen.add(src)
                try:
                    steps.append([src, fmt(_eval(node, env))])
                except FormulaError as e:
                    steps.append([src, "error: " + str(e)])
    visit(tree.body)
    return steps


def normalize_expression(expression):
    try:
        return ast.unparse(ast.parse(expression.strip(), mode="eval"))
    except SyntaxError:
        return " ".join(str(expression).split())
