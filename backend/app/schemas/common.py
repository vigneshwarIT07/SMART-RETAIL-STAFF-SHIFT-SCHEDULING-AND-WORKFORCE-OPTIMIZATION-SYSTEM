"""Shared Pydantic building blocks used across the API surface."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base schema enabling ``from_attributes`` reads."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """A simple acknowledgement payload with no domain data."""

    message: str = Field(description="Human readable confirmation message.")


class PageMeta(BaseModel):
    """Pagination metadata attached to every list response."""

    page: int = Field(ge=1, description="1-based page number.")
    page_size: int = Field(ge=1, description="Number of records per page.")
    total: int = Field(ge=0, description="Total number of matching records.")
    pages: int = Field(ge=0, description="Total number of pages available.")


class PaginatedResponse(BaseModel, Generic[T]):
    """A page of records plus the metadata needed to render pagination."""

    items: list[T]
    meta: PageMeta