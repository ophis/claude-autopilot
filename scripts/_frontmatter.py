"""Shared frontmatter reader for select-panel.py and lint-roster.py.

Both CLIs scan the same ``agents/*.md`` frontmatter; this module owns the one
fence-finding + ``key: value`` scanning implementation so the two readers
cannot drift (audit item Q1/D7). The CLIs keep their hyphenated, non-importable
names — this plain-named sibling is importable by both because Python puts the
invoked script's own directory on ``sys.path``.

Each caller applies its own typed parsing on top of the raw (key, value)
pairs: select-panel filters to its routing keys and JSON-parses ``applies_to``;
lint-roster captures every key, list-parses ``tools``/``applies_to``, and
strips block-scalar indicators.
"""


def split_frontmatter(text):
    """Split markdown text into (frontmatter lines, body str).

    The frontmatter is the block between the first two ``---`` fence lines.
    Returns ``(None, "")`` when there is no well-formed block.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, ""
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "\n".join(lines[i + 1 :])
    return None, ""


def iter_kv(fm_lines):
    """Yield (key, value) from top-level ``key: value`` frontmatter lines.

    Skips blanks, comments-without-colon, and continuation/indented lines
    (e.g. folded description bodies). Keys and values are stripped but
    otherwise raw.
    """
    for raw in fm_lines:
        if not raw.strip() or raw.lstrip() != raw:
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        yield key.strip(), value.strip()
