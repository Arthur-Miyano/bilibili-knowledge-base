import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from course_publisher import AUTO_END, PublishError, publish, safe_name


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        self.draft = json.loads(Path("sample_course.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def test_publish_is_idempotent_and_links_lessons(self):
        first = publish(self.vault, self.draft)
        snapshot = {p: p.read_bytes() for p in first}
        second = publish(self.vault, self.draft)
        self.assertEqual(snapshot, {p: p.read_bytes() for p in second})
        lesson = self.vault / "Courses" / "Python 入门示例" / "Lessons" / "01 - 变量与函数.md"
        text = lesson.read_text(encoding="utf-8")
        self.assertIn("下一课：[[02 - 列表处理]]", text)

    def test_my_notes_survive_and_auto_edit_conflicts(self):
        publish(self.vault, self.draft)
        path = self.vault / "Courses" / "Python 入门示例" / "Lessons" / "01 - 变量与函数.md"
        path.write_text(path.read_text(encoding="utf-8") + "人工补充\n", encoding="utf-8")
        publish(self.vault, self.draft)
        self.assertIn("人工补充", path.read_text(encoding="utf-8"))
        text = path.read_text(encoding="utf-8").replace("变量保存值", "人工改动自动区")
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(PublishError):
            publish(self.vault, self.draft)

    def test_missing_or_corrupt_hash_marker_conflicts(self):
        publish(self.vault, self.draft)
        path = self.vault / "Courses" / "Python 入门示例" / "Lessons" / "01 - 变量与函数.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("<!-- video-course:auto:sha256=", "<!-- video-course:auto:sha256=broken-"), encoding="utf-8")
        with self.assertRaises(PublishError):
            publish(self.vault, self.draft)

        without_marker = "\n".join(line for line in text.splitlines() if "video-course:auto:sha256=" not in line) + "\n"
        path.write_text(without_marker, encoding="utf-8")
        with self.assertRaises(PublishError):
            publish(self.vault, self.draft)

    def test_properties_update_and_manual_edit_conflicts(self):
        publish(self.vault, self.draft)
        path = self.vault / "Courses" / "Python 入门示例" / "Lessons" / "01 - 变量与函数.md"
        changed = deepcopy(self.draft)
        changed["course"]["lessons"][0]["source_id"] = "local:lesson-1-new"
        publish(self.vault, changed)
        self.assertIn('source_id: "local:lesson-1-new"', path.read_text(encoding="utf-8"))

        path.write_text(path.read_text(encoding="utf-8").replace('source_id: "local:lesson-1-new"', 'source_id: "manual"'), encoding="utf-8")
        with self.assertRaises(PublishError):
            publish(self.vault, changed)

    def test_existing_unmarked_file_is_not_overwritten(self):
        path = self.vault / "Courses" / "Python 入门示例" / "Lessons" / "01 - 变量与函数.md"
        path.parent.mkdir(parents=True)
        path.write_text("我的文件", encoding="utf-8")
        with self.assertRaises(PublishError):
            publish(self.vault, self.draft)

    def test_safe_name_avoids_windows_device_names(self):
        for name in ("CON", "prn", "AUX.txt", "COM1"):
            self.assertNotEqual(safe_name(name).lower().rstrip("."), name.lower())

    def test_marker_text_inside_generated_body_does_not_break_republish(self):
        draft = deepcopy(self.draft)
        draft["course"]["lessons"][0]["transcript"] = [{"start": 0, "text": AUTO_END}]
        first = publish(self.vault, draft)
        snapshot = {path: path.read_bytes() for path in first}
        second = publish(self.vault, draft)
        self.assertEqual(snapshot, {path: path.read_bytes() for path in second})

    def test_invalid_lesson_shape_and_order_are_publish_errors(self):
        invalid_shape = deepcopy(self.draft)
        invalid_shape["course"]["lessons"] = ["not a lesson"]
        with self.assertRaises(PublishError):
            publish(self.vault, invalid_shape)

        invalid_order = deepcopy(self.draft)
        invalid_order["course"]["lessons"][0]["order"] = "first"
        with self.assertRaises(PublishError):
            publish(self.vault, invalid_order)

    def test_conflict_does_not_partially_publish(self):
        publish(self.vault, self.draft)
        overview = self.vault / "Courses" / "Python 入门示例" / "00 - 课程总览.md"
        overview_before = overview.read_bytes()
        lesson = self.vault / "Courses" / "Python 入门示例" / "Lessons" / "01 - 变量与函数.md"
        changed = deepcopy(self.draft)
        changed["course"]["description"] = "新的总览内容"
        lesson.write_text(lesson.read_text(encoding="utf-8").replace("变量保存值", "人工改动自动区"), encoding="utf-8")

        with self.assertRaises(PublishError):
            publish(self.vault, changed)

        self.assertEqual(overview_before, overview.read_bytes())
        self.assertNotIn("新的总览内容", overview.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
