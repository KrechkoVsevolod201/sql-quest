"""OpenAI-compatible AI features, including local LM Studio endpoints."""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from json import JSONDecoder
from typing import Any
from urllib.parse import urlparse

from . import core


def configured() -> bool:
    return bool(core.get_ai_settings()["configured"] or os.environ.get("SQL_GAME_API_KEY"))


def public_settings() -> dict[str, Any]:
    settings = core.get_ai_settings()
    if not settings["configured"]:
        settings["base_url"] = os.environ.get("SQL_GAME_BASE_URL", settings["base_url"]).rstrip("/")
        settings["model"] = os.environ.get("SQL_GAME_MODEL", settings["model"])
    return {
        "base_url": settings["base_url"],
        "model": settings["model"],
        "api_key_set": bool(settings["api_key"] or os.environ.get("SQL_GAME_API_KEY")),
        "configured": bool(settings["configured"] or os.environ.get("SQL_GAME_API_KEY")),
        "provider": "LM Studio" if settings["configured"] else ("Environment" if os.environ.get("SQL_GAME_API_KEY") else "Not configured"),
    }


def _settings() -> dict[str, str]:
    stored = core.get_ai_settings()
    if stored["configured"]:
        return {key: str(stored[key]) for key in ("base_url", "model", "api_key")}
    return {
        "base_url": os.environ.get("SQL_GAME_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "model": os.environ.get("SQL_GAME_MODEL", "gpt-4o-mini" if os.environ.get("SQL_GAME_API_KEY") else ""),
        "api_key": os.environ.get("SQL_GAME_API_KEY", ""),
    }


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def list_models(base_url: str, api_key: str = "") -> list[dict[str, str]]:
    base_url = base_url.strip().rstrip("/")
    parsed = urlparse(base_url)
    if len(base_url) > 500 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Укажи корректный адрес API, например http://localhost:1234/v1")
    request = urllib.request.Request(f"{base_url}/models", headers=_headers(api_key), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = data.get("data", [])
        return [{"id": str(model.get("id", "")), "name": str(model.get("id", ""))} for model in models if model.get("id")]
    except (urllib.error.URLError, TimeoutError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось подключиться к LM Studio: {exc}") from exc


def test_connection(base_url: str, api_key: str = "") -> dict[str, Any]:
    models = list_models(base_url, api_key)
    return {"ok": True, "models": models, "message": f"Связь установлена. Доступно моделей: {len(models)}."}


def _chat(system: str, prompt: str) -> str:
    if not configured():
        raise ValueError("Сначала настрой подключение к LM Studio на странице «Настройки AI».")
    settings = _settings()
    key = settings["api_key"]
    base = settings["base_url"].rstrip("/")
    model = settings["model"]
    if not model:
        available = list_models(base, key)
        if not available:
            raise ValueError("В LM Studio нет доступных моделей. Загрузи модель и проверь подключение.")
        model = available[0]["id"]
    payload = json.dumps({"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.4}).encode("utf-8")
    request = urllib.request.Request(f"{base}/chat/completions", data=payload, headers=_headers(key), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Модель вернула пустой ответ")
        return content.strip()
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось получить ответ от AI-провайдера: {exc}") from exc


def review(question: str, sql: str, result: Any = None) -> dict[str, Any]:
    answer = _chat(
        "Ты дружелюбный преподаватель SQL. Оцени корректность, читаемость и эффективность решения. "
        "Не выдавай полное решение сразу: сначала дай конкретную подсказку. Отвечай по-русски, кратко, в JSON с полями score (0-100), verdict, strengths (список), suggestions (список), next_hint.",
        f"Задание: {question}\nSQL ученика:\n{sql}\nРезультат выполнения (если есть): {json.dumps(result, ensure_ascii=False)}",
    )
    try:
        value = _json_object(answer)
    except ValueError:
        # Local models sometimes ignore the JSON instruction. Keep their useful
        # prose instead of making the entire review disappear as a parse error.
        value = {"verdict": answer, "strengths": [], "suggestions": [], "next_hint": ""}
    return _normalize_review(value)


def generate(topic: str, level: str = "начальный", database: str = "магазин") -> dict[str, Any]:
    answer = _chat(
        "Ты автор обучающих задач по SQLite. Верни только валидный JSON-объект на русском языке: "
        "title, description, schema_sql, seed_sql, task, hint, solution_sql, explanation. "
        "Создай компактную оригинальную схему с тестовыми данными и задачу, у которой есть проверяемый результат. "
        "Указывай PRIMARY KEY и FOREIGN KEY для связей таблиц, если они есть. Используй только SQLite SQL.",
        f"Тема: {topic}\nУровень: {level}\nСеттинг базы: {database}",
    )
    return _json_object(answer)


def generate_challenge(mode: str, topic: str = "", difficulty: int = 1) -> dict[str, Any]:
    difficulty = max(1, min(3, int(difficulty)))
    if mode not in {"random", "topic"}:
        raise ValueError("Режим генерации должен быть random или topic")
    module_id = ""
    if mode == "random":
        module = secrets.choice(core.MODULES)
        topic = secrets.choice(module["topics"])
        module_id = module["id"]
    else:
        topic = str(topic).strip()
        if not topic or len(topic) > 120:
            raise ValueError("Выбери тему из списка или введи свою (до 120 символов)")
        module = next((item for item in core.MODULES if topic.casefold() == item["name"].casefold() or topic.casefold() in {t.casefold() for t in item["topics"]}), None)
        module_id = module["id"] if module else "generated"

    level = {1: "начальный", 2: "средний", 3: "продвинутый"}[difficulty]
    topics_catalog = "; ".join(f"{item['name']}: {', '.join(item['topics'])}" for item in core.MODULES)
    answer = _chat(
        "Ты генератор полноценных учебных заданий по SQLite. Верни только JSON-объект со строковыми полями "
        "title, description, topic, schema_sql, seed_sql, task, hint, solution_sql, explanation. "
        "Создай новую маленькую предметную базу (1–5 таблиц) и заполни её осмысленными тестовыми данными. "
        "solution_sql должен быть одним корректным SELECT, который решает task на созданных данных и возвращает хотя бы одну строку. "
        "Включай PRIMARY KEY и FOREIGN KEY там, где есть связи. Не добавляй Markdown, комментарии вне SQL и DML-задачи. "
        "Подбирай данные так, чтобы ответ был однозначным и условие действительно проверяло указанную тему.",
        f"Режим: {mode}. Тема задания: {topic}. Сложность: {level} ({difficulty}/3). "
        f"Каталог доступных тем: {topics_catalog}. Используй только тему, указанную выше. "
        f"Случайный seed для разнообразия варианта: {secrets.token_hex(6)}. База не должна быть большой.",
    )
    payload = _json_object(answer)
    payload["topic"] = topic
    return core.register_ai_challenge(payload, topic, difficulty, module_id)


def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    decoder = JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("AI вернул ответ не в формате JSON")


def _normalize_review(value: dict[str, Any]) -> dict[str, Any]:
    score = value.get("score", value.get("rating"))
    try:
        score = max(0, min(100, int(float(score)))) if score is not None else None
    except (TypeError, ValueError):
        score = None

    def text(key: str, *fallback_keys: str) -> str:
        for name in (key, *fallback_keys):
            item = value.get(name)
            if item is not None and not isinstance(item, (dict, list)):
                return str(item).strip()
        return ""

    def items(key: str, *fallback_keys: str) -> list[str]:
        result = next((value[name] for name in (key, *fallback_keys) if value.get(name) is not None), [])
        if isinstance(result, str):
            result = [result]
        if not isinstance(result, list):
            return []
        return [str(item).strip() for item in result if item is not None and str(item).strip()]

    normalized = {
        "score": score,
        "verdict": text("verdict", "feedback", "review", "answer", "assessment", "summary", "comment"),
        "strengths": items("strengths", "positive_points", "pros"),
        "suggestions": items("suggestions", "recommendations", "improvements", "issues", "cons"),
        "next_hint": text("next_hint", "hint", "recommendation"),
    }
    if not any((normalized["verdict"], normalized["strengths"], normalized["suggestions"], normalized["next_hint"])):
        normalized["verdict"] = json.dumps(value, ensure_ascii=False, indent=2)
    return normalized
