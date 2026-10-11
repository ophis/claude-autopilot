"""Shared frontmatter reader for select-panel.py and lint-roster.py.

The two hyphenated (non-importable) CLIs scan the same ``agents/*.md``
frontmatter; this one fence-finding + ``key: value`` reader keeps them from
drifting. Importable by both because Python puts the invoked script's own
directory on ``sys.path``. Each caller adds its own typed parsing on top.
"""


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
