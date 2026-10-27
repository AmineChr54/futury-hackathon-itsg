"""Spec documents: PDF text → numbered sections → change log → section diff.

Everything here is deterministic. The AI only sees the sections this module selects.
"""
import difflib
import hashlib
import json
import os
import re
import threading
from collections import Counter

HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){1,7}|\d{1,2}\.)\s+([A-ZÄÖÜ„\"“].{1,118})$")
DOT_LEADER = re.compile(r"(\.\s?){4,}|…{2,}")
# change-log rows: "13.4 10.03.2026 text" (Verfahrensbeschreibung) or "10.12.2025 text" (Gemeinsame Rundschreiben)
LOG_ROW = re.compile(r"^(?:(\d{1,2}\.\d{1,2})\s+)?(\d{2}\.\d{2}\.\d{4})\s+(.*)$")
LOG_REF = re.compile(r"(?<![\d.§])(\d{1,2}(?:\.\d{1,3}){0,6})\.?\s+[„\"“]")
RULE_WORDS = re.compile(r"\b(Tage?n?|Wochen?|Monate?n?|Jahre?n?|Prozent|Euro|mindestens|höchstens|mehr als|"
                        r"weniger als|nicht mehr|spätestens|frühestens|bis zu|innerhalb|vor Ablauf|nach Ablauf|"
                        r"Beitragsbemessungsgrenze|Höchstbetrag|Regelentgelt|Nettoarbeitsentgelt|Brutto)\b|%|€", re.I)
NUMBER = re.compile(r"\d")
SKIP_TITLES = re.compile(r"Änderungs|Inhalt|Vorwort|Abkürzung|Anlage|Literatur|Stichwort", re.I)
PARSER_VERSION = 2  # part of the cache key: documents are parsed again when the parsing changes
MAX_SECTION_CHARS = 400000  # no truncation in practice: a change at the end of a long section must still be seen
TYPO = str.maketrans({"\u201e": '"', "\u201c": '"', "\u201d": '"', "\u201a": "'", "\u2018": "'", "\u2019": "'", "\u00b4": "'", "`": "'",
                      "\u00ab": '"', "\u00bb": '"', "\u2013": "-", "\u2014": "-", "\u2010": "-", "\u2011": "-", "\u2212": "-",
                      "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2026": "..."})
LIGATURES = {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl"}
CONJ = r"(?:und|oder|bzw|sowie|bis|als)\b"


def _norm_line(s):
    return re.sub(r"\d+", "#", " ".join(s.split()))


def normalize_text(s):
    """Text without layout: whitespace, line-break hyphenation, quote and dash styles, ligatures and spacing
    around punctuation are made uniform, so two renderings of the same wording compare equal."""
    s = s.replace("\u00ad", "")
    for a, b in LIGATURES.items():
        s = s.replace(a, b)
    s = s.translate(TYPO)
    s = re.sub(rf"(\w)-[ \t]*\n\s*({CONJ})", r"\1- \2", s)          # "Aus-⏎und" is "Aus- und"
    s = re.sub(r"(\w)-[ \t]*\n\s*([a-zäöüß])", r"\1\2", s)            # soft hyphenation: Mit-⏎aufnahme
    s = re.sub(r"(\w)-[ \t]*\n\s*(\w)", r"\1-\2", s)                  # a real hyphen at a line end: BMV-⏎Ä
    s = re.sub(r"\s+", " ", s)
    s = re.sub(rf"(\w) -(?= {CONJ})", r"\1-", s)                       # "Aus - und" (extraction artefact)
    s = re.sub(r"(\w) -(?=\w)", r"\1-", s)                             # "Arbeitsunfähigkeits -Richtlinie"
    s = re.sub(r'\s+([.,;:!?)\]"])(?=\s|$|[.,;:])', r"\1", s)          # no space before closing punctuation
    s = re.sub(r"([(\[])\s+", r"\1", s)
    s = re.sub(r"§\s+(?=\d)", "§ ", s)
    return s.strip()


def loose(s):
    """For deciding "changed or not": also ignores case, spaces and hyphens, which PDFs render differently."""
    return re.sub(r"[\s\-]", "", normalize_text(s)).lower()


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


CHAPTER = re.compile(r'^\d{1,2}\.?\s+[A-ZÄÖÜ][a-zäöüß]+(\s+[A-Za-zÄÖÜäöüß-]+){0,8}$')  # "2. Gesetzliche Grundlagen"


def parse_changelog(pages, max_pages=40):
    """Rows of an Änderungsübersicht / Änderungshistorie table: version (or the date), date, text, § refs.

    The table of contents mentions the change log too, so the table starts on the first page whose
    lines carry change-log rows; running headers and footers are dropped so they don't run into a row.
    It ends at a page without rows, or at a chapter heading after the page's last row."""
    lines_per_page = strip_running_lines(pages)[:max_pages]
    start = next((i for i, p in enumerate(pages[:max_pages]) if re.search(r"Änderungs(übersicht|historie)", p)
                  and any(LOG_ROW.match(l.strip()) for l in lines_per_page[i])), None)
    if start is None:
        return []
    rows, cur = [], None
    for lines in lines_per_page[start:]:
        lines = [l.strip() for l in lines]
        last_row = max((k for k, t in enumerate(lines) if LOG_ROW.match(t)), default=-1)
        if rows and last_row < 0:
            break
        for k, t in enumerate(lines):
            if not t or DOT_LEADER.search(t) or re.fullmatch(r"(Seite\s+)?\d+(\s+von\s+\d+)?", t):
                continue
            m = LOG_ROW.match(t)
            if m:
                cur = {"version": m.group(1) or m.group(2), "date": m.group(2), "text": m.group(3)}
                rows.append(cur)
            elif k > last_row and rows and CHAPTER.match(t):
                return _finish_log(rows)
            elif cur is not None:
                cur["text"] += "\n" + t  # a line break, so normalize_text joins words hyphenated across lines
    return _finish_log(rows)


def _finish_log(rows):
    for r in rows:
        r["text"] = normalize_text(r["text"])
        r["refs"] = sorted(set(LOG_REF.findall(r["text"])), key=lambda n: [int(x) for x in n.split(".")])
    # a real change log names sections; dated sentences in a preface ("Rundschreiben vom 10.12.2025 …") do not
    return rows if any(r["refs"] for r in rows) else []


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


_PARSING = {}  # sha → lock: when many people start a run at once, the PDF is parsed once, not once each
_PARSING_LOCK = threading.Lock()


def load(path, cache_dir):
    """Parse a document (cached by content hash)."""
    sha = file_sha256(path)
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f"{sha}.p{PARSER_VERSION}.json")
    with _PARSING_LOCK:
        lock = _PARSING.setdefault(sha, threading.Lock())
    with lock:
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
        tmp = cache + ".tmp"  # readers never see a half-written cache file
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        os.replace(tmp, cache)
        return doc


FIELD_ROW = re.compile(r"^\d{3}\s?[–-]")  # a record-layout row: "014 – 021 …"


def _para_norm(s):
    return re.sub(r"\s+", " ", s.replace("­", "").replace(" ", " ")).strip()


def paragraphs(raw_lines):
    """Reflow PDF lines into paragraphs. A blank line ends a paragraph only after a full sentence
    (otherwise it is a page break mid-sentence); bullets and key lists („1“ = …) start new ones."""
    paras, cur = [], ""
    for raw in raw_lines:
        line = _para_norm(raw)
        sentence_done = bool(re.search(r"[.:;!?][“\")]?$", cur))
        if not line:
            if cur and (sentence_done or FIELD_ROW.match(cur)):
                paras.append(cur); cur = ""
            continue
        starts_new = (line.startswith(("•", "- ")) or FIELD_ROW.match(line) or re.match(r"^„[^“]{1,6}“\s*=", line)
                      or (sentence_done and line.startswith(("„", "Hinweis", "Beispiel"))))
        if cur and starts_new and not FIELD_ROW.match(cur):
            paras.append(cur); cur = ""
        if cur.endswith("-") and line[:1].islower():
            cur = cur[:-1] + line  # hyphenation across the line break
        else:
            cur = (cur + " " + line).strip()
    if cur:
        paras.append(cur)
    return paras


def summary(doc):
    return {k: doc[k] for k in ("name", "sha256", "pages", "version", "title", "chars")} | {
        "sections": len(doc["sections"]), "changelog_rows": len(doc["changelog"])}


def _title_key(t):
    return " ".join(re.sub(r"[^a-zäöüß0-9]+", " ", normalize_text(t).lower()).split())


def _ratio(a, b, quick=False):
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.quick_ratio() if quick else sm.ratio()


def _parent(sec):
    return sec.rsplit(".", 1)[0] if "." in sec else None


def similarity(a, b):
    """How likely two documents are versions of the same text (0…1): overlap of their section titles,
    with and without numbers, so a renumbered version still counts."""
    ka = {(s["sec"], " ".join(_title_key(s["title"]).split()[:4])) for s in a["sections"]}
    kb = {(s["sec"], " ".join(_title_key(s["title"]).split()[:4])) for s in b["sections"]}
    if not ka or not kb:
        return 0.0
    ta, tb = {t for _, t in ka}, {t for _, t in kb}
    return max(len(ka & kb) / len(ka | kb), len(ta & tb) / len(ta | tb) * 0.9)


def _shingles(text):
    """Three-word fingerprints of a text (first 6000 words), for a fast content similarity."""
    w = loose_words(text)[:6000]
    return {hash(tuple(w[i:i + 3])) for i in range(max(1, len(w) - 2))} if len(w) >= 30 else set(w)


def loose_words(text):
    return [re.sub(r"[\-]", "", x).lower() for x in normalize_text(text).split(" ") if x]


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else (1.0 if not a and not b else 0.0)


def match_sections(old_secs, new_secs):
    """Pair each new section with its previous version: {new sec: old sec}.

    Every plausible pair gets a score from title and text similarity (plus a little for an unchanged
    number); the best pairs are taken first. So renumbering, near-identical titles ("Datenbaustein DBLT –
    Zusatzdaten für die …" / "… DBSF – …") and repeated titles ("Allgemeines") pair by content, not by number."""
    ot = [(so, _title_key(so["title"]), _shingles(so["text"])) for so in old_secs]
    nt = [(sn, _title_key(sn["title"]), _shingles(sn["text"])) for sn in new_secs]
    cands = []
    for sn, tn, wn in nt:
        for so, to, wo in ot:
            same = so["sec"] == sn["sec"]
            text = _jaccard(wo, wn)
            if not same and text < 0.3 and to != tn:
                continue  # cheap filter before comparing titles
            title = 1.0 if to == tn else _ratio(to, tn)
            ok = (same and title >= 0.95) or text >= 0.5 or (title >= 0.8 and text >= 0.3) or (title >= 0.95 and text >= 0.15)
            if ok:
                cands.append((0.5 * title + 0.5 * text + (0.05 if same else 0), sn["sec"], so["sec"]))
    pairs, used = {}, set()
    for _, ns, os_ in sorted(cands, reverse=True):
        if ns not in pairs and os_ not in used:
            pairs[ns] = os_
            used.add(os_)
    return pairs


def newer_first(a, b):
    """Order two versions of a document (newest first) by version / date, then file name."""
    ka, kb = _version_key(a.get("version")), _version_key(b.get("version"))
    if ka != kb:
        return (a, b) if ka > kb else (b, a)
    return (a, b) if a["name"] >= b["name"] else (b, a)


def word_diff(old, new):
    """Word-level redline: [[op, text]] with op in '=', '-', '+'. Replacements that differ only in layout
    (hyphens, spacing, case) count as equal."""
    a, b = normalize_text(old).split(" "), normalize_text(new).split(" ")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    ops = []
    def add(op, text):
        if ops and ops[-1][0] == op:
            ops[-1][1] += " " + text
        else:
            ops.append([op, text])
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or (tag == "replace" and loose(" ".join(a[i1:i2])) == loose(" ".join(b[j1:j2]))):
            add("=", " ".join(b[j1:j2]))
            continue
        if i2 > i1:
            add("-", " ".join(a[i1:i2]))
        if j2 > j1:
            add("+", " ".join(b[j1:j2]))
    return ops, sm.ratio()


def hunks(ops, context=25):
    """The changed spots of a word diff with a little context: [{"old": …, "new": …, "before": …, "after": …}]."""
    out, cur = [], None
    for i, (op, text) in enumerate(ops):
        if op == "=":
            words = text.split(" ")
            if cur is not None:
                if len(words) <= 2 * context and i < len(ops) - 1:  # short gap: one hunk
                    cur["old"].append(text); cur["new"].append(text)
                    continue
                cur["after"] = " ".join(words[:context]); out.append(cur); cur = None
            continue
        if cur is None:
            prev = ops[i - 1][1].split(" ") if i and ops[i - 1][0] == "=" else []
            cur = {"before": " ".join(prev[-context:]), "old": [], "new": [], "after": ""}
        cur["old" if op == "-" else "new"].append(text)
    if cur is not None:
        out.append(cur)
    return [{**h, "old": " ".join(h["old"]), "new": " ".join(h["new"])} for h in out]


def _signal(text):
    return len(RULE_WORDS.findall(text)) + len(NUMBER.findall(text)) // 3


def _log_index(changelog, secs_known):
    log_refs = {}
    for row in (changelog or []):
        for r in row["refs"]:
            sec = r  # field-level refs (3.12.7) live inside their block's section (3.12)
            while sec not in secs_known and "." in sec:
                sec = sec.rsplit(".", 1)[0]
            rows = log_refs.setdefault(sec if sec in secs_known else r, [])
            if row not in rows:
                rows.append(row)
    return log_refs


def diff_documents(old, new, changelog=None):
    """Changed / added / removed sections between two documents, riskiest first. Sections are paired by
    title and content (match_sections), so renumbering alone is not a change, and layout differences
    (line breaks, hyphenation, quote styles) are ignored."""
    o = {s["sec"]: s for s in old["sections"]}
    pairs = match_sections(old["sections"], new["sections"])
    paired_old = set(pairs.values())
    log_refs = _log_index(changelog, {s["sec"] for s in new["sections"]} | set(o))
    changes = []

    def emit(kind, sec, so, sn, ops, ratio, changed):
        s = sn or so
        if SKIP_TITLES.search(s["title"]):
            return  # the change log / table of contents changes every version
        in_log = sec in log_refs or any(sec.startswith(r + ".") for r in log_refs)
        changes.append({
            "sec": sec, "title": s["title"], "page": s["page"], "kind": kind,
            "similarity": round(ratio, 4), "ops": ops, "hunks": hunks(ops, context=40) if kind == "changed" else [],
            "old_text": so["text"] if so else "", "new_text": sn["text"] if sn else "",
            "signal": _signal(changed), "changed_words": len(changed.split()),
            "source": "log+diff" if in_log else "diff-only",
            "log": [r["text"] for r in log_refs.get(sec, [])][:3],
            "moved_from": so["sec"] if so and sn and so["sec"] != sn["sec"] else None,
        })

    for sn in new["sections"]:
        so = o.get(pairs.get(sn["sec"])) if sn["sec"] in pairs else None
        if so:
            if loose(so["text"]) == loose(sn["text"]):
                continue  # same wording (perhaps renumbered or re-laid-out)
            ops, ratio = word_diff(so["text"], sn["text"])
            changed = " ".join(t for op, t in ops if op != "=")
            if changed.strip():
                emit("changed", sn["sec"], so, sn, ops, ratio, changed)
        else:
            emit("added", sn["sec"], None, sn, [["+", normalize_text(sn["text"])]], 0.0, sn["text"])
    for so in old["sections"]:
        if so["sec"] not in paired_old:
            emit("removed", so["sec"], so, None, [["-", normalize_text(so["text"])]], 0.0, so["text"])
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
