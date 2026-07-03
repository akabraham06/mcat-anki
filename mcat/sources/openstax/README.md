# OpenStax MCAT source corpus

A curated, high-yield corpus of OpenStax textbook sections, extracted as clean
readable text and mapped onto the MCAT taxonomy
(`rslib/src/mcat/taxonomy.json`). It is **staged grounding material** for the
AI Card Studio card generator — each entry becomes a registered "source" that
generated cards must cite. Nothing here is wired into the live collection until
you run `../register_sources.py` (see below).

## ⚠️ License: CC BY-NC-SA 4.0 (not plain CC BY)

Although this task was scoped around "CC BY" OpenStax content, **OpenStax has
relicensed its textbook library to Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0)**. This was verified
at staging time against both the OpenStax CMS API and the public book pages
(e.g. the Biology 2e preface). Every title used here reports CC BY-NC-SA 4.0.

What that means for reuse:

- **Attribution** — you must credit OpenStax, name the book, and link to the
  free version. Each source record carries a ready-made `attribution` string,
  and `register_sources.py` embeds it in the grounding excerpt so it shows up in
  the card's source trace.
- **NonCommercial** — the content may not be used for commercial purposes.
  Grounding a personal/educational MCAT study tool is fine; selling generated
  decks built from this content is not.
- **ShareAlike** — adaptations must be shared under the same CC BY-NC-SA 4.0
  license.
- The OpenStax **name and logo** are trademarks and are *not* covered by the CC
  license.

Full license text: <https://creativecommons.org/licenses/by-nc-sa/4.0/>

## Provenance

- **Publisher:** OpenStax, Rice University — <https://openstax.org>
- **Retrieval:** public REX "archive" content API, pinned to archive release
  `20260604.144757`. Per-book UUID + content version are recorded in
  `fetch_openstax.py` (`BOOKS`) and in each source record, so the exact snapshot
  is reproducible.
- **Extraction:** page XHTML → text via `fetch_openstax.py` (`extract_text`):
  `<style>`/`<script>` stripped, block tags turned into line breaks, HTML
  entities decoded, whitespace normalised.
- **Known extraction limitation:** MathML equations are dropped (OpenStax does
  not ship inline TeX in these pages, and raw MathML strips to unreadable token
  soup). Surrounding prose is preserved, so conceptual grounding is intact, but
  some quantitative expressions in chem/physics sections are omitted. Figures
  and images are not included (text only).

## Layout

```
mcat/sources/
├── register_sources.py         # registers this corpus into a collection (app closed)
└── openstax/
    ├── README.md               # this file
    ├── fetch_openstax.py       # reproducible fetcher + curation map (extensible)
    ├── index.json              # one record per source (metadata + attribution)
    └── text/<source_key>.txt   # extracted section text (the grounding excerpt)
```

Each `index.json` record has: `source_key`, `name`
(e.g. *"OpenStax Biology 2e — 3.4 Proteins"*), `source_section`, `topic_key`
(full `mcat::section::topic` tag), `book`/`book_title`, `page_title`,
`page_uuid`, `url` (free-access link), `text_file`, `char_count`, and the
`license*` + `attribution` fields.

## Coverage (23 of 27 taxonomy topics)

56 sources drawn from 6 books:

| Book | Sources |
| --- | --- |
| Biology 2e | 13 |
| Chemistry 2e | 19 |
| College Physics 2e | 5 |
| Psychology 2e | 13 |
| Organic Chemistry | 3 |
| Introduction to Sociology 3e | 3 |

By MCAT section:

- **Chemical & Physical Foundations (`chemphys`)** — all 8 topics covered
  (Chemistry 2e: kinetics, acids/bases, atomic structure, thermochemistry,
  electrochemistry, stoichiometry, thermodynamics; College Physics 2e:
  thermodynamics, fluids).
- **Biological & Biochemical Foundations (`biobiochem`)** — all 8 topics covered
  (Biology 2e for amino acids/proteins, enzymes, metabolism, glycolysis &
  respiration, cell biology, molecular genetics, membranes/transport; Organic
  Chemistry for amino-acid structure, protein structure, metabolic overview).
- **Psychological, Social & Biological Foundations (`psychsoc`)** — all 7 topics
  covered (Psychology 2e for learning/memory, sensation/perception,
  cognition/language, motivation/emotion, social psychology, self/identity;
  Introduction to Sociology 3e for self-development, social stratification,
  demographics).
- **Critical Analysis & Reasoning Skills (`cars`)** — **not covered (gap).** The
  4 CARS topics are reading-reasoning skills with no factual textbook basis, so
  OpenStax content does not map to them. Expected; CARS practice needs passages,
  not source text.

## Extending the corpus

Add coverage by appending `(book_key, match, topic_key)` tuples to `CURATION`
in `fetch_openstax.py` and re-running it. `match` is a section-number prefix
(e.g. `"14.2"`) or a title substring; `topic_key` is a `section::topic` pair
from the taxonomy. To add a new book, add it to `BOOKS` with its `uuid` /
`version` / `slug` (discoverable from `https://openstax.org/rex/release.json`
and the CMS at `https://openstax.org/apps/cms/api/v2/pages/?type=books.Book`).

## Registering into a collection

See `../register_sources.py`. It must be run with **the desktop app closed**
(single-writer SQLite), is idempotent (skips sources already present by name),
and does not generate any cards. Card generation is a separate gated step that
also needs a working AI provider key.
