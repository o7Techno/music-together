"""Выгрузка JSON Schema протокола и REST-моделей для генерации TS-типов фронтенда.

    uv run python -m app.ws.schema > ../frontend/src/shared/protocol/schema.json

Сообщения клиента — в режиме валидации (поля с дефолтами необязательны), всё, что отдаёт сервер, —
в режиме сериализации (поля с дефолтами всегда присутствуют).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaMode, models_json_schema

from app.api.music import ResolveResponse
from app.api.schemas import AuthConfig, Me, RoomDetails, RoomSummary, SlugResponse
from app.api.yandex_auth import DevicePollResponse, DeviceStartResponse
from app.providers.base import (
    AlbumSummary,
    PlaylistSummary,
    ResolvedEntity,
    SearchResult,
    StreamInfo,
    TrackList,
)
from app.ws import protocol


class ClientMessageSchema(BaseModel):
    message: protocol.ClientMessage


class ServerMessageSchema(BaseModel):
    message: protocol.ServerMessage


SERVER_MODELS: list[type[BaseModel]] = [
    ServerMessageSchema,
    Me,
    AuthConfig,
    RoomSummary,
    RoomDetails,
    SlugResponse,
    SearchResult,
    TrackList,
    AlbumSummary,
    PlaylistSummary,
    StreamInfo,
    ResolvedEntity,
    ResolveResponse,
    DeviceStartResponse,
    DevicePollResponse,
]


def _strip_titles(node: Any) -> None:
    """Pydantic даёт `title` каждому полю — генератор TS сделал бы из них лишние типы."""
    if isinstance(node, dict):
        node.pop("title", None)
        for key, value in node.items():
            if key in ("properties", "$defs") and isinstance(value, dict):
                # Здесь ключи — имена полей, а не ключевые слова схемы: поле `title` не трогаем.
                for field_schema in value.values():
                    _strip_titles(field_schema)
            else:
                _strip_titles(value)
    elif isinstance(node, list):
        for value in node:
            _strip_titles(value)


def build_schema() -> dict[str, Any]:
    models: list[tuple[type[BaseModel], JsonSchemaMode]] = [
        (ClientMessageSchema, "validation"),
        *[(m, "serialization") for m in SERVER_MODELS],
    ]
    _, schema = models_json_schema(models, title="Protocol", by_alias=True)
    defs: dict[str, Any] = schema["$defs"]
    # Корневые обёртки нужны только чтобы вытащить объединения — превращаем их в псевдонимы.
    defs["ClientMessage"] = defs.pop("ClientMessageSchema")["properties"]["message"]
    defs["ServerMessage"] = defs.pop("ServerMessageSchema")["properties"]["message"]
    # Дискриминатор `type` обязателен всегда, иначе в TS объединение не сужается по нему.
    for definition in defs.values():
        if "type" in definition.get("properties", {}):
            required = definition.setdefault("required", [])
            if "type" not in required:
                required.insert(0, "type")
    for name, definition in defs.items():
        _strip_titles(definition)
        definition["title"] = name
    return {
        "title": "Protocol",
        "type": "object",
        "properties": {name: {"$ref": f"#/$defs/{name}"} for name in sorted(defs)},
        "$defs": dict(sorted(defs.items())),
    }


if __name__ == "__main__":
    # UTF-8 и LF независимо от ОС: схема коммитится и сравнивается в CI.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]  # TextIO
    json.dump(build_schema(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
