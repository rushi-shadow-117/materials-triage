"""Compatibility import: the app and its OpenAPI schema live in api/app.py (Track C)."""

from __future__ import annotations

from .app import app, create_app, openapi_schema

__all__ = ["app", "create_app", "openapi_schema"]
