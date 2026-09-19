#!/usr/bin/env python3
"""
Import the department's existing course sheets from math.osu.edu and turn them
into <number>.tex files for this repository.

    python3 tools/import-course-sheets.py --fetch     # download (slow, polite)
    python3 tools/import-course-sheets.py --convert   # PDFs -> .tex
    python3 tools/import-course-sheets.py --report    # what would be written

The published sheets at math.osu.edu were produced by an older version of this
same pipeline, so they have a predictable shape: a right-aligned block of
metadata at the top of every page, then "Catalog Description:", "Prerequisite:"
and so on, then a footer.  We keep only the sections the department writes --
the catalog text now comes from the university's data instead.

This is a one-shot import.  Once the .tex files are committed and reviewed,
this script and its cache can be deleted.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = "https://math.osu.edu"
INDEX = SITE + "/courses"
CACHE = "tools/.course-sheet-cache"
HEADERS = {"User-Agent": "OSU MATH dept course sheet import"}
DELAY = 0.4

# ---------------------------------------------------------------- fetching

def get(url, binary=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as f:
        data = f.read()
    return data if binary else data.decode("utf-8", errors="replace")


def fetch(argv_limit=None):
    os.makedirs(CACHE, exist_ok=True)
    index = get(INDEX)
    slugs = sorted(set(re.findall(r'href="(/courses/math-[^"#?]*)"', index)))
    print(f"{len(slugs)} courses listed at {INDEX}")

    manifest = {}
    path = os.path.join(CACHE, "manifest.json")
    if os.path.exists(path):
        manifest = json.load(open(path))

    for i, slug in enumerate(slugs, 1):
        entry = manifest.get(slug)
        if entry is None or entry.get("pdfs") is None:
            # Visit the course page only if we have not already seen it; the
            # PDF link is not on the index.
            try:
                html = get(SITE + slug)
            except (urllib.error.URLError, OSError) as e:
                print(f"  {slug}: page fetch failed ({e})")
                continue
            entry = {"slug": slug, "files": [], "pdfs": sorted(set(re.findall(
                r'href="(/sites/default/files/courses/[^"]+\.pdf)"', html)))}
            manifest[slug] = entry
            time.sleep(DELAY)

        for href in entry["pdfs"]:
            name = os.path.basename(urllib.parse.unquote(href))
            dest = os.path.join(CACHE, name)
            if not os.path.exists(dest):
                try:
                    blob = get(SITE + href, binary=True)
                except (urllib.error.URLError, OSError) as e:
                    print(f"  {slug}: {name} failed ({e})")
                    continue
                if not blob.startswith(b"%PDF"):
                    print(f"  {slug}: {name} is not a PDF, skipped")
                    continue
                open(dest, "wb").write(blob)
                time.sleep(DELAY)
            if name not in entry["files"]:
                entry["files"].append(name)

        if i % 25 == 0:
            print(f"  ...{i}/{len(slugs)}", flush=True)
            json.dump(manifest, open(path, "w"), indent=1, sort_keys=True)

    json.dump(manifest, open(path, "w"), indent=1, sort_keys=True)
    withpdf = sum(1 for v in manifest.values() if v["files"])
    print(f"cached {withpdf} course sheets in {CACHE}")


# ---------------------------------------------------------------- parsing

FOOTER_RE = re.compile(r"^\s*Page\s+\d+\b.*\bMath\s+\d")
# The metadata block is right-aligned far into the margin; nothing in the body
# is indented anywhere near that much.
HEADER_INDENT = 40
CREDITS_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)\s+credits?(\s+each)?\s*$",
    re.IGNORECASE)
SEASON_RE = re.compile(r"^\s*((?:Autumn|Spring|Summer|Winter)\b.*)$")
# "Mathematics 4181H (Au), 4182H (Sp)" -- one sheet, two courses.
NUMBER_RE = re.compile(r"^\s*Mathematics\s+(.+?)\s*$")
COURSE_TOKEN_RE = re.compile(r"\b(\d{3,4}(?:\.\d{2})?H?)\b")
# A season given per course, in either the number line or the semesters line:
# "4181H (Au), 4182H (Sp)" or "2162.01(Sp) 2162.02(Au, Sp)".
PER_COURSE_RE = re.compile(r"(\d{3,4}(?:\.\d{2})?H?)\s*\(([^)]+)\)")
SEASON_WORD = {"au": "Autumn", "sp": "Spring", "su": "Summer"}


def expand_seasons(text):
    """'Au, Sp' -> 'Autumn, Spring'; anything unrecognized is left alone."""
    parts = [p.strip() for p in text.split(",")]
    return ", ".join(SEASON_WORD.get(p.lower(), p) for p in parts)


def pdf_lines(path):
    out = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, check=True).stdout
    return out.decode("utf-8", errors="replace")


def strip_furniture(text):
    """Drop the repeated per-page metadata block and the page footers.

    Returns (body_lines, header_block_of_page_one).
    """
    body, first_header = [], []
    for page in text.split("\f"):
        lines = page.splitlines()
        i = 0
        # leading blank lines
        while i < len(lines) and not lines[i].strip():
            i += 1
        header = []
        while i < len(lines) and lines[i].strip() and \
                len(lines[i]) - len(lines[i].lstrip()) >= HEADER_INDENT:
            header.append(lines[i].strip())
            i += 1
        if header and not first_header:
            first_header = header
        for line in lines[i:]:
            if FOOTER_RE.match(line):
                continue
            body.append(line)
    return body, first_header


def parse_header(header):
    """Mathematics <numbers> / title(s) / semesters / credits.

    Returns the numbers the sheet covers plus whatever per-course detail the
    header carries.  Nothing is guessed: when a combined sheet has one title
    for two courses, both courses get that one title and the caller is told.
    """
    meta = {"numbers": [], "titles": [], "per_course": {}}
    if not header:
        return meta
    m = NUMBER_RE.match(header[0])
    if not m:
        return meta
    number_line = m.group(1)
    meta["numbers"] = COURSE_TOKEN_RE.findall(number_line)
    for num, seasons in PER_COURSE_RE.findall(number_line):
        meta["per_course"][num] = expand_seasons(seasons)

    rest = header[1:]
    if rest:
        cm = CREDITS_RE.match(rest[-1])
        if cm:
            c = cm.group(1).replace(" ", "")
            meta["credits"] = f"{c} credit" if c == "1" else f"{c} credits"
            rest = rest[:-1]
    if rest and PER_COURSE_RE.search(rest[-1]):
        for num, seasons in PER_COURSE_RE.findall(rest[-1]):
            meta["per_course"][num] = expand_seasons(seasons)
        rest = rest[:-1]
    elif rest and SEASON_RE.match(rest[-1]):
        meta["semesters"] = rest[-1].strip()
        rest = rest[:-1]
    meta["titles"] = [x.strip() for x in rest if x.strip()]
    return meta


# Section labels seen in the published sheets, mapped to what this repo calls
# them.  None means the university's data supplies it now.
SECTION_MAP = {
    "catalog description": None,
    "description": None,
    "prerequisite": None,
    "prerequisites": None,
    "prereq": None,
    "prereqs": None,
    "exclusion": None,
    "exclusions": None,
    "purpose": "Purpose",
    "purpose of course": "Purpose",
    "course purpose": "Purpose",
    "course learning outcomes": "LearningOutcomes",
    "learning outcomes": "LearningOutcomes",
    "text": "Text",
    "texts": "Text",
    "textbook": "Text",
    "textbooks": "Text",
    "topics": "TopicsList",
    "topic list": "TopicsList",
    "topics list": "TopicsList",
    "topics covered": "TopicsList",
    "suggested schedule": "SuggestedSchedule",
    "schedule": "SuggestedSchedule",
    "follow-up courses": "FollowupCourses",
    "follow up courses": "FollowupCourses",
    "follow-up course": "FollowupCourses",
    "follow up course": "FollowupCourses",
    "technology": "Technology",
    "recommended supplemental texts": "SupplementalTexts",
    "supplemental texts": "SupplementalTexts",
    "recommended supplemental text": "SupplementalTexts",
    # A picture in the published sheets; we redraw it in sequencing-chart.tex.
    "sequencing chart": "SequencingChart",
    "comment": "Comment",
    "comments": "Comment",
}

HEADING_RE = re.compile(r"^([A-Z][A-Za-z '\-/&]{2,40}):\s*(.*?)\s*$")


def heading_tail_is_furniture(tail):
    """A few sheets leak a right-aligned 'Autumn, Spring' or '3 credits' onto
    the heading's own line.  Recognize that so the section is not missed."""
    return bool(CREDITS_RE.match(tail) or SEASON_RE.match(tail))


