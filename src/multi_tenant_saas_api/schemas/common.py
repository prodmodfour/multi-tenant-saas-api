"""Shared Pydantic schema primitives."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    """Base model for public API schemas."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class PaginationMeta(APIModel):
    """Pagination metadata returned by list endpoints."""

    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    total: int = Field(ge=0)
    count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_count_bounds(self) -> Self:
        """Ensure returned item counts are consistent with the page metadata."""

        if self.count > self.limit:
            msg = "count cannot exceed limit"
            raise ValueError(msg)
        if self.count > self.total:
            msg = "count cannot exceed total"
            raise ValueError(msg)
        return self
