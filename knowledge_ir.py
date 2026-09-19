"""Small, trusted Knowledge IR and deterministic Course View renderer."""
from __future__ import annotations

import copy
import math
from typing import Any


KnowledgeDocument = dict[str, Any]
_KINDS = {"claim", "definition", "procedure", "warning"}
_ITEM_FIELDS = ("id", "source_id", "kind", "title", "body", "evidence_ids")


class KnowledgeValidationError(ValueError):
    """The model output cannot be bound to trusted local evidence."""


def _text(value: Any, label: str, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise KnowledgeValidationError(f"{label} 必须是文本")
    value = value.strip()
    if required and not value:
        raise KnowledgeValidationError(f"{label} 不能为空")
    return value


def _number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise KnowledgeValidationError(f"{label} 必须是有限数字")
    if value < 0:
        raise KnowledgeValidationError(f"{label} 不能为负数")
    return value


def validate_knowledge_document(document: Any) -> None:
    if not isinstance(document, dict):
        raise KnowledgeValidationError("KnowledgeDocument 必须是对象")
    metadata = document.get("document")
    sources = document.get("sources")
    evidence = document.get("evidence")
    items = document.get("items")
    if not isinstance(metadata, dict) or not isinstance(sources, list) or not isinstance(evidence, list) or not isinstance(items, list):
        raise KnowledgeValidationError("KnowledgeDocument 缺少 document、sources、evidence 或 items")
    if not sources or not evidence or not items:
        raise KnowledgeValidationError("KnowledgeDocument 的 sources、evidence、items 不能为空")
    _text(metadata.get("title"), "document.title")

    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise KnowledgeValidationError("source 必须是对象")
        source_id = _text(source.get("source_id"), "source.source_id")
        if source_id in source_ids:
            raise KnowledgeValidationError("source_id 重复")
        source_ids.add(source_id)

    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_counts = {source_id: 0 for source_id in source_ids}
    for entry in evidence:
        if not isinstance(entry, dict):
            raise KnowledgeValidationError("evidence 必须是对象")
        evidence_id = _text(entry.get("id"), "evidence.id")
        source_id = _text(entry.get("source_id"), "evidence.source_id")
        if evidence_id in evidence_by_id:
            raise KnowledgeValidationError("evidence id 重复")
        if source_id not in source_ids:
            raise KnowledgeValidationError("evidence 引用了未知 source_id")
        start = _number(entry.get("start"), "evidence.start")
        end = _number(entry.get("end"), "evidence.end")
        if start > end:
            raise KnowledgeValidationError("evidence 时间范围无效")
        _text(entry.get("text"), "evidence.text")
        evidence_by_id[evidence_id] = entry
        evidence_counts[source_id] += 1
    if any(count == 0 for count in evidence_counts.values()):
        raise KnowledgeValidationError("每个 source 至少需要一条 evidence")

    item_counts = {source_id: 0 for source_id in source_ids}
    item_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise KnowledgeValidationError("knowledge item 必须是对象")
        if any(field not in item for field in _ITEM_FIELDS):
            raise KnowledgeValidationError("knowledge item 缺少必需字段")
        item_id = _text(item.get("id"), "item.id")
        if item_id in item_ids:
            raise KnowledgeValidationError("knowledge item id 重复")
        item_ids.add(item_id)
        source_id = _text(item.get("source_id"), "item.source_id")
        if source_id not in source_ids:
            raise KnowledgeValidationError("knowledge item 引用了未知 source_id")
        if item.get("kind") not in _KINDS:
            raise KnowledgeValidationError("knowledge item.kind 无效")
        _text(item.get("title"), "item.title")
        _text(item.get("body"), "item.body")
        evidence_ids = item.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise KnowledgeValidationError("knowledge item 必须引用非空 evidence_ids")
        for evidence_id in evidence_ids:
            if not isinstance(evidence_id, str) or evidence_id not in evidence_by_id:
                raise KnowledgeValidationError("knowledge item 引用了未知 evidence")
            if evidence_by_id[evidence_id]["source_id"] != source_id:
                raise KnowledgeValidationError("knowledge item 不能跨 source 引用 evidence")
        item_counts[source_id] += 1
    if any(count == 0 for count in item_counts.values()):
        raise KnowledgeValidationError("每个 source 至少需要一个 Knowledge Item")


def build_local_evidence(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create stable evidence from trusted local transcripts."""
    result: list[dict[str, Any]] = []
    for source in sources:
        source_id = _text(source.get("source_id"), "source.source_id")
        transcript = source.get("transcript")
        if not isinstance(transcript, list):
            raise KnowledgeValidationError("source transcript 必须是数组")
        for index, cue in enumerate(transcript):
            if not isinstance(cue, dict):
                raise KnowledgeValidationError("本地 transcript 必须是对象")
            text = _text(cue.get("text"), "transcript.text")
            start = _number(cue.get("start", 0), "transcript.start")
            end = _number(cue.get("end", start), "transcript.end")
            if start > end:
                raise KnowledgeValidationError("transcript 时间范围无效")
            result.append({
                "id": f"evidence:{source_id}:{index}",
                "source_id": source_id,
                "start": start,
                "end": end,
                "text": text,
            })
    return result


def bind_knowledge_document(model_output: Any, sources: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> KnowledgeDocument:
    """Bind model-authored items to caller-owned sources and evidence."""
    if not isinstance(model_output, dict) or not isinstance(model_output.get("document"), dict):
        raise KnowledgeValidationError("模型输出缺少 document")
    metadata = model_output["document"]
    model_items = model_output.get("items")
    if not isinstance(model_items, list):
        raise KnowledgeValidationError("模型输出缺少 items")
    canonical_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(model_items):
        if not isinstance(raw_item, dict):
            raise KnowledgeValidationError("knowledge item 必须是对象")
        source_id = _text(raw_item.get("source_id"), "item.source_id")
        evidence_ids = raw_item.get("evidence_ids")
        if not isinstance(evidence_ids, list):
            raise KnowledgeValidationError("knowledge item.evidence_ids 必须是数组")
        canonical_items.append({
            "id": f"item:{source_id}:{index}",
            "source_id": source_id,
            "kind": copy.deepcopy(raw_item.get("kind")),
            "title": copy.deepcopy(raw_item.get("title")),
            "body": copy.deepcopy(raw_item.get("body")),
            "evidence_ids": copy.deepcopy(evidence_ids),
        })
    bound = {
        "document": {
            "title": _text(metadata.get("title"), "document.title"),
            "description": _text(metadata.get("description", ""), "document.description", required=False),
        },
        "sources": copy.deepcopy(sources),
        "evidence": copy.deepcopy(evidence),
        "items": canonical_items,
    }
    validate_knowledge_document(bound)
    return bound


def build_knowledge_document(source_units: list[dict[str, Any]], model_output: Any) -> KnowledgeDocument:
    """Build trusted sources/evidence, then bind only model-authored items."""
    trusted_sources: list[dict[str, Any]] = []
    for source in source_units:
        if not isinstance(source, dict):
            raise KnowledgeValidationError("source unit 必须是对象")
        trusted_sources.append({key: value for key, value in source.items() if key != "transcript"})
    evidence = build_local_evidence(source_units)
    return bind_knowledge_document(model_output, trusted_sources, evidence)


def render_course_draft(document: KnowledgeDocument) -> dict[str, Any]:
    """Deterministically project the canonical IR into the legacy course view."""
    validate_knowledge_document(document)
    metadata = document["document"]
    sources = document["sources"]
    evidence_by_source: dict[str, list[dict[str, Any]]] = {}
    for entry in document["evidence"]:
        evidence_by_source.setdefault(entry["source_id"], []).append(entry)
    items_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in document["items"]:
        items_by_source.setdefault(item["source_id"], []).append(item)

    lessons: list[dict[str, Any]] = []
    for order, source in enumerate(sources, 1):
        source_id = source["source_id"]
        items = items_by_source[source_id]
        summary = "\n".join(item["body"] for item in items[:3])
        transcript = [
            {"start": entry["start"], "end": entry["end"], "text": entry["text"]}
            for entry in evidence_by_source[source_id]
        ]
        lessons.append({
            "order": order,
            "title": source.get("part") or source.get("title") or source_id,
            "summary": summary,
            "objectives": [item["body"] for item in items if item["kind"] == "procedure"],
            "concepts": [f"{item['title']}：{item['body']}" for item in items if item["kind"] in {"definition", "claim"}],
            "pitfalls": [item["body"] for item in items if item["kind"] == "warning"],
            "transcript": transcript,
            "source_id": source_id,
            "source": source.get("url") or source_id,
        })
    return {
        "course": {
            "title": metadata["title"],
            "description": metadata.get("description", ""),
            "lessons": lessons,
        }
    }
