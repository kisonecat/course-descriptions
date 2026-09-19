#!/usr/bin/env python3
"""
Compare each imported sheet against the published PDF it came from, and report
any department-written wording that did not survive the import.

    python3 tools/check-import-fidelity.py

Only the sections the department writes are compared.  The catalog description,
prerequisites and exclusions are expected to differ: those now come from the
university's data, which is the point of the exercise.
"""

import glob
import json
import os
import re
import subprocess
import sys

CACHE = "tools/.course-sheet-cache"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "imp", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "import-course-sheets.py"))
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)

WORD = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
# pdftotext emits real ligature and curly-quote characters; normalize both
# sides so a typographic difference is not mistaken for lost content.
NORMALIZE = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
             "\ufb04": "ffl", "\u2019": "'", "\u2018": "'", "\u2013": "-",
             "\u2014": "-", "\u2212": "-", "\u00a0": " "}
NORM_TABLE = str.maketrans(NORMALIZE)
# Words that legitimately appear only on one side.
IGNORE = {"page", "math", "mathematics", "credit", "credits", "catalog",
          "description", "prerequisite", "prerequisites", "exclusions",
          "prereq", "autumn", "spring", "summer", "each"}


def words(text):
    text = text.translate(NORM_TABLE)
    # Rejoin words LaTeX hyphenated across a line break ("Beck-\nmann"), then
    # drop remaining hyphens so a real one ("multi-variable") compares equal
    # whether or not the line happened to break there.
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = text.replace("-", "")
    return [w.lower() for w in WORD.findall(text) if w.lower() not in IGNORE]


def owned_text_from_source(path):
    """The department-written sections of a published sheet."""
    body, _ = imp.strip_furniture(imp.pdf_lines(path))
    sections, _ = imp.split_sections(body)
    out = []
    for label, lines in sections:
        if imp.SECTION_MAP[label.strip().lower().rstrip(":")] is not None:
            out.extend(lines)
    return "\n".join(out)


def main():
    manifest = json.load(open(os.path.join(CACHE, "manifest.json")))
    pdf_for = {}
    for slug, entry in manifest.items():
        number = imp.number_from_slug(slug)
        for name in entry["files"]:
            if number and os.path.exists(f"{number}.pdf"):
                pdf_for.setdefault(number, name)

    worst = []
    for number, name in sorted(pdf_for.items()):
        src = os.path.join(CACHE, name)
        try:
            want = words(owned_text_from_source(src))
        except Exception as e:
            print(f"  {number}: could not read source ({e})")
            continue
        if not want:
            continue
        got = set(words(subprocess.run(
            ["pdftotext", "-layout", f"{number}.pdf", "-"],
            capture_output=True).stdout.decode("utf-8", "replace")))
        missing = [w for w in want if w not in got]
        pct = 100.0 * len(missing) / len(want)
        if missing:
            worst.append((pct, number, len(want), missing))

    worst.sort(reverse=True)
    clean = len(pdf_for) - len(worst)
    print(f"{len(pdf_for)} imported sheets compared against their source PDF")
    print(f"{clean} reproduce every department-written word")
    for pct, number, total, missing in worst:
        if pct < 0.5:
            continue
        sample = " ".join(sorted(set(missing))[:12])
        print(f"  {number}: {pct:.1f}% of {total} words missing -> {sample}")


if __name__ == "__main__":
    main()
