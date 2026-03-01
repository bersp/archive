#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
ASSETS_DIR = ROOT / "assets"
DIST_DIR = ROOT / "dist"
INDEX_TEMPLATE_PATH = ROOT / "templates" / "index.html"
ENTRY_TEMPLATE_PATH = ROOT / "templates" / "entry.html"
NAVBAR_TEMPLATE_PATH = ROOT / "templates" / "partials" / "navbar.html"
PLACEHOLDER_PATTERN = re.compile(r"\{\{[A-Z_]+\}\}")
SITE_TITLE = "ARCHIVE"
SITE_LANGUAGE = "es"
DOCUMENT_TYPE_ICON_TUPLES = [
    ("file", "fa-solid fa-file"),
    ("pdf", "fa-solid fa-file-pdf"),
    ("link", "fa-solid fa-link"),
    ("python", "fa-brands fa-python"),
]
DOCUMENT_TYPE_ORDER = [document_type for document_type, _ in DOCUMENT_TYPE_ICON_TUPLES]
DOCUMENT_TYPE_ICON_BY_NAME = dict(DOCUMENT_TYPE_ICON_TUPLES)
if len(DOCUMENT_TYPE_ICON_BY_NAME) != len(DOCUMENT_TYPE_ICON_TUPLES):
    raise ValueError("Duplicate document types in DOCUMENT_TYPE_ICON_TUPLES")


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


def normalize_local_path(value: str, context: str) -> str:
    local_path = Path(value)
    if local_path.is_absolute() or ".." in local_path.parts:
        raise ValueError(f"{context}: invalid path '{value}'")
    return local_path.as_posix()


def parse_attachment(attachment: dict, entry_path: Path, context: str) -> dict:
    document_type = require_string(attachment, "type", context)
    if document_type not in DOCUMENT_TYPE_ICON_BY_NAME:
        allowed = ", ".join(DOCUMENT_TYPE_ORDER)
        raise ValueError(f"{context}: unsupported type '{document_type}' (allowed: {allowed})")

    description = require_string(attachment, "description", context)
    has_path = "path" in attachment
    has_url = "url" in attachment
    if has_path == has_url:
        raise ValueError(f"{context}: provide exactly one of 'path' or 'url'")

    if document_type == "link":
        if not has_url:
            raise ValueError(f"{context}: type 'link' requires 'url'")
        href = require_string(attachment, "url", context)
        return {
            "type": document_type,
            "icon_class": DOCUMENT_TYPE_ICON_BY_NAME[document_type],
            "description": description,
            "href": href,
            "download_name": "",
            "path": "",
            "source_path": None,
            "is_external": True,
        }

    if has_url:
        raise ValueError(f"{context}: type '{document_type}' cannot use 'url'; use 'path'")

    local_path = normalize_local_path(require_string(attachment, "path", context), context)
    source_path = entry_path.parent / local_path
    if not source_path.is_file():
        raise FileNotFoundError(f"{context}: missing file '{source_path}'")

    return {
        "type": document_type,
        "icon_class": DOCUMENT_TYPE_ICON_BY_NAME[document_type],
        "description": description,
        "href": local_path,
        "download_name": Path(local_path).name,
        "path": local_path,
        "source_path": source_path,
        "is_external": False,
    }


def parse_document(document: dict, entry_path: Path, context: str) -> dict:
    raw_attachments = document.get("attachments")
    if not isinstance(raw_attachments, list) or not raw_attachments:
        raise ValueError(f"{context}: missing required non-empty list 'attachments'")

    attachments = []
    for attachment_index, attachment in enumerate(raw_attachments):
        if not isinstance(attachment, dict):
            raise ValueError(f"{context}:attachments[{attachment_index}] must be a mapping")
        attachment_context = f"{context}:attachments[{attachment_index}]"
        parsed_attachment = parse_attachment(attachment, entry_path, attachment_context)
        attachments.append((attachment_index, parsed_attachment))

    attachments.sort(key=lambda indexed_attachment: (DOCUMENT_TYPE_ORDER.index(indexed_attachment[1]["type"]), indexed_attachment[0]))
    sorted_attachments = [attachment for _, attachment in attachments]
    first_attachment = sorted_attachments[0]

    fallback_title = first_attachment["href"]
    if first_attachment["path"]:
        fallback_title = first_attachment["path"]

    return {
        "title": str(document.get("title", fallback_title)).strip() or fallback_title,
        "description": str(document.get("description", "")).strip(),
        "attachments": sorted_attachments,
    }


