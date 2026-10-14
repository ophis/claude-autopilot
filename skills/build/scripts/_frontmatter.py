"""Shared frontmatter reader for select-panel.py and lint-roster.py.

The two hyphenated (non-importable) CLIs scan the same ``agents/*.md``
frontmatter; this one fence-finding + ``key: value`` reader keeps them from
drifting. Importable by both because Python puts the invoked script's own
directory on ``sys.path``. The typed ``applies_to``/``tier`` parsers below are
the single reading both use, so the lint rejects exactly what the selector
would silently drop.
"""
import json

PHASES_OF = {"spec": ("spec",), "work": ("work",), "both": ("spec", "work")}


def split_frontmatter(text):
    """Split markdown into (frontmatter lines, body str) at the first two
    ``---`` fence lines. Returns ``(None, "")`` when there is no such block.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, ""
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1 :])
    return None, ""


def iter_kv(fm_lines):
    """Yield stripped (key, value) from top-level ``key: value`` frontmatter
    lines. Skips blanks, colon-less lines, and indented continuations (e.g.
    folded description bodies).
    """
    for raw in fm_lines:
        if not raw.strip() or raw.lstrip() != raw:
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        yield key.strip(), value.strip()


def parse_applies_to(value):
    """A JSON array of non-empty strings, else None."""
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, list) and parsed and all(isinstance(x, str) and x for x in parsed):
        return parsed
    return None


def parse_tier(value):
    """A scalar tier, or a JSON object of phase -> tier; None if the object is malformed."""
    if not value.startswith("{"):
        return value
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def tier_for(tier, phase):
    """The tier an agent has in ``phase``: a map's entry, or the scalar itself."""
    return tier.get(phase) if isinstance(tier, dict) else tier
