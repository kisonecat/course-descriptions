# Course description sheets.
#
#   make            build every <number>.pdf
#   make data       re-download the university's data and regenerate coursedata.tex
#   make check      verify coursedata.tex is in sync and no sheet is missing data
#   make clean      remove build artifacts
#
# Editing a course sheet needs nothing but LaTeX; `make data' is the only
# target that touches the network.

TEX_FILES := $(wildcard [0-9]*.tex)
PDF_FILES := $(TEX_FILES:.tex=.pdf)

LATEXMK := latexmk -xelatex -interaction=nonstopmode -halt-on-error

all: $(PDF_FILES)

%.pdf: %.tex osucourse.cls coursedata.tex sequencing-chart.tex
	$(LATEXMK) $<

coursedata.tex: math_courses.json math_offerings.json make-course-data.py
	python3 make-course-data.py

# Network-touching, and deliberately not on the build path: a course sheet
# must still build when the university's servers are having a bad day.
data:
	python3 download-course-json.py
	python3 download-schedule-history.py
	python3 make-course-data.py

# What CI runs after `make'.
check: coursedata.tex
	@python3 make-course-data.py --out coursedata.check.tex
	@diff -q coursedata.tex coursedata.check.tex >/dev/null \
	  || { echo "coursedata.tex is out of sync with the JSON; run 'make data'"; \
	       rm -f coursedata.check.tex; exit 1; }
	@rm -f coursedata.check.tex
	@if grep -h -q 'No catalog data' *.log 2>/dev/null; then \
	   echo "some sheets are missing catalog data:"; \
	   grep -h 'No catalog data' *.log | sort -u; exit 1; \
	 fi
	@echo "check: coursedata.tex is current and every sheet has its catalog data"

clean:
	latexmk -C
	rm -f $(PDF_FILES) coursedata.check.tex

.PHONY: all data check clean
