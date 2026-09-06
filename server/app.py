from __future__ import annotations
import json, os, re, secrets, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

DB_PATH=Path(os.getenv("HEATSHIFT_DB_PATH","server/heatshift.sqlite3")); DB_PATH.parent.mkdir(parents=True,exist_ok=True)
RATE_LIMIT=max(1,int(os.getenv("HEATSHIFT_RATE_LIMIT","60"))); WINDOW_SECONDS=60; TOKEN_RE=re.compile(r"^[A-Za-z0-9_-]{20,64}$"); hits={}
class Plan(BaseModel):
    model_config=ConfigDict(extra="ignore")
    shiftName:str=Field(min_length=1,max_length=60); startTime:str=Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration:float=Field(ge=1,le=16); temperature:float=Field(ge=10,le=60); humidity:float=Field(ge=5,le=100)
    intensity:Literal["light","moderate","heavy"]; sun:Literal["shade","mixed","direct"]; ppe:Literal["breathable","standard","impermeable"]
    acclimatized:bool; heatIndex:float|None=Field(default=None,ge=-100,le=100); tier:Literal["routine","caution","high","severe"]|None=None
    @field_validator("shiftName")
    @classmethod
    def clean_name(cls,v):
        v=" ".join(v.split())
        if not v: raise ValueError("shiftName cannot be blank")
        return v
def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def migrate():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        if c.execute("SELECT 1 FROM schema_migrations WHERE version=1").fetchone() is None:
            c.execute("CREATE TABLE plans (share_token TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT)")
            c.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(1,?)",(datetime.now(timezone.utc).isoformat(),))
def create_app():
    migrate(); app=FastAPI(title="HeatShift team-sharing API",version="1.0.0",docs_url=None,redoc_url=None)
    origins=[x.strip() for x in os.getenv("HEATSHIFT_CORS_ORIGINS","http://localhost:8080").split(",") if x.strip()]
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=["GET","POST"],allow_headers=["Content-Type"],max_age=600)
    @app.middleware("http")
    async def hardening(request:Request,call_next):
        length=request.headers.get("content-length")
        if length and (not length.isdigit() or int(length)>65536): return JSONResponse({"detail":"Request body too large"},status_code=413)
        now=time.monotonic(); key=request.client.host if request.client else "unknown"; recent=[x for x in hits.get(key,[]) if now-x<WINDOW_SECONDS]
        if len(recent)>=RATE_LIMIT: return JSONResponse({"detail":"Rate limit exceeded"},status_code=429,headers={"Retry-After":"60"})
        recent.append(now); hits[key]=recent; response=await call_next(request)
        response.headers.update({"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Content-Security-Policy":"default-src 'none'; frame-ancestors 'none'"})
        return response
    @app.get("/healthz")
    def healthz():
        with db() as c: c.execute("SELECT 1")
        return {"status":"ok"}
    @app.post("/api/v1/plans",status_code=201)
    def create_plan(plan:Plan):
        token=secrets.token_urlsafe(24); created=datetime.now(timezone.utc).isoformat(); payload=plan.model_dump_json(exclude_none=True)
        with db() as c: c.execute("INSERT INTO plans(share_token,payload,created_at) VALUES(?,?,?)",(token,payload,created))
        return {"shareToken":token,"createdAt":created,"plan":plan.model_dump(exclude_none=True)}
    @app.get("/api/v1/plans/{share_token}")
    def get_plan(share_token:str):
        if not TOKEN_RE.fullmatch(share_token): raise HTTPException(404,"Plan not found")
        with db() as c: row=c.execute("SELECT payload,created_at FROM plans WHERE share_token=?",(share_token,)).fetchone()
        if row is None: raise HTTPException(404,"Plan not found")
        return {"shareToken":share_token,"createdAt":row["created_at"],"plan":json.loads(row["payload"])}
    return app
app=create_app()
