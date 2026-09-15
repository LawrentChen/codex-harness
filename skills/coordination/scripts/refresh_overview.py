"""Generate global and project progress views from control task cards."""

from dataclasses import dataclass
from datetime import datetime
import fcntl
import html
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import quote

import yaml

ROOT = Path.home() / "code" / "_control"
MARKER = "<!-- coordination: generated overview -->"
STATES = ("blocked", "doing", "ready", "deferred", "done", "cancelled")
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


@dataclass(frozen=True)
class Card:
    """Metadata required to route and display one independently owned work item."""

    path: Path
    id: str
    title: str
    status: str
    owner: str | None
    repos: tuple[str, ...]
    updated_at: datetime
    next_step: str
    depends_on: tuple[str, ...]
    parent: str | None


def is_card_path(path: Path, root: Path = ROOT) -> bool:
    """Recognize direct task-card paths, including deleted or renamed files."""
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError:
        return False
    parts = relative.parts
    return (
        path.suffix == ".md"
        and ".." not in parts
        and (
            (len(parts) == 2 and parts[0] == "tasks")
            or (
                len(parts) == 4
                and parts[0] == "projects"
                and KEY.fullmatch(parts[1]) is not None
                and parts[2] == "tasks"
            )
        )
    )


def checked_key(value: object, label: str) -> str:
    if not isinstance(value, str) or KEY.fullmatch(value) is None:
        raise ValueError(f"{label} 必须是合法的 ID 或项目键")
    return value


def text_field(metadata: dict, field: str, default: str | None = None) -> str:
    value = metadata.get(field, default)
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是文本")
    return value


def read_card(path: Path, root: Path) -> Card:
    """Read only YAML front matter and validate the metadata boundary."""
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"任务卡必须位于固定账本内且不能是符号链接：{path}")
    with path.open() as stream:
        if stream.readline().strip() != "---":
            raise ValueError(f"任务卡缺少 YAML 头：{path}")
        lines = []
        for line in stream:
            if line.strip() == "---":
                break
            lines.append(line)
        else:
            raise ValueError(f"任务卡 YAML 头未结束：{path}")
    metadata = yaml.safe_load("".join(lines))
    if not isinstance(metadata, dict):
        raise ValueError(f"任务卡 YAML 头必须是对象：{path}")

    card_id = checked_key(metadata.get("id"), "id")
    if card_id != path.stem:
        raise ValueError(f"id 必须与文件名一致：{path}")
    title = text_field(metadata, "title")
    if not title.strip():
        raise ValueError(f"title 不能为空：{path}")
    status = text_field(metadata, "status")
    if status not in STATES:
        raise ValueError(f"未知状态 {status!r}：{path}")
    if "owner" not in metadata:
        raise ValueError(f"任务卡缺少 owner：{path}")
    owner = metadata["owner"]
    if owner is not None and not isinstance(owner, str):
        raise ValueError(f"owner 必须是任务链接、文本或 null：{path}")

    repos = metadata.get("repos")
    if not isinstance(repos, list) or not repos:
        raise ValueError(f"repos 必须是非空项目键列表：{path}")
    repos = tuple(sorted({checked_key(value, "repos") for value in repos}))
    relative = path.relative_to(root)
    if relative.parts[0] == "projects" and relative.parts[1] not in repos:
        raise ValueError(f"repos 必须包含任务卡所在项目：{path}")

    value = metadata.get("updated_at")
    updated_at = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(updated_at, datetime) or updated_at.utcoffset() is None:
        raise ValueError(f"updated_at 必须是带时区的 ISO 时间：{path}")
    dependencies = metadata.get("depends_on", [])
    if not isinstance(dependencies, list):
        raise ValueError(f"depends_on 必须是 ID 列表：{path}")
    dependencies = tuple(checked_key(value, "depends_on") for value in dependencies)
    parent = metadata.get("parent")
    if parent is not None:
        parent = checked_key(parent, "parent")
    return Card(
        path,
        card_id,
        title,
        status,
        owner,
        repos,
        updated_at,
        text_field(metadata, "next_step", ""),
        dependencies,
        parent,
    )


def cell(value: str) -> str:
    """Escape metadata so it remains a single Markdown table cell."""
    text = html.escape(value, quote=False).replace("\\", "\\\\")
    for character in ("|", "[", "]", chr(96), "*", "_"):
        text = text.replace(character, "\\" + character)
    return text.replace("\r", "").replace("\n", "<br>")


