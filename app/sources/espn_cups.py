"""Domestic cup fixtures from ESPN's public site API.

football-data.org carries no domestic cups at any tier. ESPN's (unofficial,
keyless) site API does, per competition:

    https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/teams/{id}/schedule?fixture=true

Verified on the NAS 2026-10-14: team 364 resolves to "Liverpool", and the
15 Sep 2026 League Cup tie v Tottenham (the fixture that went missing from
the display) is present under eng.league_cup.

This is a GAP-FILLER, never the primary source: an undocumented API can
change without notice, so a failure here costs only cup ties. The caller
catches every exception and keeps the last good result.

Output is the API-Football fixture shape that normalise.py already consumes.
Our own side carries config.TEAM_ID (the football-data.org id) so the crest
pipeline resolves; the opponent's id is None, so full.liquid falls back to
initials — the same behaviour as the listings back-fill.
"""
import json
import logging
import os

import requests

from .. import config

log = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# ESPN league slug → competition name as normalise.py/join.py expect it.
# "League Cup" is mapped to "Carabao Cup" by normalise.COMP_DISPLAY, and is
# in join.DOMESTIC_COMPS, so the 3pm blackout logic applies unchanged.
LEAGUE_NAMES = {
    "eng.league_cup": "League Cup",
    "eng.fa": "FA Cup",
    "eng.charity": "Community Shield",
}


def _translate(event: dict, league_name: str) -> dict | None:
    comps = event.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]

    status = (comp.get("status") or event.get("status") or {}).get("type", {})
    if status.get("completed"):
        return None

    sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    if "home" not in sides or "away" not in sides:
        return None

    def side(c: dict) -> dict:
        team = c.get("team", {})
        ours = str(team.get("id")) == str(config.ESPN_TEAM_ID)
        return {
            "id": config.TEAM_ID if ours else None,
            "name": config.TEAM_NAME if ours else (
                team.get("shortDisplayName") or team.get("displayName") or "?"),
            "winner": None,
        }

    venue = comp.get("venue") or {}
    notes = comp.get("notes") or []
    round_str = (notes[0].get("headline") if notes else "") or ""

    # ESPN sets timeValid=false when only the date is fixed.
    tbd = comp.get("timeValid") is False

    try:
        eid = int(event.get("id"))
    except (TypeError, ValueError):
        eid = 0

    return {
        "fixture": {
            "id": -abs(eid) - 1,            # negative: can never collide with a real id
            "date": event.get("date", ""),
            "timestamp": None,
            "venue": {"id": None,
                      "name": venue.get("fullName") or "",
                      "city": (venue.get("address") or {}).get("city", "")},
            "status": {"long": status.get("name", ""),
                       "short": "TBD" if tbd else "NS", "elapsed": None},
        },
        "league": {"id": None, "name": league_name, "country": "England",
                   "season": None, "round": round_str},
        "teams": {"home": side(sides["home"]), "away": side(sides["away"])},
        "goals": {"home": None, "away": None},
        "_source": "espn",
    }


def _fetch_league(slug: str) -> list[dict]:
    if config.FIXTURES_SOURCE == "stub":
        path = os.path.join(config.STUB_DIR, f"espn_{slug.replace('.', '_')}.json")
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            data = json.load(fh)
    else:
        r = requests.get(
            f"{BASE}/{slug}/teams/{config.ESPN_TEAM_ID}/schedule",
            params={"fixture": "true"},
            headers={"User-Agent": config.ESPN_USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

    name = LEAGUE_NAMES.get(slug, slug)
    out = []
    for ev in data.get("events") or []:
        fx = _translate(ev, name)
        if fx is not None:
            out.append(fx)
    return out


def fetch_cup_fixtures() -> list[dict]:
    """All upcoming cup fixtures across config.ESPN_CUP_LEAGUES.

    Raises if EVERY league fails, so the caller can keep its last good
    result; a single failing league is logged and skipped."""
    out: list[dict] = []
    errors = 0
    for slug in config.ESPN_CUP_LEAGUES:
        try:
            out.extend(_fetch_league(slug))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log.warning("espn %s fetch failed: %s", slug, exc)
    if config.ESPN_CUP_LEAGUES and errors == len(config.ESPN_CUP_LEAGUES):
        raise RuntimeError("all ESPN cup fetches failed")
    return out