def split_sections(body):
    """([(label, [lines])], [unknown labels]).

    A heading we do not recognize is reported rather than folded into the
    section above it, so an unimported section can never pass unnoticed.
    """
    sections, unknown, current, buf = [], [], None, []
    for line in body:
        m = HEADING_RE.match(line)
        if m:
            label, tail = m.group(1).strip(), m.group(2).strip()
            if tail and not heading_tail_is_furniture(tail):
                m = None        # real text after the colon: not a heading
        if m:
            if label.lower().rstrip(":") in SECTION_MAP:
                if current is not None:
                    sections.append((current, buf))
                current, buf = label, []
                continue
            if re.match(r"^[A-Z][a-z]", label) and len(label.split()) <= 5:
                unknown.append(label)
        buf.append(line)
    if current is not None:
        sections.append((current, buf))
    return sections, unknown


# ---------------------------------------------------------------- rendering

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
             "\ufb03": "ffi", "\ufb04": "ffl", "\u00a0": " "}
ESCAPES = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
           "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
           "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
ESCAPE_TABLE = str.maketrans({**LIGATURES, **ESCAPES})


def endashify(s):
    """Number ranges take en-dashes, as in the rest of this repository."""
    s = re.sub(r"(\d[0-9A-Za-z.]*)\s*-\s*(\d)", r"\1--\2", s)
    return re.sub(r"H-(\d)", r"H--\1", s)


