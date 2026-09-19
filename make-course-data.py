#!/usr/bin/env python3
"""
Turn the downloaded JSON into coursedata.tex, the table of catalog facts that
osucourse.cls reads.

Usage:
    python3 make-course-data.py [--courses math_courses.json]
                                [--offerings math_offerings.json]
                                [--out coursedata.tex]

Catalog prose (title, credit hours, description, prerequisites, exclusions)
comes from math_courses.json; when a course is offered comes from
math_offerings.json.  Every value is escaped here, in Python, so that the TeX
side never has to think about catcodes: because braces are escaped, each
value is guaranteed brace-balanced, and because "#" and "%" are escaped, no
value can disturb the macro definition it lands in.

This file is generated.  Do not edit it by hand -- run `make coursedata.tex`.
"""

import argparse
import datetime
import json
import os
import re

# One pass, so an escape introduced here can never be escaped again.
ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": "\x00CARET\x00",   # decided below, once escaping is done
}
TABLE = str.maketrans(ESCAPES)

# "L^p" is the only way a caret shows up in this catalog; render it as maths.
SUPERSCRIPT_RE = re.compile(r"\b([A-Za-z])\x00CARET\x00(\w+)")


def endashify(s):
    """Number ranges take en-dashes: 4580-4581, 1.1-1.2, 4181H - 4182H.

    Extends build.py's original rules to ranges written with spaces around
    the hyphen, which is how the catalog writes "4181H - 4182H".  Both sides
    must start with a digit, so "C- or better" is left alone.
    """
    s = re.sub(r"(\d[0-9A-Za-z.]*)\s*-\s*(\d)", r"\1--\2", s)
    return re.sub(r"H-(\d)", r"H--\1", s)


def texify(value):
    """Escape a catalog string, then apply the house typography."""
    s = re.sub(r"\s+", " ", (value or "")).strip()
    s = s.translate(TABLE)
    s = SUPERSCRIPT_RE.sub(r"$\1^{\2}$", s)
    s = s.replace("\x00CARET\x00", r"\textasciicircum{}")
    # Typography runs last: it deliberately introduces unescaped "$" and "-".
    s = endashify(s)
    s = s.replace("C- ", "C$-$ ")
    s = s.replace("B- ", "B$-$ ")
    s = s.replace("’", "'").replace("‘", "`")
    s = s.replace("“", "``").replace("”", "''")
    return s


def credits_phrase(credit_hours):
    """'3' -> '3 credits', '1' -> '1 credit', '1-5' -> '1--5 credits'."""
    ch = (credit_hours or "").strip()
    if not ch:
        return ""
    return f"{ch} credit" if ch == "1" else f"{ch} credits"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--courses", default="math_courses.json")
    ap.add_argument("--offerings", default="math_offerings.json")
    ap.add_argument("--out", default="coursedata.tex")
    args = ap.parse_args()

    catalog = {}
    if os.path.exists(args.courses):
        for rec in json.load(open(args.courses)):
            catalog[rec["catalog_number"]] = rec

    offerings = {}
    if os.path.exists(args.offerings):
        offerings = json.load(open(args.offerings)).get("courses", {})

    numbers = sorted(set(catalog) | set(offerings),
                     key=lambda n: [int(x) if x.isdigit() else x
                                    for x in re.split(r"(\d+)", n)])

    lines = [
        "%% GENERATED FILE -- do not edit by hand.",
        "%% Regenerate with:  make coursedata.tex",
        "%%",
        "%% Catalog prose from content.osu.edu; offering history from",
        "%% www.asc.ohio-state.edu/barrett.3/schedule/MATH/",
        r"\CourseDataDate{%s}" % datetime.date.today().isoformat(),
    ]

    for number in numbers:
        rec = catalog.get(number, {})
        off = offerings.get(number, {})
        fields = [
            ("title", rec.get("title", "")),
            ("credits", credits_phrase(rec.get("credit_hours", ""))),
            ("semesters", ", ".join(off.get("seasons_recent", []))),
            ("description", rec.get("description", "")),
            ("prereq", rec.get("prereqs", "")),
            ("exclusions", rec.get("exclusions", "")),
            ("lastoffered", off.get("last_offered", "")),
        ]
        emitted = [(name, texify(v)) for name, v in fields if v and v.strip()]
        if not emitted:
            continue
        lines.append("%% Math " + number)
        # One physical line per entry: no wrapping means no stray spaces from
        # line breaks inside a braced argument.
        lines += [r"\CourseData{%s}{%s}{%s}" % (number, name, value)
                  for name, value in emitted]

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {args.out}: {len(numbers)} courses, "
          f"{sum(1 for l in lines if l.startswith(chr(92) + 'CourseData{'))} fields")


if __name__ == "__main__":
    main()
