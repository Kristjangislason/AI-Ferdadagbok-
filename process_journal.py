import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv
from notion_client import Client

load_dotenv(dotenv_path=".env")

ENTRIES_DIR = Path(__file__).parent / "entries"
ENTRIES_DIR.mkdir(exist_ok=True)
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)
SLUG_REGISTRY_PATH = Path(__file__).parent / "entries" / ".slug_registry.json"
REDIRECTS_PATH = Path(__file__).parent / "docs" / "_redirects"

ICELANDIC_SLUG_MAP = str.maketrans({"á":"a","ð":"d","é":"e","í":"i","ó":"o","ú":"u","ý":"y","þ":"th","æ":"ae","ö":"o","Á":"A","Ð":"D","É":"E","Í":"I","Ó":"O","Ú":"U","Ý":"Y","Þ":"Th","Æ":"Ae","Ö":"O"})

YOUTUBE_URL_RE = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com/watch\?[^\s]*v=|youtube\.com/embed/|youtube\.com/shorts/|youtu\.be/)([\w-]{11})")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}. Set it in GitHub Secrets or .env before running.")
    return value


def slugify(text):
    text = text.translate(ICELANDIC_SLUG_MAP)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "entry"


def md_escape(s: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>~])", r"\\\1", s)


def rich_text_to_md(rich_texts):
    out = []
    for rt in rich_texts:
        text = md_escape(rt.get("plain_text", ""))
        if rt.get("type") == "equation":
            text = f"${rt.get('equation', {}).get('expression', '')}$"
        href = rt.get("href")
        ann = rt.get("annotations", {})
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if ann.get("strikethrough"):
            text = f"~~{text}~~"
        if ann.get("underline"):
            text = f"<u>{text}</u>"
        if href:
            text = f"[{text}]({href})"
        out.append(text)
    return "".join(out)


def extract_youtube_id(url):
    if not url:
        return None
    m = YOUTUBE_URL_RE.search(url.strip())
    if m:
        return m.group(1)
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        vid = parse_qs(parsed.query).get("v", [None])[0]
        if vid and re.match(r"^[\w-]{11}$", vid):
            return vid
    return None


def list_child_pages(notion, parent_id):
    pages, cursor = [], None
    while True:
        resp = notion.blocks.children.list(block_id=parent_id, start_cursor=cursor)
        pages.extend([b for b in resp["results"] if b["type"] == "child_page"])
        if not resp["has_more"]:
            return pages
        cursor = resp["next_cursor"]


def get_blocks(notion, block_id):
    blocks, cursor = [], None
    while True:
        resp = notion.blocks.children.list(block_id=block_id, start_cursor=cursor)
        blocks.extend(resp["results"])
        if not resp["has_more"]:
            return blocks
        cursor = resp["next_cursor"]


def download_image(url, prefix=""):
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        ext = ".jpg"
    h = hashlib.sha256(parsed.path.encode()).hexdigest()[:12]
    filename = f"{prefix}{h}{ext}"
    filepath = IMAGES_DIR / filename
    if not filepath.exists():
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        filepath.write_bytes(resp.content)
    return filename


