"""Spec documents: PDF text → numbered sections → change log → section diff.

Everything here is deterministic. The AI only sees the sections this module selects.
"""
import difflib
import hashlib
import json
import os
import re
from collections import Counter

HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){1,7}|\d{1,2}\.)\s+([A-ZÄÖÜ„\"“].{1,118})$")
DOT_LEADER = re.compile(r"(\.\s?){4,}|…{2,}")
LOG_ROW = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(\d{2}\.\d{2}\.\d{4})\s+(.*)$")
LOG_REF = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d{1,3}){1,6})\s+[„\"“]")
RULE_WORDS = re.compile(r"\b(Tage?n?|Wochen?|Monate?n?|Jahre?n?|Prozent|Euro|mindestens|höchstens|mehr als|"
                        r"weniger als|nicht mehr|spätestens|frühestens|bis zu|innerhalb|vor Ablauf|nach Ablauf|"
                        r"Beitragsbemessungsgrenze|Höchstbetrag|Regelentgelt|Nettoarbeitsentgelt|Brutto)\b|%|€", re.I)
NUMBER = re.compile(r"\d")
SKIP_TITLES = re.compile(r"Änderungs|Inhalt|Vorwort|Abkürzung|Anlage|Literatur|Stichwort", re.I)
MAX_SECTION_CHARS = 40000


def _norm_line(s):
    return re.sub(r"\d+", "#", " ".join(s.split()))


def normalize_text(s):
    """Whitespace- and hyphenation-insensitive text, used for quote checks and the diff."""
    s = s.replace("­", "").replace(" ", " ")
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)  # line-break hyphenation: Mit-\naufnahme
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract_pages(path):
    """Text per page. PDFs via pypdf; .txt/.md files are treated as a single page (useful for tests)."""
    if path.lower().endswith((".txt", ".md")):
        with open(path, encoding="utf-8") as f:
            return [f.read()]
    import pypdf  # imported lazily so the rest of the module works without it
    reader = pypdf.PdfReader(path)
    return [(p.extract_text() or "") for p in reader.pages]


def strip_running_lines(pages):
    """Remove headers/footers: lines that repeat (ignoring digits) on many pages."""
    if len(pages) < 5:
        return [p.splitlines() for p in pages]
    counts = Counter()
    for p in pages:
        counts.update({_norm_line(l) for l in p.splitlines() if l.strip()})
    limit = max(3, int(len(pages) * 0.4))
    running = {k for k, n in counts.items() if n >= limit}
    return [[l for l in p.splitlines() if _norm_line(l) not in running] for p in pages]


def split_sections(pages):
    """Find numbered headings and cut the text into sections.

    Heading-like lines also occur in the table of contents, overview lists, the change log,
    cross references ("3.12.9 „Kennzeichen …“ übermittelt.") and numbered lists in examples.
    Real headings are the ones in document order, so we keep the longest strictly increasing
    sequence of candidate numbers; every other candidate stays body text."""
    lines_per_page = strip_running_lines(pages)
    lines = [(pno, raw) for pno, ls in enumerate(lines_per_page, start=1) for raw in ls]
    cands = []  # (line index, key, number, title)
    for i, (pno, raw) in enumerate(lines):
        line = raw.strip()
        if not line or DOT_LEADER.search(line) or re.search(r"\s\d{1,3}$", line):  # TOC lines
            continue
        m = HEADING.match(line)
        if not m:
            continue
        title = m.group(2).strip()
        if title[0] in "„\"“" or title.endswith((".", ",", ";")) or title.count("„") > title.count("“") + 1:
            continue  # cross reference or sentence, not a heading
        num = m.group(1).rstrip(".")
        cands.append((i, tuple(int(x) for x in num.split(".")), num, title))
    # longest strictly increasing subsequence of keys (patience sorting, O(n log n))
    import bisect
    tails, tails_idx, prev = [], [], [None] * len(cands)
    for j, c in enumerate(cands):
        k = bisect.bisect_left(tails, c[1])
        if k == len(tails):
            tails.append(c[1]); tails_idx.append(j)
        else:
            tails[k] = c[1]; tails_idx[k] = j
        prev[j] = tails_idx[k - 1] if k else None
    keep, j = [], (tails_idx[-1] if tails_idx else None)
    while j is not None:
        keep.append(cands[j]); j = prev[j]
    keep.reverse()
    sections = []
    starts = [c[0] for c in keep] + [len(lines)]
    for (i, _, num, title), end in zip(keep, starts[1:]):
        text = "\n".join(raw for _, raw in lines[i + 1:end]).strip()
        sections.append({"sec": num, "title": title, "page": lines[i][0], "text": text[:MAX_SECTION_CHARS]})
    preamble = "\n".join(raw for _, raw in lines[:starts[0]])
    return sections, preamble


