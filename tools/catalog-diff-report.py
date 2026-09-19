#!/usr/bin/env python3
"""
Describe, in markdown, how the freshly downloaded university data differs from
what is committed.  Used as the body of the weekly refresh pull request.

Usage:
    python3 tools/catalog-diff-report.py [--ref HEAD]

Run it after `make data`, with the new JSON in the working tree.  Courses that
have a sheet in this repository are reported in full; everything else is
summarized in one line, so the pull request stays about the sheets.
"""

import argparse
import glob
import json
import os
import subprocess
import sys

CATALOG_FIELDS = ["title", "credit_hours", "description", "prereqs", "exclusions"]


def committed(ref, path):
    try:
        blob = subprocess.run(["git", "show", f"{ref}:{path}"],
                              capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    return json.loads(blob)


def by_number(records):
    return {r["catalog_number"]: r for r in records} if records else {}


def sheets():
    return {os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob("[0-9]*.tex")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="HEAD")
    args = ap.parse_args()

    old_cat = by_number(committed(args.ref, "math_courses.json"))
    new_cat = by_number(json.load(open("math_courses.json")))

    old_raw = committed(args.ref, "math_offerings.json") or {}
    old_off = old_raw.get("courses", {})
    new_off = json.load(open("math_offerings.json")).get("courses", {})

    ours = sheets()
    lines = ["The university's course data changed. Every difference below is",
             "the university's, not ours.", ""]

    interesting, other = [], 0
    for number in sorted(set(old_cat) | set(new_cat) | set(old_off) | set(new_off)):
        changes = []
        o, n = old_cat.get(number, {}), new_cat.get(number, {})
        for field in CATALOG_FIELDS:
            if o.get(field, "") != n.get(field, ""):
                changes.append((field, o.get(field, ""), n.get(field, "")))
        oo = old_off.get(number, {}).get("seasons_recent")
        no = new_off.get(number, {}).get("seasons_recent")
        if oo != no:
            changes.append(("semesters offered",
                            ", ".join(oo or []), ", ".join(no or [])))
        if not changes:
            continue
        if number in ours:
            interesting.append((number, n.get("title", ""), changes))
        else:
            other += 1

    if interesting:
        lines.append("## Courses with a sheet in this repository")
        lines.append("")
        for number, title, changes in interesting:
            lines.append(f"### {number} {title}".rstrip())
            for field, was, now in changes:
                lines.append(f"- **{field}**")
                lines.append(f"  - was: {was or '(empty)'}")
                lines.append(f"  - now: {now or '(empty)'}")
            lines.append("")
    else:
        lines.append("No course with a sheet in this repository changed.")
        lines.append("")

    if other:
        lines.append(f"{other} other MATH course(s) changed; they have no sheet here.")
        lines.append("")

    lines.append("Merging this updates the published PDFs. If the university's "
                 "wording is wrong for one of our courses, override it in that "
                 "course's `.tex` with `\\SetCourseField` rather than editing "
                 "`coursedata.tex`, which is generated.")
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
