.PHONY: all build update-content

all: update-content build

build:
	python3 build_site.py

update-content:
	./scripts/update_content.sh
