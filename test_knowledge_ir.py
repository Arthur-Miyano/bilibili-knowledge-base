import math
import unittest

from knowledge_ir import KnowledgeValidationError, build_knowledge_document, render_course_draft


def source_units():
    return [
        {"source_id": "bilibili:BV1:1", "bvid": "BV1", "page": 1, "title": "第一课", "part": "一", "url": "https://www.bilibili.com/video/BV1?p=1", "transcript": [{"start": 1.0, "end": 3.0, "text": "定义变量。"}]},
        {"source_id": "bilibili:BV1:2", "bvid": "BV1", "page": 2, "title": "第二课", "part": "二", "url": "https://www.bilibili.com/video/BV1?p=2", "transcript": [{"start": 4.0, "end": 8.0, "text": "注意边界。"}]},
    ]


def model_output(evidence_id="evidence:bilibili:BV1:1:0"):
    return {"document": {"title": "可信课程", "description": "从证据生成"}, "items": [
        {"id": "model-controlled", "source_id": "bilibili:BV1:1", "kind": "definition", "title": "变量", "body": "变量保存值。", "evidence_ids": [evidence_id]},
        {"source_id": "bilibili:BV1:2", "kind": "warning", "title": "边界", "body": "输入需要检查。", "evidence_ids": ["evidence:bilibili:BV1:2:0"]},
    ]}


class KnowledgeIRTests(unittest.TestCase):
    def test_unknown_and_cross_source_evidence_are_rejected(self):
        for evidence_id in ("missing", "evidence:bilibili:BV1:2:0"):
            with self.subTest(evidence_id=evidence_id), self.assertRaises(KnowledgeValidationError):
                build_knowledge_document(source_units(), model_output(evidence_id))

    def test_empty_evidence_ids_are_rejected(self):
        output = model_output()
        output["items"][0]["evidence_ids"] = []
        with self.assertRaises(KnowledgeValidationError):
            build_knowledge_document(source_units(), output)

    def test_each_source_needs_evidence_and_item(self):
        units = source_units()
        units[1]["transcript"] = []
        with self.assertRaises(KnowledgeValidationError):
            build_knowledge_document(units, model_output())
        output = model_output()
        output["items"] = [output["items"][0]]
        with self.assertRaises(KnowledgeValidationError):
            build_knowledge_document(source_units(), output)

    def test_model_item_id_and_extra_fields_are_not_canonical(self):
        output = model_output()
        output["items"][0]["id"] = "model-controlled"
        output["items"][0]["extra"] = {"secret": "discard"}
        output["items"][0]["evidence_ids"].append("evidence:bilibili:BV1:1:0")
        document = build_knowledge_document(source_units(), output)
        item = document["items"][0]
        self.assertEqual(item["id"], "item:bilibili:BV1:1:0")
        self.assertEqual(set(item), {"id", "source_id", "kind", "title", "body", "evidence_ids"})
        output["items"][0]["evidence_ids"].clear()
        self.assertTrue(document["items"][0]["evidence_ids"])

    def test_model_cannot_replace_trusted_evidence_or_timestamps(self):
        output = model_output()
        output["sources"] = [{"source_id": "fake"}]
        output["evidence"] = [{"id": "evidence:bilibili:BV1:1:0", "source_id": "bilibili:BV1:1", "start": 999, "end": 1000, "text": "伪造原文"}]
        document = build_knowledge_document(source_units(), output)
        self.assertEqual(document["sources"][0]["source_id"], "bilibili:BV1:1")
        self.assertEqual(document["evidence"][0]["start"], 1.0)
        self.assertEqual(document["evidence"][0]["text"], "定义变量。")

    def test_invalid_timestamps_are_rejected(self):
        for start, end in ((-1, 0), (math.nan, 1), (0, math.inf), (3, 2)):
            units = source_units()
            units[0]["transcript"][0].update(start=start, end=end)
            with self.subTest(start=start, end=end), self.assertRaises(KnowledgeValidationError):
                build_knowledge_document(units, model_output())

    def test_renderer_maps_items_limits_summary_and_preserves_order(self):
        output = model_output()
        output["items"].extend([
            {"source_id": "bilibili:BV1:1", "kind": "procedure", "title": "操作", "body": "先运行。", "evidence_ids": ["evidence:bilibili:BV1:1:0"]},
            {"source_id": "bilibili:BV1:1", "kind": "claim", "title": "结论", "body": "结果稳定。", "evidence_ids": ["evidence:bilibili:BV1:1:0"]},
            {"source_id": "bilibili:BV1:1", "kind": "warning", "title": "警告", "body": "第三条。", "evidence_ids": ["evidence:bilibili:BV1:1:0"]},
            {"source_id": "bilibili:BV1:1", "kind": "claim", "title": "忽略", "body": "第四条。", "evidence_ids": ["evidence:bilibili:BV1:1:0"]},
        ])
        draft = render_course_draft(build_knowledge_document(source_units(), output))
        lessons = draft["course"]["lessons"]
        self.assertEqual([lesson["source_id"] for lesson in lessons], ["bilibili:BV1:1", "bilibili:BV1:2"])
        self.assertEqual(lessons[0]["summary"], "变量保存值。\n先运行。\n结果稳定。")
        self.assertEqual(lessons[0]["objectives"], ["先运行。"])
        self.assertEqual(lessons[0]["concepts"], ["变量：变量保存值。", "结论：结果稳定。", "忽略：第四条。"])
        self.assertEqual(lessons[0]["pitfalls"], ["第三条。"])
        self.assertEqual(lessons[0]["transcript"], [{"start": 1.0, "end": 3.0, "text": "定义变量。"}])
        self.assertEqual(lessons[0]["source"], "https://www.bilibili.com/video/BV1?p=1")


if __name__ == "__main__":
    unittest.main()
