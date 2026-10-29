"""Базовая Pydantic-модель API/протокола: camelCase в JSON, snake_case в Python."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
        json_schema_serialization_defaults_required=True,
    )
