import http.client
import json
import os
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import web_app


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.server = web_app.LocalWebServer(("127.0.0.1", 0), web_app.WebRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, response.getheader("Content-Type", ""), data

    def test_status_api_does_not_expose_keys(self):
        old_groq = os.environ.pop("GROQ_API_KEY", None)
        old_gemini = os.environ.pop("GEMINI_API_KEY", None)
        old_cookie = os.environ.get("BILIBILI_COOKIE")
        os.environ["BILIBILI_COOKIE"] = "SESSDATA=status-secret"
        try:
            with patch.object(web_app.shutil, "which", return_value=None), patch.object(web_app.importlib.util, "find_spec", return_value=None):
                status, content_type, body = self.request("GET", "/api/status")
        finally:
            if old_groq is not None:
                os.environ["GROQ_API_KEY"] = old_groq
            if old_gemini is not None:
                os.environ["GEMINI_API_KEY"] = old_gemini
            if old_cookie is None:
                os.environ.pop("BILIBILI_COOKIE", None)
            else:
                os.environ["BILIBILI_COOKIE"] = old_cookie
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertFalse(payload["statuses"]["groq"]["ready"])
        self.assertIn("bilibili_api", payload["statuses"])
        self.assertIn('pip install -e ".[bilibili]"', payload["statuses"]["bilibili_api"]["label"])
        self.assertNotIn("GROQ_API_KEY", body.decode())
        self.assertNotIn("GEMINI_API_KEY", body.decode())
        self.assertNotIn("status-secret", body.decode())

    def test_static_and_json_responses_include_browser_security_headers(self):
        for path in ("/", "/api/status"):
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
            connection.request("GET", path)
            response = connection.getresponse()
            response.read()
            connection.close()
            self.assertEqual(response.status, 200)
            self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
            self.assertIn("img-src 'self' data:", response.getheader("Content-Security-Policy"))
            self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
            self.assertIn("form-action 'self'", response.getheader("Content-Security-Policy"))
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertEqual(response.getheader("Referrer-Policy"), "no-referrer")
            self.assertEqual(response.getheader("X-Frame-Options"), "DENY")

    def test_status_handles_broken_adapter_spec(self):
        with patch.object(web_app.importlib.util, "find_spec", side_effect=ValueError("broken spec")):
            payload = web_app.status_payload()
        self.assertFalse(payload["statuses"]["bilibili_api"]["ready"])
        self.assertIn('pip install -e ".[bilibili]"', payload["statuses"]["bilibili_api"]["label"])

    def test_bilibili_provider_error_remains_actionable_in_web_response(self):
        message = web_app._safe_public_error(web_app.CloudError("B站风控/HTTP 412，请显式配置 BILIBILI_COOKIE 后重试"))
        self.assertIn("B站风控/HTTP 412", message)
        self.assertIn("BILIBILI_COOKIE", message)

    def test_missing_known_environment_key_remains_actionable_without_echoing_value(self):
        for name in ("GROQ_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"):
            with self.subTest(name=name):
                message = web_app._safe_public_error(
                    web_app.CloudError(f"缺少环境变量 {name}，请配置 API Key")
                )
                self.assertEqual(message, f"缺少环境变量 {name}，请配置对应 API Key。")
                self.assertNotIn("secret", message.lower())

    def test_publish_http_preserves_missing_provider_env_error(self):
        body = json.dumps({
            "source": "BV1abcXYZ",
            "vault": "C:/vault",
            "text_provider": "gemini",
            "text_model": "gemini-3.5-flash-lite",
            "gemini_api_key": "fake-secret-value",
        }).encode()
        with patch.object(
            web_app,
            "make_draft",
            side_effect=web_app.CloudError("缺少环境变量 GEMINI_API_KEY，请配置 API Key"),
        ):
            status, _, response_body = self.request(
                "POST", "/api/publish", body,
                {"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
        error = json.loads(response_body)["error"]
        self.assertEqual(status, 422)
        self.assertIn("GEMINI_API_KEY", error)
        self.assertNotIn("fake-secret-value", error)

    def test_publish_uses_memory_qr_credential(self):
        memory_credential = object()
        with patch.object(web_app.bilibili_qr_login, "credential", return_value=memory_credential), \
                patch.object(web_app, "BilibiliSource") as source, \
                patch.object(web_app, "GroqTranscriber"), \
                patch.object(web_app, "GeminiDraftGenerator"), \
                patch.object(web_app, "make_draft", return_value={"course": {}}), \
                patch.object(web_app, "publish", return_value=[]):
            web_app.publish_request({"source": "BV1abcXYZ", "vault": "C:/vault", "gemini_api_key": "key"})
        source.assert_called_once_with(cookie=None, credential=memory_credential)

    def test_bilibili_qr_login_state_machine_and_http_endpoints(self):
        events = SimpleNamespace(SCAN="scan", CONF="confirm", TIMEOUT="timeout", DONE="done")
        memory_credential = SimpleNamespace(
            sessdata="sessdata-secret", bili_jct="csrf-secret", ac_time_value="refresh-secret"
        )

        class FakeLogin:
            def __init__(self):
                self.states = iter((events.SCAN, events.CONF, events.DONE))

            async def generate_qrcode(self):
                return None

            def get_qrcode_picture(self):
                return SimpleNamespace(content=b"fake-png")

            async def check_state(self):
                return next(self.states)

            def get_credential(self):
                return memory_credential

        manager = web_app.BilibiliQrLoginManager()
        with patch.object(web_app, "_load_qr_login", return_value=(FakeLogin, events)):
            started = manager.start()
            self.assertTrue(started["qr_code"].startswith("data:image/png;base64,"))
            self.assertEqual(manager.check()["status"], "confirm")
            self.assertEqual(manager.check()["status"], "confirm")
            self.assertEqual(manager.check()["status"], "logged_in")
            self.assertIs(manager.credential(), memory_credential)
            self.assertEqual(manager.logout()["status"], "logged_out")
            self.assertIsNone(manager.credential())

        with patch.object(web_app, "_load_qr_login", return_value=(FakeLogin, events)), \
                patch.object(web_app, "bilibili_qr_login", manager):
            status, _, body = self.request("POST", "/api/bilibili/login/start")
            self.assertEqual(status, 200)
            self.assertIn("qr_code", json.loads(body))
            self.assertNotIn("sessdata-secret", body.decode())
            status, _, body = self.request("GET", "/api/bilibili/login/check")
            self.assertEqual(status, 200)
            self.assertIn("status", json.loads(body))
            status, _, _ = self.request(
                "GET", "/api/bilibili/login/check", headers={"Origin": "http://evil.example"}
            )
            self.assertEqual(status, 403)
            status, _, body = self.request("POST", "/api/bilibili/login/logout")
            self.assertEqual(status, 200)
            self.assertNotIn("SESSDATA", body.decode())
            self.assertNotIn("csrf-secret", body.decode())
            self.assertNotIn("refresh_token", body.decode())

    def test_invalid_input_is_rejected_before_pipeline(self):
        body = json.dumps({"source": "not-a-bilibili-video", "vault": "C:/vault"}).encode()
        with patch.object(web_app, "make_draft") as make_draft:
            status, _, response_body = self.request(
                "POST", "/api/publish", body,
                {"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
        self.assertEqual(status, 400)
        self.assertIn("B站链接无效", json.loads(response_body)["error"])
        make_draft.assert_not_called()

    def test_host_header_rejects_dns_rebinding(self):
        status, _, _ = self.request("GET", "/api/status", headers={"Host": "evil.example"})
        self.assertEqual(status, 421)

    def test_cross_origin_publish_is_rejected(self):
        body = json.dumps({"source": "BV1abcXYZ", "vault": "C:/vault"}).encode()
        with patch.object(web_app, "make_draft") as make_draft:
            status, _, _ = self.request(
                "POST", "/api/publish", body,
                {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Origin": "http://evil.example",
                },
            )
        self.assertEqual(status, 403)
        make_draft.assert_not_called()

    def test_non_loopback_server_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "回环"):
            web_app.run_server("0.0.0.0", 0, open_browser=False)

    def test_success_calls_existing_pipeline_and_returns_files(self):
        body = json.dumps({
            "source": "BV1abcXYZ",
            "vault": "C:/vault",
            "gemini_model": "gemini-custom-1",
            "groq_model": "whisper-custom-1",
            "gemini_api_key": "gemini-secret",
            "groq_api_key": "groq-secret",
            "bilibili_cookie": "SESSDATA=explicit",
        }).encode()
        generated = {"course": {"title": "T", "lessons": [{"title": "L"}]}}
        output = [Path("C:/vault/Courses/T/00 - 课程总览.md")]
        with patch.object(web_app, "BilibiliSource") as source, patch.object(web_app, "GroqTranscriber") as groq, patch.object(web_app, "GeminiDraftGenerator") as gemini, patch.object(web_app, "make_draft", return_value=generated) as make_draft, patch.object(web_app, "publish", return_value=output) as publish:
            status, _, response_body = self.request(
                "POST", "/api/publish", body,
                {"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(response_body)["files"], [str(output[0])])
        source.assert_called_once_with(cookie="SESSDATA=explicit")
        groq.assert_called_once_with(api_key="groq-secret", model="whisper-custom-1")
        gemini.assert_called_once_with(api_key="gemini-secret", model="gemini-custom-1")
        make_draft.assert_called_once_with(source.return_value, groq.return_value, gemini.return_value, "BV1abcXYZ")
        publish.assert_called_once_with("C:/vault", generated)

    def test_empty_settings_fall_back_to_defaults_and_environment(self):
        with patch.object(web_app, "BilibiliSource") as source, patch.object(web_app, "GroqTranscriber") as groq, patch.object(web_app, "GeminiDraftGenerator") as gemini, patch.object(web_app, "make_draft", return_value={"course": {}}), patch.object(web_app, "publish", return_value=[]):
            web_app.publish_request({"source": "BV1abcXYZ", "vault": "C:/vault", "gemini_model": "", "groq_model": "", "gemini_api_key": "", "groq_api_key": "", "bilibili_cookie": ""})
        source.assert_called_once_with(cookie=None)
        groq.assert_called_once_with(api_key=None, model=web_app.DEFAULT_GROQ_MODEL)
        gemini.assert_called_once_with(api_key=None, model=web_app.DEFAULT_GEMINI_MODEL)

    def test_deepseek_selection_uses_selected_model_and_key(self):
        payload = {
            "source": "BV1abcXYZ", "vault": "C:/vault", "text_provider": "deepseek",
            "text_model": "deepseek-v4-pro", "deepseek_api_key": "deepseek-secret",
            "groq_model": "", "groq_api_key": "", "bilibili_cookie": "",
        }
        with patch.object(web_app, "BilibiliSource") as source, patch.object(web_app, "GroqTranscriber") as groq, patch.object(web_app, "OpenAIChatDraftGenerator") as generator, patch.object(web_app, "make_draft", return_value={"course": {}}) as make_draft, patch.object(web_app, "publish", return_value=[]):
            web_app.publish_request(payload)
        generator.assert_called_once_with(
            api_key="deepseek-secret", model="deepseek-v4-pro",
            base_url="https://api.deepseek.com", env_name="DEEPSEEK_API_KEY", service="DeepSeek",
        )
        make_draft.assert_called_once_with(source.return_value, groq.return_value, generator.return_value, "BV1abcXYZ")

    def test_model_and_secret_limits_are_rejected_before_pipeline(self):
        with patch.object(web_app, "make_draft") as make_draft:
            with self.assertRaisesRegex(ValueError, "模型 ID"):
                web_app.publish_request({"source": "BV1abcXYZ", "vault": "C:/vault", "gemini_model": "bad model"})
            with self.assertRaisesRegex(ValueError, "长度或内容无效"):
                web_app.publish_request({"source": "BV1abcXYZ", "vault": "C:/vault", "groq_api_key": "x" * (web_app.MAX_SECRET_LENGTH + 1)})
        make_draft.assert_not_called()

    def test_static_paths_cannot_traverse_outside_web_directory(self):
        status, _, _ = self.request("GET", "/%2e%2e/web_app.py")
        self.assertEqual(status, 404)
        status, _, _ = self.request("GET", "/web_app.py")
        self.assertEqual(status, 404)
        status, content_type, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("B站知识库", body.decode("utf-8"))

    def test_static_form_descriptions_and_copy_action_are_available(self):
        status, _, body = self.request("GET", "/")
        html = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn('aria-describedby="source-hint source-error"', html)
        self.assertIn('aria-describedby="vault-hint vault-error"', html)
        self.assertIn('id="copy-files-button"', html)
        self.assertIn("复制文件路径", html)
        self.assertIn('role="status"', html)
        self.assertIn('aria-busy="false"', html)
        self.assertIn('role="tablist"', html)
        self.assertIn('data-view-target="settings"', html)
        for name in ("text_provider", "text_model", "groq_model", "gemini_api_key", "deepseek_api_key", "kimi_api_key", "groq_api_key", "bilibili_cookie"):
            self.assertIn(f'name="{name}"', html)
        for name in ("bilibili-login-start", "bilibili-login-logout", "bilibili-qr-code", "bilibili-login-status"):
            self.assertIn(f'id="{name}"', html)
        self.assertIn("B站官方扫码登录", html)
        self.assertIn("aria-live=\"polite\"", html)
        self.assertGreaterEqual(html.count('type="password"'), 5)
        self.assertIn('autocomplete="off"', html)
        self.assertNotIn("localStorage", html)
        self.assertNotIn("sessionStorage", html)
        self.assertNotIn("document.cookie", html)
        self.assertNotIn("发布器", html)
        for field_id in ("text-provider", "text-model", "groq-model", "gemini-api-key", "deepseek-api-key", "kimi-api-key", "groq-api-key", "bilibili-cookie"):
            self.assertIn(f'id="{field_id}" name=', html)
            self.assertIn('form="publish-form"', html[html.index(f'id="{field_id}"'):html.index(f'id="{field_id}"') + 280])

    def test_publish_script_clears_credentials_after_request(self):
        script = (web_app.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("const clearCredentials = () =>", script)
        self.assertIn('input.value = "";', script)
        self.assertRegex(script, r"finally \{\s*clearCredentials\(\);")
        self.assertIn('state.textContent = "使用环境变量";', script)

    def test_only_vault_path_is_persisted_in_browser_storage(self):
        script = (web_app.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        storage_lines = [line for line in script.splitlines() if "localStorage" in line]
        self.assertGreaterEqual(len(storage_lines), 3)
        self.assertTrue(all("vault" in line.lower() or "VAULT_STORAGE_KEY" in line for line in storage_lines))
        for name in ("sourceInput", "providerKeyInputs", "groqKeyInput", "bilibiliCookieInput"):
            self.assertFalse(any(name in line for line in storage_lines))
        self.assertIn('vaultInput.addEventListener("change"', script)

        html = (web_app.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("仅保存在当前浏览器", html)

    def test_publish_script_checks_selected_provider_credentials(self):
        script = (web_app.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("providerStatuses", script)
        self.assertIn("当前未检测到", script)
        self.assertIn("请填写本次 Key，或配置环境变量后重试", script)

    def test_publish_script_uses_qr_login_endpoints_without_browser_credentials(self):
        script = (web_app.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/bilibili/login/start", script)
        self.assertIn("/api/bilibili/login/check", script)
        self.assertIn("/api/bilibili/login/logout", script)
        self.assertIn('bilibiliQrCode.removeAttribute("src")', script)
        self.assertIn('checkQrLogin();', script)
        self.assertNotIn("document.cookie", script)
        self.assertNotIn("localStorage.setItem(\"bilibili-cookie\"", script)

    def test_deepseek_default_model_uses_current_id(self):
        self.assertEqual(web_app.DEFAULT_DEEPSEEK_MODEL, "deepseek-v4-flash")
        script = (web_app.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('"deepseek-v4-flash"', script)
        self.assertNotIn('"deepseek-flash"', script)

    def test_mobile_status_rows_give_description_and_value_full_width(self):
        css = (web_app.STATIC_ROOT / "styles.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: 248px minmax(0, 1fr)", css)
        self.assertIn(".status-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));", css)
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn("@media (max-width: 700px)", css)
        self.assertIn(".field-grid, .settings-grid, .credential-grid, .status-list { grid-template-columns: minmax(0, 1fr); }", css)


if __name__ == "__main__":
    unittest.main()
