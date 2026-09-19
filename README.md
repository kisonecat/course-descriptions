# Course Descriptions

One `.tex` file per course, named for the course number. Each one builds a
one- or two-page sheet describing the course. For example,

<https://github.com/kisonecat/course-descriptions/blob/main/4580.tex>

automatically generates

<https://kisonecat.github.io/course-descriptions/4580.pdf>

A GitHub Action rebuilds every sheet on each push to `main`.

## Editing your course

Open your course's `.tex` file and edit it like any other LaTeX document.
`TEMPLATE.tex` shows every section that is available.

You do **not** write the catalog description, the prerequisites, or the
exclusions. Those two lines

```latex
\CatalogDescription
\PrerequisitesAndExclusions
```

fill themselves in from the university's own data, so they cannot drift out of
date. What you write is everything the department owns:

| | |
|---|---|
| `\begin{Purpose} ... \end{Purpose}` | what the course is for |
| `\begin{LearningOutcomes} ... \end{LearningOutcomes}` | what students should be able to do |
| `\begin{Text} ... \end{Text}` | the textbook |
| `\begin{SupplementalTexts} ... \end{SupplementalTexts}` | further recommended reading |
| `\begin{Technology} ... \end{Technology}` | calculator or software requirements |
| `\begin{TopicsList} \item ... \end{TopicsList}` | a numbered list of topics |
| `\begin{TopicsOutline} ... \end{TopicsOutline}` | a topics list that is an outline rather than a flat list |
| `\begin{SuggestedSchedule} \week{1}{...} \finalsweek{...} \end{SuggestedSchedule}` | the week-by-week plan |
| `\begin{FollowupCourses} ... \end{FollowupCourses}` | what to take next |
| `\SequencingChart` | the shared 1000-level sequencing figure |
| `\begin{Comment} ... \end{Comment}` | anything else |

Using these instead of writing your own headings is what keeps every sheet
looking alike: the wording, the order and the styling of the headings are all
decided in one place, `osucourse.cls`.

## Building a sheet

Any LaTeX installation will do. To build one sheet:

```
latexmk -xelatex 4551.tex
```

To build all of them, `make`. In Overleaf, upload `osucourse.cls`,
`coursedata.tex` and your `NNNN.tex`; those three files are all a sheet needs.

## Where the automatic text comes from

Two sources, both downloaded and committed to this repository so that a sheet
always builds even when the university's servers are down:

| file | holds | from |
|---|---|---|
| `math_courses.json` | title, credit hours, description, prerequisites, exclusions | the class-search feed behind [classes.osu.edu](https://classes.osu.edu) |
| `math_offerings.json` | which courses actually ran, term by term, back to Autumn 2012 | the department's [schedule archive](https://www.asc.ohio-state.edu/barrett.3/schedule/MATH/) |

`make data` refreshes both and regenerates `coursedata.tex`, the table the
LaTeX side reads. **Do not edit `coursedata.tex` by hand** — it is generated,
and `make check` will fail if it disagrees with the JSON.

The class-search feed only answers for the two or three terms currently open
for scheduling, which is why the semesters on each sheet come from the schedule
archive instead: it knows that 4573 has run every Spring since 2013.

A scheduled Action re-downloads both sources every Monday and opens a pull
request when anything changes, with a summary of exactly which courses the
university reworded. Nothing is published until someone merges it.

## When the university's data is wrong

Override the field in your course's preamble, before `\begin{document}`:

```latex
\course{4573}
\SetCourseField{semesters}{Spring (odd years)}
```

The fields are `title`, `credits`, `semesters`, `description`, `prereq` and
`exclusions`. `4545.tex` overrides all of them, because Math 4545 has not been
scheduled since Autumn 2024 and so has fallen out of the class-search feed
entirely.

To keep the catalog's description but add to it, use
`\DescriptionAddendum{...}` rather than replacing the whole thing.

Overrides are recorded in the build log, so it is always possible to see where
the sheets deliberately disagree with the university.

## Where these sheets came from

The upper-level sheets (4350–4581) were maintained here as Markdown and were
converted to LaTeX. The rest were imported from the PDFs already published on
`math.osu.edu`, which an older version of this same pipeline produced:

```
python3 tools/import-course-sheets.py --fetch      # download them (slow, polite)
python3 tools/import-course-sheets.py --report     # show what would be written
python3 tools/import-course-sheets.py --convert    # write the .tex files
python3 tools/check-import-fidelity.py             # compare each against its PDF
```

The importer never overwrites an existing `.tex`, so a sheet that has been
edited here is safe. `check-import-fidelity.py` compares every
department-written word in the published PDF against the sheet we now generate,
which is how the import was verified.

Both scripts are one-shot. Once the import is reviewed and committed they can
be deleted, along with `tools/.course-sheet-cache/`.

## Repository layout

| | |
|---|---|
| `NNNN.tex` | one course sheet |
| `TEMPLATE.tex` | starting point for a new course |
| `osucourse.cls` | the document class: page layout, the OSU logo, and every section command |
| `coursedata.tex` | generated table of catalog facts — do not edit |
| `sequencing-chart.tex` | the 1000-level sequencing figure, drawn in TikZ |
| `math_courses.json`, `math_offerings.json` | the downloaded data |
| `download-course-json.py`, `download-schedule-history.py` | the downloaders |
| `make-course-data.py` | JSON to `coursedata.tex` |
| `tools/` | the weekly diff reporter and the one-shot importers |
| `Makefile` | `make`, `make data`, `make check`, `make clean` |

Both downloaders use only the Python standard library, so there is nothing to
install.