# Hyphenated ISBNs would be turned into en-dashed nonsense by the rule above,
# and every sheet in this repository writes them without dashes anyway.
ISBN_RE = re.compile(r"\b(97[89])[-\s]?((?:\d[-\s]?){9}\d)\b")


def tex(s):
    s = ISBN_RE.sub(lambda m: m.group(1) + re.sub(r"[-\s]", "", m.group(2)), s)
    s = s.translate(ESCAPE_TABLE)
    s = endashify(s)
    s = s.replace("C- ", "C$-$ ").replace("B- ", "B$-$ ")
    return s


def join_wrapped(parts):
    """Undo pdftotext's hard wraps.

    A line ending in a hyphen is continued without a space: the published
    sheets never hyphenate at a line break, so every such hyphen is a real one
    ("Ching-Shan", "teacher-student", "ISBN: 978-3-319-...").
    """
    if not parts:
        return ""
    out = parts[0]
    for part in parts[1:]:
        out = out + part if out.endswith("-") else out + " " + part
    return out


def paragraphs(lines):
    """Blank-line separated blocks, with pdftotext's hard wraps joined."""
    out, buf = [], []
    for line in lines:
        if line.strip():
            buf.append(line.strip())
        elif buf:
            out.append(join_wrapped(buf))
            buf = []
    if buf:
        out.append(join_wrapped(buf))
    return out


NUMBERED_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
WEEK_RE = re.compile(r"^\s*Week\s+(\d+)[.:]?\s*(.*)$", re.IGNORECASE)
FINALS_RE = re.compile(r"^\s*Finals?\s*week[.:]?\s*(.*)$", re.IGNORECASE)


def render_prose(env, lines, qualifier=""):
    paras = [tex(p) for p in paragraphs(lines)]
    if not paras:
        return None
    opt = f"[{tex(qualifier)}]" if qualifier else ""
    return f"\\begin{{{env}}}{opt}\n" + "\n\n".join(paras) + f"\n\\end{{{env}}}"


def render_topics(lines, qualifier=""):
    """A flat numbered list becomes TopicsList; anything else an outline."""
    kept = [l for l in lines if l.strip()]
    if not kept:
        return None
    numbered = [l for l in kept if NUMBERED_RE.match(l)]
    opt = f"[{tex(qualifier)}]" if qualifier else ""

    # Treat it as a list only if the numbers actually run 1, 2, 3, ...
    if len(numbered) >= 2 and len(numbered) >= len(kept) // 2:
        seq = [int(NUMBERED_RE.match(l).group(1)) for l in numbered]
        if seq == list(range(1, len(seq) + 1)):
            items, cur = [], None
            for line in kept:
                m = NUMBERED_RE.match(line)
                if m:
                    if cur:
                        items.append(cur)
                    cur = m.group(2).strip()
                elif cur is not None:
                    cur = join_wrapped([cur, line.strip()])
            if cur:
                items.append(cur)
            body = "\n".join(f"\\item {tex(i)}" for i in items)
            return f"\\begin{{TopicsList}}{opt}\n{body}\n\\end{{TopicsList}}"

    # Otherwise keep the outline's shape: one line per line, sub-items indented.
    indents = sorted({len(l) - len(l.lstrip()) for l in kept})
    base = indents[0]
    sub = indents[1] if len(indents) > 1 else base
    body = []
    for line in kept:
        indent = len(line) - len(line.lstrip())
        text = tex(line.strip())
        if indent > sub and body:
            # Deeper than the sub-level: a wrapped continuation of the line
            # above, not an item of its own.
            body[-1] = join_wrapped([body[-1][:-1], text]) + "}" \
                if body[-1].startswith("\\topicsub{") else join_wrapped([body[-1], text])
        elif indent > base:
            body.append(f"\\topicsub{{{text}}}")
        else:
            body.append(text)
    return "\\begin{TopicsOutline}" + opt + "\n" + "\n\n".join(body) \
        + "\n\\end{TopicsOutline}"


