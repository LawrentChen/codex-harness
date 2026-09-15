"""Behavioral tests using synthetic cards in private temporary directories."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import yaml

import refresh_overview as overview

HOOK_PATH = Path(__file__).resolve().parents[4] / "hooks/coordination_after_edit.py"
hook_spec = importlib.util.spec_from_file_location("coordination_after_edit", HOOK_PATH)
hook = importlib.util.module_from_spec(hook_spec)
hook_spec.loader.exec_module(hook)


class OverviewTests(unittest.TestCase):
    """Exercise routing, update behavior, error reporting and concurrent refresh."""

    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="coordination-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "control with spaces"
        self.root.mkdir()

    def card(self, card_id="field", location=None, **overrides):
        metadata = {
            "id": card_id,
            "title": "统一字段",
            "status": "doing",
            "owner": "codex://threads/01234567-89ab-cdef-0123-456789abcdef",
            "repos": ["alpha", "beta"],
            "updated_at": "2026-09-15T14:30:00+08:00",
            "next_step": "核对消费端",
            "depends_on": [],
        }
        metadata.update(overrides)
        path = self.root / (location or f"tasks/{card_id}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
            + "---\n\n## 接手摘要\n正文保持原样。\n"
        )
        return path

    def event(self, command, cwd=None, **overrides):
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "cwd": str(cwd or self.root),
            "tool_input": {"command": command},
        }
        payload.update(overrides)
        return payload

    def test_cross_project_card_is_in_global_and_both_project_views(self):
        path = self.card(location="projects/alpha/tasks/field.md")
        before = path.read_bytes()
        changed = overview.refresh(self.root)
        self.assertEqual(len(changed), 3)
        for project in ("alpha", "beta"):
            text = (self.root / "projects" / project / "OVERVIEW.md").read_text()
            self.assertIn("统一字段", text)
            self.assertIn("打开任务", text)
        beta = (self.root / "projects/beta/OVERVIEW.md").read_text()
        self.assertIn("../alpha/tasks/field.md", beta)
        self.assertEqual(path.read_bytes(), before)

    def test_ordinary_edits_do_not_read_or_initialize_ledger(self):
        missing = self.root / "absent"
        events = [
            self.event("*** Update File: /home/project/app.py"),
            self.event("*** Update File: docs/TODO.md\n+使用 _control"),
            self.event("*** Update File: OVERVIEW.md"),
            self.event("*** Update File: CURRENT.md"),
            self.event("*** Update File: /somewhere/_control/tasks/x.md"),
            self.event("*** Update File: tasks/x.md", tool_name="Bash"),
        ]
        with patch.object(hook, "refresh") as refresh:
            for event in events:
                hook.handle(event, missing)
            refresh.assert_not_called()
        self.assertFalse(missing.exists())

    def test_card_patch_triggers_real_refresh_and_is_silent(self):
        self.card()
        with redirect_stdout(io.StringIO()) as output:
            hook.handle(self.event("*** Update File: tasks/field.md"), self.root)
        self.assertEqual(output.getvalue(), "")
        self.assertTrue((self.root / "OVERVIEW.md").is_file())
        self.assertIn("统一字段", (self.root / "OVERVIEW.md").read_text())

    def test_absolute_patch_from_other_repository(self):
        path = self.card()
        event = self.event(
            f"*** Add File: {path}", cwd=Path("/home/unrelated-repository")
        )
        hook.handle(event, self.root)
        self.assertTrue((self.root / "OVERVIEW.md").is_file())

    def test_delete_and_move_are_recognized(self):
        path = self.card()
        overview.refresh(self.root)
        path.unlink()
        hook.handle(self.event("*** Delete File: tasks/field.md"), self.root)
        self.assertIn("活跃 0 项", (self.root / "OVERVIEW.md").read_text())
        self.assertIn(
            "活跃 0 项", (self.root / "projects/alpha/OVERVIEW.md").read_text()
        )
        self.card()
        event = self.event("*** Update File: incoming.md\n*** Move to: tasks/field.md")
        hook.handle(event, self.root)
        self.assertIn("活跃 1 项", (self.root / "OVERVIEW.md").read_text())

    def test_repeated_refresh_does_not_rewrite_unchanged_views(self):
        self.card()
        first = overview.refresh(self.root)
        timestamps = {path: path.stat().st_mtime_ns for path in first}
        self.assertEqual(overview.refresh(self.root), [])
        self.assertEqual(timestamps, {path: path.stat().st_mtime_ns for path in first})

    def test_invalid_card_preserves_previous_views(self):
        self.card()
        paths = overview.refresh(self.root)
        previous = {path: path.read_bytes() for path in paths}
        self.card("invalid", updated_at="2026-09-15")
        with self.assertRaisesRegex(ValueError, "时区"):
            overview.refresh(self.root)
        self.assertEqual(previous, {path: path.read_bytes() for path in paths})

    def test_duplicate_id_is_rejected(self):
        self.card()
        self.card(location="projects/alpha/tasks/field.md")
        with self.assertRaisesRegex(ValueError, "重复 ID"):
            overview.refresh(self.root)
        self.assertFalse((self.root / "OVERVIEW.md").exists())

    def test_parent_completion_is_not_inferred(self):
        parent = self.card("parent")
        self.card("child", status="done", parent="parent")
        overview.refresh(self.root)
        text = (self.root / "OVERVIEW.md").read_text()
        self.assertIn("活跃 1 项；已完成 1 项", text)
        self.assertIn("| doing |", text)
        self.assertEqual(overview.read_card(parent, self.root).status, "doing")

    def test_unowned_view_and_symlink_are_not_overwritten(self):
        self.card()
        existing = self.root / "projects/alpha/OVERVIEW.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("自然人用户的文档")
        with self.assertRaisesRegex(ValueError, "非生成文件"):
            overview.refresh(self.root)
        self.assertFalse((self.root / "OVERVIEW.md").exists())
        self.assertEqual(existing.read_text(), "自然人用户的文档")
        existing.unlink()
        external = Path(self.temporary.name) / "external.md"
        external.write_text("保留")
        existing.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "非法总览路径"):
            overview.refresh(self.root)
        self.assertEqual(external.read_text(), "保留")

    def test_metadata_is_escaped_and_dependencies_are_linked(self):
        self.card("parent", status="done")
        self.card(title="a|b <tag>\n第二行", depends_on=["parent", "missing"])
        overview.refresh(self.root)
        text = (self.root / "OVERVIEW.md").read_text()
        self.assertIn(r"a\|b &lt;tag&gt;<br>第二行", text)
        self.assertIn("[parent](tasks/parent.md)", text)
        self.assertIn("missing（待定位）", text)

    def test_parallel_refreshes_leave_complete_views(self):
        for index in range(12):
            self.card(f"task-{index}")
        scripts = Path(overview.__file__).parent
        command = [
            sys.executable,
            "-B",
            "-c",
            f"from pathlib import Path; from refresh_overview import refresh; refresh(Path({str(self.root)!r}))",
        ]

        def run():
            subprocess.run(command, cwd=scripts, check=True, capture_output=True)

        with ThreadPoolExecutor(max_workers=6) as executor:
            list(executor.map(lambda _: run(), range(6)))
        for path in [
            self.root / "OVERVIEW.md",
            self.root / "projects/alpha/OVERVIEW.md",
            self.root / "projects/beta/OVERVIEW.md",
        ]:
            text = path.read_text()
            self.assertIn("活跃 12 项", text)
            for index in range(12):
                self.assertIn(f"task-{index}", text)
        self.assertEqual(list(self.root.rglob(".overview-*")), [])
        self.assertEqual(overview.refresh(self.root), [])

    def test_hook_error_reports_stale_view_without_blocking_edit(self):
        with (
            patch.object(hook.sys, "stdin", io.StringIO("{}")),
            patch.object(hook, "handle", side_effect=ValueError("bad metadata")),
            redirect_stdout(io.StringIO()) as output,
        ):
            hook.main()
        result = json.loads(output.getvalue())
        self.assertIn("可能未更新", result["systemMessage"])
        self.assertNotIn("continue", result)
        self.assertNotIn("decision", result)

    def test_absent_root_is_not_initialized_by_refresh(self):
        missing = self.root / "absent"
        self.assertEqual(overview.refresh(missing), [])
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
