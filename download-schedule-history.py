#!/usr/bin/env python3
"""
Build a history of which MATH courses actually ran, from the department's
term-by-term schedule archive:

    https://www.asc.ohio-state.edu/barrett.3/schedule/MATH/

Usage:
    python3 download-schedule-history.py [--out math_offerings.json]

Uses only the Python standard library.

The archive holds one fixed-column text file per term, going back to Autumn
2008.  This is the only source of offering history: the class-search feed
behind classes.osu.edu answers only for the two or three terms currently open
for scheduling, so it can never tell you whether a course is an Autumn course.
"""

import argparse
import collections
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

INDEX_URL = "https://www.asc.ohio-state.edu/barrett.3/schedule/MATH/"
DELAY_SECONDS = 0.5
HEADERS = {"User-Agent": "OSU MATH dept course list"}

# Autumn 2012 is the first semester term.  Everything before it is on quarters,
# with a Winter season and pre-conversion course numbers (254, 263) that no
# longer exist, so it would only pollute the history.
FIRST_SEMESTER_TERM = 1128

# Seasons offered within this many years of the newest term in the archive are
# what the course sheets report.  Five years is long enough to ride out a
# one-term gap and short enough to drop a pattern the department has abandoned.
RECENT_YEARS = 5

SEASON_ORDER = ["Autumn", "Spring", "Summer"]

# "MATH         1268 (Autumn 2026)         updated: 19-Sep-2026"
HEADER_RE = re.compile(r"^MATH\s+(\d{4})\s+\((\w+)\s+(\d{4})\)")

# "    MATH 4551            18115 L   M W F   1020A   EC0358   17/32   M.Drake"
# Regional-campus sections carry a campus code in an extra column
# ("MATH 1050       LMA  14847 L ..."), so anchoring the class number directly
# after the catalog number keeps this to Columbus.
SECTION_RE = re.compile(
    r"^\s+MATH\s+([0-9][0-9A-Z.]*)\s+(\d{4,5})\s+([A-Z])\b(.*)$")

# "... 17/32" or "... 152/272  +4" -- enrolled/limit, optionally a waitlist.
ENROLL_RE = re.compile(r"\b(\d+)/(\d+)\b")


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def term_files():
    """Semester-era <term>.txt names from the archive's directory index."""
    html = fetch(INDEX_URL)
    names = sorted(set(re.findall(r'href="(\d{4})\.txt"', html)))
    return [n for n in names if int(n) >= FIRST_SEMESTER_TERM]


def parse_term(text):
    """Return (term, season, year, {catalog_number: [(sections, enrolled)]})."""
    lines = text.splitlines()
    if not lines:
        return None
    m = HEADER_RE.match(lines[0])
    if not m:
        return None
    term, season, year = m.group(1), m.group(2), int(m.group(3))

    sections = collections.Counter()
    enrolled = collections.Counter()
    for line in lines[1:]:
        sm = SECTION_RE.match(line)
        if not sm:
            continue
        number, _class_no, component, rest = sm.groups()
        # Recitations auto-enroll under their lecture, so counting them would
        # multiply a course by its number of sections.  Everything else is a
        # primary component: L lecture, S seminar (1295, 1187H), I independent
        # study, F field study, B and so on.
        if component == "R":
            continue
        sections[number] += 1
        em = ENROLL_RE.search(rest)
        if em:
            enrolled[number] += int(em.group(1))
    return term, season, year, sections, enrolled


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="math_offerings.json",
                    help="where to write the JSON (default: %(default)s)")
    args = ap.parse_args()

    names = term_files()
    print(f"{len(names)} semester-era term files in the archive")

    offerings = collections.defaultdict(list)
    newest_year = 0
    skipped = []
    for name in names:
        try:
            text = fetch(urllib.parse.urljoin(INDEX_URL, name + ".txt"))
        except (urllib.error.URLError, OSError) as e:
            print(f"  {name}: skipped ({e})")
            continue
        parsed = parse_term(text)
        if parsed is None:
            print(f"  {name}: skipped (no recognizable header)")
            continue
        term, season, year, sections, enrolled = parsed
        if not sections:
            # Future terms get a placeholder file before anything is scheduled.
            skipped.append(f"{season} {year}")
            continue
        newest_year = max(newest_year, year)
        for number, count in sections.items():
            offerings[number].append({
                "term": term,
                "season": season,
                "year": year,
                "sections": count,
                "enrolled": enrolled.get(number, 0),
            })
        time.sleep(DELAY_SECONDS)

    if not offerings:
        sys.exit(f"no offerings parsed; refusing to overwrite {args.out}. "
                 f"The archive format at {INDEX_URL} has probably changed.")
    if skipped:
        print("  terms with no sections yet (ignored): " + ", ".join(skipped))

    cutoff = newest_year - RECENT_YEARS
    out = {}
    for number, terms in offerings.items():
        terms.sort(key=lambda t: t["term"])
        recent = {t["season"] for t in terms if t["year"] > cutoff}
        every = {t["season"] for t in terms}
        out[number] = {
            "catalog_number": number,
            "seasons_recent": [s for s in SEASON_ORDER if s in recent],
            "seasons_all": [s for s in SEASON_ORDER if s in every],
            "first_offered": f"{terms[0]['season']} {terms[0]['year']}",
            "last_offered": f"{terms[-1]['season']} {terms[-1]['year']}",
            "terms": terms,
        }

    with open(args.out, "w") as f:
        json.dump({
            "source": INDEX_URL,
            "recent_years": RECENT_YEARS,
            "recent_since": cutoff + 1,
            "courses": dict(sorted(out.items())),
        }, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Saved {len(out)} courses to {args.out} "
          f"(recent window: {cutoff + 1}-{newest_year})")


if __name__ == "__main__":
    main()
