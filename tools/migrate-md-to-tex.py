#!/usr/bin/env python3
"""
One-shot conversion of the old <number>.md course sheets into <number>.tex.

Usage:
    python3 tools/migrate-md-to-tex.py [--outdir .] [file.md ...]

Catalog Description, Prerequisite(s) and Exclusions are dropped: those now
come from coursedata.tex.  Everything else is converted with pandoc (the same
converter build.py used) and wrapped in the semantic environments that
osucourse.cls provides, in a canonical order.

Any heading this script does not recognize is a hard error, so nothing can be
silently lost.  Delete this script once the migration is committed.
"""

import argparse
import glob
import os
import re
import subprocess
import sys

# Sections in the order every sheet should present them.  \CatalogDescription
# and \PrerequisitesAndExclusions are emitted first, before any of these.
CANONICAL_ORDER = [
    "FollowupCourses",     # in the originals this trailed the exclusions
    "Purpose",
    "LearningOutcomes",
    "Text",
    "TopicsList",
    "Comment",
    "SuggestedSchedule",
]

# Headings whose content now comes from the university's data.
DROPPED = {"catalog description", "prerequisite", "prerequisites", "exclusions"}

HEADING_MAP = {
    "purpose": "Purpose",
    "purpose of course": "Purpose",
    "course learning outcomes": "LearningOutcomes",
    "text": "Text",
    "texts": "Text",
    "textbook": "Text",
    "suggested schedule": "SuggestedSchedule",
    "follow-up courses": "FollowupCourses",
    "comment": "Comment",
}

TOPICS_RE = re.compile(r"^(?:\d+\s+)?topics list\s*(.*)$")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)


def endashify(s):
    """Same rule build.py applied to every converted sheet."""
    return re.sub(r"H-(\d)", r"H--\1", re.sub(r"(\d)-(\d)", r"\1--\2", s))


def strip_preambles(text):
    """Remove the YAML front matter -- 4551.md has two copies of it."""
    while True:
        m = re.match(r"\A\s*---\s*\n.*?\n---\s*\n", text, re.DOTALL)
        if not m:
            return text.lstrip("\n")
        text = text[m.end():]


def classify(raw):
    """Map a markdown heading to (environment, qualifier, text pushed back).

    Returns None for headings whose content is now supplied automatically.
    """
    # "## ## Purpose" -- doubled hash markers in 4350.md
    title = re.sub(r"^#+\s*", "", raw).strip()
    key = title.lower().rstrip(":").strip()

    if key in DROPPED:
        return None
    if key in HEADING_MAP:
        return HEADING_MAP[key], "", ""

    m = TOPICS_RE.match(key)
    if m:
        # Keep a qualifier like "(Chapters from Judson's book)", using the
        # original capitalization rather than the lowercased key.
        qualifier = title[len(title) - len(m.group(1)):].strip() if m.group(1) else ""
        return "TopicsList", (" " + qualifier if qualifier else ""), ""

    # "## Text Instructors will choose one of the following" (4548.md): the
    # heading swallowed a sentence.  Put the sentence back in the body.
    for word, env in (("text", "Text"), ("texts", "Text"), ("textbook", "Text")):
        if key.startswith(word + " "):
            return env, "", title[len(word):].strip()

    sys.exit(f"unrecognized heading: {raw!r} -- add it to HEADING_MAP")


def split_sections(body):
    """[(raw heading, body text)] in source order."""
    marks = list(HEADING_RE.finditer(body))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out.append((m.group(1), body[m.end():end].strip()))
    return out


def pandoc(markdown):
    if not markdown.strip():
        return ""
    r = subprocess.run(["pandoc", "--from", "markdown", "--to", "latex"],
                       input=markdown.encode(), capture_output=True, check=True)
    tex = r.stdout.decode()
    # The same two fixes build.py applied after conversion.
    tex = tex.replace("C- ", "C$-$ ")
    tex = endashify(tex)
    # Pandoc turns markdown's escaped apostrophes into \textquotesingle; the
    # originals only had those because the text came out of Word.
    tex = tex.replace(r"\textquotesingle", "'")
    # Section labels are pandoc bookkeeping we no longer need.
    tex = re.sub(r"\\label\{[^}]*\}", "", tex)
    return tex.strip()


