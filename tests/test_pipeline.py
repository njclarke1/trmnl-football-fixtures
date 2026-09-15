"""Pipeline tests covering both the football-data.org translation layer and
all five broadcast.state values.
Run: FIXTURES_SOURCE=stub TEAM_ID=64 python -m pytest tests/ -q
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FIXTURES_SOURCE", "stub")
os.environ.setdefault("CACHE_DIR", "/tmp/tff-cache")
os.environ.setdefault("TEAM_ID", "64")

from app import join, normalise  # noqa: E402
from app.channels import split_broadcast  # noqa: E402
from app.sources.broadcast_html import parse_listings  # noqa: E402
from app.sources.football_data import fetch_next_fixtures, _translate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = dt.datetime(2026, 8, 11, 8, 14, tzinfo=dt.timezone.utc)


def _fixtures():
    """Load stub fixtures via the football_data translation layer."""
    return fetch_next_fixtures()


def _raw_fd():
    """Raw football-data.org response (untranslated)."""
    with open(os.path.join(HERE, "fixtures", "football_data_scheduled.json")) as fh:
        return json.load(fh)


def _listings():
    real = os.path.join(HERE, "fixtures", "real_listings.html")
    path = real if os.path.exists(real) else os.path.join(HERE, "fixtures", "listings_sample.html")
    with open(path) as fh:
        return parse_listings(fh.read())


# --- translation layer ---

def test_translate_shape():
    """football-data.org match → API-Football fixture shape."""
    raw = _raw_fd()["matches"][0]
    fx = _translate(raw)
    assert fx["fixture"]["date"] == "2026-08-23T15:30:00Z"
    assert fx["fixture"]["venue"]["name"] == "St James' Park"
    assert fx["fixture"]["status"]["short"] == "NS"
    assert fx["league"]["name"] == "Premier League"
    assert fx["league"]["round"] == "Regular Season - 2"
    assert fx["teams"]["home"]["name"] == "Newcastle United"
    assert fx["teams"]["away"]["name"] == "Liverpool"
    assert fx["teams"]["home"]["id"] == 67
    assert fx["teams"]["away"]["id"] == 64


def test_translate_all_stubs():
    fxs = _fixtures()
    assert len(fxs) == 5
    assert all(f["fixture"]["status"]["short"] == "NS" for f in fxs)


# --- broadcast ---

def test_parser_row_count_and_channels():
    rows = _listings()
    assert len(rows) >= 6
    ncl = next(r for r in rows if "Newcastle" in r["home"])
    assert ncl["date"] == dt.date(2026, 8, 23)
    assert ncl["time"] == "16:30"
    assert ncl["competition"] == "Premier League"
    assert ncl["channels"] == [
        "Sky Sports Main Event", "Sky Sports Premier League", "Sky Sports Ultra HDR"]


def test_state_available():
    assert split_broadcast(["Sky Sports Main Event"])["state"] == "available"
    b = split_broadcast(["HBO Max", "TNT Sports 1"])
    assert b["state"] == "available" and b["primary"] == "TNT Sports 1"


def test_state_unavailable():
    b = split_broadcast(["LFCTV", "All Red Video"])
    assert b["state"] == "unavailable" and b["status_label"] == "Not on your channels"


def test_state_blackout():
    k = dt.datetime(2026, 9, 26, 14, 0, tzinfo=dt.timezone.utc)
    assert join.broadcast_for(k, "Premier League", _listings())["state"] == "blackout"


def test_state_tbc():
    k = dt.datetime(2026, 10, 21, 19, 0, tzinfo=dt.timezone.utc)
    assert join.broadcast_for(k, "Champions League", _listings())["state"] == "tbc"


def test_state_none():
    k = dt.datetime(2026, 7, 20, 14, 0, tzinfo=dt.timezone.utc)
    assert join.broadcast_for(k, "Friendly", None)["state"] == "none"


# --- payload contract ---

def test_payload_contract():
    p = normalise.build_payload(_fixtures(), _listings(), now=NOW)
    n = p["next"]
    assert n["competition"] == "Premier League"
    assert n["home"]["name"] == "Newcastle United"
    assert n["broadcast"]["state"] == "available"
    assert len(p["on_deck"]) == 3
    assert p["on_deck"][0]["opponent"] == "Nott'm Forest"
    assert p["on_deck"][0]["channel_short"] == "TNT 1" and p["on_deck"][0]["owned"]


def test_matchday_hold_and_rollover():
    fxs = _fixtures()
    # 90 min after Newcastle 16:30 BST (15:30 UTC) kickoff — hold=120
    during = dt.datetime(2026, 8, 23, 17, 0, tzinfo=dt.timezone.utc)
    p = normalise.build_payload(fxs, _listings(), now=during)
    assert p["next"]["home"]["name"] == "Newcastle United"
    # 3h after — rolls to Forest
    after = dt.datetime(2026, 8, 23, 18, 31, tzinfo=dt.timezone.utc)
    p = normalise.build_payload(fxs, _listings(), now=after)
    assert p["next"]["home"]["name"] == "Liverpool"
    assert p["next"]["away"]["name"] == "Nottingham Forest"


def test_round_display():
    p = normalise.build_payload(_fixtures(), _listings(), now=NOW)
    assert p["next"]["round"] == "Matchweek 2"


def test_empty_state():
    p = normalise.build_payload([], None, now=NOW)
    assert p["next"] is None and p["on_deck"] == []


def test_broadcast_disabled_falls_to_tbc():
    p = normalise.build_payload(_fixtures(), None, now=NOW, broadcast_enabled=False)
    assert p["on_deck"][0]["channel_short"] == "TBC"


# --- cup back-fill (football-data.org carries no domestic cups) -------------

def _cup_row(date, time="19:45", comp="League Cup",
             home="Liverpool", away="Grimsby Town",
             channels=("Sky Sports Main Event",)):
    return {"date": date, "time": time, "home": home, "away": away,
            "competition": comp, "channels": list(channels)}


def test_cupfill_promotes_orphan_cup_tie():
    """A televised cup tie absent from the fixtures API must appear, with
    its broadcast data joined in the normal way."""
    listings = _listings() + [_cup_row(dt.date(2026, 8, 12))]
    p = normalise.build_payload(_fixtures(), listings, now=NOW)
    assert p["sources"]["cup_fill"] == 1
    nxt = p["next"]
    assert nxt["competition"] == "Carabao Cup"        # COMP_DISPLAY maps it
    assert nxt["away"]["name"] == "Grimsby Town"
    assert nxt["home"]["crest"] is not None           # our side resolves
    assert nxt["away"]["crest"] is None               # opponent → initials
    assert nxt["broadcast"]["state"] == "available"
    assert nxt["broadcast"]["owned"] is True


def test_cupfill_never_duplicates_an_api_fixture():
    """Same-date dedupe: an API fixture always wins, even if the listings
    row disagrees on kickoff time."""
    api = _fixtures()
    first = min(dt.datetime.fromisoformat(f["fixture"]["date"]) for f in api)
    clash = _cup_row(first.date(), time="23:59", comp="FA Cup")
    p = normalise.build_payload(api, _listings() + [clash], now=NOW)
    assert p["sources"]["cup_fill"] == 0


def test_cupfill_ignores_non_cup_and_other_squads():
    listings = [
        _cup_row(dt.date(2026, 8, 12), comp="Premier League"),
        _cup_row(dt.date(2026, 8, 13), home="Liverpool Women",
                 away="Arsenal Women"),
    ]
    p = normalise.build_payload(_fixtures(), listings, now=NOW)
    assert p["sources"]["cup_fill"] == 0
