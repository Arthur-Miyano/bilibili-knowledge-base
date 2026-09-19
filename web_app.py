"""Local, standard-library web entry point for B站知识库."""

from __future__ import annotations

import argparse
import asyncio
import base64
import importlib
import importlib.util
import json
import logging
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from cloud_pipeline import (
    BilibiliSource,
    CloudError,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_KIMI_MODEL,
    GeminiDraftGenerator,
    GroqTranscriber,
    OpenAIChatDraftGenerator,
    _close_bilibili_client,
    make_draft,
    parse_bilibili_id,
)
from course_publisher import PublishError, publish


HOST = "127.0.0.1"
PORT = 8877
MAX_JSON_BYTES = 24 * 1024
MAX_SOURCE_LENGTH = 2048
MAX_VAULT_LENGTH = 4096
MAX_MODEL_LENGTH = 128
MAX_SECRET_LENGTH = 8192
QR_SESSION_TTL_SECONDS = 180
QR_OPERATION_TIMEOUT_SECONDS = 10
QR_STOP_JOIN_SECONDS = 2
MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
MISSING_ENV_RE = re.compile(
    r"^缺少环境变量\s+(GROQ_API_KEY|GEMINI_API_KEY|DEEPSEEK_API_KEY|MOONSHOT_API_KEY)(?:[，,:].*)?$"
)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
STATIC_ROOT = Path(__file__).resolve().parent / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
TEXT_PROVIDERS = {
    "gemini": {"default_model": DEFAULT_GEMINI_MODEL, "env": "GEMINI_API_KEY"},
    "deepseek": {
        "default_model": DEFAULT_DEEPSEEK_MODEL,
        "env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "service": "DeepSeek",
    },
    "kimi": {
        "default_model": DEFAULT_KIMI_MODEL,
        "env": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.ai/v1",
        "service": "Kimi",
    },
}


def _load_qr_login() -> tuple[Any, Any]:
    try:
        module = importlib.import_module("bilibili_api.login_v2")
        return module.QrCodeLogin, module.QrCodeLoginEvents
    except (ImportError, ModuleNotFoundError):
        raise CloudError('缺少 B站扫码登录适配器：请运行 `pip install -e ".[bilibili]"`') from None


class _QrWorkerResult:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


class _BilibiliQrWorker:
    """Keep one QrCodeLogin and one asyncio loop together until stopped."""

    def __init__(self, login_type: Any, events_type: Any):
        self._login_type = login_type
        self._events_type = events_type
        self._commands: queue.Queue[tuple[str | None, _QrWorkerResult | None]] = queue.Queue()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._init_error: BaseException | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._current_task: asyncio.Task[Any] | None = None
        self._thread = threading.Thread(target=self._run, name="bilibili-qr-login", daemon=True)
        self._thread.start()
        if not self._ready.wait(QR_OPERATION_TIMEOUT_SECONDS):
            self.stop()
            raise CloudError("B站扫码登录初始化超时，请重试")
        if self._init_error is not None:
            error = self._init_error
            self.stop()
            if isinstance(error, CloudError):
                raise error
            raise CloudError("B站扫码登录初始化失败，请重试") from None

    async def _generate(self) -> bytes:
        await asyncio.wait_for(self._login.generate_qrcode(), QR_OPERATION_TIMEOUT_SECONDS)
        picture = self._login.get_qrcode_picture()
        content = getattr(picture, "content", b"")
        if not isinstance(content, (bytes, bytearray)) or not content:
            raise CloudError("B站二维码生成失败，请重试")
        return bytes(content)

    async def _check(self) -> tuple[Any, Any | None]:
        event = await asyncio.wait_for(self._login.check_state(), QR_OPERATION_TIMEOUT_SECONDS)
        if event == self._events_type.DONE:
            return event, self._login.get_credential()
        return event, None

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._login = self._login_type()
            self._ready.set()
            while not self._stop.is_set():
                try:
                    command, result = self._commands.get(timeout=0.25)
                except queue.Empty:
                    continue
                if command is None or result is None:
                    break
                try:
                    if command == "generate":
                        try:
                            self._current_task = loop.create_task(self._generate())
                            result.value = loop.run_until_complete(self._current_task)
                        finally:
                            self._current_task = None
                            for filename in ("qrcode.png", "test.png"):
                                try:
                                    (Path(tempfile.gettempdir()) / filename).unlink(missing_ok=True)
                                except OSError:
                                    pass
                    elif command == "check":
                        self._current_task = loop.create_task(self._check())
                        try:
                            result.value = loop.run_until_complete(self._current_task)
                        finally:
                            self._current_task = None
                    else:
                        raise CloudError("B站扫码登录操作无效")
                except BaseException as exc:
                    result.error = exc
                finally:
                    result.done.set()
        except BaseException as exc:
            self._init_error = exc
            self._ready.set()
        finally:
            try:
                loop.run_until_complete(_close_bilibili_client())
            except Exception:
                pass
            loop.close()

    def call(self, command: str) -> Any:
        if not self._thread.is_alive() or self._stop.is_set():
            raise CloudError("B站扫码登录会话已停止，请重新开始")
        result = _QrWorkerResult()
        self._commands.put((command, result))
        if not result.done.wait(QR_OPERATION_TIMEOUT_SECONDS + 1):
            raise CloudError("B站扫码登录请求超时，请重试")
        if result.error is not None:
            raise result.error
        return result.value

    def stop(self) -> None:
        if not self._thread.is_alive():
            return
        self._stop.set()
        if self._loop is not None and self._current_task is not None:
            try:
                self._loop.call_soon_threadsafe(self._current_task.cancel)
            except RuntimeError:
                pass
        self._commands.put((None, None))
        self._thread.join(QR_STOP_JOIN_SECONDS)


class BilibiliQrLoginManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._worker: _BilibiliQrWorker | None = None
        self._events_type: Any = None
        self._credential: Any = None
        self._started_at = 0.0
        self._status = "idle"
        self._message = "尚未开始扫码登录。"

    def _snapshot_locked(self) -> dict[str, str]:
        return {"status": self._status, "message": self._message}

    def _stop_locked(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._worker = None
        self._events_type = None

    def _fail_locked(self, message: str) -> dict[str, str]:
        self._stop_locked()
        self._credential = None
        self._status = "failed"
        self._message = message
        return self._snapshot_locked()

    def start(self) -> dict[str, str]:
        login_type, events_type = _load_qr_login()
        with self._lock:
            self._stop_locked()
            self._credential = None
            worker = _BilibiliQrWorker(login_type, events_type)
            try:
                content = worker.call("generate")
            except TimeoutError:
                worker.stop()
                self._status = "failed"
                self._message = "B站二维码生成超时，请重试。"
                raise CloudError(self._message) from None
            except CloudError:
                worker.stop()
                self._status = "failed"
                self._message = "B站二维码生成失败，请重试。"
                raise CloudError(self._message) from None
            except Exception as exc:
                worker.stop()
                logging.warning("B站二维码生成失败：%s", type(exc).__name__)
                self._status = "failed"
                self._message = "B站二维码生成失败，请重试。"
                raise CloudError(self._message) from None
            self._worker = worker
            self._events_type = events_type
            self._started_at = time.monotonic()
            self._status = "pending"
            self._message = "请使用 B 站 App 扫码。"
            return {
                **self._snapshot_locked(),
                "qr_code": "data:image/png;base64," + base64.b64encode(content).decode("ascii"),
            }

    def check(self) -> dict[str, str]:
        with self._lock:
            if self._credential is not None:
                self._status = "logged_in"
                self._message = "B站已登录，本次服务重启后失效。"
                return self._snapshot_locked()
            if self._worker is None:
                return self._snapshot_locked()
            if time.monotonic() - self._started_at > QR_SESSION_TTL_SECONDS:
                self._stop_locked()
                self._status = "expired"
                self._message = "二维码已过期，请重新开始扫码。"
                return self._snapshot_locked()
            try:
                event, credential = self._worker.call("check")
            except Exception as exc:
                logging.warning("B站二维码状态检查失败：%s", type(exc).__name__)
                return self._fail_locked("B站二维码状态检查失败，请重试。")
            if event == self._events_type.SCAN:
                self._status = "confirm"
                self._message = "已扫码，请在 B 站 App 确认登录。"
            elif event == self._events_type.CONF:
                self._status = "confirm"
                self._message = "已扫码，等待 B 站 App 确认。"
            elif event == self._events_type.TIMEOUT:
                self._stop_locked()
                self._status = "expired"
                self._message = "二维码已过期，请重新开始扫码。"
            elif event == self._events_type.DONE and credential is not None:
                self._credential = credential
                self._stop_locked()
                self._status = "logged_in"
                self._message = "B站已登录，本次服务重启后失效。"
            else:
                return self._fail_locked("B站二维码登录失败，请重试。")
            return self._snapshot_locked()

    def logout(self) -> dict[str, str]:
        with self._lock:
            self._stop_locked()
            self._credential = None
            self._status = "logged_out"
            self._message = "已清除本机内存中的 B站登录。"
            return self._snapshot_locked()

    def credential(self) -> Any | None:
        with self._lock:
            return self._credential


bilibili_qr_login = BilibiliQrLoginManager()


def status_payload() -> dict[str, object]:
    """Return readiness without returning credentials or their contents."""
    ffmpeg_ready = bool(shutil.which("ffmpeg"))
    try:
        bilibili_ready = importlib.util.find_spec("bilibili_api") is not None
    except (ModuleNotFoundError, ValueError):
        bilibili_ready = False
    groq_ready = bool(os.environ.get("GROQ_API_KEY", "").strip())
    text_ready = {
        name: bool(os.environ.get(config["env"], "").strip())
        for name, config in TEXT_PROVIDERS.items()
    }
    checks = {
        "ffmpeg": (ffmpeg_ready, "已就绪" if ffmpeg_ready else "未找到"),
        "bilibili_api": (
            bilibili_ready,
            ("已安装；环境 Cookie 已配置" if os.environ.get("BILIBILI_COOKIE", "").strip()
             else "已安装；可扫码登录或填写 Cookie") if bilibili_ready
            else '缺少：pip install -e ".[bilibili]"',
        ),
        "groq": (groq_ready, "已配置" if groq_ready else "未配置"),
        **{
            name: (ready, "已配置" if ready else "未配置")
            for name, ready in text_ready.items()
        },
    }
    statuses = {name: {"ready": ready, "label": label} for name, (ready, label) in checks.items()}
    return {
        "ready": ffmpeg_ready and bilibili_ready and groq_ready and any(text_ready.values()),
        "statuses": statuses,
    }


def _text_field(payload: dict[str, object], name: str, limit: int) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} 必须是文本")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} 不能为空")
    if len(value) > limit or "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError(f"{name} 长度或内容无效")
    return value


