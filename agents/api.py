from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path
import os, json

app = FastAPI(title="Revive Agents - minimal settings API")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_token() -> str:
    # prefer environment variable, fallback to .env
    if os.environ.get("AGENT_TOKEN"):
        return os.environ.get("AGENT_TOKEN")
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "AGENT_TOKEN":
                    return v.strip()
    return "devtoken"


AGENT_TOKEN = _load_token()


def authorize(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != AGENT_TOKEN:
        raise HTTPException(status_code=403, detail="invalid token")
    return True


SETTINGS_FILE = CONFIG_DIR / "settings.json"


def read_settings() -> Dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    # default settings
    return {"post_daily": True, "platforms": ["moltbook"], "tone": "supportive", "keywords": ["mystical"]}


def write_settings(data: Dict[str, Any]):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


class SettingsIn(BaseModel):
    post_daily: Optional[bool]
    platforms: Optional[list]
    tone: Optional[str]
    keywords: Optional[list]


@app.get("/")
def root():
    return {"ok": True}


@app.get("/settings")
def get_settings(authorization: Optional[str] = Header(None)):
    authorize(authorization)
    return read_settings()


@app.post("/settings")
def post_settings(payload: SettingsIn, authorization: Optional[str] = Header(None)):
    authorize(authorization)
    current = read_settings()
    update = payload.dict(exclude_none=True)
    current.update(update)
    write_settings(current)
    return {"ok": True, "settings": current}
