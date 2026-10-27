"""Embed the full v13.4 specification and the slide images into demo/index.html.

    python demo/embed.py

Rewrites only the blocks between /*SPEC-FULL-START*/ … /*SPEC-FULL-END*/ and
/*IMAGES-START*/ … /*IMAGES-END*/, so it can be run again at any time.

The § list comes from the table of contents (pp. 7–14). Field-level entries have no number
in the PDF text (the headings are auto-numbered), so they are numbered in order under their
parent: 3.12 → 3.12.1 … 3.12.14. That matches the spec's own cross references
("3.12.12 „Kennzeichen Arbeitsunfähigkeit „nn““", "3.1.18 „Abgabegrund“").
Level-4 headings (2.2.2.1 …) do carry numbers and come from pipeline/documents.py.
"""
import base64
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import documents  # noqa: E402  (Achraf's deterministic PDF module)

PDF = os.path.join(ROOT, "hackathon-files", "ITSG - The Challenge Sponsor",
                   "2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf")
HTML = os.path.join(ROOT, "demo", "index.html")
IMAGES = {"logo": "ITSG-logo.png", "patrick": "tired-patrick-meme.jpeg",
          "tired": "tired-guy-meme.jpeg", "squirrel": "happy-squirrel-meme.jpeg"}

RUNNING = re.compile(r"^Stand:\s*\d{2}\.\d{2}\.\d{4}\s+Seite\s+\d+\s+von\s+\d+\s+Version\s+[\d.]+\s*$")
NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)\.?\s+(.+)$")
FIELD_ROW = re.compile(r"^\d{3}\s?[–-]")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("­", "").replace(" ", " ")).strip()


def key(s):
    """Loose comparison key for titles: letters and digits only, lower case."""
    return re.sub(r"[^0-9a-zäöüß]", "", norm(s).lower())


def parse_toc(pages):
    start = next(i for i, p in enumerate(pages) if "Inhaltsverzeichnis" in p)
    first_body = None
    entries, buf = [], []
    for p in pages[start:start + 10]:
        for raw in p.splitlines():
            line = raw.rstrip()
            if not line.strip() or RUNNING.match(line.strip()) or "Inhaltsverzeichnis" in line:
                continue
            buf.append(line)
            # an entry ends with its page number: after a dot leader, glued to the last word
            # ("…Beschäftigungsverhältnis123"), alone on the next line (" 52 ") or after a space
            if not (re.search(r"(?:\.{2,}|…)\s*\d{1,3}\s*$", line) or re.fullmatch(r"\s*\d{1,3}\s*", line)
                    or re.search(r"[A-Za-zäöüß)“]\d{1,3}\s*$", line) or re.search(r"\s\d{2,3}\s*$", line)):
                continue
            text = norm(" ".join(buf))
            buf = []
            page = int(re.search(r"(\d{1,3})\s*$", text).group(1))
            title = re.sub(r"[\s.…]*\d{1,3}\s*$", "", text).strip()
            title = re.sub(r"(?:\s?\.){3,}.*$", "", title).strip()  # dot leaders with spaces in between
            entries.append((title, page, not raw.startswith(" ")))
            if first_body is None and title.startswith("1."):
                first_body = len(entries) - 1
    out, parent, child = [], None, 0
    for title, page, _ in entries[first_body:]:
        m = NUMBERED.match(title)
        if m and (title[0].isdigit()):
            num, title = m.group(1), m.group(2)
            parent, child = num, 0
            out.append({"sec": num, "title": title, "page": page})
        elif parent:
            child += 1
            out.append({"sec": f"{parent}.{child}", "title": title, "page": page})
    return out


def body_lines(pages):
    """(page number, line) for every body line; drops the page footer and the running title."""
    lines = []
    for pno, p in enumerate(pages, start=1):
        ls = [l for l in p.splitlines()]
        # the running title is the first line of a page in chapter 3 ("Datenbaustein DBVO – …")
        while ls and not ls[0].strip():
            ls.pop(0)
        if ls and pno > 35 and re.match(r"^(Datensatz|Datenbaustein)\s", ls[0].strip()) and len(ls) > 1 and RUNNING.match(ls[1].strip()):
            ls = ls[1:]
        for l in ls:
            if RUNNING.match(l.strip()):
                continue
            lines.append((pno, l))
    return lines


