"""trmnl-football-fixtures sidecar API.

GET /fixtures         → §3 payload (3 h cache; serve-stale-with-flag on upstream error)
GET /crest/<id>.png   → 1-bit processed crest
GET /healthz          → liveness + cache state
"""
import json
import logging
import os
import threading
import time

from flask import Flask, abort, jsonify, send_file

from . import config, crests, normalise
from .sources import football_data

try:
    from .sources import broadcast_html
except Exception:  # bs4 missing etc. — broadcast is optional garnish
    broadcast_html = None

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")

app = Flask(__name__)

LAST_GOOD_FILE = os.path.join(config.CACHE_DIR, "last_good.json")
_lock = threading.Lock()
_state = {"fetched_at": 0.0, "raw_fixtures": None, "listings": None,
          "listings_ok": False}


def _load_last_good():
    try:
        with open(LAST_GOOD_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _save_last_good(raw_fixtures):
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(LAST_GOOD_FILE, "w") as fh:
            json.dump(raw_fixtures, fh)
    except OSError as exc:
        log.warning("could not persist last-good fixtures: %s", exc)


def _refresh_if_due() -> bool:
    """Refresh upstream data if the TTL has lapsed. Returns stale flag."""
    with _lock:
        age = time.time() - _state["fetched_at"]
        if _state["raw_fixtures"] is not None and age < config.CACHE_TTL:
            return False

        stale = False
        try:
            raw = football_data.fetch_next_fixtures()
            _state["raw_fixtures"] = raw
            _state["fetched_at"] = time.time()
            _save_last_good(raw)
        except Exception as exc:  # noqa: BLE001
            log.error("fixtures fetch failed: %s", exc)
            if _state["raw_fixtures"] is None:
                _state["raw_fixtures"] = _load_last_good()
            stale = True
            # Back off 10 min before retrying upstream, never a tight loop.
            _state["fetched_at"] = time.time() - config.CACHE_TTL + 600

        _state["listings"] = None
        _state["listings_ok"] = False
        if config.ENABLE_BROADCAST and broadcast_html is not None:
            try:
                html = broadcast_html.fetch_listings_html()
                _state["listings"] = broadcast_html.parse_listings(html)
                _state["listings_ok"] = True
            except Exception as exc:  # noqa: BLE001 — fail soft to tbc
                log.error("broadcast fetch/parse failed (fail-soft to tbc): %s", exc)
        return stale


@app.get("/fixtures")
def fixtures():
    stale = _refresh_if_due()
    raw = _state["raw_fixtures"]
    if raw is None:
        return jsonify({"generated_display": "", "sources": {}, "stale": True,
                        "next": None, "on_deck": [],
                        "error": "no fixture data available"}), 503
    payload = normalise.build_payload(
        raw, _state["listings"],
        stale=stale or (time.time() - _state["fetched_at"] > config.CACHE_TTL * 2),
        broadcast_enabled=config.ENABLE_BROADCAST and _state["listings_ok"],
    )
    return jsonify(payload)


@app.get("/crest/<int:team_id>.png")
def crest(team_id: int):
    path = crests.get_crest(team_id)
    if path is None:
        abort(404)
    return send_file(path, mimetype="image/png", max_age=86400)


@app.get("/healthz")
def healthz():
    return jsonify({
        "ok": True,
        "fixtures_cached": _state["raw_fixtures"] is not None,
        "cache_age_s": int(time.time() - _state["fetched_at"]) if _state["fetched_at"] else None,
        "broadcast_enabled": config.ENABLE_BROADCAST,
        "listings_ok": _state["listings_ok"],
        "source": config.FIXTURES_SOURCE,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3458")))