def render_schedule(lines):
    out = []
    for para in paragraphs(lines):
        m = WEEK_RE.match(para)
        if m:
            out.append(f"\\week{{{m.group(1)}}}{{{tex(m.group(2).strip())}}}")
            continue
        m = FINALS_RE.match(para)
        if m:
            out.append(f"\\finalsweek{{{tex(m.group(1).strip())}}}")
            continue
        return None      # not a week-by-week schedule; let the caller decide
    return "\\begin{SuggestedSchedule}\n" + "\n".join(out) \
        + "\n\\end{SuggestedSchedule}" if out else None


CANONICAL_ORDER = ["FollowupCourses", "SequencingChart", "Purpose",
                   "LearningOutcomes", "Text",
                   "SupplementalTexts", "Technology", "TopicsList", "Comment",
                   "SuggestedSchedule"]


def convert_one(pdf_path):
    """Return (body_blocks, meta, notes) for one published sheet."""
    notes = []
    body, header = strip_furniture(pdf_lines(pdf_path))
    meta = parse_header(header)
    blocks, catalog = {}, {}
    CATALOG_SLOT = {"catalog description": "description", "description": "description",
                    "prerequisite": "prereq", "prerequisites": "prereq",
                    "prereq": "prereq", "prereqs": "prereq",
                    "exclusion": "exclusions", "exclusions": "exclusions"}
    sections, unknown = split_sections(body)
    for label in unknown:
        notes.append(f"unrecognized section {label!r} left in place")
    for label, lines in sections:
        key = label.strip().lower().rstrip(":")
        env = SECTION_MAP[key]
        if env is None:
            # Not written into the sheet -- the university's data supplies it.
            # Kept only as a fallback for courses missing from that data.
            if key in CATALOG_SLOT:
                paras = paragraphs(lines)
                if paras:
                    catalog[CATALOG_SLOT[key]] = " ".join(paras)
            continue
        if env == "SequencingChart":
            # The published sheets hold this as an image, so there is no text
            # to carry over -- just call the figure in.
            rendered = "\\SequencingChart"
        elif env == "TopicsList":
            rendered = render_topics(lines)
        elif env == "SuggestedSchedule":
            rendered = render_schedule(lines)
            if rendered is None:
                notes.append("schedule was not week-by-week; kept as a comment")
                rendered = render_prose("Comment", lines)
                env = "Comment"
        else:
            rendered = render_prose(env, lines)
        if rendered:
            blocks[env] = rendered
    meta["catalog"] = catalog
    return blocks, meta, notes


# ---------------------------------------------------------------- driving

FIELD_RE = re.compile(r"\\CourseData\{([^}]*)\}\{([^}]*)\}")


def known_fields(path="coursedata.tex"):
    """{course number: set of fields the university's data already supplies}."""
    out = {}
    if os.path.exists(path):
        for number, field in FIELD_RE.findall(open(path, encoding="utf-8").read()):
            out.setdefault(number, set()).add(field)
    return out


SLUG_NUMBER_RE = re.compile(r"^math-(\d{3,4}(?:\.\d{2})?)(h)?$", re.IGNORECASE)


def number_from_slug(slug):
    """/courses/math-4182h -> 4182H.  The page says which course it is for."""
    m = SLUG_NUMBER_RE.match(slug.rsplit("/", 1)[-1])
    if not m:
        return None
    return m.group(1) + ("H" if m.group(2) else "")


OVERRIDE_ORDER = ["title", "credits", "semesters",
                  "description", "prereq", "exclusions"]


