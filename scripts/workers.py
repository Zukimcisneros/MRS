#!/usr/bin/env python3
"""Simple worker scaffolds: Content, Podcast, Promo, Analytics.

These expose callable functions that the `orchestrator` can import and use.
"""
from typing import Dict, Any
import time


def content_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    # payload might contain: persona, tone, keywords, prompt
    # Return a draft post
    persona = payload.get('persona', 'default')
    tone = payload.get('tone', 'supportive')
    title = payload.get('title') or f"Draft post for {persona}"
    body = payload.get('prompt') or f"A short post in {tone} tone. Keywords: {', '.join(payload.get('keywords', []))}"
    return {'type': 'content', 'persona': persona, 'title': title, 'body': body, 'created': int(time.time())}


def podcast_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    # payload: persona, fmt
    persona = payload.get('persona', 'Curious Beginner')
    fmt = payload.get('fmt', 'guided')
    # Reuse existing local generator if available
    try:
        import podcast_generator as pg
        title, description, sections = pg.generate_script(persona, fmt=fmt)
        return {'type': 'podcast', 'title': title, 'description': description, 'sections': sections}
    except Exception:
        # fallback
        return {'type': 'podcast', 'title': f'Session for {persona}', 'description': '', 'sections': ['Intro', 'Main', 'Close']}


def promo_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    # create CTA variations
    title = payload.get('title', '')
    link = payload.get('link', '')
    variants = [f"Listen to {title}: {link}", f"New episode — {title}. Hear it here: {link}"]
    return {'type': 'promo', 'variants': variants}


def analytics_agent(metrics_store_path: str = 'memory/analytics.json') -> Dict[str, Any]:
    # Simple analytics reader that summarizes stored metrics
    try:
        import json
        from pathlib import Path
        p = Path(metrics_store_path)
        if not p.exists():
            return {'summary': {}, 'count': 0}
        data = json.loads(p.read_text(encoding='utf-8'))
        # naive summary: counts per event
        counts = {}
        for ev in data:
            k = ev.get('event') or 'unknown'
            counts[k] = counts.get(k, 0) + 1
        return {'summary': counts, 'count': len(data)}
    except Exception:
        return {'summary': {}, 'count': 0}


if __name__ == '__main__':
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument('--demo', action='store_true')
    args = p.parse_args()
    if args.demo:
        print('Content demo:', content_agent({'persona':'Demo','keywords':['mystical']}))
        print('Podcast demo:', podcast_agent({'persona':'Demo'}))
        print('Promo demo:', promo_agent({'title':'Demo Ep','link':'https://example.com'}))