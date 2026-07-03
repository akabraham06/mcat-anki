#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Fetch and stage a curated OpenStax corpus as MCAT AI-generation source material.

This script downloads a *curated, high-yield* set of OpenStax textbook sections
(mapped to the MCAT taxonomy in ``rslib/src/mcat/taxonomy.json``), extracts clean
readable text from each page, and writes:

* ``text/<source_key>.txt``   — the extracted section text (the grounding excerpt)
* ``index.json``              — one record per source (name, section, topic_key,
                                book, page URL, license + attribution, text file)

It only performs **web fetches + local file writes**. It does NOT touch the Anki
collection. Registration of these sources into a collection is a separate step —
see ``mcat/sources/register_sources.py`` (run with the app closed).

Provenance / licensing
----------------------
All content is from OpenStax (openstax.org), retrieved via the public REX
"archive" content API. As of this writing OpenStax publishes these titles under
**CC BY-NC-SA 4.0** (Attribution-NonCommercial-ShareAlike), *not* plain CC BY.
The attribution captured per source satisfies the CC BY-NC-SA attribution
requirement (credit OpenStax, book title, link to the free version). Any reuse
must remain non-commercial and share-alike. See README.md.

Usage (network required)::

    python3 mcat/sources/openstax/fetch_openstax.py

Add more coverage by extending ``CURATION`` below (each entry just needs a book
key, a section-number/title ``match``, and an MCAT ``topic_key``).
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TEXT_DIR = os.path.join(HERE, "text")
INDEX_PATH = os.path.join(HERE, "index.json")

# REX archive release pinned for reproducibility. Bump these (and the per-book
# ``version``) when refreshing against a newer OpenStax snapshot.
ARCHIVE = "https://openstax.org/apps/archive/20260604.144757/contents"

LICENSE_NAME = "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International"
LICENSE_SHORT = "CC BY-NC-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"

# Book registry: key -> metadata. ``uuid@version`` identifies the exact snapshot
# in the pinned archive; ``slug`` builds the human-facing "access for free" URL.
BOOKS: dict[str, dict[str, str]] = {
    "biology-2e": {
        "title": "Biology 2e",
        "uuid": "8d50a0af-948b-4204-a71d-4826cba765b8",
        "version": "392e181",
        "slug": "biology-2e",
    },
    "organic-chemistry": {
        "title": "Organic Chemistry",
        "uuid": "6c2f7d1d-fbad-42e8-b977-9b903e6cb83b",
        "version": "93b8bef",
        "slug": "organic-chemistry",
    },
    "chemistry-2e": {
        "title": "Chemistry 2e",
        "uuid": "7fccc9cf-9b71-44f6-800b-f9457fd64335",
        "version": "aa82c2c",
        "slug": "chemistry-2e",
    },
    "college-physics-2e": {
        "title": "College Physics 2e",
        "uuid": "a31df062-930a-4f46-8953-605711e6d204",
        "version": "74c4749",
        "slug": "college-physics-2e",
    },
    "psychology-2e": {
        "title": "Psychology 2e",
        "uuid": "06aba565-9432-40f6-97ee-b8a361f118a8",
        "version": "ee086d3",
        "slug": "psychology-2e",
    },
    "introduction-sociology-3e": {
        "title": "Introduction to Sociology 3e",
        "uuid": "746f171e-0d6a-4ef2-b69d-367880872f4a",
        "version": "cc31c47",
        "slug": "introduction-sociology-3e",
    },
}

