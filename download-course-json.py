#!/usr/bin/env python3
"""
Pull Ohio State MATH course data from the class search JSON feed
(the unofficial endpoint behind classes.osu.edu): titles, credit hours,
catalog descriptions, prerequisites and exclusions.

Usage:
    python3 download-course-json.py [--out math_courses.json]

Uses only the Python standard library, so it runs anywhere python3 does.

Note: this endpoint is undocumented and may change.  Its filter values are
lowercase slugs (subject=math, campus=col); passing "MATH"/"COL" silently
returns zero results.  If requests start coming back empty, open
classes.osu.edu in a browser, search MATH, and check the Network tab
(developer tools) for the current request URL and parameters.

This feed only answers for the terms currently open for scheduling -- about
three at any moment.  It is therefore NOT a source of offering history;
download-schedule-history.py handles that.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://content.osu.edu/v2/classes/search"
SUBJECT = "MATH"          # the value that appears inside the records
SUBJECT_SLUG = "math"     # the value the filter expects
CAMPUS_SLUG = "col"       # Columbus; set to None for all campuses
DELAY_SECONDS = 1.0       # be polite to the server
HEADERS = {"User-Agent": "OSU MATH dept course list"}

# A full MATH fetch returns well over a hundred distinct courses.  If we get
# far fewer, the endpoint or its parameters have changed and we should refuse
# to overwrite good data with an empty file.
MIN_EXPECTED_COURSES = 100


def get(params):
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def available_terms():
    """Ask the feed which terms it will actually answer for."""
    data = get({"q": SUBJECT}).get("data", {})
    for f in data.get("filters", []):
        if f.get("slug") == "term":
            return [(i["term"], i["title"]) for i in f.get("items", [])]
    sys.exit("feed shape changed: no term filter in the response")


def fetch_term(term):
    """Return all course records for SUBJECT in one term (all pages)."""
    courses, page = [], 1
    while True:
        params = {"q": SUBJECT, "subject": SUBJECT_SLUG, "term": term, "p": page}
        if CAMPUS_SLUG:
            params["campus"] = CAMPUS_SLUG
        data = get(params).get("data", {})
        for item in data.get("courses", []):
            course = item.get("course", {})
            if course.get("subject") == SUBJECT:
                courses.append(course)
        total = data.get("totalPages", 0)
        if total == 0 or page >= total:
            break
        page += 1
        time.sleep(DELAY_SECONDS)
    return courses


# Catalog text runs description, then "Prereq: ...", then one of a handful of
# restriction sentences.  Splitting on the first period truncates anything
# containing a decimal course number (2162.xx, 263.01H), so we split on the
# markers themselves and take each fragment up to the next marker.
PREREQ_RE = re.compile(r"\bPrereq(?:uisite)?s?:\s*", re.IGNORECASE)
EXCLUSION_MARKERS = (
    r"Not open to\b",
    r"Not open for credit to\b",
    r"Entry to this course is restricted\b",
    r"This course is available for EM credit\b",
)
EXCLUSION_RE = re.compile(r"(" + "|".join(EXCLUSION_MARKERS) + r")", re.IGNORECASE)


def split_description(text):
    """Split catalog text into (description, prereq, exclusion)."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return "", "", ""

    m = PREREQ_RE.search(text)
    if m:
        desc, rest = text[:m.start()].strip(), text[m.end():].strip()
    else:
        first, _, tail = text.partition("\n")
        desc, rest = first.strip(), tail.strip()

    # The exclusion runs from its marker to the end of the text; anything
    # before it is prerequisite prose.
    exclusion = ""
    e = EXCLUSION_RE.search(rest)
    if e:
        exclusion = rest[e.start():].strip()
        rest = rest[:e.start()].strip()

    # Some records repeat the "Prereq:" label on later lines.
    prereq = PREREQ_RE.sub("", rest).strip()
    return collapse(desc), collapse(prereq), collapse(exclusion)


def collapse(s):
    """Join hard-wrapped lines and squeeze runs of whitespace."""
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="math_courses.json",
                    help="where to write the JSON (default: %(default)s)")
    args = ap.parse_args()

    terms = available_terms()
    print("terms the feed will answer for: "
          + ", ".join(f"{title} ({code})" for code, title in terms))

    records = {}
    for code, title in terms:
        try:
            courses = fetch_term(code)
        except (urllib.error.URLError, OSError) as e:
            print(f"  {title} ({code}): skipped ({e})")
            continue
        print(f"  {title} ({code}): {len(courses)} course offerings")
        for c in courses:
            key = f"{SUBJECT} {c.get('catalogNumber')}"
            desc, prereq, excl = split_description(c.get("description"))
            lo, hi = c.get("minUnits"), c.get("maxUnits")
            # Later terms overwrite earlier ones, so the newest wording wins.
            records[key] = {
                "course": key,
                "catalog_number": c.get("catalogNumber", ""),
                "title": c.get("title", ""),
                "career": c.get("academicCareer", ""),
                "credit_hours": f"{lo}" if lo == hi else f"{lo}-{hi}",
                "description": desc,
                "prereqs": prereq,
                "exclusions": excl,
                "full_catalog_text": collapse(c.get("description") or ""),
            }
        time.sleep(DELAY_SECONDS)

    if len(records) < MIN_EXPECTED_COURSES:
        sys.exit(f"only {len(records)} MATH courses returned; refusing to "
                 f"overwrite {args.out}. The feed or its parameters have "
                 f"probably changed -- check {BASE_URL} by hand.")

    out = sorted(records.values(),
                 key=lambda r: [int(x) if x.isdigit() else x
                                for x in re.split(r"(\d+)", r["course"])])
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Saved {len(out)} courses to {args.out}")


if __name__ == "__main__":
    main()
