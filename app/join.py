"""Fixture ↔ broadcast join.

Key is (local date, local HH:MM) — team names differ between sources
("AFC Bournemouth" vs "Bournemouth") and are unreliable as a key (plan §9 P3).
Broadcast data joins ONTO the API-Football fixture list, never the reverse:
absence from listings means "not televised", not "no fixture" (plan §5.2).
"""
import datetime as dt
from zoneinfo import ZoneInfo

from . import config
from .channels import split_broadcast

LONDON = ZoneInfo(config.TZ)

# Competitions subject to the UK Saturday 3pm blackout window.
DOMESTIC_COMPS = {"Premier League", "Championship", "League One", "League Two",
                  "FA Cup", "League Cup", "Carabao Cup", "EFL Cup"}

# Competitions where "no listing" carries no meaning at all (plan state `none`).
NO_BROADCAST_CONCEPT = {"Club Friendlies", "Friendly", "Friendlies"}


def _local(kick_utc: dt.datetime) -> dt.datetime:
    return kick_utc.astimezone(LONDON)


def _in_blackout_window(local: dt.datetime) -> bool:
    """Saturday, kickoff inside the 14:45–17:15 UK closed period."""
    if local.weekday() != 5:
        return False
    mins = local.hour * 60 + local.minute
    return 14 * 60 + 45 <= mins <= 17 * 60 + 15


def broadcast_for(fixture_kick_utc: dt.datetime, competition: str,
                  listings: list[dict] | None) -> dict:
    """Return the §3 broadcast object for one fixture.

    listings=None means the broadcast source is disabled or failed →
    state "none" for friendlies, "tbc" otherwise (fail-soft)."""
    none = {"state": "none", "primary": None, "others": [],
            "owned": False, "status_label": None, "note": None}

    if competition in NO_BROADCAST_CONCEPT and listings is None:
        return none

    if listings is None:
        return {**none, "state": "tbc"}

    local = _local(fixture_kick_utc)
    key = (local.date(), local.strftime("%H:%M"))
    for row in listings:
        if (row["date"], row["time"]) == key:
            return split_broadcast(row["channels"])

    # No listing row for a real fixture:
    if _in_blackout_window(local) and competition in DOMESTIC_COMPS:
        return {**none, "state": "blackout",
                "note": "3pm Saturday blackout"}
    if competition in NO_BROADCAST_CONCEPT:
        return none
    return {**none, "state": "tbc"}
