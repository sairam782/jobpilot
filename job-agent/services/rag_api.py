"""Backward-compatible entry point.

The RAG endpoints now live inside the full API app. This module keeps the
old ``uvicorn services.rag_api:app`` command working.
"""

from services.api import app  # noqa: F401
