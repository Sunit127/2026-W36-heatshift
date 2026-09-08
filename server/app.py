from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

DB_PATH = Path(os.getenv("HEATSHIFT_DB_PATH", "server/heatshift.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

RATE_LIMIT = max(1, int(os.getenv("HEATSHIFT_RATE_LIMIT", "60")))
WINDOW_SECONDS = 60
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
hits: dict[str, list[float]] = {}


def configured_share_ttl() -> int:
    """Keep opt-in share retention bounded even when deployment config is malformed."""
    try:
        value = int(os.getenv("HEATSHIFT_SHARE_TTL_SECONDS", str(30 * 24 * 60 * 60)))
    except ValueError:
        value = 30 * 24 * 60 * 60
    return max(300, min(value, 365 * 24 * 60 * 60))


SHARE_TTL_SECONDS = configured_share_ttl()


class Plan(BaseModel):
    # Security hardening: reject unknown fields so the backend only accepts known schema.
    model_config = ConfigDict(extra="forbid")
    shiftName: str = Field(min_length=1, max_length=60)
    startTime: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    duration: float = Field(ge=1, le=16)
    temperature: float = Field(ge=10, le=60)
    humidity: float = Field(ge=5, le=100)

    intensity: Literal["light", "moderate", "heavy"]
    sun: Literal["shade", "mixed", "direct"]
    ppe: Literal["breathable", "standard", "impermeable"]

    acclimatized: bool
    heatIndex: float | None = Field(default=None, ge=-100, le=100)
    tier: Literal["routine", "caution", "high", "severe"] | None = None

    @field_validator("shiftName")
    @classmethod
    def clean_name(cls, v):
        # Normalize spacing and reject empty names after normalization.
        v = " ".join(v.split())
        if not v:
            raise ValueError("shiftName cannot be blank")
        return v


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def expiry_for(created_at: str) -> str:
    """Return an ISO-8601 expiry for a stored share, tolerating legacy timestamps."""
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        created = datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (created + timedelta(seconds=SHARE_TTL_SECONDS)).isoformat()


def purge_expired(connection: sqlite3.Connection) -> None:
    connection.execute(
        "DELETE FROM plans WHERE expires_at IS NOT NULL AND expires_at <= ?",
        (datetime.now(timezone.utc).isoformat(),),
    )


def migrate():
    with db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        if (
            c.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone()
            is None
        ):
            c.execute(
                "CREATE TABLE plans ("
                "share_token TEXT PRIMARY KEY, "
                "payload TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "expires_at TEXT"
                ")"
            )
            c.execute(
                "INSERT INTO schema_migrations(version,applied_at) VALUES(1, ?)",
                (datetime.now(timezone.utc).isoformat(),),
            )

        columns = {
            row["name"]
            for row in c.execute("PRAGMA table_info(plans)").fetchall()
        }
        if "expires_at" not in columns:
            c.execute("ALTER TABLE plans ADD COLUMN expires_at TEXT")

        legacy_rows = c.execute(
            "SELECT share_token,created_at FROM plans WHERE expires_at IS NULL"
        ).fetchall()
        for row in legacy_rows:
            c.execute(
                "UPDATE plans SET expires_at=? WHERE share_token=?",
                (expiry_for(row["created_at"]), row["share_token"]),
            )
        purge_expired(c)


def create_app():
    migrate()
    app = FastAPI(
        title="HeatShift team-sharing API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )

    raw_origins = os.getenv("HEATSHIFT_CORS_ORIGINS", "http://localhost:8080")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def hardening(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if (
            content_length
            and (
                not content_length.isdigit()
                or int(content_length) > 65536
            )
        ):
            # Reject oversized payloads before application parsing.
            return JSONResponse({"detail": "Request body too large"}, status_code=413)

        now = time.monotonic()
        client_key = request.client.host if request.client else "unknown"
        recent_calls = [
            event
            for event in hits.get(client_key, [])
            if now - event < WINDOW_SECONDS
        ]
        if len(recent_calls) >= RATE_LIMIT:
            # Per-client in-memory rate limiting to reduce burst abuse.
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )

        recent_calls.append(now)
        hits[client_key] = recent_calls
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            }
        )
        return response

    @app.get("/healthz")
    def healthz():
        # DB health check: if the query fails, the route returns an error before reply.
        with db() as c:
            c.execute("SELECT 1")
        return {"status": "ok"}

    @app.post("/api/v1/plans", status_code=201)
    def create_plan(plan: Plan):
        # Explicitly store normalized payload to keep DB rows consistent.
        token = secrets.token_urlsafe(24)
        created_at = datetime.now(timezone.utc).isoformat()
        expires_at = expiry_for(created_at)
        payload = plan.model_dump_json(exclude_none=True)
        with db() as c:
            purge_expired(c)
            c.execute(
                "INSERT INTO plans(share_token,payload,created_at,expires_at) "
                "VALUES(?,?,?,?)",
                (token, payload, created_at, expires_at),
            )
        return {
            "shareToken": token,
            "createdAt": created_at,
            "expiresAt": expires_at,
            "plan": plan.model_dump(exclude_none=True),
        }

    @app.get("/api/v1/plans/{share_token}")
    def get_plan(share_token: str):
        # Token format check blocks malformed keys before DB lookup.
        if not TOKEN_RE.fullmatch(share_token):
            raise HTTPException(404, "Plan not found")

        with db() as c:
            purge_expired(c)
            row = c.execute(
                "SELECT payload,created_at,expires_at "
                "FROM plans WHERE share_token=? AND expires_at > ?",
                (share_token, datetime.now(timezone.utc).isoformat()),
            ).fetchone()

        if row is None:
            raise HTTPException(404, "Plan not found")

        return {
            "shareToken": share_token,
            "createdAt": row["created_at"],
            "expiresAt": row["expires_at"],
            "plan": json.loads(row["payload"]),
        }

    return app


app = create_app()