def parse_changelog(pages, max_pages=15):
    """Rows of an Änderungsübersicht/Änderungshistorie table: version, date, text, § refs."""
    text_pages = pages[:max_pages]
    start = next((i for i, p in enumerate(text_pages) if re.search(r"Änderungs(übersicht|historie)", p)), None)
    if start is None:
        return []
    rows, cur = [], None
    for p in text_pages[start:]:
        for line in p.splitlines():
            m = LOG_ROW.match(line.strip())
            if m:
                cur = {"version": m.group(1), "date": m.group(2), "text": m.group(3)}
                rows.append(cur)
            elif cur is not None and line.strip():
                cur["text"] += " " + line.strip()
        if rows and not any(LOG_ROW.match(l.strip()) for l in p.splitlines()):
            break  # the table has ended
    for r in rows:
        r["text"] = " ".join(r["text"].split())
        r["refs"] = sorted(set(LOG_REF.findall(r["text"])), key=lambda n: [int(x) for x in n.split(".")])
    return rows


def detect_version(pages):
    head = "\n".join(pages[:3])
    m = re.search(r"Version\s+(\d+(?:\.\d+)+)", head)
    if m:
        return m.group(1)
    m = re.search(r"in der Fassung vom\s+(\d{2}\.\d{2}\.\d{4})", head) or re.search(r"Stand:?\s+(\d{2}\.\d{2}\.\d{4})", head)
    return m.group(1) if m else None


def _version_key(v):
    if not v:
        return (0,)
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", v):
        d, m, y = v.split(".")
        return (int(y), int(m), int(d))
    return tuple(int(x) for x in v.split("."))


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path, cache_dir):
    """Parse a document (cached by content hash)."""
    sha = file_sha256(path)
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, sha + ".json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            doc = json.load(f)
        doc["name"] = os.path.basename(path)
        return doc
    pages = extract_pages(path)
    sections, preamble = split_sections(pages)
    first = " ".join(" ".join(pages[0].split()).split()[:40]) if pages else ""
    doc = {"name": os.path.basename(path), "sha256": sha, "pages": len(pages), "version": detect_version(pages),
           "title": first[:200], "sections": sections, "changelog": parse_changelog(pages),
           "chars": sum(len(p) for p in pages)}
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return doc


def summary(doc):
    return {k: doc[k] for k in ("name", "sha256", "pages", "version", "title", "chars")} | {
        "sections": len(doc["sections"]), "changelog_rows": len(doc["changelog"])}


def similarity(a, b):
    """How likely two documents are versions of the same text (0…1): overlap of numbered headings."""
    ka = {(s["sec"], " ".join(s["title"].lower().split()[:4])) for s in a["sections"]}
    kb = {(s["sec"], " ".join(s["title"].lower().split()[:4])) for s in b["sections"]}
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / len(ka | kb)


def newer_first(a, b):
    """Order two versions of a document (newest first) by version / date, then file name."""
    ka, kb = _version_key(a.get("version")), _version_key(b.get("version"))
    if ka != kb:
        return (a, b) if ka > kb else (b, a)
    return (a, b) if a["name"] >= b["name"] else (b, a)


def word_diff(old, new):
    """Word-level redline: [[op, text]] with op in '=', '-', '+'."""
    a, b = normalize_text(old).split(" "), normalize_text(new).split(" ")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append(["=", " ".join(a[i1:i2])])
        else:
            if i2 > i1:
                ops.append(["-", " ".join(a[i1:i2])])
            if j2 > j1:
                ops.append(["+", " ".join(b[j1:j2])])
    return ops, sm.ratio()


