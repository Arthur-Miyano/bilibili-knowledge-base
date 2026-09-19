"""Offline JSON-to-Obsidian course publisher (Python standard library only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


AUTO_START = "<!-- video-course:auto:start -->"
AUTO_END = "<!-- video-course:auto:end -->"
NOTES_HEADING = "## 我的笔记"
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$', re.IGNORECASE)


class PublishError(Exception):
    """A user-actionable publishing failure."""


def safe_name(value: str, fallback: str = "未命名") -> str:
    value = INVALID.sub("-", str(value)).strip().rstrip(".")
    value = value or fallback
    if RESERVED.fullmatch(value):
        value = f"{value}-"
    return value[:120]


def _inside(root: Path, target: Path) -> Path:
    root = root.resolve()
    target = target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PublishError(f"目标路径超出 Vault: {target}") from exc
    return target


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _yaml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _properties(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {_yaml_value(item)}" for item in value)
        else:
            lines.append(f"{key}: {_yaml_value(value)}")
    return "\n".join(lines) + "\n---\n"


def _auto_block(prefix: str, body: str) -> str:
    body = body.rstrip()
    digest = hashlib.sha256((prefix + body).encode("utf-8")).hexdigest()
    # The hash makes manual edits to the generated region detectable on the next run.
    marker = f"<!-- video-course:auto:sha256={digest} -->"
    return f"{AUTO_START}\n{marker}\n{body}\n{AUTO_END}"


def _extract_auto(text: str) -> tuple[str, str | None] | None:
    start = text.find(AUTO_START)
    end = text.rfind(AUTO_END)
    if start < 0 or end < start:
        return None
    block = text[start : end + len(AUTO_END)]
    match = re.search(r"auto:sha256=([0-9a-f]{64})", block)
    body_start = block.find("\n", block.find("\n") + 1) + 1
    body = block[body_start : block.rfind("\n" + AUTO_END)]
    return body, match.group(1) if match else None


def _merge(path: Path, generated_prefix: str, generated_body: str) -> str:
    generated = _auto_block(generated_prefix, generated_body)
    if not path.exists():
        return generated + f"\n\n{NOTES_HEADING}\n\n"
    old = path.read_text(encoding="utf-8")
    parsed = _extract_auto(old)
    if parsed:
        old_body, expected = parsed
        old_prefix = old[: old.find(AUTO_START)]
        if expected is None:
            raise PublishError(f"自动区哈希标记缺失或损坏，拒绝覆盖: {path}")
        actual = hashlib.sha256((old_prefix + old_body).encode("utf-8")).hexdigest()
        legacy_actual = hashlib.sha256(old_body.encode("utf-8")).hexdigest()
        # New markers authenticate Properties plus body; legacy markers only
        # authenticate body, so their unchanged prefix must match exactly.
        if expected != actual and (expected != legacy_actual or old_prefix != generated_prefix):
            raise PublishError(f"自动区已被修改，拒绝覆盖: {path}")
        suffix = old[old.rfind(AUTO_END) + len(AUTO_END) :]
        return generated_prefix + generated + suffix
    # Existing files without our markers are never overwritten.
    raise PublishError(f"文件缺少自动区标记，拒绝覆盖: {path}")


def _cue_lines(lesson: dict[str, Any]) -> str:
    cues = lesson.get("transcript", lesson.get("cues", []))
    if not cues:
        return "（未提供带时间戳字幕。）\n"
    lines = []
    for cue in cues:
        if not isinstance(cue, dict) or "text" not in cue:
            raise PublishError("transcript 每项必须是包含 text 的对象")
        start = cue.get("start", 0)
        lines.append(f"- [{start}s] {str(cue['text']).strip()}")
    return "\n".join(lines) + "\n"


def _lesson_body(lesson: dict[str, Any], previous: str | None, following: str | None) -> str:
    lines = [f"# {lesson['title']}", "", f"> [!summary] {lesson.get('summary', '暂无摘要。')}", "", "## 学习目标", ""]
    for objective in lesson.get("objectives", []):
        lines.append(f"- {objective}")
    if not lesson.get("objectives"):
        lines.append("- 根据带时间戳材料复习本课内容")
    lines += ["", "## 章节时间轴", "", _cue_lines(lesson).rstrip(), "", "## 核心概念", ""]
    concepts = lesson.get("concepts", [])
    lines.extend(f"- {item}" for item in concepts) or lines.append("- （待整理）")
    lines += ["", "## 易错点与适用边界", ""]
    lines.extend(f"- {item}" for item in lesson.get("pitfalls", [])) or lines.append("- （未提供）")
    lines += ["", "## 原始材料", "", f"来源：{lesson.get('source', '本地材料')}"]
    if previous:
        lines += ["", f"上一课：[[{previous}]]"]
    if following:
        lines += ["", f"下一课：[[{following}]]"]
    return "\n".join(lines) + "\n"


def _overview_body(course: dict[str, Any], lessons: list[dict[str, Any]]) -> str:
    lines = [f"# {course['title']}", "", course.get("description", "本课程由本地材料生成。"), "", "## 课程目录", ""]
    for index, lesson in enumerate(lessons, 1):
        filename = f"{index:02d} - {safe_name(lesson['title'])}"
        lines.append(f"{index}. [[Lessons/{filename}|{lesson['title']}]]")
    lines += ["", "## 学习目标", ""]
    lines.extend(f"- {item}" for item in course.get("objectives", [])) or lines.append("- （待补充）")
    lines += ["", "## 复习清单", "", "- [ ] 完成每课复习", "- [ ] 整理我的笔记"]
    return "\n".join(lines) + "\n"


def publish(vault: str | Path, draft: dict[str, Any]) -> list[Path]:
    root = Path(vault).resolve()
    if not root.exists() or not root.is_dir() or not os.access(root, os.W_OK):
        raise PublishError(f"Vault 必须是可写的已存在目录: {root}")
    if not isinstance(draft, dict) or not isinstance(draft.get("course"), dict):
        raise PublishError("输入必须包含 course 对象")
    course = draft["course"]
    title = str(course.get("title", "")).strip()
    lessons = course.get("lessons", [])
    if not title or not isinstance(lessons, list) or not lessons:
        raise PublishError("course.title 和至少一个 course.lessons 是必需的")
    if "objectives" in course and not isinstance(course["objectives"], list):
        raise PublishError("course.objectives 必须是数组")
    for lesson in lessons:
        if not isinstance(lesson, dict) or not lesson.get("title"):
            raise PublishError("每个 lesson 必须有 title")
        for field in ("objectives", "concepts", "pitfalls", "transcript", "cues"):
            if field in lesson and not isinstance(lesson[field], list):
                raise PublishError(f"lesson.{field} 必须是数组")
    try:
        ordered = sorted(lessons, key=lambda item: item.get("order", 0))
    except TypeError as exc:
        raise PublishError("lesson.order 必须是可比较的值") from exc
    course_dir = _inside(root, root / "Courses" / safe_name(title))
    lesson_dir = _inside(root, course_dir / "Lessons")
    targets: list[tuple[Path, str, str]] = []
    overview = _inside(root, course_dir / "00 - 课程总览.md")
    props = {"type": "course", "course_id": course.get("id", safe_name(title)), "lesson_count": len(ordered)}
    targets.append((overview, _properties(props), _overview_body(course, ordered)))
    names = [f"{i:02d} - {safe_name(item.get('title', f'第{i}课'))}" for i, item in enumerate(ordered, 1)]
    for index, lesson in enumerate(ordered):
        previous = names[index - 1] if index else None
        following = names[index + 1] if index + 1 < len(names) else None
        properties = {"type": "video-lesson", "course": f"[[00 - 课程总览]]", "lesson": index + 1,
                      "source_id": lesson.get("source_id", "local"), "status": "generated"}
        filename = _inside(root, lesson_dir / f"{names[index]}.md")
        targets.append((filename, _properties(properties), _lesson_body(lesson, previous, following)))
    prepared: list[tuple[Path, str]] = []
    for path, prefix, auto_body in targets:
        generated = prefix + _auto_block(prefix, auto_body)
        if path.exists():
            generated = _merge(path, prefix, auto_body)
        prepared.append((path, generated))
    written: list[Path] = []
    for path, generated in prepared:
        _atomic_write(path, generated)
        written.append(path)
    return written


def load_draft(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishError(f"无法读取 JSON: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="离线发布知识库 JSON 到 Obsidian Vault")
    parser.add_argument("draft", help="课程 JSON 文件")
    parser.add_argument("--vault", required=True, help="Obsidian Vault 根目录")
    args = parser.parse_args(argv)
    try:
        for path in publish(args.vault, load_draft(args.draft)):
            print(path)
        return 0
    except (PublishError, OSError) as exc:
        print(f"错误: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
