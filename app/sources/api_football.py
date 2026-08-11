"""API-Football v3 client. One call per refresh cycle; stub mode reads a saved
response from disk so the whole pipeline runs offline (dev, demo, tests)."""
import json
import logging
import os

import requests

from .. import config

log = logging.getLogger(__name__)


class UpstreamError(Exception):
    pass


def fetch_next_fixtures() -> list[dict]:
    """Return the raw `response` array from /fixtures?team=&next=."""
    if config.FIXTURES_SOURCE == "stub":
        path = os.path.join(config.STUB_DIR, "api_football_next6.json")
        with open(path) as fh:
            return json.load(fh)["response"]

    if not config.API_FOOTBALL_KEY:
        raise UpstreamError("API_FOOTBALL_KEY not set")

    r = requests.get(
        f"{config.API_FOOTBALL_BASE}/fixtures",
        params={"team": config.TEAM_ID, "next": config.FIXTURE_COUNT},
        headers={"x-apisports-key": config.API_FOOTBALL_KEY},
        timeout=15,
    )
    if r.status_code != 200:
        raise UpstreamError(f"api-football HTTP {r.status_code}")
    body = r.json()
    if body.get("errors"):
        # API-Football signals quota/auth problems inside a 200 body.
        raise UpstreamError(f"api-football errors: {body['errors']}")
    return body.get("response", [])
