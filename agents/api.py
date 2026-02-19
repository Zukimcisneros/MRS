from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv
import json
from pathlib import Path

load_dotenv()

AGENT_TOKEN = os.getenv('AGENT_TOKEN')  # must be set to secure the endpoints
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

app = FastAPI(title="Revive Agent API", version="0.1")


def authorize(authorization: Optional[str]):
    if not AGENT_TOKEN:
        # no token configured: open mode (development only)
        return True
    if not authorization:
        return False
    parts = authorization.split()
    if len(parts) != 2:
        return False
    scheme, token = parts
    return scheme.lower() == 'bearer' and token == AGENT_TOKEN


class PostRequest(BaseModel):
    persona: str
    trigger: str


class EpisodeRequest(BaseModel):
    persona: Optional[str] = None
    fmt: Optional[str] = None
    tts: bool = False
    translate_th: bool = False


@app.get("/", tags=["health"])
def health():
    return {"status": "ok", "service": "revive-agent"}


@app.post("/generate_post", tags=["poster"])
def generate_post(req: PostRequest, request: Request, authorization: Optional[str] = Header(None)):
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Import locally to avoid heavy imports on startup
    try:
        from revive_trio_poster import generate_post as gen
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server import error: {e}")

    try:
        text = gen(req.persona, req.trigger)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation error: {e}")


