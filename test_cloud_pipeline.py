import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from pathlib import Path

from cloud_pipeline import (
    BilibiliSource, CloudError, GeminiDraftGenerator, GroqTranscriber,
    OpenAIChatDraftGenerator, make_draft, parse_bilibili_id, validate_course_draft,
)


class Source(BilibiliSource):
    def _subtitle(self, cid, bvid=""):
        return []


class CloudTests(unittest.TestCase):
    def test_parse_bv_and_url(self):
        self.assertEqual(parse_bilibili_id("BV1abcXYZ"), "BV1abcXYZ")
        self.assertEqual(parse_bilibili_id("https://www.bilibili.com/video/BV1abcXYZ?p=2"), "BV1abcXYZ")
        self.assertEqual(parse_bilibili_id("bilibili.com/video/bv1abcXYZ/"), "BV1abcXYZ")
        with self.assertRaises(CloudError):
            parse_bilibili_id("not a video")
        with self.assertRaises(CloudError):
            parse_bilibili_id("https://example.com/bilibili.com/video/BV1abcXYZ")

    def test_bilibili_multi_page_and_subtitle(self):
        def transport(url, method, headers, body):
            if "/view?" in url:
                return {"code": 0, "data": {"title": "课", "pages": [{"cid": 1, "page": 1, "part": "一"}, {"cid": 2, "page": 2, "part": "二"}]}}
            if "/player/v2?" in url:
                return {"code": 0, "data": {"subtitle": {"subtitle": [{"subtitle_url": "https://sub"}]}}}
            return {"body": [{"from": 1.5, "content": "字幕"}]}
        lessons = BilibiliSource(transport).lessons("BV1abcXYZ")
        self.assertEqual(len(lessons), 2)
        self.assertEqual(lessons[0]["subtitle"][0]["text"], "字幕")

    def test_bilibili_library_contract_supports_multi_page_and_subtitle_priority(self):
        cloud = __import__("cloud_pipeline")
        calls = {"credential": [], "subtitle": [], "audio": [], "subtitle_urls": []}

        class Credential:
            def __init__(self, **kwargs):
                calls["credential"].append(kwargs)

        class Video:
            def __init__(self, bvid, credential):
                self.bvid = bvid
                self.credential = credential

            async def get_info(self):
                return {"title": "库课程"}

            async def get_pages(self):
                return [{"cid": 101, "page": 1, "part": "一"}, {"cid": 202, "page": 2, "part": "二"}]

            async def get_subtitle(self, cid):
                calls["subtitle"].append(cid)
                return {"subtitles": [{"subtitle_url": f"https://subtitle/{cid}"}]} if cid == 101 else {}

            async def get_download_url(self, page_index):
                calls["audio"].append(page_index)
                return {"dash": {"audio": [{"base_url": f"https://audio/{page_index}"}]}}

        def subtitle_transport(url, method, headers, body, service):
            calls["subtitle_urls"].append((url, headers))
            return {"body": [{"from": 1.5, "to": 2.5, "content": "字幕"}]}

        old_cookie = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=secret; bili_jct=csrf; buvid3=b3; buvid4=b4; DedeUserID=uid; ac_time_value=refresh"
        try:
            with patch.object(cloud, "_load_bilibili_api", return_value=(SimpleNamespace(Video=Video), Credential)), \
                    patch.object(cloud, "_default_transport", side_effect=subtitle_transport):
                lessons = BilibiliSource().lessons("BV1abcXYZ")
        finally:
            if old_cookie is None:
                os.environ.pop("BILIBILI_COOKIE", None)
            else:
                os.environ["BILIBILI_COOKIE"] = old_cookie
        self.assertEqual([item["page"]["page"] for item in lessons], [1, 2])
        self.assertEqual(lessons[0]["subtitle"][0]["text"], "字幕")
        self.assertIsNone(lessons[0]["audio_url"])
        self.assertEqual(lessons[1]["audio_url"], "https://audio/1")
        self.assertEqual(calls["subtitle"], [101, 202])
        self.assertEqual(calls["audio"], [1])
        self.assertEqual(calls["credential"], [{"sessdata": "secret", "bili_jct": "csrf", "buvid3": "b3", "buvid4": "b4", "dedeuserid": "uid", "ac_time_value": "refresh"}])
        self.assertNotIn("Cookie", calls["subtitle_urls"][0][1])

    def test_bilibili_library_without_cookie_uses_empty_credential(self):
        cloud = __import__("cloud_pipeline")
        calls = []

        class Credential:
            def __init__(self, **kwargs):
                calls.append(kwargs)

        class Video:
            def __init__(self, bvid, credential):
                self.credential = credential

            async def get_info(self):
                return {"title": "T"}

            async def get_pages(self):
                return [{"cid": 1, "page": 1, "part": "一"}]

            async def get_subtitle(self, cid):
                return {}

            async def get_download_url(self, page_index):
                return {"durl": [{"url": "https://audio/one"}]}

        old_cookie = os.environ.pop("BILIBILI_COOKIE", None)
        try:
            with patch.object(cloud, "_load_bilibili_api", return_value=(SimpleNamespace(Video=Video), Credential)):
                lessons = BilibiliSource().lessons("BV1abcXYZ")
        finally:
            if old_cookie is not None:
                os.environ["BILIBILI_COOKIE"] = old_cookie
        self.assertEqual(calls, [{}])
        self.assertEqual(lessons[0]["audio_url"], "https://audio/one")

    def test_bilibili_library_maps_request_cookie_to_credential(self):
        cloud = __import__("cloud_pipeline")
        calls = []

        class Credential:
            def __init__(self, **kwargs):
                calls.append(kwargs)

        class Video:
            def __init__(self, bvid, credential):
                pass

            async def get_info(self):
                return {"title": "T"}

            async def get_pages(self):
                return [{"cid": 1, "page": 1, "part": "一"}]

            async def get_subtitle(self, cid):
                return {"body": [{"from": 0, "content": "字幕"}]}

        old_cookie = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=environment"
        try:
            with patch.object(cloud, "_load_bilibili_api", return_value=(SimpleNamespace(Video=Video), Credential)):
                BilibiliSource(cookie="SESSDATA=request; bili_jct=csrf").lessons("BV1abcXYZ")
        finally:
            if old_cookie is None: os.environ.pop("BILIBILI_COOKIE", None)
            else: os.environ["BILIBILI_COOKIE"] = old_cookie
        self.assertEqual(calls, [{"sessdata": "request", "bili_jct": "csrf", "buvid3": "", "buvid4": ""}])

    def test_bilibili_memory_credential_precedes_environment_and_cookie_overrides_it(self):
        cloud = __import__("cloud_pipeline")
        memory_credential = object()
        calls = []

        class Credential:
            def __init__(self, **kwargs):
                calls.append(kwargs)

        class Video:
            def __init__(self, bvid, credential):
                calls.append(credential)

            async def get_info(self):
                return {"title": "T"}

            async def get_pages(self):
                return [{"cid": 1, "page": 1, "part": "一"}]

            async def get_subtitle(self, cid):
                return {"body": [{"from": 0, "content": "字幕"}]}

        old_cookie = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=environment"
        try:
            with patch.object(cloud, "_load_bilibili_api", return_value=(SimpleNamespace(Video=Video), Credential)):
                BilibiliSource(credential=memory_credential).lessons("BV1abcXYZ")
                BilibiliSource(cookie="SESSDATA=request", credential=memory_credential).lessons("BV1abcXYZ")
        finally:
            if old_cookie is None:
                os.environ.pop("BILIBILI_COOKIE", None)
            else:
                os.environ["BILIBILI_COOKIE"] = old_cookie
        self.assertIs(calls[0], memory_credential)
        self.assertEqual(calls[1], {"sessdata": "request", "bili_jct": "", "buvid3": "", "buvid4": ""})

    def test_bilibili_library_missing_is_actionable(self):
        cloud = __import__("cloud_pipeline")
        with patch.object(cloud, "_load_bilibili_api", side_effect=ImportError("missing")):
            with self.assertRaises(CloudError) as error:
                BilibiliSource().lessons("BV1abcXYZ")
        self.assertIn('pip install -e ".[bilibili]"', str(error.exception))

    def test_bilibili_library_412_is_safe(self):
        cloud = __import__("cloud_pipeline")

        class Video:
            def __init__(self, **kwargs):
                pass

            async def get_info(self):
                error = RuntimeError("response body SESSDATA=secret")
                error.code = 412
                raise error

        with patch.object(cloud, "_load_bilibili_api", return_value=(SimpleNamespace(Video=Video), lambda **kwargs: object())):
            with self.assertRaisesRegex(CloudError, "412") as error:
                BilibiliSource().lessons("BV1abcXYZ")
        self.assertNotIn("SESSDATA", str(error.exception))

    def test_bilibili_library_errors_are_specific_and_safe(self):
        cloud = __import__("cloud_pipeline")

        class LibraryError(Exception):
            def __init__(self, code):
                super().__init__("response body API_KEY=secret SESSDATA=secret")
                self.code = code

        for code, expected in ((401, "需要登录"), (403, "需要登录"), (429, "限流"), (500, "暂时不可用")):
            with self.subTest(code=code):
                class Video:
                    def __init__(self, **kwargs):
                        pass

                    async def get_info(self):
                        raise LibraryError(code)

                with patch.object(cloud, "_load_bilibili_api", return_value=(SimpleNamespace(Video=Video), lambda **kwargs: object())):
                    with self.assertRaisesRegex(CloudError, expected) as error:
                        BilibiliSource().lessons("BV1abcXYZ")
                self.assertNotIn("API_KEY", str(error.exception))
                self.assertNotIn("SESSDATA", str(error.exception))

        class TimeoutVideo:
            def __init__(self, **kwargs):
                pass

            async def get_info(self):
                raise TimeoutError("secret timeout response")

        with patch.object(cloud, "_load_bilibili_api", return_value=(SimpleNamespace(Video=TimeoutVideo), lambda **kwargs: object())):
            with self.assertRaisesRegex(CloudError, "超时") as error:
                BilibiliSource().lessons("BV1abcXYZ")
        self.assertNotIn("secret timeout response", str(error.exception))

    def test_bilibili_audio_url_is_per_page(self):
        def transport(url, method, headers, body):
            if "/view?" in url:
                return {"code": 0, "data": {"title": "课", "pages": [{"cid": 1, "page": 1, "part": "一"}, {"cid": 2, "page": 2, "part": "二"}]}}
            if "/playurl?" in url:
                return {"code": 0, "data": {"dash": {"audio": [{"baseUrl": "https://audio/" + ("one" if "cid=1" in url else "two")} ]}}}
            return {"code": 0, "data": {"subtitle": {"subtitle": []}}}
        lessons = BilibiliSource(transport).lessons("BV1abcXYZ")
        self.assertEqual([item["audio_url"] for item in lessons], ["https://audio/one", "https://audio/two"])

    def test_multi_page_downloads_each_audio_url(self):
        seen = []
        source = BilibiliSource(download_transport=lambda url, headers: seen.append(url) or b"audio")
        with tempfile.TemporaryDirectory() as directory:
            source.download_audio("https://audio/one", Path(directory) / "one")
            source.download_audio("https://audio/two", Path(directory) / "two")
        self.assertEqual(seen, ["https://audio/one", "https://audio/two"])

    def test_make_draft_transcribes_each_subtitleless_page_audio_url(self):
        cloud = __import__("cloud_pipeline")
        seen = []
        class NoSubPages(Source):
            def lessons(self, value):
                return [
                    {"bvid": "BV1", "title": "T", "page": {"page": 1, "part": "一"}, "subtitle": [], "audio_url": "https://audio/one"},
                    {"bvid": "BV1", "title": "T", "page": {"page": 2, "part": "二"}, "subtitle": [], "audio_url": "https://audio/two"},
                ]
        def prepare(source, transcriber, audio_source, workdir, stem):
            seen.append(audio_source)
            return [{"start": 0, "text": stem}]
        class Generator:
            def generate(self, title, lessons):
                return {"course": {"title": title, "lessons": [{"title": item["title"], "summary": "S", "objectives": [], "concepts": [], "pitfalls": [], "source_id": item["source_id"]} for item in lessons]}}
        with patch.object(cloud, "_prepare_and_transcribe", side_effect=prepare):
            draft = cloud.make_draft(NoSubPages(), object(), Generator(), "BV1")
        self.assertEqual(seen, ["https://audio/one", "https://audio/two"])
        self.assertEqual(len(draft["course"]["lessons"]), 2)

    def test_groq_multipart_contract_and_limit(self):
        seen = {}
        def transport(url, method, headers, body):
            seen.update(url=url, method=method, headers=headers, body=body)
            return {"segments": [{"start": 1, "end": 2, "text": " hello "}]}
        file = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False)
        try:
            file.write(b"audio")
            file.close()
            result = GroqTranscriber(api_key="secret", transport=transport).transcribe(file.name)
        finally:
            os.unlink(file.name)
        self.assertEqual(result[0]["text"], "hello")
        self.assertIn(b"name=\"file\"", seen["body"])
        self.assertIn(b"timestamp_granularities[]", seen["body"])

    def test_groq_malformed_timestamps_are_safe_cloud_errors(self):
        file = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False)
        try:
            file.write(b"audio")
            file.close()
            transcriber = GroqTranscriber(api_key="secret", transport=lambda *args: {"segments": [{"start": "bad", "text": "x"}]})
            with self.assertRaises(CloudError):
                transcriber.transcribe(file.name)
        finally:
            os.unlink(file.name)

    def test_gemini_schema_and_validation(self):
        seen = {}
        def transport(url, method, headers, body):
            seen["url"] = url
            seen["headers"] = headers
            seen["body"] = json.loads(body)
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({"course": {"title": "T", "lessons": [{"order": 99, "title": "L", "summary": "S", "objectives": [], "concepts": [], "pitfalls": [], "source_id": "x"}]}})}]}}]}
        draft = GeminiDraftGenerator(api_key="secret", transport=transport).generate("T", [{"title": "L", "transcript": [], "source_id": "x"}])
        self.assertEqual(draft["course"]["title"], "T")
        self.assertEqual(seen["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertNotIn("order", seen["body"]["generationConfig"]["responseSchema"]["properties"]["course"]["properties"]["lessons"]["items"]["required"])
        self.assertNotIn("key=", seen.get("url", ""))
        self.assertEqual(seen["headers"].get("x-goog-api-key"), "secret")
        with self.assertRaises(CloudError):
            validate_course_draft({"course": {"title": "", "lessons": []}})

    def test_openai_compatible_generator_contract(self):
        seen = {}
        def transport(url, method, headers, body):
            seen.update(url=url, method=method, headers=headers, body=json.loads(body))
            content = {"course": {"title": "T", "lessons": [{"title": "L", "summary": "S", "objectives": [], "concepts": [], "pitfalls": [], "source_id": "x"}]}}
            return {"choices": [{"message": {"content": json.dumps(content)}}]}
        generator = OpenAIChatDraftGenerator(
            api_key="secret", model="deepseek-flash", base_url="https://api.deepseek.com",
            env_name="DEEPSEEK_API_KEY", service="DeepSeek", transport=transport,
        )
        draft = generator.generate("T", [{"title": "L", "transcript": [], "source_id": "x"}])
        self.assertEqual(draft["course"]["title"], "T")
        self.assertEqual(seen["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(seen["body"]["response_format"], {"type": "json_object"})
        self.assertIn("source_id", seen["body"]["messages"][1]["content"])

    def test_missing_key_and_no_subtitle(self):
        old = os.environ.pop("GROQ_API_KEY", None)
        try:
            GroqTranscriber()
        finally:
            if old is not None:
                os.environ["GROQ_API_KEY"] = old
        class NoSub(Source):
            def lessons(self, value):
                return [{"bvid": "BV1", "title": "T", "page": {"page": 1, "part": "L"}, "subtitle": [], "audio_url": "https://audio"}]
        with self.assertRaisesRegex(CloudError, "GROQ_API_KEY"):
            make_draft(NoSub(), GroqTranscriber(transport=lambda *args: {}), object(), "BV1")

    def test_end_to_end_mock_publish(self):
        class GoodSource(Source):
            def lessons(self, value):
                return [{"bvid": "BV1", "title": "T", "page": {"page": 1, "part": "L"}, "subtitle": [{"start": 0, "text": "x"}]}]
        class Generator:
            def generate(self, title, lessons):
                return {"course": {"title": title, "lessons": lessons}}
        with tempfile.TemporaryDirectory() as directory:
            paths = __import__("course_publisher").publish(directory, make_draft(GoodSource(), object(), Generator(), "BV1"))
            self.assertTrue(paths)

    def test_cdn_download_headers_never_include_cookie(self):
        seen = {}
        old = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=secret"
        try:
            source = BilibiliSource(download_transport=lambda url, headers: seen.update(url=url, headers=headers) or b"x")
            with tempfile.TemporaryDirectory() as directory:
                source.download_audio("https://upos-sz-mirrorali.bilivideo.com/audio", Path(directory) / "a.m4s")
        finally:
            if old is None: os.environ.pop("BILIBILI_COOKIE", None)
            else: os.environ["BILIBILI_COOKIE"] = old
        self.assertEqual(seen["headers"]["User-Agent"], "Mozilla/5.0")
        self.assertEqual(seen["headers"]["Referer"], "https://www.bilibili.com/")
        self.assertNotIn("Cookie", seen["headers"])

    def test_api_transport_receives_explicit_cookie(self):
        seen = {}
        old = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=secret"
        try:
            source = BilibiliSource(transport=lambda url, method, headers, body: seen.update(headers=headers) or {"code": 0, "data": {}})
            source._get("/x/web-interface/view", bvid="BV1abcXYZ")
        finally:
            if old is None: os.environ.pop("BILIBILI_COOKIE", None)
            else: os.environ["BILIBILI_COOKIE"] = old
        self.assertEqual(seen["headers"]["Cookie"], "SESSDATA=secret")

    def test_api_transport_prefers_per_request_cookie_without_environment_mutation(self):
        seen = {}
        old = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=environment"
        try:
            source = BilibiliSource(
                cookie="SESSDATA=request",
                transport=lambda url, method, headers, body: seen.update(headers=headers) or {"code": 0, "data": {}},
            )
            source._get("/x/web-interface/view", bvid="BV1abcXYZ")
        finally:
            if old is None: os.environ.pop("BILIBILI_COOKIE", None)
            else: os.environ["BILIBILI_COOKIE"] = old
        self.assertEqual(seen["headers"]["Cookie"], "SESSDATA=request")

    def test_third_party_audio_url_never_receives_cookie(self):
        seen = {}
        old = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=secret"
        try:
            source = BilibiliSource(download_transport=lambda url, headers: seen.update(headers) or b"x")
            with tempfile.TemporaryDirectory() as directory:
                source.download_audio("https://evil.example/audio", Path(directory) / "a.m4s")
        finally:
            if old is None: os.environ.pop("BILIBILI_COOKIE", None)
            else: os.environ["BILIBILI_COOKIE"] = old
        self.assertNotIn("Cookie", seen)

    def test_default_download_streams_chunks_to_disk(self):
        cloud = __import__("cloud_pipeline")

        class Response:
            headers = {"Content-Length": "6"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1):
                self.size = size
                if not hasattr(self, "chunks"):
                    self.chunks = [b"abc", b"def", b""]
                return self.chunks.pop(0)

        response = Response()
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen", return_value=response):
            destination = Path(directory) / "audio.bin"
            cloud._default_download("https://upos-sz-mirrorali.bilivideo.com/audio", {}, destination)
            self.assertEqual(destination.read_bytes(), b"abcdef")
        self.assertEqual(response.size, 256 * 1024)

    def test_multipart_filename_strips_header_breakout_characters(self):
        cloud = __import__("cloud_pipeline")
        filename = cloud._multipart_filename('bad\"\r\n\\name.m4a')
        self.assertNotRegex(filename, r'[\r\n"\\]')

    def test_default_transports_classify_errors_without_body(self):
        cases = [(401, "认证/权限"), (403, "认证/权限"), (429, "配额/限流")]
        for status, expected in cases:
            with self.subTest(status=status), patch("urllib.request.urlopen", side_effect=HTTPError("https://x", status, "API_KEY=leak", {}, None)):
                with self.assertRaisesRegex(CloudError, expected) as error:
                    __import__("cloud_pipeline")._default_transport("https://x", "GET", {}, None)
                self.assertNotIn("API_KEY", str(error.exception))
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen", side_effect=URLError("secret body")):
            with self.assertRaisesRegex(CloudError, "网络错误"):
                __import__("cloud_pipeline")._default_download("https://x", {}, Path(directory) / "audio")
        with patch("urllib.request.urlopen", side_effect=HTTPError("https://x", 412, "risk", {}, None)):
            with self.assertRaisesRegex(CloudError, "B站风控"):
                __import__("cloud_pipeline")._default_transport("https://x", "GET", {}, None, service="B站请求失败")

    def test_redirect_handler_rejects_cross_origin_credentials(self):
        cloud = __import__("cloud_pipeline")
        handler = cloud._SameOriginRedirectHandler()
        for header, value in (("Authorization", "Bearer secret"), ("x-goog-api-key", "secret"), ("Cookie", "SESSDATA=secret")):
            with self.subTest(header=header):
                request = cloud.urllib.request.Request("https://api.example.test/v1", headers={header: value})
                with self.assertRaises(HTTPError) as error:
                    handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example.test/collect")
                self.assertNotIn("secret", str(error.exception))

        request = cloud.urllib.request.Request("https://api.example.test/v1", headers={"Authorization": "Bearer secret"})
        with self.assertRaises(HTTPError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://api.example.test/v2")

        request = cloud.urllib.request.Request("http://api.example.test/v1", headers={"Authorization": "Bearer secret"})
        with self.assertRaises(HTTPError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://api.example.test/v2")

        request = cloud.urllib.request.Request("https://api.example.test/v1")
        redirected = handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example.test/collect")
        self.assertEqual(redirected.full_url, "https://evil.example.test/collect")

        request = cloud.urllib.request.Request("https://api.example.test/v1", headers={"Authorization": "Bearer secret"})
        redirected = handler.redirect_request(request, None, 302, "Found", {}, "https://api.example.test/v2")
        self.assertEqual(redirected.get_header("Authorization"), "Bearer secret")

    def test_injected_bilibili_transport_errors_are_service_specific(self):
        source = BilibiliSource(transport=lambda *args: (_ for _ in ()).throw(HTTPError(
            "https://api.bilibili.com", 412, "secret response", {}, None)))
        with self.assertRaisesRegex(CloudError, "B站风控") as error:
            source.lessons("BV1abcXYZ")
        self.assertNotIn("secret response", str(error.exception))

        source = BilibiliSource(transport=lambda *args: (_ for _ in ()).throw(URLError("secret response")))
        with self.assertRaisesRegex(CloudError, "B站请求失败：网络错误") as error:
            source.lessons("BV1abcXYZ")
        self.assertNotIn("secret response", str(error.exception))

    def test_injected_groq_and_gemini_transport_errors_are_service_specific(self):
        file = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False)
        try:
            file.write(b"audio")
            file.close()
            transcriber = GroqTranscriber(
                api_key="secret",
                transport=lambda *args: (_ for _ in ()).throw(HTTPError(
                    "https://api.groq.com", 429, "secret response", {}, None)),
            )
            with self.assertRaisesRegex(CloudError, "Groq 请求失败：配额/限流") as error:
                transcriber.transcribe(file.name)
            self.assertNotIn("secret response", str(error.exception))
        finally:
            os.unlink(file.name)

        generator = GeminiDraftGenerator(
            api_key="secret",
            transport=lambda *args: (_ for _ in ()).throw(URLError("secret response")),
        )
        with self.assertRaisesRegex(CloudError, "Gemini 请求失败：网络错误") as error:
            generator.generate("T", [{"title": "L", "transcript": [], "source_id": "x"}])
        self.assertNotIn("secret response", str(error.exception))

    def test_ffmpeg_required_and_prepare_command(self):
        cloud = __import__("cloud_pipeline")
        with patch.object(cloud.shutil, "which", return_value=None):
            with self.assertRaisesRegex(CloudError, "FFmpeg"):
                cloud._ffmpeg_prepare(Path("in"), Path("out"))
        with patch.object(cloud.shutil, "which", return_value="ffmpeg"), patch.object(cloud.subprocess, "run") as run:
            cloud._ffmpeg_prepare(Path("in"), Path("out"))
        self.assertEqual(run.call_args.args[0][:6], ["ffmpeg", "-y", "-i", "in", "-ac", "1"])
        self.assertIn("out", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["timeout"], cloud.FFMPEG_TIMEOUT_SECONDS)

    def test_oversize_segments_use_600_second_offsets(self):
        cloud = __import__("cloud_pipeline")
        with tempfile.TemporaryDirectory() as directory:
            workdir, path = Path(directory), Path(directory) / "normalized.m4a"
            files = [workdir / "segment-000.m4a", workdir / "segment-001.m4a"]
            with patch.object(cloud.Path, "stat", return_value=SimpleNamespace(st_size=cloud.MAX_AUDIO_BYTES + 1)), patch.object(cloud.subprocess, "run") as run, patch.object(Path, "glob", return_value=files):
                result = cloud._segments(path, workdir)
        self.assertEqual(result, [(files[0], 0), (files[1], 600)])
        self.assertIn("600", run.call_args.args[0])

    def test_make_draft_cleans_temporary_directory(self):
        cloud = __import__("cloud_pipeline")
        workdirs = []
        class NoSub(Source):
            def lessons(self, value):
                return [{"bvid": "BV1", "title": "T", "page": {"page": 1, "part": "L"}, "subtitle": [], "audio_url": "https://audio"}]
        class Generator:
            def generate(self, title, lessons): return {"course": {"title": title, "lessons": [{"title": "L", "summary": "S", "objectives": [], "concepts": [], "pitfalls": [], "source_id": lessons[0]["source_id"]}]}}
        def fake_prepare(source, transcriber, audio_source, workdir, stem):
            workdirs.append(workdir)
            return [{"start": 0, "text": "x"}]
        with patch.object(cloud, "_prepare_and_transcribe", side_effect=fake_prepare):
            cloud.make_draft(NoSub(), object(), Generator(), "BV1")
        self.assertTrue(workdirs)
        self.assertFalse(workdirs[0].exists())

    def test_make_draft_cleans_temporary_directory_on_failure(self):
        cloud = __import__("cloud_pipeline")
        workdirs = []
        class NoSub(Source):
            def lessons(self, value):
                return [{"bvid": "BV1", "title": "T", "page": {"page": 1, "part": "L"}, "subtitle": [], "audio_url": "https://audio"}]
        def fail_prepare(source, transcriber, audio_source, workdir, stem):
            workdirs.append(workdir)
            raise CloudError("boom")
        with patch.object(cloud, "_prepare_and_transcribe", side_effect=fail_prepare):
            with self.assertRaises(CloudError): cloud.make_draft(NoSub(), object(), object(), "BV1")
        self.assertFalse(workdirs[0].exists())

    def test_merge_rejects_ids_and_restores_source_order_and_evidence(self):
        cloud = __import__("cloud_pipeline")
        sources = [{"source_id": "a", "transcript": [{"text": "A"}]}, {"source_id": "b", "transcript": [{"text": "B"}]}]
        draft = {"course": {"title": "T", "lessons": [{"source_id": "b", "order": 88, "title": "B", "summary": "", "objectives": [], "concepts": [], "pitfalls": []}, {"source_id": "a", "order": -1, "title": "A", "summary": "", "objectives": [], "concepts": [], "pitfalls": []}]}}
        result = cloud.merge_transcripts(draft, sources)
        self.assertEqual([x["source_id"] for x in result["course"]["lessons"]], ["a", "b"])
        self.assertEqual([x["order"] for x in result["course"]["lessons"]], [1, 2])
        self.assertEqual(result["course"]["lessons"][0]["transcript"], sources[0]["transcript"])
        for ids in (("a", "a"), ("a", "x"), ("a", None)):
            broken = {"course": {"title": "T", "lessons": [{"source_id": sid, "title": "L", "summary": "", "objectives": [], "concepts": [], "pitfalls": []} for sid in ids]}}
            with self.assertRaises(CloudError): cloud.merge_transcripts(broken, sources)

    def test_merge_rejects_non_string_source_id_without_type_error(self):
        cloud = __import__("cloud_pipeline")
        sources = [{"source_id": "a", "transcript": []}]
        broken = {"course": {"title": "T", "lessons": [{"source_id": ["a"], "title": "L", "summary": "", "objectives": [], "concepts": [], "pitfalls": []}]}}
        with self.assertRaises(CloudError):
            cloud.merge_transcripts(broken, sources)

    def test_validate_course_draft_rejects_wrong_field_types(self):
        with self.assertRaises(CloudError):
            validate_course_draft({"course": {"title": "T", "lessons": [{
                "order": 1, "title": "L", "summary": "S", "objectives": "not-list",
                "concepts": [], "pitfalls": [], "transcript": [], "source_id": "a",
            }]}})


if __name__ == "__main__":
    unittest.main()