def _signal(text):
    return len(RULE_WORDS.findall(text)) + len(NUMBER.findall(text)) // 3


def diff_documents(old, new, changelog=None):
    """Changed / added / removed sections between two documents, riskiest first."""
    o = {s["sec"]: s for s in old["sections"]}
    n = {s["sec"]: s for s in new["sections"]}
    log_refs = {}
    for row in (changelog or []):
        for r in row["refs"]:
            log_refs.setdefault(r, []).append(row)
    changes = []
    for sec in sorted(set(o) | set(n), key=lambda x: [int(p) for p in x.split(".")]):
        so, sn = o.get(sec), n.get(sec)
        if so and sn:
            if normalize_text(so["text"]) == normalize_text(sn["text"]):
                continue
            ops, ratio = word_diff(so["text"], sn["text"])
            changed = " ".join(t for op, t in ops if op != "=")
            kind = "changed"
        elif sn:
            ops, ratio, changed, kind = [["+", normalize_text(sn["text"])]], 0.0, sn["text"], "added"
        else:
            ops, ratio, changed, kind = [["-", normalize_text(so["text"])]], 0.0, so["text"], "removed"
        if not changed.strip() and kind == "changed":
            continue
        s = sn or so
        if SKIP_TITLES.search(s["title"]):
            continue  # the change log / table of contents changes every version
        in_log = sec in log_refs or any(sec.startswith(r + ".") for r in log_refs)
        changes.append({
            "sec": sec, "title": s["title"], "page": s["page"], "kind": kind,
            "similarity": round(ratio, 4), "ops": ops,
            "old_text": so["text"] if so else "", "new_text": sn["text"] if sn else "",
            "signal": _signal(changed), "changed_words": len(changed.split()),
            "source": "log+diff" if in_log else "diff-only",
            "log": [r["text"] for r in log_refs.get(sec, [])][:3],
        })
    changes.sort(key=lambda c: (-(c["signal"] > 0), c["kind"] == "removed", -c["signal"], -c["changed_words"]))
    return changes


def single_document_items(doc):
    """No earlier version to compare with: use the document's own change log for its latest
    version if it has one, otherwise the sections with the most testable rule signals."""
    rows = doc["changelog"]
    secs = {s["sec"]: s for s in doc["sections"]}
    items = {}
    if rows:
        latest = max(rows, key=lambda r: _version_key(r["version"]))["version"]
        for row in rows:
            if row["version"] != latest:
                continue
            for ref in row["refs"]:
                sec = ref  # field-level refs (3.12.7) live inside their block's section (3.12)
                while sec not in secs and "." in sec:
                    sec = sec.rsplit(".", 1)[0]
                s = secs.get(sec)
                if not s:
                    continue
                it = items.setdefault(sec, {"sec": sec, "title": s["title"], "page": s["page"], "kind": "changelog",
                                            "similarity": None, "ops": [], "old_text": "", "new_text": s["text"],
                                            "signal": _signal(s["text"]), "changed_words": len(s["text"].split()),
                                            "source": f"change log v{latest}", "log": [], "refs": []})
                if row["text"] not in it["log"]:
                    it["log"].append(row["text"])
                if ref not in it["refs"]:
                    it["refs"].append(ref)
    if items:
        return sorted(items.values(), key=lambda c: -len(c["log"]))
    out = []
    for s in doc["sections"]:
        if SKIP_TITLES.search(s["title"]):
            continue
        sig = _signal(s["text"])
        if sig >= 3 and len(s["text"]) > 200:
            out.append({"sec": s["sec"], "title": s["title"], "page": s["page"], "kind": "rule",
                        "similarity": None, "ops": [], "old_text": "", "new_text": s["text"],
                        "signal": sig, "changed_words": len(s["text"].split()),
                        "source": "rule signals", "log": []})
    # rule density, so long sections don't win just by being long
    out.sort(key=lambda c: -c["signal"] / (1 + len(c["new_text"]) / 4000) ** 0.5)
    return out