def find_heading(lines, cursor, entry):
    """First line at/after cursor, on or near the ToC page, that starts with the entry's title."""
    want = key(entry["title"])[:48]
    num = entry["sec"]
    for i in range(cursor, len(lines)):
        pno, raw = lines[i]
        if pno < entry["page"] - 1:
            continue
        if pno > entry["page"] + 1:
            return None
        line = raw.strip()
        line = re.sub(r"^" + re.escape(num) + r"\.?\s+", "", line)
        joined = key(line + " " + (lines[i + 1][1] if i + 1 < len(lines) else ""))
        if want and joined.startswith(want[:min(len(want), max(12, len(key(line))))]) and key(line):
            return i
    return None


def paragraphs(raw_lines):
    """Reflow PDF lines into paragraphs. A blank line ends a paragraph only after a full sentence
    (otherwise it is a page break mid-sentence); bullets and key lists („1“ = …) start new ones."""
    paras, cur = [], ""
    for raw in raw_lines:
        line = norm(raw)
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


def build_spec():
    pages = documents.extract_pages(PDF)
    toc = parse_toc(pages)
    level4, _ = documents.split_sections(pages)
    level4 = [s for s in level4 if s["sec"].count(".") == 3]
    # merge level-4 headings after their parent, in document order
    merged = []
    for e in toc:
        merged.append(e)
        merged += [{"sec": s["sec"], "title": s["title"], "page": s["page"]}
                   for s in level4 if s["sec"].rsplit(".", 1)[0] == e["sec"]]
    lines = body_lines(pages)
    starts, cursor = [], 0
    for e in merged:
        i = find_heading(lines, cursor, e)
        starts.append(i)
        if i is not None:
            cursor = i + 1
    found = [(i, n) for n, i in enumerate(starts) if i is not None]
    sections = []
    for n, e in enumerate(merged):
        i = starts[n]
        text = []
        if i is not None:
            nxt = next((j for j, m in found if j > i), len(lines))
            body = i + 1  # skip the rest of a heading that wraps over several lines
            got, want = key(re.sub(r"^" + re.escape(e["sec"]) + r"\.?\s+", "", lines[i][1].strip())), key(e["title"])
            while body < nxt and len(got) < len(want) and want.startswith(got + key(lines[body][1])[:3]):
                got += key(lines[body][1]); body += 1
            text = paragraphs(raw for _, raw in lines[body:nxt])
        sections.append({"sec": e["sec"], "title": e["title"], "page": e["page"], "text": text})
    missing = [e["sec"] for e, i in zip(merged, starts) if i is None]
    return sections, missing, len(pages)


def transparent_logo(path):
    """The logo PNG has a white background. Turn white into transparency so it blends into light
    and dark pages: alpha = 255 − min(r, g, b), colour = the logo's red. Keeps anti-aliased edges."""
    import io
    from PIL import Image
    im = Image.open(path).convert("RGB")
    red = (192, 0, 47)
    out = Image.new("RGBA", im.size)
    out.putdata([(*red, 255 - min(px)) for px in im.getdata()])
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def replace_block(html, name, payload):
    pat = re.compile(r"/\*" + name + r"-START\*/.*?/\*" + name + r"-END\*/", re.S)
    if not pat.search(html):
        raise SystemExit(f"marker /*{name}-START*/ … /*{name}-END*/ not found in index.html")
    return pat.sub(lambda _: f"/*{name}-START*/{payload}/*{name}-END*/", html)


def main():
    sections, missing, npages = build_spec()
    spec = {"doc": "Verfahrensbeschreibung DTA EEL", "version": "13.4", "pages": npages, "sections": sections}
    imgs = {}
    for k, f in IMAGES.items():
        path = os.path.join(ROOT, "images", f)
        mime = "image/png" if f.endswith(".png") else "image/jpeg"
        data = transparent_logo(path) if k == "logo" else open(path, "rb").read()
        imgs[k] = f"data:{mime};base64," + base64.b64encode(data).decode()
    with open(HTML, encoding="utf-8") as fh:
        html = fh.read()
    # "</" would end the <script> element early
    html = replace_block(html, "SPEC-FULL", json.dumps(spec, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    html = replace_block(html, "IMAGES", json.dumps(imgs, separators=(",", ":")))
    with open(HTML, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    chars = sum(len(p) for s in sections for p in s["text"])
    print(f"{len(sections)} sections, {chars:,} characters of text, {len(missing)} without a heading match"
          + (f": {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
