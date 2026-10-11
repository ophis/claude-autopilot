#!/usr/bin/env python3
"""Read (and initialize) the Claude Autopilot plugin config.

Run once at skill startup: locate the plugin's own data dir for the selected host
(Claude by default; ``--host codex`` uses ``$CODEX_HOME`` or ``~/.codex``).
``--data-dir`` overrides host defaults. For Claude, honor ``$CLAUDE_PLUGIN_DATA``.
ensure ``<data-dir>/config.json`` exists (write DEFAULTS if absent), and print
the effective config (DEFAULTS deep-merged with the user's file) as JSON to
stdout. Config lives in the plugin's data dir, never in host settings files.
"""
import argparse
import json
import os
import sys

DEFAULTS = {
    # The deprecated "enabled" driver toggle is gone (native loop is the only
    # driver); a user config still carrying it merges through harmlessly.
    "ralphLoop": {
        # Per-phase round cap: spec-phase = S3 spec review,
        # implementation-phase = S6 work review.
        "maxIterations": {"spec-phase": 3, "implementation-phase": 3},
    }
}


def deep_merge(base, override):
    """Return base with override applied recursively (override wins)."""
    out = dict(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("claude", "codex"), default="claude")
    parser.add_argument("--data-dir", help="explicit plugin config directory")
    args = parser.parse_args()
    # Fallback {id} = "<plugin>-<marketplace>" with non-[A-Za-z0-9_-] sanitized to '-'.
    if args.data_dir:
        data_dir = args.data_dir
    elif args.host == "codex":
        data_dir = os.path.join(os.environ.get("CODEX_HOME") or "~/.codex",
                                "plugins", "data", "autopilot-claude-autopilot")
    else:
        data_dir = os.environ.get("CLAUDE_PLUGIN_DATA") or (
            "~/.claude/plugins/data/autopilot-claude-autopilot")
    data_dir = os.path.expanduser(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "config.json")

    effective = DEFAULTS
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                effective = deep_merge(DEFAULTS, json.load(fh))
        except (json.JSONDecodeError, OSError):
            # Don't overwrite a bad file — leave it for the user to fix.
            effective = DEFAULTS
    else:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(DEFAULTS, fh, indent=2)
                fh.write("\n")
        except OSError:
            pass  # printing defaults below is still correct

    json.dump(effective, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
