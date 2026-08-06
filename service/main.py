"""Run the ticket workflow API locally:  py -m uvicorn service.main:app

Uses SQLite at data/service/tickets.db (override with SUPPORT_DB_PATH).
The decision pipeline needs DEEPSEEK_API_KEY / GROQ_API_KEY at runtime; the
service layer itself is DB-only and fully offline.
"""
from .api import app

__all__ = ["app"]