@app.post("/generate_episode", tags=["podcast"])
def generate_episode(req: EpisodeRequest, request: Request, authorization: Optional[str] = Header(None)):
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        import podcast_generator as pg
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server import error: {e}")

    persona = req.persona or pg.get_next_persona()
    try:
        # Force fallback generation when Anthropic/Claude is unavailable or billing-limited
        try:
            pg.anthropic = None
        except Exception:
            pass
        try:
            pg.CLAUDE_API_KEY = None
        except Exception:
            pass
        title, description, sections = pg.generate_script(persona, fmt=req.fmt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Script generation error: {e}")

    try:
        ep = pg.append_episode(title, description, sections, fmt=req.fmt or 'guided')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Append episode error: {e}")

    results = {"episode": ep}

    # optionally translate
    if req.translate_th:
        try:
            ok = pg.generate_translation_th(ep)
            results['translate_th'] = bool(ok)
        except Exception as e:
            results['translate_th'] = False
            results['translate_th_error'] = str(e)

    # optionally generate TTS
    if req.tts:
        try:
            gen_files = pg.generate_tts_for_episode(ep)
            results['tts'] = gen_files
        except Exception as e:
            results['tts'] = {}
            results['tts_error'] = str(e)

    return results


@app.post("/post_episode_promo", tags=["poster"])
def post_episode_promo(payload: dict, request: Request, authorization: Optional[str] = Header(None)):
    """Create a short promo social post for an existing episode_id.
    Body: {"episode_id": "ep1771353120", "persona": "support"}
    """
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    episode_id = payload.get('episode_id')
    persona = payload.get('persona', 'support')
    if not episode_id:
        raise HTTPException(status_code=400, detail="episode_id required in body")

    # load episodes
    try:
        import json
        from pathlib import Path
        eps_file = Path('podcast_mystical/episodes.json')
        if not eps_file.exists():
            raise HTTPException(status_code=404, detail="episodes.json not found")
        eps = json.loads(eps_file.read_text(encoding='utf-8'))
        ep = next((e for e in eps if e.get('id') == episode_id), None)
        if not ep:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read episodes: {e}")

    # Build trigger from episode metadata
    title = ep.get('title') or ''
    desc = ep.get('description') or ''
    trigger = f"Announcing new episode: {title} — {desc[:140]}"

    # Try to generate via the poster generator; if Claude missing, fall back to a simple template
    try:
        from revive_trio_poster import generate_post as gen
        text = gen(persona, trigger)
    except Exception:
        # Fallback promo
        link = ep.get('audio_url') or ep.get('cover') or ''
        text = f"New Mystical Revival Session: {title}\n{desc}\nListen: {link}\n#mysticalrevival"

    return {"text": text, "episode": {"id": ep.get('id'), "title": title}}


@app.get('/settings', tags=['dashboard'])
def get_settings(request: Request, authorization: Optional[str] = Header(None)):
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    cfg = Path('config') / 'settings.json'
    if not cfg.exists():
        # return defaults
        return {"post_daily": True, "platforms": ["moltbook"], "offers": [], "links": [], "tone": "supportive", "keywords": []}
    try:
        return json.loads(cfg.read_text(encoding='utf-8'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Could not read settings: {e}')


@app.post('/settings', tags=['dashboard'])
def update_settings(payload: dict, request: Request, authorization: Optional[str] = Header(None)):
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    cfgdir = Path('config')
    cfgdir.mkdir(exist_ok=True)
    cfg = cfgdir / 'settings.json'
    # load existing and merge
    try:
        existing = {}
        if cfg.exists():
            existing = json.loads(cfg.read_text(encoding='utf-8'))
        existing.update(payload)
        cfg.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
        return existing
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Could not write settings: {e}')


@app.get('/queue', tags=['dashboard'])
def list_queue(request: Request, authorization: Optional[str] = Header(None)):
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    qpath = Path('queue') / 'moltbook_posts.jsonl'
    if not qpath.exists():
        return {'items': []}
    items = []
    try:
        with qpath.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                items.append({'index': i, 'item': obj})
        return {'items': items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Could not read queue: {e}')


@app.post('/queue/approve', tags=['dashboard'])
def approve_queue_item(payload: dict, request: Request, authorization: Optional[str] = Header(None)):
    """Approve an item by index: {"index": 0}
    Approving sets `approved: true` on the queued object.
    """
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    idx = payload.get('index')
    if idx is None:
        raise HTTPException(status_code=400, detail='index required')
    qpath = Path('queue') / 'moltbook_posts.jsonl'
    if not qpath.exists():
        raise HTTPException(status_code=404, detail='queue not found')
    try:
        lines = qpath.read_text(encoding='utf-8').splitlines()
        if idx < 0 or idx >= len(lines):
            raise HTTPException(status_code=400, detail='index out of range')
        obj = json.loads(lines[idx])
        obj['approved'] = True
        lines[idx] = json.dumps(obj, ensure_ascii=False)
        qpath.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return {'ok': True, 'index': idx, 'item': obj}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Could not update queue: {e}')


@app.post('/queue/process', tags=['dashboard'])
def process_queue_endpoint(payload: dict, request: Request, authorization: Optional[str] = Header(None)):
    """Trigger processing of the Moltbook queue.
    Body: {"live": false, "limit": 10}
    """
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    live = bool(payload.get('live', False))
    limit = int(payload.get('limit', 20))
    try:
        # import worker
        from moltbook_queue import process_queue
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Could not import queue worker: {e}')

    try:
        processed = process_queue(dry_run=(not live), limit=limit)
        return {'processed': processed, 'live': live}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Queue processing failed: {e}')


@app.get('/decisions', tags=['dashboard'])
def list_decisions(request: Request, authorization: Optional[str] = Header(None)):
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    from pathlib import Path
    ddir = Path('logs')
    if not ddir.exists():
        return {'files': []}
    files = sorted([p.name for p in ddir.glob('decisions_*.json')], reverse=True)
    return {'files': files}


@app.get('/decisions/{name}', tags=['dashboard'])
def get_decision(name: str, request: Request, authorization: Optional[str] = Header(None)):
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    from pathlib import Path
    p = Path('logs') / name
    if not p.exists():
        raise HTTPException(status_code=404, detail='not found')
    try:
        import json
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Could not read decision: {e}')


@app.post('/decisions/enqueue', tags=['dashboard'])
def enqueue_from_decision(payload: dict, request: Request, authorization: Optional[str] = Header(None)):
    """Enqueue promo items from a decision log.
    Body: {"name":"decisions_123.json","only_unapproved":true}
    """
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail='Unauthorized')
    name = payload.get('name')
    only_unapproved = bool(payload.get('only_unapproved', True))
    if not name:
        raise HTTPException(status_code=400, detail='name required')
    from pathlib import Path
    p = Path('logs') / name
    if not p.exists():
        raise HTTPException(status_code=404, detail='not found')
    try:
        import json
        data = json.loads(p.read_text(encoding='utf-8'))
        enqueued = []
        # find enqueued promo items
        items = data.get('enqueued') or []
        # fallback: try decisions -> promo variants
        if not items:
            for d in data.get('decisions', []):
                if d.get('agent') == 'promo':
                    res = d.get('result', {})
                    variants = res.get('variants', [])
                    title = d.get('payload', {}).get('title', '')
                    link = d.get('payload', {}).get('link', '')
                    for v in variants:
                        items.append({'type':'link','submolt':'general','title':title,'url':link,'content':v,'next_attempt':0,'approved': False})

        # enqueue to queue file
        from moltbook_queue import enqueue as qenqueue
        for it in items:
            if only_unapproved and it.get('approved'):
                continue
            try:
                qenqueue(it)
                enqueued.append(it)
            except Exception:
                continue
        return {'enqueued': len(enqueued)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'could not enqueue: {e}')


@app.post("/openai_generate", tags=["openai"])
def openai_generate(payload: dict, request: Request, authorization: Optional[str] = Header(None)):
    """Call the provided OpenAI prompt ID (realtime/prompts) to generate an episode.
    Body: {"prompt_id":"pmpt_...","persona":"Curious Beginner","fmt":"micro_story","tts":true}
    Requires `OPENAI_API_KEY` set in environment.
    """
    if not authorize(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    prompt_id = payload.get('prompt_id')
    persona = payload.get('persona') or None
    fmt = payload.get('fmt') or None
    do_tts = bool(payload.get('tts', False))

    if not prompt_id:
        raise HTTPException(status_code=400, detail='prompt_id required')
    # read OPENAI key at runtime (safer if env changed after server start)
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        # fallback: try reading .env directly
        try:
            from dotenv import dotenv_values
            vals = dotenv_values('.env')
            openai_key = vals.get('OPENAI_API_KEY')
        except Exception:
            openai_key = None
    if not openai_key:
        raise HTTPException(status_code=400, detail='OPENAI_API_KEY not set in server environment')

    # Build request to OpenAI (using the prompt ID in a realtime/session POST payload)
    import requests, json

    url = 'https://api.openai.com/v1/realtime/sessions'
    headers = {
        'Authorization': f'Bearer {openai_key}',
        'Content-Type': 'application/json'
    }
    body = {
        'prompt': {
            'id': prompt_id,
            'version': '1'
        },
        'input': {
            'persona': persona,
            'format': fmt
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'OpenAI request failed: {e}')

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f'OpenAI error: {resp.status_code} {resp.text[:500]}')

    # Try to parse response text for structured JSON (the prompt may return JSON)
    text = ''
    try:
        data = resp.json()
        # Common places: data['output'] or data['result'] or data['choices']
        if isinstance(data, dict):
            # search for a textual output
            for k in ('output', 'result', 'choices', 'content', 'response'):
                if k in data:
                    text = json.dumps(data[k], ensure_ascii=False) if not isinstance(data[k], str) else data[k]
                    break
        if not text:
            text = json.dumps(data, ensure_ascii=False)
    except Exception:
        text = resp.text

    # Attempt to extract JSON object from returned text
    def extract_json(s):
        try:
            start = s.find('{')
            end = s.rfind('}')
            if start != -1 and end != -1 and end > start:
                return json.loads(s[start:end+1])
            # try array
            start = s.find('[')
            end = s.rfind(']')
            if start != -1 and end != -1 and end > start:
                return json.loads(s[start:end+1])
        except Exception:
            return None
        return None

    parsed = extract_json(text)
    title = None
    description = ''
    sections = []
    if isinstance(parsed, dict):
        title = parsed.get('title') or parsed.get('episode') or parsed.get('name')
        description = parsed.get('description') or parsed.get('summary') or ''
        sections = parsed.get('sections') or parsed.get('script_sections') or []
    elif isinstance(parsed, list):
        # if list of strings
        sections = parsed[:3]

    # Fallback: if no structured content, split text into up to 3 sections
    if not sections:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        # chunk heuristically
        if len(lines) >= 3:
            sections = ['\n'.join(lines[:1]), '\n'.join(lines[1:2]), '\n'.join(lines[2:4])]
        else:
            parts = text.split('\n\n')
            sections = [p.strip() for p in parts if p.strip()][:3]

    if not title:
        title = f"Session for {persona or 'Listener'}"
    if not sections:
        raise HTTPException(status_code=502, detail='Could not parse content from OpenAI response')

    # Append episode and optionally generate TTS
    try:
        import podcast_generator as pg
        ep = pg.append_episode(title, description, sections, fmt=fmt or 'guided')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error appending episode: {e}')

    tts_files = None
    if do_tts:
        try:
            tts_files = pg.generate_tts_for_episode(ep)
        except Exception as e:
            # non-fatal
            tts_files = {'error': str(e)}

    # Optionally assemble a faceless MP4 (static cover + audio)
    video_path = None
    try:
        import shutil, subprocess, pathlib, requests
        ffmpeg_bin = shutil.which('ffmpeg')
        if ffmpeg_bin and isinstance(tts_files, dict) and tts_files:
            # tts_files expected to be dict like {'en': [...]} or similar
            # find first mp3 path
            mp3 = None
            if isinstance(tts_files, dict):
                for v in tts_files.values():
                    if isinstance(v, list) and len(v) > 0:
                        mp3 = v[0]
                        break
            # normalize path
            if mp3 and mp3.startswith('podcast_mystical/'):
                mp3_fp = pathlib.Path(mp3)
            else:
                mp3_fp = pathlib.Path(mp3) if mp3 else None

            if mp3_fp and mp3_fp.exists():
                video_dir = pathlib.Path('podcast_mystical') / 'video'
                video_dir.mkdir(parents=True, exist_ok=True)
                cover_url = ep.get('cover') or ''
                cover_fp = video_dir / f"{ep['id']}_cover.jpg"
                # download cover if it's a URL
                try:
                    if cover_url and cover_url.startswith('http'):
                        r = requests.get(cover_url, timeout=10)
                        if r.status_code == 200:
                            cover_fp.write_bytes(r.content)
                    else:
                        # try copy from thumbnails
                        src = pathlib.Path(cover_url)
                        if src.exists():
                            cover_fp.write_bytes(src.read_bytes())
                except Exception:
                    pass

                mp4_fp = video_dir / f"{ep['id']}.mp4"
                try:
                    cmd = [ffmpeg_bin, '-y', '-loop', '1', '-i', str(cover_fp), '-i', str(mp3_fp), '-c:v', 'libx264', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-pix_fmt', 'yuv420p', str(mp4_fp)]
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    video_path = str(pathlib.Path('podcast_mystical') / 'video' / mp4_fp.name)
                    # attach to episode metadata
                    ep['video_url'] = video_path
                    # save back
                    eps_all = pg.load_episodes()
                    for e in eps_all:
                        if e.get('id') == ep.get('id'):
                            e.update(ep)
                    pg.save_episodes(eps_all)
                except Exception:
                    video_path = None
    except Exception:
        video_path = None

    return { 'episode': ep, 'tts': tts_files, 'video': video_path }
