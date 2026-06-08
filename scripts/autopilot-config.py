#!/usr/bin/env python3
"""Read (and initialize) the Claude Autopilot plugin config.

The build/fix commands run this once at startup. It:
  1. locates the plugin's own data dir (``$CLAUDE_PLUGIN_DATA``; falls back to
     ``~/.claude/plugins/data/autopilot-claude-autopilot`` if the env var is unset),
  2. ensures ``<data-dir>/config.json`` exists, writing DEFAULTS if it is absent
     or unparseable,
  3. prints the *effective* config (DEFAULTS deep-merged with the user's file) as
     JSON to stdout.

Config lives in the plugin's own data dir — never in Claude's managed
settings.json. Editing the file takes effect on the next command run.
"""
import json
import os
import sys

DEFAULTS = {
    # Inner review-convergence loop driver for the two review phases.
    "ralphLoop": {
        "enabled": False,  # False -> native loop; True -> ralph-loop plugin
        # per-phase round cap (also --max-iterations when enabled):
        #   spec-phase           = S1 spec review
        #   implementation-phase = S5 work/implementation review
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
    # fallback {id} = "<plugin-name>-<marketplace-name>" = autopilot-claude-autopilot
    # (Claude Code sanitizes non-[A-Za-z0-9_-] to '-')
    data_dir = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser(
        "~/.claude/plugins/data/autopilot-claude-autopilot"
    )
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "config.json")

    effective = DEFAULTS
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                effective = deep_merge(DEFAULTS, json.load(fh))
        except (json.JSONDecodeError, OSError):
            # Leave the (bad) file in place for the user to fix; fall back to
            # defaults for this run rather than overwriting their edits.
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