def render_block(notion, block, depth=0, image_prefix=""):
    t = block["type"]
    data = block.get(t, {})
    indent = "  " * depth
    line = ""
    if t in ("paragraph", "heading_1", "heading_2", "heading_3", "quote"):
        text = rich_text_to_md(data.get("rich_text", []))
        if t == "heading_1": line = "## " + text
        elif t == "heading_2": line = "### " + text
        elif t == "heading_3": line = "#### " + text
        elif t == "quote": line = "> " + text
        else:
            yid = extract_youtube_id("".join(rt.get("plain_text", "") for rt in data.get("rich_text", [])))
            line = f"<!--youtube:{yid}-->" if yid else text
    elif t == "bulleted_list_item":
        line = f"{indent}- {rich_text_to_md(data.get('rich_text', []))}"
    elif t == "numbered_list_item":
        line = f"{indent}1. {rich_text_to_md(data.get('rich_text', []))}"
    elif t == "to_do":
        line = f"{indent}- [{'x' if data.get('checked') else ' '}] {rich_text_to_md(data.get('rich_text', []))}"
    elif t == "code":
        raw = "".join(rt.get("plain_text", "") for rt in data.get("rich_text", []))
        line = f"```{data.get('language','')}\n{raw}\n```"
    elif t == "image":
        url = data[data.get("type", "external")]["url"]
        cap = rich_text_to_md(data.get("caption", []))
        filename = download_image(url, image_prefix)
        line = f"![{cap}](../images/{filename})"
    elif t in ("video", "embed", "bookmark", "audio", "pdf", "file"):
        url = data.get("url") or data.get("external", {}).get("url") or data.get("file", {}).get("url", "")
        yid = extract_youtube_id(url)
        line = f"<!--youtube:{yid}-->" if yid else f"[{t}]({url})"
    elif t == "equation":
        line = f"$${data.get('expression','')}$$"
    elif t == "divider":
        line = "---"
    elif t == "callout":
        line = f"> ℹ️ {rich_text_to_md(data.get('rich_text', []))}"
    else:
        line = f"<!-- unsupported notion block: {t} -->"

    lines = [line] if line else []
    if block.get("has_children"):
        for child in get_blocks(notion, block["id"]):
            child_md = render_block(notion, child, depth + (1 if t in ("bulleted_list_item","numbered_list_item","to_do") else 0), image_prefix)
            if child_md:
                lines.append(child_md)
    return "\n\n".join([l for l in lines if l])


def parse_title_and_date(raw_title, page_meta):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*[-—:]?\s*(.*)$", raw_title.strip())
    if m:
        return m.group(1), (m.group(2).strip() or raw_title.strip())
    return page_meta.get("created_time", "")[:10], raw_title.strip()


def load_registry():
    return json.loads(SLUG_REGISTRY_PATH.read_text(encoding="utf-8")) if SLUG_REGISTRY_PATH.exists() else {}


def main():
    api_key = require_env("NOTION_API_KEY")
    parent_id = require_env("NOTION_PAGE_ID")
    notion = Client(auth=api_key)
    reg = load_registry()
    redirects = []
    pages = list_child_pages(notion, parent_id)
    expected = set()
    failed = []
    for page in pages:
        date, title = parse_title_and_date(page["child_page"]["title"], page)
        page_id = page["id"].replace("-", "")
        slug = reg.get(page_id, {}).get("slug") or f"{date}-{slugify(title)}"
        if slug in expected:
            slug = f"{slug}-{page_id[:6]}"
        filename = f"{slug}.md"
        try:
            blocks = get_blocks(notion, page["id"])
            body = "\n\n".join(filter(None, [render_block(notion, b, image_prefix=f"{date}-") for b in blocks]))
            fm = f"---\ntitle: {title}\ndate: {date}\nnotion_page_id: {page_id}\nslug: {slug}\ncreated_time: {page.get('created_time','')}\nlast_edited_time: {page.get('last_edited_time','')}\n---\n\n"
            (ENTRIES_DIR / filename).write_text(fm + body + "\n", encoding="utf-8")
            old = reg.get(page_id, {}).get("slug")
            if old and old != slug:
                redirects.append(f"/{old}.html /{slug}.html 301")
            reg[page_id] = {"slug": slug, "title": title, "updated": datetime.utcnow().isoformat()}
            expected.add(filename)
        except Exception as e:
            failed.append(f"{title}: {e}")
    if failed:
        print("Sync failures:\n" + "\n".join(failed), file=sys.stderr)
        raise SystemExit(1)
    for f in ENTRIES_DIR.glob("*.md"):
        if f.name not in expected and f.name != ".slug_registry.json":
            f.unlink()
    SLUG_REGISTRY_PATH.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
    if redirects:
        REDIRECTS_PATH.parent.mkdir(exist_ok=True)
        REDIRECTS_PATH.write_text("\n".join(sorted(set(redirects))) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
