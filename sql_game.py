"""Start SQL Quest's local web application."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlgame import ai, core


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"


class Handler(BaseHTTPRequestHandler):
    server_version = "SQLQuest/1.0"

    def log_message(self, format: str, *args: object) -> None:
        if os.environ.get("SQL_GAME_DEBUG"):
            super().log_message(format, *args)

    def _json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                raise ValueError("Request too large")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Некорректное тело запроса") from exc

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/dashboard":
                return self._json({**core.dashboard(), "ai_enabled": ai.configured()})
            if parsed.path == "/api/modules":
                return self._json(core.MODULES)
            if parsed.path == "/api/databases":
                return self._json([{"id": key, **{k: v for k, v in value.items() if k in {"name", "description"}}} for key, value in core.DATABASES.items()])
            if parsed.path == "/api/exercises":
                return self._json(core.list_exercises(params.get("module", [None])[0]))
            if parsed.path.startswith("/api/exercises/"):
                return self._json(core.exercise_details(parsed.path.rsplit("/", 1)[-1]))
            if parsed.path == "/api/schema":
                return self._json(core.schema(params.get("database", [""])[0]))
            if parsed.path == "/api/lab/template":
                return self._json({"sql": core.lab_template()})
            if parsed.path == "/api/lab/schema":
                return self._json(core.lab_schema())
            if parsed.path == "/api/ai/settings":
                return self._json(ai.public_settings())
            if parsed.path == "/api/ai/challenges":
                return self._json(core.list_ai_challenges())
            return self._static(parsed.path)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except (OSError, KeyError) as exc:
            self._json({"error": str(exc)}, 404)

    def _static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        path = (WEB_DIR / relative).resolve()
        if not path.is_relative_to(WEB_DIR.resolve()) or not path.is_file():
            self.send_error(404)
            return
        content = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
            mime += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        try:
            data = self._body()
            path = urlparse(self.path).path
            if path == "/api/run":
                return self._json(core.run_query(data.get("database", ""), data.get("sql", "")))
            if path == "/api/grade":
                return self._json(core.grade(data.get("exercise_id", ""), data.get("sql", "")))
            if path == "/api/complete":
                return self._json(core.record_completion(data.get("exercise_id", ""), data.get("mode", "practice"), data.get("duration_ms", 0), data.get("query_ms", 0), bool(data.get("correct"))))
            if path == "/api/lab":
                return self._json(core.run_lab(data.get("sql", ""), data.get("mode", "query")))
            if path == "/api/lab/grade":
                return self._json(core.grade_lab(data.get("sql", ""), data.get("solution", "")))
            if path == "/api/lab/complete":
                return self._json(core.complete_lab_task(data.get("challenge_id", ""), bool(data.get("correct"))))
            if path == "/api/ai/review":
                return self._json(ai.review(data.get("question", ""), data.get("sql", ""), data.get("result")))
            if path == "/api/ai/generate":
                return self._json(ai.generate(data.get("topic", "SELECT"), data.get("level", "начальный"), data.get("database", "учебная база")))
            if path == "/api/ai/challenge":
                return self._json(ai.generate_challenge(data.get("mode", "random"), data.get("topic", ""), data.get("difficulty", 1)))
            if path == "/api/ai/settings":
                core.save_ai_settings(data.get("base_url", ""), data.get("model", ""), data.get("api_key", ""), bool(data.get("clear_api_key")))
                return self._json(ai.public_settings())
            if path == "/api/ai/test":
                saved = core.get_ai_settings()
                return self._json(ai.test_connection(data.get("base_url", saved["base_url"]), data.get("api_key", "") or saved["api_key"] or os.environ.get("SQL_GAME_API_KEY", "")))
            return self._json({"error": "Маршрут не найден"}, 404)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:
            self._json({"error": f"Внутренняя ошибка: {exc}"}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальная игра для изучения SQL")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Сервер хранит локальные учебные данные и по умолчанию доступен только на этом компьютере.")
    core.initialize()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{server.server_port}"
    print(f"SQL Quest запущен: {url}\nОстановить сервер: Ctrl+C")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСохраняем прогресс…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
