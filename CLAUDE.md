# Ferðadagbók (Travel Journal)

## What this project is
A personal travel journal for a trip through Indonesia (1. maí – 6. júní 2026).
Route: Jakarta → Tanjung Puting (Borneo) → Sulawesi → Flores → Jakarta.
Site is published in Icelandic at **https://landkonnudir.is**
(custom domain via `CNAME` at the repo root, served by Netlify from `docs/`).

## Workflow
Entries live as sub-pages under one parent Notion page (`NOTION_PAGE_ID` in `.env`).
Each sub-page is one blog entry — the Notion title becomes the entry title and
the page body is rendered verbatim on the site. No AI rewriting.

- `process_journal.py` — fetch every Notion sub-page, write `entries/*.md`,
  and prune any local entry/image that no longer corresponds to a current
  Notion sub-page. Notion is the single source of truth: deleting or renaming
  a sub-page automatically removes/updates the entry on the next run.
  Image filenames are hashed from the URL path (not the signed URL) so
  Notion's URL refreshes don't create duplicates.
- `build_site.py` — render `entries/` + `videos.json` into `docs/`. The
  homepage (`index.html`) is the Dagbók itself: a sticky map on the left and
  a `<details>` accordion of entries on the right. Per-entry pages
  (`<slug>.html`) are kept as standalone deep-links. Gallery and Videos use
  a wider canvas; per-entry pages stay narrow for reading.

A GitHub Action (`.github/workflows/journal.yml`) runs both scripts every
hour and commits any changes back to `main`.

## Notion page conventions
- **Sub-page title** is the entry title shown on the website.
- **Sub-page body** is the entry body shown on the website.
- **Date**: if the title starts with `YYYY-MM-DD` it's used as the entry date
  (and stripped from the displayed title). Otherwise the page's Notion
  `created_time` is used.
- **Map pins**: each pin needs an explicit line in the body of the form
  `Staður: <Name>, <lat>, <lng>` (one line per pin; multiple lines for
  multiple pins). Coordinates are decimal numbers. The build does no
  geocoding — what you write is what gets pinned. Lines are case-
  insensitive and hidden from the rendered page.
- Images embedded in the page are downloaded into `images/` and shown on the site.
- **YouTube videos**: paste a YouTube URL into the body (as a video block, embed,
  bookmark, or a paragraph that's just the URL on its own line). The build
  embeds it inline in the post and auto-adds it to the **Myndbönd** page.
  Titles are fetched via YouTube's oEmbed API and cached in `.youtube-cache.json`.
