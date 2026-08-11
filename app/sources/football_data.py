"""football-data.org v4 client.

Replaces API-Football (free tier locked to seasons 2022–2024).
football-data.org free tier covers PL + CL current season, forever, no
credit card. FA Cup and League Cup are paid-only — cup fixtures will be
absent from the API but still appear on the broadcast listings page.

Translates the v4 response into the same shape normalise.py already
consumes (the API-Football fixture shape), so the rest of the pipeline
is untouched.

Rate limiting (per registration email): the API returns
X-Requests-Available-Minute in response headers. Free tier = 10 req/min.
With a 3h cache we'll never hit this, but the header is logged on low
values to aid debugging during development.
"""
import json
import logging
import os

import requests

from .. import config

log = logging.getLogger(__name__)

BASE = "https://api.football-data.org/v4"

# football-data.org stage strings → API-Football-style round strings
# that normalise.py's ROUND_DISPLAY rules already handle.
STAGE_MAP = {
    "REGULAR_SEASON": "Regular Season",
    "LEAGUE_STAGE": "League Stage",
    "GROUP_STAGE": "Group Stage",
    "LAST_16": "Round of 16",
    "QUARTER_FINALS": "Quarter-finals",
    "SEMI_FINALS": "Semi-finals",
    "FINAL": "Final",
    "PRELIMINARY_ROUND": "Preliminary Round",
    "PRELIMINARY_SEMI_FINALS": "Preliminary Semi-finals",
    "PRELIMINARY_FINAL": "Preliminary Final",
    "QUALIFICATION": "Qualification",
    "QUALIFICATION_ROUND_1": "Qualification Round 1",
    "QUALIFICATION_ROUND_2": "Qualification Round 2",
    "QUALIFICATION_ROUND_3": "Qualification Round 3",
    "PLAY_OFF_ROUND": "Play-off Round",
    "ROUND_OF_16": "Round of 16",
    "1ST_QUALIFYING_ROUND": "1st Qualifying Round",
    "2ND_QUALIFYING_ROUND": "2nd Qualifying Round",
    "3RD_QUALIFYING_ROUND": "3rd Qualifying Round",
    "PLAYOFFS": "Play-offs",
}

# football-data.org status → API-Football short status code
STATUS_MAP = {
    "SCHEDULED": "NS",
    "TIMED": "NS",
    "IN_PLAY": "1H",
    "PAUSED": "HT",
    "FINISHED": "FT",
    "POSTPONED": "PST",
    "SUSPENDED": "SUSP",
    "CANCELLED": "CANC",
    "AWARDED": "AWD",
}


class UpstreamError(Exception):
    pass


def _round_string(match: dict) -> str:
    """Build a round string that normalise.py's ROUND_DISPLAY can parse."""
    stage = STAGE_MAP.get(match.get("stage", ""), match.get("stage", ""))
    md = match.get("matchday")
    if md and stage in ("Regular Season", "League Stage", "Group Stage"):
        return f"{stage} - {md}"
    return stage


def _translate(match: dict) -> dict:
    """Translate a football-data.org v4 match object into the API-Football
    fixture shape that normalise.py expects."""
    home = match.get("homeTeam", {})
    away = match.get("awayTeam", {})
    score = match.get("score", {})
    ft = score.get("fullTime", {}) if score else {}

    return {
        "fixture": {
            "id": match.get("id"),
            "date": match.get("utcDate", ""),
            "timestamp": None,
            "venue": {
                "id": None,
                "name": match.get("venue") or "",
                "city": "",
            },
            "status": {
                "long": match.get("status", ""),
                "short": STATUS_MAP.get(match.get("status", ""), "NS"),
                "elapsed": None,
            },
        },
        "league": {
            "id": match.get("competition", {}).get("id"),
            "name": match.get("competition", {}).get("name", ""),
            "country": match.get("area", {}).get("name", ""),
            "season": None,
            "round": _round_string(match),
        },
        "teams": {
            "home": {
                "id": home.get("id"),
                "name": home.get("shortName") or home.get("name", ""),
                "winner": None,
            },
            "away": {
                "id": away.get("id"),
                "name": away.get("shortName") or away.get("name", ""),
                "winner": None,
            },
        },
        "goals": {
            "home": ft.get("home"),
            "away": ft.get("away"),
        },
    }


def fetch_next_fixtures() -> list[dict]:
    """Return translated fixtures in the API-Football shape."""
    if config.FIXTURES_SOURCE == "stub":
        path = os.path.join(config.STUB_DIR, "football_data_scheduled.json")
        with open(path) as fh:
            data = json.load(fh)
        return [_translate(m) for m in data.get("matches", [])]

    if not config.FOOTBALL_DATA_TOKEN:
        raise UpstreamError("FOOTBALL_DATA_TOKEN not set")

    url = f"{BASE}/teams/{config.TEAM_ID}/matches"
    params = {"status": "SCHEDULED", "limit": config.FIXTURE_COUNT}

    r = requests.get(
        url,
        params=params,
        headers={
            "X-Auth-Token": config.FOOTBALL_DATA_TOKEN,
            "User-Agent": config.USER_AGENT,
        },
        timeout=15,
    )

    # Rate limit awareness (per registration email).
    avail = r.headers.get("X-Requests-Available-Minute")
    if avail is not None and int(avail) < 3:
        log.warning("football-data.org rate limit low: %s req/min remaining", avail)

    if r.status_code == 429:
        raise UpstreamError("football-data.org rate limited (429)")
    if r.status_code != 200:
        raise UpstreamError(f"football-data.org HTTP {r.status_code}: {r.text[:200]}")

    body = r.json()
    matches = body.get("matches", [])
    return [_translate(m) for m in matches]