def _optional_text_field(payload: dict[str, object], name: str, limit: int) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} 必须是文本")
    value = value.strip()
    if not value:
        return None
    if len(value) > limit or "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError(f"{name} 长度或内容无效")
    return value


def _model_field(payload: dict[str, object], name: str, default: str) -> str:
    value = _optional_text_field(payload, name, MAX_MODEL_LENGTH)
    if value is None:
        return default
    if not MODEL_ID_RE.fullmatch(value):
        raise ValueError(f"{name} 模型 ID 无效：只能使用字母、数字、点、下划线、冒号、斜线或连字符")
    return value


def _draft_generator(provider: str, model: str, api_key: str | None):
    config = TEXT_PROVIDERS[provider]
    if provider == "gemini":
        return GeminiDraftGenerator(api_key=api_key, model=model)
    return OpenAIChatDraftGenerator(
        api_key=api_key,
        model=model,
        base_url=config["base_url"],
        env_name=config["env"],
        service=config["service"],
    )


def publish_request(payload: object) -> list[str]:
    """Validate a browser request, run the existing pipeline, and return paths."""
    if not isinstance(payload, dict):
        raise ValueError("请求必须是 JSON 对象")
    source_value = _text_field(payload, "source", MAX_SOURCE_LENGTH)
    vault = _text_field(payload, "vault", MAX_VAULT_LENGTH)
    provider = _optional_text_field(payload, "text_provider", 32) or "gemini"
    if provider not in TEXT_PROVIDERS:
        raise ValueError("text_provider 不受支持")
    model_field = "text_model" if "text_model" in payload else "gemini_model"
    text_model = _model_field(payload, model_field, TEXT_PROVIDERS[provider]["default_model"])
    groq_model = _model_field(payload, "groq_model", DEFAULT_GROQ_MODEL)
    key_field = f"{provider}_api_key"
    text_key = _optional_text_field(payload, key_field, MAX_SECRET_LENGTH)
    groq_key = _optional_text_field(payload, "groq_api_key", MAX_SECRET_LENGTH)
    bilibili_cookie = _optional_text_field(payload, "bilibili_cookie", MAX_SECRET_LENGTH)
    try:
        parse_bilibili_id(source_value)
    except CloudError as exc:
        raise ValueError(str(exc)) from exc
    qr_credential = bilibili_qr_login.credential()
    source = (BilibiliSource(cookie=bilibili_cookie, credential=qr_credential)
              if qr_credential is not None else BilibiliSource(cookie=bilibili_cookie))
    draft = make_draft(
        source,
        GroqTranscriber(api_key=groq_key, model=groq_model),
        _draft_generator(provider, text_model, text_key),
        source_value,
    )
    return [str(path) for path in publish(vault, draft)]


