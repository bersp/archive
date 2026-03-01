.PHONY: all build update-content

all: update-content build

build:
	python3 build_site.py

update-content:
	./scripts/update_content.sh

preview:
	python3 -m http.server 8000 --directory dist