def relative_link(path: Path, output: Path) -> str:
    """Build local links without depending on the invoking task's cwd."""
    common = output.parent
    prefix = ""
    while not path.is_relative_to(common):
        common = common.parent
        prefix += "../"
    return quote(prefix + path.relative_to(common).as_posix(), safe="/")


def render(
    cards: list[Card], all_cards: dict[str, Card], output: Path, title: str
) -> str:
    """Render reported progress without inferring readiness or parent completion."""
    active = sorted(
        (card for card in cards if card.status not in ("done", "cancelled")),
        key=lambda card: (STATES.index(card.status), card.id),
    )
    lines = [
        MARKER,
        f"# {title}",
        "",
        "自动生成，请修改任务卡。这里显示各任务最后记录的状态，不代表实时运行或自动验收。",
        "",
        f"活跃 {len(active)} 项；已完成 {sum(c.status == 'done' for c in cards)} 项；"
        f"已取消 {sum(c.status == 'cancelled' for c in cards)} 项。结束项详情保留在原卡。",
        "",
    ]
    if not active:
        lines.append("暂无活跃工作项。")
    else:
        lines.extend(
            [
                "| 工作项 | 状态 | 项目 | 承接任务 | 依赖 | 下一步 | 更新时间 |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for card in active:
            link = f"[{cell(card.id)} · {cell(card.title)}]({relative_link(card.path, output)})"
            owner = cell(card.owner or "未分配")
            if card.owner and re.fullmatch(
                r"codex://threads/[0-9a-fA-F-]+", card.owner
            ):
                owner = f"[打开任务]({card.owner})"
            dependencies = []
            for dependency in card.depends_on:
                target = all_cards.get(dependency)
                dependencies.append(
                    f"[{cell(dependency)}]({relative_link(target.path, output)})"
                    if target
                    else f"{cell(dependency)}（待定位）"
                )
            if card.parent:
                target = all_cards.get(card.parent)
                parent = (
                    f"[{cell(card.parent)}]({relative_link(target.path, output)})"
                    if target
                    else cell(card.parent)
                )
                dependencies.append(f"上级：{parent}")
            values = [
                link,
                card.status,
                cell(", ".join(card.repos)),
                owner,
                "<br>".join(dependencies) or "—",
                cell(card.next_step) or "—",
                card.updated_at.isoformat(timespec="seconds"),
            ]
            lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def write_view(path: Path, content: str, root: Path) -> bool:
    """Atomically replace an owned generated view only when its content changes."""
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"总览输出路径越过固定账本或是符号链接：{path}")
    if path.exists():
        previous = path.read_text()
        if not previous.startswith(MARKER + "\n"):
            raise ValueError(f"拒绝覆盖非生成文件：{path}")
        if previous == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=".overview-", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return True


def refresh(root: Path = ROOT) -> list[Path]:
    """Refresh global and project views under one lock; never initialize an absent root."""
    root = root.absolute()
    if not root.is_dir():
        return []
    lock_path = root / ".overview.lock"
    if lock_path.is_symlink():
        raise ValueError(f"锁文件不能是符号链接：{lock_path}")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        paths = sorted([*root.glob("tasks/*.md"), *root.glob("projects/*/tasks/*.md")])
        cards = [read_card(path, root) for path in paths]
        all_cards = {card.id: card for card in cards}
        if len(all_cards) != len(cards):
            raise ValueError("任务卡存在重复 ID，请保留唯一记录")
        projects = {repo for card in cards for repo in card.repos}
        # Keep views of existing projects accurate after their final card is removed.
        projects.update(
            path.name for path in (root / "projects").glob("*") if path.is_dir()
        )
        projects = sorted(checked_key(project, "项目目录") for project in projects)
        output = root / "OVERVIEW.md"
        content = render(cards, all_cards, output, "总控面 · 全局进度")
        if projects:
            content += "\n## 项目进度\n\n"
            for project in projects:
                target = root / "projects" / project / "OVERVIEW.md"
                content += f"- [{cell(project)}]({relative_link(target, output)})\n"
        views = {output: content}
        for project in projects:
            output = root / "projects" / project / "OVERVIEW.md"
            views[output] = render(
                [card for card in cards if project in card.repos],
                all_cards,
                output,
                f"总控面 · {project}",
            )
        # Validate all destinations before publishing any view.
        for path in views:
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"非法总览路径：{path}")
            if path.exists() and not path.read_text().startswith(MARKER + "\n"):
                raise ValueError(f"拒绝覆盖非生成文件：{path}")
        return [
            path for path, content in views.items() if write_view(path, content, root)
        ]


def main() -> None:
    """Refresh views silently; errors naturally propagate to the caller."""
    refresh()


if __name__ == "__main__":
    main()
