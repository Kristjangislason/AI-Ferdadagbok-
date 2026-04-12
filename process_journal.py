"""
AI-Ferðadagbók — Process rough travel notes from Notion into polished journal entries.

Reads notes from ## TO PROCESS, sends each to Claude for writing,
saves as Markdown, then moves processed notes to ## DONE.
"""

import os
import re
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from notion_client import Client

load_dotenv(dotenv_path='.env')

anthropic = Anthropic()
notion = Client(auth=os.environ["NOTION_API_KEY"])
PAGE_ID = os.environ["NOTION_PAGE_ID"]
ENTRIES_DIR = Path(__file__).parent / "entries"
ENTRIES_DIR.mkdir(exist_ok=True)

SYSTEM_PROMPT = """\
You are a travel journal writer. The user gives you rough travel notes and you \
turn them into a polished, vivid, warm journal entry in Markdown.

Rules:
- Write in first person, present-tense feeling (as if reliving the day)
- Never invent facts — only use what the notes provide
- Keep it concise but evocative — aim for 150–300 words
- Start with a heading: # Month Day — Short Title
- Infer the date from the notes

After the journal entry, on a new line, output exactly:
FILENAME: <yyyy-mm-dd-short-slug.md>

The slug should be lowercase, hyphenated, descriptive (e.g. 2025-05-01-first-night-in-jakarta.md).
"""


def get_page_blocks():
    """Fetch all blocks from the Notion page."""
    blocks = []
    cursor = None
    while True:
        response = notion.blocks.children.list(block_id=PAGE_ID, start_cursor=cursor)
        blocks.extend(response["results"])
        if not response["has_more"]:
            break
        cursor = response["next_cursor"]
    return blocks


def extract_text(block):
    """Extract plain text from a block."""
    block_type = block["type"]
    if block_type not in block:
        return ""
    rich_texts = block[block_type].get("rich_text", [])
    return "".join(rt["plain_text"] for rt in rich_texts)


def find_section_blocks(blocks, header_text):
    """Find all blocks between a given ## header and the next ## header."""
    section_blocks = []
    in_section = False

    for block in blocks:
        # Check if this is a heading_2 block
        if block["type"] == "heading_2":
            text = extract_text(block)
            if text.strip().upper() == header_text.upper():
                in_section = True
                continue
            elif in_section:
                break
        elif in_section:
            section_blocks.append(block)

    return section_blocks


def blocks_to_text(blocks):
    """Convert a list of blocks to plain text."""
    lines = []
    for block in blocks:
        text = extract_text(block)
        if text:
            lines.append(text)
        elif block["type"] == "divider":
            lines.append("---")
    return "\n".join(lines)


def split_entries(text):
    """Split text by --- separators into individual entries."""
    entries = [e.strip() for e in text.split("---")]
    return [e for e in entries if e]


def write_journal_entry(notes):
    """Send notes to Claude and get back a polished journal entry."""
    response = anthropic.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": notes}],
    )

    output = response.content[0].text

    # Split off the FILENAME line
    match = re.search(r"FILENAME:\s*(.+\.md)", output)
    if not match:
        raise ValueError(f"Claude didn't return a FILENAME line. Output:\n{output}")

    filename = match.group(1).strip()
    entry_text = output[: match.start()].strip()

    return filename, entry_text


def move_to_done(blocks_to_move, all_blocks):
    """Delete processed blocks from TO PROCESS and append them under DONE."""
    # Find the DONE heading
    done_heading_id = None
    for block in all_blocks:
        if block["type"] == "heading_2" and extract_text(block).strip().upper() == "DONE":
            done_heading_id = block["id"]
            break

    # If no DONE section exists, create it at the end of the page
    if not done_heading_id:
        notion.blocks.children.append(
            block_id=PAGE_ID,
            children=[
                {"type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": "DONE"}}]}},
                {"type": "divider", "divider": {}},
            ],
        )

    # Rebuild the content to append under DONE — add a divider then the blocks
    children_to_append = [{"type": "divider", "divider": {}}]
    for block in blocks_to_move:
        block_type = block["type"]
        if block_type == "divider":
            children_to_append.append({"type": "divider", "divider": {}})
        else:
            rich_text = block[block_type].get("rich_text", [])
            children_to_append.append({
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text},
            })

    # Append under DONE — find the block after DONE heading to insert after
    if done_heading_id:
        notion.blocks.children.append(block_id=PAGE_ID, children=children_to_append, after=done_heading_id)
    else:
        notion.blocks.children.append(block_id=PAGE_ID, children=children_to_append)

    # Delete the original blocks from TO PROCESS
    for block in blocks_to_move:
        notion.blocks.delete(block_id=block["id"])


def main():
    print("Fetching notes from Notion...")
    all_blocks = get_page_blocks()
    section_blocks = find_section_blocks(all_blocks, "TO PROCESS")

    if not section_blocks:
        print("Nothing to process.")
        return

    text = blocks_to_text(section_blocks)
    entries = split_entries(text)
    print(f"Found {len(entries)} entry/entries to process.")

    for i, notes in enumerate(entries, 1):
        print(f"\n[{i}/{len(entries)}] Processing...")
        print(f"  Notes: {notes[:80]}...")

        filename, entry_text = write_journal_entry(notes)
        date_prefix = filename[:11]  # e.g. "2025-05-01-"

        # Skip if an entry for this date already exists
        existing = list(ENTRIES_DIR.glob(f"{date_prefix}*"))
        if existing:
            print(f"  Skipping — entry for {date_prefix[:-1]} already exists: {existing[0].name}")
            continue

        filepath = ENTRIES_DIR / filename
        filepath.write_text(entry_text + "\n")
        print(f"  Saved: {filename}")

    # Move everything from TO PROCESS to DONE
    print("\nMoving processed notes to DONE...")
    move_to_done(section_blocks, all_blocks)
    print("Done!")


if __name__ == "__main__":
    main()
