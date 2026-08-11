"""Render full.liquid against payloads for all four states -> demo HTML.
Also serves as a Liquid syntax check. Run from repo root:
    FIXTURES_SOURCE=stub python plugin/demo/render_demo.py
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("FIXTURES_SOURCE", "stub")
os.environ.setdefault("CACHE_DIR", "/tmp/tff-cache")

from liquid import Environment
from app import normalise
from app.sources.broadcast_html import parse_listings

env = Environment()
tpl = env.from_string(open("plugin/full.liquid").read())
raw = json.load(open("tests/fixtures/api_football_next6.json"))["response"]
listings = parse_listings(open("tests/fixtures/listings_sample.html").read())
U = dt.timezone.utc

states = {
    "state1_league_sky": normalise.build_payload(raw, listings, now=dt.datetime(2026, 8, 17, 9, 0, tzinfo=U)),
    "state2_unavailable": normalise.build_payload(raw, listings, now=dt.datetime(2026, 8, 11, 8, 14, tzinfo=U)),
    "state3_blackout": normalise.build_payload(raw, listings, now=dt.datetime(2026, 9, 21, 9, 0, tzinfo=U)),
    "state4_empty": normalise.build_payload([], None, now=dt.datetime(2026, 8, 11, 8, 14, tzinfo=U)),
}

frame = ('<meta charset="utf-8"><body style="background:#3a3a3a;display:flex;flex-direction:column;'
         'align-items:center;gap:24px;padding:24px">{}</body>')
for name, payload in states.items():
    if payload["next"]:
        payload["next"]["home"]["crest"] = None
        payload["next"]["away"]["crest"] = None
    html = tpl.render(**payload)
    out = f"plugin/demo/{name}.html"
    open(out, "w").write(frame.format(html))
    n = payload["next"]
    desc = f'{n["home"]["name"]} v {n["away"]["name"]} | bc={n["broadcast"]["state"]}' if n else "EMPTY"
    print(f"{out}: {desc}")
