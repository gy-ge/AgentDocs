"""Shared schema types used across multiple schema modules."""

from typing import Annotated

from pydantic import StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