def _safe_public_error(exc: BaseException) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, (CloudError, PublishError)):
        text = str(exc)
        missing_env = MISSING_ENV_RE.fullmatch(text)
        if missing_env:
            return f"缺少环境变量 {missing_env.group(1)}，请配置对应 API Key。"
        lowered = text.lower()
        if any(secret in lowered for secret in ("api_key", "authorization", "bearer", "key=", "sessdata")):
            return "云端配置或请求失败，请检查运行状态和环境变量。"
        return text[:500]
    return "服务内部错误，请查看启动终端中的错误信息。"


class LocalWebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class WebRequestHandler(BaseHTTPRequestHandler):
    server_version = "BilibiliKnowledgeBase/0.1"

    def _send_security_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; form-action 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")

    def log_message(self, format: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str) -> None:
        # Whitelist first, then resolve: neither encoded nor normalized .. can leave web/.
        decoded = unquote(urlsplit(path).path)
        if "\x00" in decoded or any(part == ".." for part in decoded.split("/")):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        asset = STATIC_FILES.get(decoded)
        if asset is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        relative, content_type = asset
        target = (STATIC_ROOT / relative).resolve()
        try:
            target.relative_to(STATIC_ROOT)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self._send_security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _host_allowed(self) -> bool:
        raw = self.headers.get("Host", "").strip()
        if not raw:
            return False
        if raw.startswith("[") and "]" in raw:
            hostname, _, port = raw[1:].partition("]")
            port = port[1:] if port.startswith(":") else ""
        else:
            hostname, separator, port = raw.rpartition(":")
            if not separator:
                hostname, port = raw, ""
        hostname = hostname.lower().rstrip(".")
        if hostname not in LOOPBACK_HOSTS:
            return False
        if port:
            try:
                return int(port) == self.server.server_port
            except ValueError:
                return False
        return self.server.server_port in (80, 443)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return True
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
            return False
        try:
            return parsed.port == self.server.server_port
        except ValueError:
            return False

    def _request_allowed(self, check_origin: bool = False) -> bool:
        if not self._host_allowed():
            self.send_error(421, "Misdirected Request")
            return False
        if check_origin and not self._origin_allowed():
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        if not self._request_allowed(check_origin=path == "/api/bilibili/login/check"):
            return
        if path == "/api/status":
            self._send_json(HTTPStatus.OK, status_payload())
            return
        if path == "/api/bilibili/login/check":
            self._send_json(HTTPStatus.OK, {"ok": True, **bilibili_qr_login.check()})
            return
        self._send_static(path)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._request_allowed(check_origin=True):
            return
        path = urlsplit(self.path).path
        if path == "/api/bilibili/login/start":
            try:
                payload = bilibili_qr_login.start()
            except (CloudError, OSError) as exc:
                self.log_message("bilibili login start failed: %s", type(exc).__name__)
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": _safe_public_error(exc)})
                return
            except Exception:
                logging.warning("bilibili login start failed: unexpected error")
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "B站二维码登录失败，请重试。"})
                return
            self._send_json(HTTPStatus.OK, {"ok": True, **payload})
            return
        if path == "/api/bilibili/login/logout":
            self._send_json(HTTPStatus.OK, {"ok": True, **bilibili_qr_login.logout()})
            return
        if path != "/api/publish":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_JSON_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "请求内容过大或缺少长度信息"})
            return
        if "application/json" not in self.headers.get("Content-Type", "").lower():
            self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "请使用 application/json 请求"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            files = publish_request(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": _safe_public_error(exc)})
            return
        except (CloudError, PublishError, OSError) as exc:
            self.log_message("publish failed: %s", type(exc).__name__)
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": _safe_public_error(exc)})
            return
        except Exception:
            logging.exception("unexpected publish failure")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": _safe_public_error(RuntimeError())})
            return
        self._send_json(HTTPStatus.OK, {"ok": True, "message": "知识库笔记已发布到 Obsidian Vault。", "files": files})


def run_server(host: str = HOST, port: int = PORT, open_browser: bool = True) -> None:
    if host.strip().lower().rstrip(".") not in LOOPBACK_HOSTS:
        raise ValueError("Web 面板只允许监听本机回环地址（127.0.0.1、localhost 或 ::1）")
    server = LocalWebServer((host, port), WebRequestHandler)
    address = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{server.server_port}/"
    print(f"B站知识库已启动：{address}", flush=True)
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动本地 B站知识库 Web 面板")
    parser.add_argument("--host", default=HOST, help="监听地址，默认仅本机 127.0.0.1")
    parser.add_argument("--port", default=PORT, type=int, help="监听端口，默认 8877")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("端口必须在 0 到 65535 之间")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run_server(args.host, args.port, not args.no_open)
    except (OSError, ValueError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