def render_document_card(document: dict, index: int) -> str:
    toggle_id = f"card-toggle-{index}"
    indicator_icons = []
    indicator_types = set()
    attachment_items = []
    for attachment in document["attachments"]:
        if attachment["type"] not in indicator_types:
            indicator_types.add(attachment["type"])
            indicator_icons.append(
                "                <i class=\"{icon_class} card-expand-attachment-icon\" aria-hidden=\"true\"></i>".format(
                    icon_class=esc(attachment["icon_class"])
                )
            )
        download_attr = f" download=\"{esc(attachment['download_name'])}\"" if attachment["download_name"] else ""
        external_attrs = " target=\"_blank\" rel=\"noopener noreferrer\"" if attachment["is_external"] else ""
        attachment_items.append(
            "            <a class=\"card-attachment\" href=\"{href}\"{download_attr}{external_attrs}>"
            "<i class=\"{icon_class}\" aria-hidden=\"true\"></i>"
            "<span>{description}</span>"
            "</a>".format(
                href=esc(attachment["href"]),
                download_attr=download_attr,
                external_attrs=external_attrs,
                icon_class=esc(attachment["icon_class"]),
                description=esc(attachment["description"]),
            )
        )

    subtitle_html = ""
    if document["description"]:
        subtitle_html = f"              <p class=\"card-subtitle\">{esc(document['description'])}</p>\n"

    return (
        "        <article class=\"card card-document\">\n"
        f"          <input id=\"{esc(toggle_id)}\" class=\"card-toggle\" type=\"checkbox\" />\n"
        f"          <label class=\"card-summary\" for=\"{esc(toggle_id)}\">\n"
        "            <div class=\"card-summary-main\">\n"
        f"              <h2 class=\"card-title\">{esc(document['title'])}</h2>\n"
        f"{subtitle_html}"
        "            </div>\n"
        "            <div class=\"card-expand-indicator\" aria-hidden=\"true\">\n"
        "              <span class=\"card-expand-icons\">\n"
        f"{chr(10).join(indicator_icons)}\n"
        "              </span>\n"
        "              <i class=\"fa-solid fa-chevron-down card-expand-chevron\" aria-hidden=\"true\"></i>\n"
        "            </div>\n"
        "          </label>\n"
        "          <div class=\"card-attachments\" aria-label=\"Adjuntos disponibles\">\n"
        "            <div class=\"card-attachments-inner\">\n"
        f"{chr(10).join(attachment_items)}\n"
        "            </div>\n"
        "          </div>\n"
        "        </article>"
    )


def render_navbar(home_url: str) -> str:
    return render_template(NAVBAR_TEMPLATE_PATH, {"HOME_URL": esc(home_url)})


def render_entry_cards(entries: list[dict]) -> str:
    return "\n\n".join(
        [
            "        <a class=\"card\" href=\"content/{slug}/\">\n"
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
            "NAVBAR": render_navbar("./"),
            "ENTRY_CARDS": render_entry_cards(entries),
        },
    )


def render_entry_html(site: dict, entry: dict) -> str:
    cards = [render_document_card(doc, index) for index, doc in enumerate(entry["documents"])]
    return render_template(
        ENTRY_TEMPLATE_PATH,
        {
            "LANG": esc(site["language"]),
            "SITE_TITLE": esc(site["title"]),
            "ENTRY_TITLE": esc(entry["title"]),
            "ENTRY_SUBTITLE": esc(entry["subtitle"]),
            "NAVBAR": render_navbar("../../"),
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

    documents = []
    for index, document in enumerate(raw_documents):
        if not isinstance(document, dict):
            raise ValueError(f"{path}:documents[{index}] must be a mapping")

        doc_context = f"{path}:documents[{index}]"
        documents.append(parse_document(document, path, doc_context))

    return {
        "source_path": path,
        "slug": slug,
        "title": title,
        "subtitle": subtitle,
        "documents": documents,
    }


def resolve_entry_paths() -> list[Path]:
    return sorted((ROOT / "content").glob("*/main.yaml"))


def load_site_and_entries() -> tuple[dict, list[dict]]:
    site = {
        "title": SITE_TITLE,
        "language": SITE_LANGUAGE,
    }

    entries = []
    seen_slugs: dict[str, Path] = {}
    for entry_path in resolve_entry_paths():
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

        copied_paths = set()
        for document in entry["documents"]:
            for attachment in document["attachments"]:
                if not attachment["path"]:
                    continue
                if attachment["path"] in copied_paths:
                    continue
                copied_paths.add(attachment["path"])
                destination_path = output_dir / attachment["path"]
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(attachment["source_path"], destination_path)


def main() -> None:
    site, entries = load_site_and_entries()
    write_site(site, entries)


if __name__ == "__main__":
    main()
