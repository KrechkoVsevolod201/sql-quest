"""Minimal stdio MCP server exposing SQL Quest's learning tools.

Run with: python mcp_server.py
"""

from __future__ import annotations

import json
import sys
from typing import Any

from sqlgame import ai, core


TOOLS = [
    {"name": "list_learning_databases", "description": "Список учебных баз данных и их таблиц.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "run_sql", "description": "Выполнить безопасный read-only SQL-запрос на учебной базе.", "inputSchema": {"type": "object", "properties": {"database": {"type": "string", "description": "Идентификатор: shop, library или games"}, "sql": {"type": "string"}}, "required": ["database", "sql"]}},
    {"name": "grade_exercise", "description": "Сверить результат SQL с ответом учебного задания.", "inputSchema": {"type": "object", "properties": {"exercise_id": {"type": "string"}, "sql": {"type": "string"}}, "required": ["exercise_id", "sql"]}},
    {"name": "review_sql_with_ai", "description": "Получить педагогический разбор SQL от настроенной модели.", "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}, "sql": {"type": "string"}, "result": {}}, "required": ["question", "sql"]}},
    {"name": "generate_exercise", "description": "Создать задание и схему SQLite с помощью настроенной модели.", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}, "level": {"type": "string"}, "database": {"type": "string"}}, "required": ["topic"]}},
]


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "list_learning_databases":
        return [{"id": key, "name": value["name"], "description": value["description"], "tables": core.schema(key)} for key, value in core.DATABASES.items()]
    if name == "run_sql":
        return core.run_query(arguments["database"], arguments["sql"])
    if name == "grade_exercise":
        return core.grade(arguments["exercise_id"], arguments["sql"])
    if name == "review_sql_with_ai":
        return ai.review(arguments["question"], arguments["sql"], arguments.get("result"))
    if name == "generate_exercise":
        return ai.generate(arguments["topic"], arguments.get("level", "начальный"), arguments.get("database", "учебная база"))
    raise ValueError(f"Неизвестный tool: {name}")


def respond(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return None
    request_id = message.get("id")
    params = message.get("params", {})
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "sql-quest", "version": "1.0.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        try:
            result = call_tool(params.get("name", ""), params.get("arguments", {}))
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": False}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True}}
    if request_id is not None:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main() -> None:
    core.initialize()
    for line in sys.stdin:
        try:
            response = respond(json.loads(line))
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
