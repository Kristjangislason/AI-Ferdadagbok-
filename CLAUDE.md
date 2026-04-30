# AI-Ferðadagbók (Travel Journal)

## What this project is
A personal travel journal for a trip through Indonesia (1. maí – 6. júní 2026).
Route: Jakarta → Tanjung Puting (Borneo) → Sulawesi → Flores → Jakarta.
Site is published in Icelandic.

## Workflow
Entries live as sub-pages under one parent Notion page (`NOTION_PAGE_ID` in `.env`).
Each sub-page is one blog entry — the Notion title becomes the entry title and
the page body is rendered verbatim on the site. No AI rewriting.

- `process_journal.py` — fetch every Notion sub-page and write `entries/*.md`.
- `build_site.py` — render `entries/` + `videos.json` into `docs/`.

## Notion page conventions
- **Sub-page title** is the entry title shown on the website.
- **Sub-page body** is the entry body shown on the website.
- **Date**: if the title starts with `YYYY-MM-DD` it's used as the entry date
  (and stripped from the displayed title). Otherwise the page's Notion
  `created_time` is used.
- **Map pins**: include a line `Staðir: Jakarta, Tana Toraja` (or `Staður: Jakarta`)
  anywhere in the body to drop pins on the landing-page map. Comma-separated,
  case-insensitive, hidden from the rendered page. If absent, the build falls
  back to guessing one place from the entry title.
- Images embedded in the page are downloaded into `images/` and shown on the site.
