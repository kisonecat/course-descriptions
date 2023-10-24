# Course Descriptions

These are Markdown files with a YAML preamble to associate metadata
like the course title, semesters, credits.

For example, the plain text file at

https://github.com/kisonecat/course-descriptions/blob/main/4580.md

automatically generates

https://kisonecat.github.io/course-descriptions/4580.pdf

This is handled with a GitHub action that calls `build.py` which uses
`header.tex` and `footer.tex` to generate the PDF file.