# Curated, high-yield section list. Each entry:
#   (book_key, match, topic_key)
# ``match`` is matched against the (tag-stripped) page title in the book tree;
# a section-number prefix like "3.4" or "14.2" is the most robust selector.
# ``topic_key`` is the full MCAT taxonomy tag (section::topic) from taxonomy.json.
CURATION: list[tuple[str, str, str]] = [
    # ===== Biological & Biochemical Foundations (biobiochem) =====
    ("organic-chemistry", "26.1", "biobiochem::amino_acids"),
    ("biology-2e", "3.4", "biobiochem::amino_acids"),
    ("biology-2e", "3.4 Proteins", "biobiochem::protein_structure"),
    ("organic-chemistry", "26.9", "biobiochem::protein_structure"),
    ("biology-2e", "6.5", "biobiochem::enzymes"),
    ("biology-2e", "6.1", "biobiochem::metabolism"),
    ("organic-chemistry", "29.1", "biobiochem::metabolism"),
    ("biology-2e", "7.2", "biobiochem::glycolysis"),
    ("biology-2e", "7.3", "biobiochem::glycolysis"),
    ("biology-2e", "7.4", "biobiochem::glycolysis"),
    ("biology-2e", "4.3", "biobiochem::cell_biology"),
    ("biology-2e", "14.2", "biobiochem::molecular_genetics"),
    ("biology-2e", "15.1", "biobiochem::molecular_genetics"),
    ("biology-2e", "15.5", "biobiochem::molecular_genetics"),
    ("biology-2e", "5.1", "biobiochem::membranes"),
    ("biology-2e", "5.2", "biobiochem::membranes"),
    ("biology-2e", "5.3", "biobiochem::membranes"),
    # ===== Chemical & Physical Foundations (chemphys) =====
    ("college-physics-2e", "15.1", "chemphys::thermodynamics"),
    ("college-physics-2e", "15.2", "chemphys::thermodynamics"),
    ("chemistry-2e", "16.4", "chemphys::thermodynamics"),
    ("chemistry-2e", "12.1", "chemphys::kinetics"),
    ("chemistry-2e", "12.3", "chemphys::kinetics"),
    ("chemistry-2e", "12.5", "chemphys::kinetics"),
    ("chemistry-2e", "14.1", "chemphys::acids_bases"),
    ("chemistry-2e", "14.2", "chemphys::acids_bases"),
    ("chemistry-2e", "14.3", "chemphys::acids_bases"),
    ("chemistry-2e", "2.3", "chemphys::atomic_structure"),
    ("chemistry-2e", "6.2", "chemphys::atomic_structure"),
    ("chemistry-2e", "6.4", "chemphys::atomic_structure"),
    ("chemistry-2e", "5.1", "chemphys::thermochemistry"),
    ("chemistry-2e", "5.2", "chemphys::thermochemistry"),
    ("chemistry-2e", "5.3", "chemphys::thermochemistry"),
    ("college-physics-2e", "11.1", "chemphys::fluids"),
    ("college-physics-2e", "11.2", "chemphys::fluids"),
    ("college-physics-2e", "12.1", "chemphys::fluids"),
    ("chemistry-2e", "17.2", "chemphys::electrochemistry"),
    ("chemistry-2e", "17.3", "chemphys::electrochemistry"),
    ("chemistry-2e", "17.4", "chemphys::electrochemistry"),
    ("chemistry-2e", "4.1", "chemphys::stoichiometry"),
    ("chemistry-2e", "4.3", "chemphys::stoichiometry"),
    ("chemistry-2e", "3.1", "chemphys::stoichiometry"),
    # ===== Psychological, Social & Biological Foundations (psychsoc) =====
    ("psychology-2e", "6.2", "psychsoc::learning_memory"),
    ("psychology-2e", "6.3", "psychsoc::learning_memory"),
    ("psychology-2e", "8.1", "psychsoc::learning_memory"),
    ("psychology-2e", "5.1", "psychsoc::sensation_perception"),
    ("psychology-2e", "5.6", "psychsoc::sensation_perception"),
    ("psychology-2e", "7.1", "psychsoc::cognition"),
    ("psychology-2e", "7.2", "psychsoc::cognition"),
    ("psychology-2e", "10.1", "psychsoc::motivation_emotion"),
    ("psychology-2e", "10.4", "psychsoc::motivation_emotion"),
    ("psychology-2e", "12.1", "psychsoc::social_psychology"),
    ("psychology-2e", "12.3", "psychsoc::social_psychology"),
    ("psychology-2e", "12.4", "psychsoc::social_psychology"),
    ("psychology-2e", "12.2", "psychsoc::identity"),
    ("introduction-sociology-3e", "5.1", "psychsoc::identity"),
    ("introduction-sociology-3e", "9.1", "psychsoc::demographics"),
    ("introduction-sociology-3e", "20.1", "psychsoc::demographics"),
]

