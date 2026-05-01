# Ferðadagbók

Personal travel journal for a five-week trip through Indonesia (1. maí – 6. júní 2026).

**Live site:** [landkonnudir.is](https://landkonnudir.is)

**Route:** Jakarta → Tanjung Puting (Borneo) → Sulawesi → Flores → Jakarta

## How it works
Entries live as sub-pages under one Notion parent page. A GitHub Action runs every hour: pulls the sub-pages, writes them to `entries/*.md`, prunes anything that's been deleted in Notion, builds the static site into `docs/`, and commits the result back to `main`. Netlify deploys `docs/` to landkonnudir.is.

No AI rewriting — what you type in Notion is exactly what shows up on the site.

## Stack
- Python (`process_journal.py`, `build_site.py`)
- [notion-client](https://pypi.org/project/notion-client/) for the Notion API
- [Leaflet](https://leafletjs.com/) for the map
- Vanilla JS for the lightbox and accordion
- GitHub Actions (hourly) → Netlify (auto-deploy from `main`)