# Pandoc restates the label format; the value contains braces, so match the
# whole line rather than trying to balance them.  Article's default label is
# identical, so dropping the \def changes nothing.
ENUM_ONLY_RE = re.compile(
    r"\A\\begin\{enumerate\}\s*(?:\\def\\label\w+\{[^\n]*\n\s*)*"
    r"(?:\\tightlist\s*)?(.*)\\end\{enumerate\}\Z", re.DOTALL)


def render_topics(tex, qualifier):
    """A flat enumeration becomes TopicsList; anything else, TopicsOutline."""
    m = ENUM_ONLY_RE.match(tex.strip())
    if m:
        items = m.group(1).strip()
        return f"\\begin{{TopicsList}}[{qualifier}]\n{items}\n\\end{{TopicsList}}" \
            if qualifier else f"\\begin{{TopicsList}}\n{items}\n\\end{{TopicsList}}"
    opt = f"[{qualifier}]" if qualifier else ""
    return f"\\begin{{TopicsOutline}}{opt}\n{tex}\n\\end{{TopicsOutline}}"


WEEK_RE = re.compile(r"\A\\textbf\{Week\s+(\d+)\.\}\s*(.*)\Z", re.DOTALL)
FINALS_RE = re.compile(r"\A\\textbf\{Finals week\.\}\s*(.*)\Z", re.DOTALL)


def render_schedule(tex):
    """Turn pandoc's bullet list back into \\week / \\finalsweek calls."""
    body = re.sub(r"\A\\begin\{itemize\}\s*(?:\\tightlist\s*)?", "", tex.strip())
    body = re.sub(r"\\end\{itemize\}\Z", "", body).strip()
    lines = []
    for chunk in [c.strip() for c in body.split("\\item") if c.strip()]:
        chunk = " ".join(chunk.split())
        m = WEEK_RE.match(chunk)
        if m:
            lines.append(f"\\week{{{m.group(1)}}}{{{m.group(2)}}}")
            continue
        m = FINALS_RE.match(chunk)
        if m:
            lines.append(f"\\finalsweek{{{m.group(1)}}}")
            continue
        sys.exit(f"schedule bullet is not a week: {chunk[:80]!r}")
    return "\\begin{SuggestedSchedule}\n" + "\n".join(lines) + "\n\\end{SuggestedSchedule}"


def convert(path, outdir):
    number = os.path.splitext(os.path.basename(path))[0]
    raw = strip_preambles(open(path, encoding="utf-8").read())
    # Repair the Word-conversion scars before pandoc sees them.
    raw = raw.replace("\\'", "'")

    blocks, source_order = {}, []
    for heading, body in split_sections(raw):
        result = classify(heading)
        if result is None:
            continue
        env, qualifier, pushed_back = result
        if pushed_back:
            body = pushed_back + ("\n" + body if body else "")
        tex = pandoc(body)
        if not tex:
            continue
        if env == "TopicsList":
            rendered = render_topics(tex, qualifier)
        elif env == "SuggestedSchedule":
            rendered = render_schedule(tex)
        else:
            rendered = f"\\begin{{{env}}}\n{tex}\n\\end{{{env}}}"
        blocks[env] = rendered
        source_order.append(env)

    ordered = [e for e in CANONICAL_ORDER if e in blocks]
    parts = [
        "\\documentclass{osucourse}",
        f"\\course{{{number}}}",
        "",
        "\\begin{document}",
        "",
        "\\CatalogDescription",
        "\\PrerequisitesAndExclusions",
        "",
    ]
    parts += [blocks[e] + "\n" for e in ordered]
    parts += ["\\end{document}"]

    out = os.path.join(outdir, number + ".tex")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")

    reordered = "" if source_order == ordered else \
        f"  (reordered: {' '.join(source_order)} -> {' '.join(ordered)})"
    print(f"{number}.tex  {' '.join(ordered)}{reordered}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=".")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args()
    files = args.files or sorted(glob.glob("[0-9]*.md"))
    for path in files:
        convert(path, args.outdir)


if __name__ == "__main__":
    main()
