"""Shared schema types used across multiple schema modules."""

from datetime import datetime
from typing import Annotated, Any, get_args, get_origin

from pydantic import BaseModel, StringConstraints, ValidationInfo, field_validator

from app.time_utils import ensure_utc_datetime


def _annotation_includes_datetime(annotation: Any) -> bool:
    if annotation is datetime:
        return True

    origin = get_origin(annotation)
    if origin is None:
        return False

    return any(
        _annotation_includes_datetime(arg)
        for arg in get_args(annotation)
        if arg is not type(None)
    )


class ApiModel(BaseModel):
    """Base schema that normalizes response datetimes to UTC-aware values."""

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def _normalize_datetime_fields(cls, value: Any, info: ValidationInfo) -> Any:
        field = cls.model_fields.get(info.field_name)
        if field is None or not _annotation_includes_datetime(field.annotation):
            return value
        return ensure_utc_datetime(value)


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
