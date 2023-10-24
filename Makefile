# Find all .md files in the current directory
MD_FILES := $(wildcard *.md)
# Convert the list of .md files to .pdf files
PDF_FILES := $(patsubst %.md,%.pdf,$(MD_FILES))

all: $(PDF_FILES)

%.pdf: %.md
	python build.py $<

.PHONY: all
