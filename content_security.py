"""Validation shared by the Notion importer and static site generator."""

import re


def validate_slug(slug):
    """Accept only one safe filename component, including for existing metadata."""
    if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", slug):
        raise ValueError("Entry slug must be a single filename of letters, numbers, hyphens or underscores")
    return slug