TAG_PREFIX = "mcat"


# --------------------------------------------------------------------------- #
# HTML -> clean text
# --------------------------------------------------------------------------- #

_BLOCK_CLOSE = re.compile(
    r"</(p|div|section|h[1-6]|li|ul|ol|tr|table|figure|figcaption|blockquote|dd|dt)\s*>",
    re.I,
)
_BR = re.compile(r"<br\s*/?>", re.I)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
_MATH = re.compile(r"<math\b[^>]*>.*?</math>", re.I | re.S)
_TEX = re.compile(
    r'<annotation[^>]*encoding="application/x-tex"[^>]*>(.*?)</annotation>',
    re.I | re.S,
)
_TAG = re.compile(r"<[^>]+>")
_WS_LINE = re.compile(r"[ \t]+")
_MULTI_NL = re.compile(r"\n{3,}")


def _math_to_text(match: re.Match[str]) -> str:
    """Replace a MathML block with its inline TeX if available, else drop it.

    Stripping raw MathML tags produces garbled token soup, so we prefer the
    embedded TeX annotation (kept inline between $...$)."""
    block = match.group(0)
    tex = _TEX.search(block)
    if tex:
        expr = html.unescape(_TAG.sub("", tex.group(1))).strip()
        return f" ${expr}$ " if expr else " "
    return " "


def extract_text(content_html: str) -> str:
    """Turn an OpenStax page's XHTML ``content`` into clean prose text."""
    s = content_html
    s = _STYLE.sub(" ", s)
    s = _SCRIPT.sub(" ", s)
    s = _MATH.sub(_math_to_text, s)
    s = _BR.sub("\n", s)
    s = _BLOCK_CLOSE.sub("\n", s)
    s = _TAG.sub("", s)
    s = html.unescape(s)
    # Normalise whitespace: trim each line, collapse runs of blank lines.
    lines = [_WS_LINE.sub(" ", ln).strip() for ln in s.split("\n")]
    s = "\n".join(lines)
    s = _MULTI_NL.sub("\n\n", s)
    return s.strip()


# --------------------------------------------------------------------------- #
# Archive access
# --------------------------------------------------------------------------- #

_TREE_CACHE: dict[str, dict] = {}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "anki-mcat-openstax-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def book_tree(book_key: str) -> dict:
    if book_key not in _TREE_CACHE:
        b = BOOKS[book_key]
        _TREE_CACHE[book_key] = _get_json(f"{ARCHIVE}/{b['uuid']}@{b['version']}.json")
    return _TREE_CACHE[book_key]


def _clean_title(t: str) -> str:
    return re.sub(r"<[^>]+>", "", t).strip()


def find_page(book_key: str, match: str) -> tuple[str, str]:
    """Return (page_uuid, clean_title) for the first leaf whose title matches.

    Matches a section-number prefix (e.g. "3.4") or a title substring.
    """
    tree = book_tree(book_key)["tree"]
    number_prefix = bool(re.match(r"^\d+\.\d+$", match))
    found: list[tuple[str, str]] = []

    def walk(node: dict) -> None:
        for c in node.get("contents", []):
            if "contents" in c:
                walk(c)
            else:
                title = _clean_title(c.get("title", ""))
                uuid = c.get("id", "").split("@")[0]
                if number_prefix:
                    if re.match(rf"^{re.escape(match)}(\D|$)", title):
                        found.append((uuid, title))
                elif match.lower() in title.lower():
                    found.append((uuid, title))

    walk(tree)
    if not found:
        raise LookupError(f"no page in {book_key} matching {match!r}")
    return found[0]


