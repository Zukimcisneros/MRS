from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, json, uuid, shutil, datetime

app = FastAPI(title="Revive Agents - minimal settings & content API")
# Allow frontend access (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
UPLOAD_DIR = ROOT / "frontend" / "static" / "uploads"
for d in (CONFIG_DIR, DATA_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)

def _load_env(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip()
    return default

AGENT_TOKEN = _load_env("AGENT_TOKEN", "devtoken")
ADMIN_PASSWORD = _load_env("ADMIN_PASSWORD", "admin")


def admin_auth(authorization: Optional[str] = Header(None)):
    # Accept Authorization: Bearer <ADMIN_PASSWORD> for admin actions
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="invalid admin credentials")
    return True

def list_posts() -> List[Dict[str, Any]]:
    posts = []
    for f in DATA_DIR.glob("*.json"):
        try:
            posts.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    posts.sort(key=lambda p: p.get("publish_date") or "", reverse=True)
    return posts

@app.get("/posts")
def get_posts():
    return list_posts()

@app.get("/posts/{post_id}")
def get_post(post_id: str):
    p = _post_path(post_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return json.loads(p.read_text(encoding="utf-8"))

@app.post("/posts")
def create_post(payload: PostIn, authorized: bool = Depends(admin_auth)):
    pid = payload.slug or payload.title.lower().replace(" ", "-") + "-" + uuid.uuid4().hex[:6]
    post = payload.dict()
    post.update({"id": pid, "created_at": datetime.datetime.utcnow().isoformat()})
    _post_path(pid).write_text(json.dumps(post, indent=2), encoding="utf-8")
    return {"ok": True, "post": post}

@app.put("/posts/{post_id}")
def update_post(post_id: str, payload: PostIn, authorized: bool = Depends(admin_auth)):
    p = _post_path(post_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    current = json.loads(p.read_text(encoding="utf-8"))
    update = payload.dict(exclude_none=True)
    current.update(update)
    current["updated_at"] = datetime.datetime.utcnow().isoformat()
    p.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return {"ok": True, "post": current}

@app.delete("/posts/{post_id}")
def delete_post(post_id: str, authorized: bool = Depends(admin_auth)):
    p = _post_path(post_id)
    if p.exists():
        p.unlink()
        return {"ok": True}
    raise HTTPException(status_code=404, detail="not found")

@app.post("/upload")
def upload_file(file: UploadFile = File(...), authorized: bool = Depends(admin_auth)):
    ext = Path(file.filename).suffix
    dest = UPLOAD_DIR / (uuid.uuid4().hex + ext)
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"/static/uploads/{dest.name}"
    return {"ok": True, "url": rel}

@app.post("/schedule")
def schedule_publish(post_id: str, publish_date: Optional[str] = None, authorized: bool = Depends(admin_auth)):
    # simple scheduling: update post publish_date; actual worker to publish later is out of scope
    p = _post_path(post_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    post = json.loads(p.read_text(encoding="utf-8"))
    post["publish_date"] = publish_date or datetime.datetime.utcnow().isoformat()
    p.write_text(json.dumps(post, indent=2), encoding="utf-8")
    return {"ok": True, "post": post}

@app.post("/video")
def create_short_video(post_id: str, authorized: bool = Depends(admin_auth)):
    # Placeholder endpoint to enqueue short vertical video generation from post content.
    # Real implementation requires external TTS / video APIs and a worker.
    job_id = uuid.uuid4().hex
    jobs_file = DATA_DIR / "video_jobs.json"
    jobs = []
    if jobs_file.exists():
        jobs = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs.append({"job_id": job_id, "post_id": post_id, "status": "queued", "created_at": datetime.datetime.utcnow().isoformat()})
    jobs_file.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
    return {"ok": True, "job_id": job_id}
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
    return {
        "post_daily": True,
        "platforms": ["moltbook"],
        "tone": "supportive",
        "keywords": ["mystical"],
        # agent personality controls behavior when composing or scheduling content
        "agent_personality": "supportive, mystical-themed assistant",
        # platform specific settings (keeps API keys/flags; recommend storing sensitive keys in env vars)
        "moltbook": {
            "enabled": True,
            "api_key": "",
            "username": "",
            "auto_publish": False
        }
    }


def write_settings(data: Dict[str, Any]):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


class SettingsIn(BaseModel):
    post_daily: Optional[bool]
    platforms: Optional[list]
    tone: Optional[str]
    keywords: Optional[list]
    agent_personality: Optional[str]
    moltbook: Optional[dict]


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
