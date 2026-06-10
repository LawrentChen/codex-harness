"""Format Python files changed by a Codex apply_patch tool call."""

import json
import subprocess
import sys
from pathlib import Path


CONDA = Path("/opt/miniconda3/bin/conda")
PATCH_PATH_PREFIXES = (
    "*** Add File: ",
    "*** Update File: ",
    "*** Move to: ",
)


def extract_python_paths(patch: str, cwd: Path) -> list[Path]:
    """Return existing Python files referenced by an apply_patch command."""
    paths: set[Path] = set()

    for line in patch.splitlines():
        for prefix in PATCH_PATH_PREFIXES:
            if not line.startswith(prefix):
                continue

            raw_path = line.removeprefix(prefix)
            path = Path(raw_path)
            if not path.is_absolute():
                path = cwd / path

            path = path.resolve()
            if path.suffix == ".py" and path.is_file():
                paths.add(path)
            break

    return sorted(paths)


def main() -> None:
    """Read hook input and format Python files changed by the patch."""
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})
    patch = tool_input.get("command", "")
    cwd = Path(payload["cwd"]).resolve()
    paths = extract_python_paths(patch, cwd)

    if not paths:
        return

    command = [
        str(CONDA),
        "run",
        "-n",
        "base",
        "black",
        "--",
        *(str(path) for path in paths),
    ]
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return

    details = (result.stderr or result.stdout).strip()
    message = f"Black hook failed: {details}"
    print(
        json.dumps(
            {
                "continue": False,
                "stopReason": message,
                "systemMessage": message,
            }
        )
    )


if __name__ == "__main__":
    main()
