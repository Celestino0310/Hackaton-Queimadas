"""Vercel WSGI entry point for the QueimAlerta Dash application."""

from __future__ import annotations

import os
import secrets
from dataclasses import asdict

from flask import jsonify, request

from queimalerta.dashboard.app import create_app
from queimalerta.ingestion.service import IngestionService
from queimalerta.observability.logging import configure_logging
from queimalerta.repositories.database import DatabaseRepository
from queimalerta.settings import Settings
from queimalerta.sources.inpe import InpeDailySource

settings = Settings.from_env()
configure_logging(settings.log_level)
dash_app = create_app(settings)
app = dash_app.server


@app.get("/api/cron/ingest")
def ingest_from_cron():
    """Run one idempotent INPE ingestion after verifying the cron bearer token."""
    cron_secret = os.getenv("CRON_SECRET")
    authorization = request.headers.get("Authorization", "")
    if not cron_secret:
        return jsonify({"status": "disabled", "error": "CRON_SECRET is not configured"}), 503
    if not secrets.compare_digest(authorization, f"Bearer {cron_secret}"):
        return jsonify({"status": "unauthorized"}), 401
    if settings.database_url.startswith("sqlite"):
        return (
            jsonify(
                {
                    "status": "disabled",
                    "error": "Persistent PostgreSQL is required for serverless ingestion",
                }
            ),
            503,
        )

    days = max(1, min(7, int(os.getenv("QUEIMALERTA_INGEST_DAYS", "1"))))
    repository = DatabaseRepository(settings.database_url)
    service = IngestionService(
        InpeDailySource(settings.inpe_daily_url),
        repository,
        archive_dir=None,
    )
    result = asdict(service.run(days=days))
    if result["newest_observation"] is not None:
        result["newest_observation"] = result["newest_observation"].isoformat()
    return jsonify({"status": "ok", **result})
