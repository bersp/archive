#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
INDEX_YAML_PATH = ROOT / "index.yaml"
ASSETS_DIR = ROOT / "assets"
DIST_DIR = ROOT / "dist"
INDEX_TEMPLATE_PATH = ROOT / "templates" / "index.html"
ENTRY_TEMPLATE_PATH = ROOT / "templates" / "entry.html"
NAVBAR_TEMPLATE_PATH = ROOT / "templates" / "partials" / "navbar.html"
PLACEHOLDER_PATTERN = re.compile(r"\{\{[A-Z_]+\}\}")


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing YAML file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in YAML file: {path}")
    return data


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return path.read_text(encoding="utf-8")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_template(path: Path, substitutions: dict[str, str]) -> str:
    rendered = load_text(path)
    for key, value in substitutions.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)

    unresolved = sorted(set(PLACEHOLDER_PATTERN.findall(rendered)))
    if unresolved:
        raise ValueError(f"{path}: unresolved placeholders: {', '.join(unresolved)}")
    return rendered


def require_string(mapping: dict, key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{context}: missing required string '{key}'")
    value = value.strip()
    if not value:
        raise ValueError(f"{context}: '{key}' cannot be empty")
    return value


def normalize_filename(filename: str, context: str) -> str:
    filename_path = Path(filename)
    if filename_path.is_absolute() or ".." in filename_path.parts:
        raise ValueError(f"{context}: invalid filename '{filename}'")
    return filename_path.as_posix()


def render_empty_card(empty_state: dict) -> str:
    tag = empty_state.get("tag", "Sin archivos")
    title = empty_state.get("title", "No hay documentos publicados")
    description = empty_state.get("description", "Este espacio todavía no tiene archivos disponibles.")
    return (
        "        <div class=\"card card-empty\">\n"
        f"          <p class=\"file-tag\">{esc(tag)}</p>\n"
        f"          <h2 class=\"card-title\">{esc(title)}</h2>\n"
        f"          <p class=\"card-subtitle\">{esc(description)}</p>\n"
        "        </div>"
    )


def render_document_card(document: dict) -> str:
    filename = document["filename"]
    extension = Path(filename).suffix.lstrip(".").upper() or "FILE"
    download_name = Path(filename).name
    return (
        f"        <a class=\"card\" href=\"{esc(filename)}\" download=\"{esc(download_name)}\">\n"
        f"          <p class=\"file-tag\">{esc(extension)}</p>\n"
        f"          <h2 class=\"card-title\">{esc(document['title'])}</h2>\n"
        f"          <p class=\"card-subtitle\">{esc(document['description'])}</p>\n"
        "        </a>"
    )


def render_navbar(home_url: str) -> str:
    return render_template(NAVBAR_TEMPLATE_PATH, {"HOME_URL": esc(home_url)})


def render_entry_cards(entries: list[dict]) -> str:
    return "\n\n".join(
        [
            "        <a class=\"card\" href=\"content/{slug}/index.html\">\n"
            "          <h2 class=\"card-title\">{title}</h2>\n"
            "          <p class=\"card-subtitle\">{subtitle}</p>\n"
            "        </a>".format(
                slug=esc(entry["slug"]),
                title=esc(entry["title"]),
                subtitle=esc(entry["subtitle"]),
            )
            for entry in entries
        ]
    )


def render_index_html(site: dict, entries: list[dict]) -> str:
    return render_template(
        INDEX_TEMPLATE_PATH,
        {
            "LANG": esc(site["language"]),
            "SITE_TITLE": esc(site["title"]),
            "NAVBAR": render_navbar("index.html"),
            "ENTRY_CARDS": render_entry_cards(entries),
        },
    )


def render_entry_html(site: dict, entry: dict) -> str:
    cards = [render_document_card(doc) for doc in entry["documents"]] or [render_empty_card(site["empty_state"])]
    return render_template(
        ENTRY_TEMPLATE_PATH,
        {
            "LANG": esc(site["language"]),
            "SITE_TITLE": esc(site["title"]),
            "ENTRY_TITLE": esc(entry["title"]),
            "ENTRY_SUBTITLE": esc(entry["subtitle"]),
            "NAVBAR": render_navbar("../../index.html"),
            "DOCUMENT_CARDS": "\n\n".join(cards),
        },
    )


def load_entry(path: Path) -> dict:
    data = load_yaml(path)
    page = data.get("page")
    if not isinstance(page, dict):
        raise ValueError(f"{path}: missing required mapping 'page'")

    context = f"{path}:page"
    title = require_string(page, "title", context)
    subtitle = require_string(page, "subtitle", context)
    if "slug" in page:
        raise ValueError(f"{context}: 'slug' is no longer supported; use folder name instead")

    slug = path.parent.name.strip()
    if not slug:
        raise ValueError(f"{path}: could not derive slug from parent folder name")

    raw_documents = data.get("documents", [])
    if not isinstance(raw_documents, list):
        raise ValueError(f"{path}: 'documents' must be a list")

    seen_filenames = set()
    documents = []
    for index, document in enumerate(raw_documents):
        if not isinstance(document, dict):
            raise ValueError(f"{path}:documents[{index}] must be a mapping")

        doc_context = f"{path}:documents[{index}]"
        filename = normalize_filename(require_string(document, "filename", doc_context), doc_context)
        if filename in seen_filenames:
            raise ValueError(f"{doc_context}: duplicate filename '{filename}'")
        seen_filenames.add(filename)

        source_path = path.parent / filename
        if not source_path.is_file():
            raise FileNotFoundError(f"{doc_context}: missing file '{source_path}'")

        documents.append(
            {
                "filename": filename,
                "title": str(document.get("title", filename)).strip() or filename,
                "description": str(document.get("description", "")).strip(),
                "source_path": source_path,
            }
        )

    return {
        "source_path": path,
        "slug": slug,
        "title": title,
        "subtitle": subtitle,
        "documents": documents,
    }


def resolve_entry_paths(index_data: dict) -> list[Path]:
    configured_entries = index_data.get("entry")
    if configured_entries is None:
        return sorted((ROOT / "content").glob("*/main.yaml"))

    if not isinstance(configured_entries, list):
        raise ValueError("index.yaml: 'entry' must be a list when provided")
    if not configured_entries:
        return []

    paths = []
    for index, configured_entry in enumerate(configured_entries):
        if not isinstance(configured_entry, str) or not configured_entry.strip():
            raise ValueError(f"index.yaml:entry[{index}] must be a non-empty string path")
        paths.append(ROOT / configured_entry)
    return paths


def load_site_and_entries(index_data: dict) -> tuple[dict, list[dict]]:
    site_config = index_data.get("site")
    if not isinstance(site_config, dict):
        raise ValueError("index.yaml: missing required mapping 'site'")

    site = {
        "title": str(site_config.get("title", "ARCHIVE")).strip() or "ARCHIVE",
        "language": str(site_config.get("language", "es")).strip() or "es",
        "empty_state": site_config.get("empty_state", {}),
    }
    if not isinstance(site["empty_state"], dict):
        raise ValueError("index.yaml: 'site.empty_state' must be a mapping")

    entries = []
    seen_slugs: dict[str, Path] = {}
    for entry_path in resolve_entry_paths(index_data):
        entry = load_entry(entry_path)
        slug = entry["slug"]
        if slug in seen_slugs:
            raise ValueError(f"Duplicate slug '{slug}' in {entry['source_path']} and {seen_slugs[slug]}")
        seen_slugs[slug] = entry["source_path"]
        entries.append(entry)

    return site, entries


def write_site(site: dict, entries: list[dict]) -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    if not ASSETS_DIR.is_dir():
        raise FileNotFoundError(f"Missing assets directory: {ASSETS_DIR}")
    shutil.copytree(ASSETS_DIR, DIST_DIR / "assets")

    (DIST_DIR / "index.html").write_text(render_index_html(site, entries), encoding="utf-8")
    for entry in entries:
        output_dir = DIST_DIR / "content" / entry["slug"]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "index.html").write_text(render_entry_html(site, entry), encoding="utf-8")

        for document in entry["documents"]:
            destination_path = output_dir / document["filename"]
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(document["source_path"], destination_path)


def main() -> None:
    site, entries = load_site_and_entries(load_yaml(INDEX_YAML_PATH))
    write_site(site, entries)


if __name__ == "__main__":
    main()
