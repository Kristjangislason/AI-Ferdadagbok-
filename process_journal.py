"""
AI-Ferðadagbók — Pull each Notion sub-page from the parent page and save as
a Markdown journal entry.

Each sub-page under NOTION_PAGE_ID becomes one entry:
  - sub-page title  → entry title (the # heading)
  - sub-page body   → entry body (verbatim)
  - date            → leading "YYYY-MM-DD" in the title if present, else Notion's created_time

No AI rewriting — what you write in Notion is exactly what shows up on the site.
"""

import hashlib
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from notion_client import Client

load_dotenv(dotenv_path=".env")

notion = Client(auth=os.environ["NOTION_API_KEY"])
PARENT_PAGE_ID = os.environ["NOTION_PAGE_ID"]
ENTRIES_DIR = Path(__file__).parent / "entries"
ENTRIES_DIR.mkdir(exist_ok=True)
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)


ICELANDIC_SLUG_MAP = str.maketrans({
    "á": "a", "ð": "d", "é": "e", "í": "i", "ó": "o", "ú": "u", "ý": "y",
    "þ": "th", "æ": "ae", "ö": "o",
    "Á": "A", "Ð": "D", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ý": "Y",
    "Þ": "Th", "Æ": "Ae", "Ö": "O",
})


def slugify(text):
    text = text.translate(ICELANDIC_SLUG_MAP)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "entry"


def list_child_pages():
    pages = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(block_id=PARENT_PAGE_ID, start_cursor=cursor)
        for block in resp["results"]:
            if block["type"] == "child_page":
                pages.append(block)
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]
    return pages


def get_blocks(block_id):
    blocks = []
    cursor = None
    while True:
        resp = notion.blocks.children.list(block_id=block_id, start_cursor=cursor)
        blocks.extend(resp["results"])
        if not resp["has_more"]:
            break
        cursor = resp["next_cursor"]
    return blocks


def rich_text_to_md(rich_texts):
    out = []
    for rt in rich_texts:
        text = rt.get("plain_text", "")
        if not text:
            continue
        ann = rt.get("annotations", {})
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if ann.get("strikethrough"):
            text = f"~~{text}~~"
        href = rt.get("href")
        if href:
            text = f"[{text}]({href})"
        out.append(text)
    return "".join(out)


YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})\b"
)


def extract_youtube_id(url):
    if not url:
        return None
    m = YOUTUBE_URL_RE.match(url.strip())
    return m.group(1) if m else None


def download_image(url, prefix=""):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")
    if "png" in ct:
        ext = ".png"
    elif "gif" in ct:
        ext = ".gif"
    elif "webp" in ct:
        ext = ".webp"
    else:
        ext = ".jpg"
    h = hashlib.sha256(url.encode()).hexdigest()[:12]
    filename = f"{prefix}{h}{ext}"
    (IMAGES_DIR / filename).write_bytes(resp.content)
    return filename


def block_to_md(block, image_prefix=""):
    t = block["type"]
    data = block.get(t, {})

    if t == "paragraph":
        rich = data.get("rich_text", [])
        full_text = "".join(rt.get("plain_text", "") for rt in rich).strip()
        if full_text and " " not in full_text:
            yid = extract_youtube_id(full_text)
            if yid:
                return f"<!--youtube:{yid}-->"
        return rich_text_to_md(rich)
    if t == "heading_1":
        return "## " + rich_text_to_md(data.get("rich_text", []))
    if t == "heading_2":
        return "### " + rich_text_to_md(data.get("rich_text", []))
    if t == "heading_3":
        return "#### " + rich_text_to_md(data.get("rich_text", []))
    if t == "bulleted_list_item":
        return "- " + rich_text_to_md(data.get("rich_text", []))
    if t == "numbered_list_item":
        return "1. " + rich_text_to_md(data.get("rich_text", []))
    if t == "quote":
        text = rich_text_to_md(data.get("rich_text", []))
        return "> " + text.replace("\n", "\n> ")
    if t == "to_do":
        checked = "[x]" if data.get("checked") else "[ ]"
        return f"- {checked} " + rich_text_to_md(data.get("rich_text", []))
    if t == "code":
        text = "".join(rt.get("plain_text", "") for rt in data.get("rich_text", []))
        lang = data.get("language", "")
        return f"```{lang}\n{text}\n```"
    if t == "divider":
        return "---"
    if t == "video":
        if data.get("type") == "external":
            url = data.get("external", {}).get("url", "")
        elif data.get("type") == "file":
            url = data.get("file", {}).get("url", "")
        else:
            url = ""
        yid = extract_youtube_id(url)
        if yid:
            return f"<!--youtube:{yid}-->"
        return ""
    if t == "embed":
        yid = extract_youtube_id(data.get("url", ""))
        if yid:
            return f"<!--youtube:{yid}-->"
        return ""
    if t == "bookmark":
        yid = extract_youtube_id(data.get("url", ""))
        if yid:
            return f"<!--youtube:{yid}-->"
        return ""
    if t == "image":
        if data["type"] == "file":
            url = data["file"]["url"]
        else:
            url = data["external"]["url"]
        caption = "".join(rt.get("plain_text", "") for rt in data.get("caption", []))
        try:
            filename = download_image(url, image_prefix)
            print(f"    Image: {filename}")
            return f"![{caption}](../images/{filename})"
        except Exception as e:
            print(f"    Warning: failed to download image: {e}")
            return ""
    return ""


def blocks_to_markdown(blocks, image_prefix=""):
    return "\n\n".join(filter(None, (block_to_md(b, image_prefix) for b in blocks)))


def parse_title_and_date(raw_title, page_meta):
    """Pull a YYYY-MM-DD prefix from the title if present, else use created_time."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*[-—:]?\s*(.*)$", raw_title.strip())
    if m:
        return m.group(1), (m.group(2).strip() or raw_title.strip())
    created = page_meta.get("created_time", "")[:10]
    return created, raw_title.strip()


def main():
    print("Fetching sub-pages from Notion…")
    pages = list_child_pages()

    if not pages:
        print("No sub-pages found under the parent page. Add some in Notion first.")
        return

    print(f"Found {len(pages)} sub-page(s).")

    for i, page in enumerate(pages, 1):
        raw_title = page["child_page"]["title"]
        date, title = parse_title_and_date(raw_title, page)

        print(f"\n[{i}/{len(pages)}] {title}  ({date})")

        blocks = get_blocks(page["id"])
        body_md = blocks_to_markdown(blocks, image_prefix=f"{date}-")

        slug = slugify(title)
        filename = f"{date}-{slug}.md"
        filepath = ENTRIES_DIR / filename
        filepath.write_text(f"# {title}\n\n{body_md}\n")
        print(f"  Saved: {filename}")

    print(f"\nDone — {len(pages)} entry/entries written to entries/.")


if __name__ == "__main__":
    main()
