"""Cup fixture back-fill from the broadcast listings.

Why this exists
---------------
football-data.org's catalogue is thirteen league/international competitions
(PL, ELC, CL, EC, WC, CLI + eight foreign leagues). Domestic cups — FA Cup
and the League/Carabao Cup — are not in it at any tier, so a cup tie simply
never arrives from the fixtures API and the display silently skips it.

The broadcast listings page we already fetch and parse DOES carry cup ties,
with date, kickoff, both teams, competition and channels. Until now every
listing row that didn't match an API fixture was discarded by join.py. This
module promotes those orphan rows into synthetic fixtures so they flow
through the normal pipeline — including the broadcast join, which is
guaranteed to match because the fixture came from the listings in the
first place.

Known limitation (state it in the README, don't paper over it)
--------------------------------------------------------------
Only *televised* cup ties appear on the listings page. An untelevised cup
fixture is still invisible. This is a genuine hole, not a bug: absence from
listings means "not on TV", never "no fixture" — which is exactly why this
merge is additive and never removes or overrides an API fixture.

Synthetic fixtures carry:
  - a negative fixture id, so they can never collide with a real one
  - our team's real id (crest resolves) and None for the opponent
    (full.liquid already falls back to initials when crest is null)
  - an empty round string — listings don't carry round information
"""
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from . import config

log = logging.getLogger(__name__)

LONDON = ZoneInfo(config.TZ)

# Rows for other Liverpool sides on the same club page.
EXCLUDE_TEAM_TOKENS = ("women", "u21", "u23", "u18", "academy", "ladies")


def _is_our_team(name: str) -> bool:
    n = name.casefold()
    if any(tok in n for tok in EXCLUDE_TEAM_TOKENS):
        return False
    ours = config.TEAM_NAME.casefold()
    return ours in n or n in ours


def _kick_utc(row: dict) -> dt.datetime | None:
    try:
        hh, mm = (int(x) for x in row["time"].split(":"))
    except (ValueError, KeyError):
        return None
    local = dt.datetime.combine(row["date"], dt.time(hh, mm), tzinfo=LONDON)
    return local.astimezone(dt.timezone.utc)


def _synth(row: dict, kick_utc: dt.datetime) -> dict | None:
    home_is_ours = _is_our_team(row["home"])
    away_is_ours = _is_our_team(row["away"])
    if home_is_ours == away_is_ours:
        # Neither side is us, or a self-match — the club page shouldn't
        # produce either. Skip rather than guess.
        return None

    def side(name: str, ours: bool) -> dict:
        return {"id": config.TEAM_ID if ours else None, "name": name,
                "winner": None}

    # Stable negative id derived from the natural key, so repeated refreshes
    # of the same tie produce the same id.
    fid = -abs(hash((row["date"].isoformat(), row["time"], row["home"],
                     row["away"]))) % (10 ** 9) - 1

    return {
        "fixture": {
            "id": fid,
            "date": kick_utc.isoformat(),
            "timestamp": None,
            "venue": {"id": None, "name": "", "city": ""},
            "status": {"long": "SCHEDULED", "short": "NS", "elapsed": None},
        },
        "league": {
            "id": None,
            "name": row.get("competition") or "",
            "country": "England",
            "season": None,
            "round": "",
        },
        "teams": {
            "home": side(row["home"], home_is_ours),
            "away": side(row["away"], away_is_ours),
        },
        "goals": {"home": None, "away": None},
        "_source": "cup-fill",
    }


def merge(raw_fixtures: list[dict], listings: list[dict] | None) -> list[dict]:
    """Return raw_fixtures plus synthetic fixtures for orphan listing rows.

    Never mutates or drops an API fixture. Dedupe is on local match DATE:
    a side does not play twice in a day, and date is the one field both
    sources agree on even when a kickoff time has been moved.
    """
    if not listings or not config.CUP_FILL_COMPS:
        return raw_fixtures

    known_dates: set[dt.date] = set()
    for fx in raw_fixtures:
        try:
            k = dt.datetime.fromisoformat(fx["fixture"]["date"])
        except (KeyError, ValueError):
            continue
        known_dates.add(k.astimezone(LONDON).date())

    wanted = {c.casefold() for c in config.CUP_FILL_COMPS}
    added: list[dict] = []

    for row in listings:
        comp = (row.get("competition") or "").casefold()
        if comp not in wanted:
            continue
        if row["date"] in known_dates:
            continue
        kick = _kick_utc(row)
        if kick is None:
            continue
        fx = _synth(row, kick)
        if fx is None:
            continue
        added.append(fx)
        known_dates.add(row["date"])

    if added:
        log.info("cup-fill added %d fixture(s) absent from the fixtures API: %s",
                 len(added),
                 ", ".join(f'{f["league"]["name"]} {f["fixture"]["date"][:10]}'
                           for f in added))
    return raw_fixtures + added
