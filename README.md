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

## Content and download safety

Imported Markdown keeps normal formatting, images and validated YouTube embeds;
active HTML and unsafe link schemes are removed before publishing. Entry slugs
must be a single filename using letters, numbers, hyphens or underscores.

Image downloads use HTTPS, check each redirect, and accept only raster images up
to 20 MiB. Notion's standard file hosts and `images.unsplash.com` are allowed by
default. For other trusted image sources, set `IMAGE_DOWNLOAD_HOSTS` to a
comma-separated list of exact hostnames in your environment, or as a GitHub
Actions repository variable. Add only origins you trust; wildcard hosts are not
supported. The importer does not use ambient proxy settings or `.netrc` login
credentials for image downloads. A failed sync does not prune existing entries.

Run `pip install -r requirements.txt` and `pytest -q` before changing the importer
or generator. After merging generator changes, run **Process Journal** (or wait
for its hourly schedule) to rebuild the published files.
