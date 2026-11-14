from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("HEATSHIFT_DB_PATH", "server/heatshift.sqlite3"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def configured_rate_limit() -> int:
    """Parse a bounded request quota without crashing or disabling protection."""
    try:
        value = int(os.getenv("HEATSHIFT_RATE_LIMIT", "60"))
    except (TypeError, ValueError):
        value = 60
    return max(1, min(value, 1_000))


RATE_LIMIT = configured_rate_limit()
WINDOW_SECONDS = 60
MAX_BODY_BYTES = 64 * 1024
MAX_TRACKED_CLIENTS = 10_000
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
hits: dict[str, list[float]] = {}
_last_rate_cleanup = 0.0

def prune_rate_limit_entries(now: float) -> None:
    """Bound in-memory rate-limit state even when clients rotate addresses."""
    global _last_rate_cleanup
    if now - _last_rate_cleanup < WINDOW_SECONDS and len(hits) <= MAX_TRACKED_CLIENTS:
        return
    _last_rate_cleanup = now
    for key, events in list(hits.items()):
        recent = [event for event in events if now - event < WINDOW_SECONDS]
        if recent:
            hits[key] = recent
        else:
            del hits[key]
    if len(hits) > MAX_TRACKED_CLIENTS:
        # Keep the newest keys if a burst creates more entries than the cap.
        newest = sorted(hits.items(), key=lambda item: item[1][-1], reverse=True)
        hits.clear()
        hits.update(newest[:MAX_TRACKED_CLIENTS])

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
  "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
  "X-Permitted-Cross-Domain-Policies": "none",
}


class BodyLimitMiddleware:
    """Bound received bytes before FastAPI parses any request body."""

    def __init__(self, app, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        received = 0
        messages = []
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break

            received += len(message.get("body", b""))
            if received > self.max_body_bytes:
                response = JSONResponse(
                    {"detail": "Request body too large"},
                    status_code=413,
                    headers=SECURITY_HEADERS,
                )
                return await response(scope, receive, send)

            if not message.get("more_body", False):
                break

        async def replay_receive():
            if messages:
                return messages.pop(0)
            return await receive()

        return await self.app(scope, replay_receive, send)


def configured_share_ttl() -> int:
    """Keep opt-in share retention bounded even when deployment config is malformed."""
    try:
        value = int(os.getenv("HEATSHIFT_SHARE_TTL_SECONDS", str(30 * 24 * 60 * 60)))
    except ValueError:
        value = 30 * 24 * 60 * 60
    return max(300, min(value, 365 * 24 * 60 * 60))


SHARE_TTL_SECONDS = configured_share_ttl()


def configured_cleanup_interval() -> int:
    """Bound idle retention cleanup frequency to a practical operator range."""
    try:
        value = int(os.getenv("HEATSHIFT_CLEANUP_INTERVAL_SECONDS", "3600"))
    except ValueError:
        value = 3600
    return max(60, min(value, 24 * 60 * 60))


CLEANUP_INTERVAL_SECONDS = configured_cleanup_interval()


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

    # Accept only source observations. Derived heat-index and tier values are
    # calculated by the offline client and must not be trusted or persisted.
    acclimatized: bool

    @field_validator("duration", "temperature", "humidity", mode="before")
    @classmethod
    def require_finite_json_number(cls, value):
        # Reject bools, numeric strings, NaN, and infinity instead of silently
        # coercing a malformed or non-standard JSON value into stored plan data.
        if value is None:
            return value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a JSON number")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("must be finite")
        return value

    @field_validator("acclimatized", mode="before")
    @classmethod
    def require_json_boolean(cls, value):
        if not isinstance(value, bool):
            raise ValueError("must be a JSON boolean")
        return value

    @field_validator("shiftName")
    @classmethod
    def clean_name(cls, v):
        # Normalize spacing and reject empty names after normalization.
        v = " ".join(v.split())
        if not v:
            raise ValueError("shiftName cannot be blank")
        return v


def db():
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    # WAL lets health/read requests continue while an opt-in share is written;
    # the busy timeout turns short writer contention into a retry window instead
    # of an avoidable 500/503 for a small team deployment.
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
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
                "CREATE TABLE IF NOT EXISTS plans ("
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


def cleanup_expired() -> None:
    """Delete expired shares even when no user request reaches the service."""
    with db() as connection:
        purge_expired(connection)


async def retention_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(cleanup_expired)
        except Exception:
            # A transient cleanup failure must not stop the API or future attempts.
            logger.exception("HeatShift retention cleanup failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cleanup_task = asyncio.create_task(retention_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


def create_app():
    migrate()
    app = FastAPI(
        title="HeatShift team-sharing API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    raw_origins = os.getenv("HEATSHIFT_CORS_ORIGINS", "http://localhost:8080")
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    app.add_middleware(BodyLimitMiddleware, max_body_bytes=MAX_BODY_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        # Do not reflect raw invalid values. Besides limiting data exposure, this
        # keeps non-standard floats such as NaN from breaking JSON serialization.
        details = [
            {
                "loc": error["loc"],
                "msg": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse({"detail": details}, status_code=422)

    @app.middleware("http")
    async def hardening(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if (
            content_length
            and (
                not content_length.isdigit()
                or int(content_length) > MAX_BODY_BYTES
            )
        ):
            # Reject oversized payloads before application parsing.
            return JSONResponse({"detail": "Request body too large"}, status_code=413, headers=SECURITY_HEADERS)

        if request.method == "POST" and request.url.path == "/api/v1/plans":
            content_type = request.headers.get("content-type", "").lower()
            if not content_type.startswith("application/json"):
                return JSONResponse(
                    {"detail": "Content-Type must be application/json"},
                    status_code=415,
                    headers=SECURITY_HEADERS,
                )

        # CORS preflights and liveness probes should not consume the write quota.
        should_limit = request.method != "OPTIONS" and request.url.path != "/healthz"
        if should_limit:
            now = time.monotonic()
            prune_rate_limit_entries(now)
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
                    headers={**SECURITY_HEADERS, "Retry-After": "60"},
                )

            recent_calls.append(now)
            hits[client_key] = recent_calls

        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
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

    @app.delete("/api/v1/plans/{share_token}", status_code=204)
    def delete_plan(share_token: str):
        # Share tokens are bearer capabilities; deletion supports explicit data minimization.
        if not TOKEN_RE.fullmatch(share_token):
            raise HTTPException(404, "Plan not found")
        with db() as c:
            result = c.execute("DELETE FROM plans WHERE share_token=?", (share_token,))
            if result.rowcount != 1:
                raise HTTPException(404, "Plan not found")
        return Response(status_code=204)

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
