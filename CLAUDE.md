# AI-Ferðadagbók (Travel Journal)

## What this project is
A personal travel journal for a trip through Indonesia (1. maí – 6. júní 2026).
Route: Jakarta → Tanjung Puting (Borneo) → Sulawesi → Flores → Jakarta.
Site is published in Icelandic.

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
- `build_site.py` — render `entries/` + `videos.json` into `docs/`.

A GitHub Action (`.github/workflows/journal.yml`) runs both scripts every
hour and commits any changes back to `main`.

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
- **YouTube videos**: paste a YouTube URL into the body (as a video block, embed,
  bookmark, or a paragraph that's just the URL on its own line). The build
  embeds it inline in the post and auto-adds it to the **Myndbönd** page.
  Titles are fetched via YouTube's oEmbed API and cached in `.youtube-cache.json`.
