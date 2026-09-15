"""Refresh progress after apply_patch changes a task card; ignore ordinary edits."""

import json
from pathlib import Path
import runpy
import sys

import yaml

# Load the skill helper by absolute path so the hook works from any repository.
OVERVIEW_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills/coordination/scripts/refresh_overview.py"
)
overview = runpy.run_path(str(OVERVIEW_SCRIPT))
ROOT = overview["ROOT"]
is_card_path = overview["is_card_path"]
refresh = overview["refresh"]

PATH_PREFIXES = (
    "*** Add File: ",
    "*** Update File: ",
    "*** Delete File: ",
    "*** Move to: ",
)


def handle(payload: dict, root: Path = ROOT) -> None:
    """Use the actual patch paths, without reading prompts or other conversations."""
    if payload.get("hook_event_name") != "PostToolUse":
        return
    if payload.get("tool_name") not in ("apply_patch", "Edit", "Write"):
        return
    tool_input = payload.get("tool_input", {})
    patch = tool_input if isinstance(tool_input, str) else tool_input.get("command", "")
    if not isinstance(patch, str):
        return
    cwd = Path(payload["cwd"])
    for line in patch.splitlines():
        for prefix in PATH_PREFIXES:
            if line.startswith(prefix):
                path = Path(line.removeprefix(prefix))
                if not path.is_absolute():
                    path = cwd / path
                if is_card_path(path, root):
                    refresh(root)
                    return
                break


def main() -> None:
    """Consume hook JSON; report rendering failure without blocking the completed edit."""
    try:
        handle(json.load(sys.stdin))
    except (OSError, ValueError, yaml.YAMLError) as error:
        message = f"总控面汇总失败，进度总览可能未更新：{error}"
        print(
            json.dumps(
                {
                    "systemMessage": message,
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": message,
                    },
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