def overrides_for(number, meta, have):
    r"""\SetCourseField lines for facts the university's data is missing."""
    supplied = have.get(number, set())
    values = {k: meta[k] for k in ("title", "credits", "semesters") if meta.get(k)}
    values.update(meta.get("catalog", {}))
    lines = []
    for field in OVERRIDE_ORDER:
        if field in supplied or field not in values:
            continue
        lines.append(f"\\SetCourseField{{{field}}}{{{tex(values[field])}}}")
    return lines


def convert_all(write):
    manifest_path = os.path.join(CACHE, "manifest.json")
    if not os.path.exists(manifest_path):
        sys.exit(f"no cache at {CACHE}; run with --fetch first")
    manifest = json.load(open(manifest_path))
    have = known_fields()

    parsed = {}          # cached PDF -> (blocks, meta, notes)
    written, skipped, not_sheets, problems, done = [], [], [], [], set()

    for slug in sorted(manifest):
        for name in manifest[slug]["files"]:
            path = os.path.join(CACHE, name)
            if not os.path.exists(path):
                continue
            if name not in parsed:
                try:
                    parsed[name] = convert_one(path)
                except Exception as e:
                    problems.append((name, f"could not be read ({e})"))
                    parsed[name] = (None, None, None)
            blocks, meta, notes = parsed[name]
            if meta is None:
                continue
            sheet_numbers = meta.get("numbers") or []
            if not sheet_numbers:
                if name not in not_sheets:
                    not_sheets.append(name)
                continue
            if not blocks:
                problems.append((name, "no department-written sections"))
                continue

            # A sheet may cover a two-course sequence; this page is for one of
            # them.  Fall back to everything the sheet covers if the page's
            # number is not one of them (e.g. /courses/math-1187 -> 1187H).
            want = number_from_slug(slug)
            numbers = [want] if want in sheet_numbers else sheet_numbers

            for number in numbers:
                dest = f"{number}.tex"
                if dest in done:
                    continue
                done.add(dest)
                if os.path.exists(dest):
                    skipped.append(dest)
                    continue

                titles = meta.get("titles", [])
                idx = sheet_numbers.index(number)
                per = dict(meta)
                if titles:
                    per["title"] = titles[idx] \
                        if len(titles) == len(sheet_numbers) else " / ".join(titles)
                season = meta["per_course"].get(number) or meta.get("semesters")
                if season:
                    per["semesters"] = season

                sheet_notes = list(notes)
                others = [n for n in sheet_numbers if n != number]
                if others:
                    sheet_notes.append("shares a sheet with " + ", ".join(others))

                head = ["\\documentclass{osucourse}", f"\\course{{{number}}}"]
                if others:
                    head.append(f"%% Imported from the sheet Math {number} shares"
                                f" with {', '.join(others)}; the sections below"
                                f" are common to both.")
                extra = overrides_for(number, per, have)
                if extra:
                    head += ["",
                             "%% Not in the university's course data, so these come",
                             "%% from the published sheet this file was imported from."]
                    head += extra
                parts = head + ["", "\\begin{document}", "",
                                "\\CatalogDescription",
                                "\\PrerequisitesAndExclusions", ""]
                parts += [blocks[e] + "\n" for e in CANONICAL_ORDER if e in blocks]
                parts.append("\\end{document}")
                if write:
                    open(dest, "w", encoding="utf-8").write("\n".join(parts) + "\n")
                written.append((dest, len(extra), sheet_notes))

    verb = "wrote" if write else "would write"
    print(f"{verb} {len(written)} sheets from {len(parsed)} cached PDFs")
    for dest, n_over, notes in sorted(written):
        flags = ([f"{n_over} override(s)"] if n_over else []) + notes
        print(f"  {dest}" + (f"   [{'; '.join(flags)}]" if flags else ""))
    if skipped:
        print(f"\n{len(skipped)} already present, left alone: "
              + " ".join(sorted(set(skipped))))
    if not_sheets:
        print(f"\n{len(not_sheets)} PDFs are not course-description sheets "
              f"(no 'Mathematics NNNN' header) and were skipped:")
        for n in sorted(not_sheets):
            print(f"  {n}")
    for name, why in sorted(set(problems)):
        print(f"  PROBLEM {name}: {why}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--convert", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch()
    if args.convert or args.report:
        convert_all(write=args.convert)


if __name__ == "__main__":
    main()