def fetch_page(book_key: str, page_uuid: str) -> dict:
    b = BOOKS[book_key]
    url = f"{ARCHIVE}/{b['uuid']}@{b['version']}:{page_uuid}.json"
    return _get_json(url)


# --------------------------------------------------------------------------- #
# Staging
# --------------------------------------------------------------------------- #


def source_key(book_key: str, section_no: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", f"{book_key}-{section_no}".lower()).strip("-")
    return safe


def page_url(book_key: str, page_slug: str) -> str:
    return f"https://openstax.org/books/{BOOKS[book_key]['slug']}/pages/{page_slug}"


def attribution(book_key: str, page_title: str, url: str) -> str:
    title = BOOKS[book_key]["title"]
    return (
        f'Content from OpenStax, "{title}" ({page_title}). '
        f"Access this book for free at {url}. "
        f"Licensed under {LICENSE_SHORT} ({LICENSE_URL}). "
        "Attribution to OpenStax; NonCommercial + ShareAlike required. "
        "The OpenStax name and logo are not covered by the CC license."
    )


def main() -> None:
    os.makedirs(TEXT_DIR, exist_ok=True)
    records: list[dict] = []
    seen_keys: set[str] = set()
    errors: list[str] = []

    for i, (book_key, match, topic) in enumerate(CURATION):
        try:
            page_uuid, title = find_page(book_key, match)
            # A numeric section label like "3.4 Proteins"; fall back to title.
            m = re.match(r"^(\d+\.\d+)", title)
            section_no = m.group(1) if m else match
            key = source_key(book_key, section_no)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            page = fetch_page(book_key, page_uuid)
            text = extract_text(page.get("content", ""))
            url = page_url(book_key, page.get("slug", ""))
            book_title = BOOKS[book_key]["title"]

            txt_name = f"{key}.txt"
            with open(os.path.join(TEXT_DIR, txt_name), "w", encoding="utf-8") as fh:
                fh.write(text)

            records.append(
                {
                    "source_key": key,
                    "name": f"OpenStax {book_title} — {title}",
                    "source_section": f"{book_title} · {title}",
                    "topic_key": f"{TAG_PREFIX}::{topic}",
                    "book": book_key,
                    "book_title": book_title,
                    "page_title": title,
                    "page_uuid": page_uuid,
                    "url": url,
                    "text_file": f"text/{txt_name}",
                    "char_count": len(text),
                    "license": LICENSE_SHORT,
                    "license_name": LICENSE_NAME,
                    "license_url": LICENSE_URL,
                    "attribution": attribution(book_key, title, url),
                }
            )
            print(f"[{i + 1:>2}/{len(CURATION)}] {book_key} {section_no:>5}  "
                  f"{len(text):>6} chars  {title}")
            time.sleep(0.3)  # be polite
        except Exception as exc:  # noqa: BLE001
            msg = f"FAILED {book_key} {match}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)

    index = {
        "generator": "mcat/sources/openstax/fetch_openstax.py",
        "publisher": "OpenStax (openstax.org)",
        "archive": ARCHIVE,
        "license": LICENSE_SHORT,
        "license_name": LICENSE_NAME,
        "license_url": LICENSE_URL,
        "attribution_note": (
            "All sources are OpenStax content under CC BY-NC-SA 4.0. Each record "
            "carries its own attribution string. Reuse must remain non-commercial "
            "and share-alike."
        ),
        "tag_prefix": TAG_PREFIX,
        "source_count": len(records),
        "sources": records,
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    covered = sorted({r["topic_key"] for r in records})
    print(f"\nStaged {len(records)} sources across {len(covered)} topics.")
    print(f"Index: {INDEX_PATH}")
    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print("  " + e)


if __name__ == "__main__":
    main()
