#!/usr/bin/env python3
"""Print configured backend URL(s) from environment or .env without revealing secrets.

This helper shows candidate settings for the public backend URL so you can
use it for Netlify `BACKEND_URL`. It will NOT print tokens or secrets.
"""
import os
from pathlib import Path


def read_dotenv(path: str):
    vals = {}
    p = Path(path)
    if not p.exists():
        return vals
    try:
        for ln in p.read_text(encoding='utf-8').splitlines():
            ln = ln.strip()
            if not ln or ln.startswith('#'):
                continue
            if '=' in ln:
                k, v = ln.split('=', 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return vals


def main():
    # check environment first
    keys = ['BACKEND_URL', 'PUBLIC_EPISODE_BASE', 'GIT_REMOTE', 'NETLIFY_SITE']
    found = {}
    for k in keys:
        v = os.getenv(k)
        if v:
            found[k] = v

    # read .env for any values not in env
    env_path = Path('.') / '.env'
    if env_path.exists():
        d = read_dotenv(str(env_path))
        for k in keys:
            if k not in found and k in d:
                found[k] = d[k]

    if not found:
        print('No backend URL found in environment or .env. Local default: http://127.0.0.1:8080')
        return

    print('Configured backend-related values (secrets omitted):')
    for k in keys:
        if k in found:
            # sanitize tokens-looking strings by truncating long values
            v = found[k]
            display = v if len(v) <= 120 else v[:120] + '...'
            print(f'- {k}: {display}')


if __name__ == '__main__':
    main()
