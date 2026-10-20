"""Paginazione a cursore: stabile anche mentre i dati cambiano sotto la lista."""

from __future__ import annotations

from rest_framework.pagination import CursorPagination


class StandardCursorPagination(CursorPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
    ordering = "-created_at"


class CodeCursorPagination(StandardCursorPagination):
    """Per le liste ordinate per codice (progetti, attività)."""

    ordering = "code"
