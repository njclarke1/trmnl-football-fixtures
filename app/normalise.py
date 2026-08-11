"""Build the flat, pre-formatted §3 payload. All date maths lives here in
Python with zoneinfo — Liquid does presentation only."""
import datetime as dt
from zoneinfo import ZoneInfo

from . import config, join
from .channels import short_name
from .shortnames import initials, is_long, rail_name

LONDON = ZoneInfo(config.TZ)

COMP_DISPLAY = {
    "UEFA Champions League": "Champions League",
    "UEFA Europa League": "Europa League",
    "UEFA Europa Conference League": "Conference League",
    "Club Friendlies": "Friendly",
    "FIFA Club World Cup": "Club World Cup",
    "League Cup": "Carabao Cup",
    "EFL Cup": "Carabao Cup",
}

ROUND_DISPLAY = [
    ("Regular Season - ", "Matchweek "),
    ("League Stage - ", "League phase · MD"),
    ("League Phase - ", "League phase · MD"),
]


def _display_round(raw: str | None) -> str:
    if not raw:
        return ""
    for prefix, repl in ROUND_DISPLAY:
        if raw.startswith(prefix):
            return repl + raw[len(prefix):]
    return raw


def _countdown(kick_local: dt.datetime, now_local: dt.datetime) -> str:
    days = (kick_local.date() - now_local.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Tomorrow"
    return f"In {days} days"


def _crest_url(team_id: int | None) -> str | None:
    if team_id is None:
        return None
    return f"{config.PUBLIC_BASE_URL}/crest/{team_id}.png"


def _team(obj: dict) -> dict:
    name = obj.get("name", "?")
    return {
        "name": name,
        "short": rail_name(name),
        "long": is_long(name),
        "initials": initials(name),
        "crest": _crest_url(obj.get("id")),
    }


def _kickoff_utc(fx: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(fx["fixture"]["date"]).astimezone(dt.timezone.utc)


def _tbc(fx: dict) -> bool:
    # API-Football: status "TBD" = date known, time not confirmed.
    return fx["fixture"].get("status", {}).get("short") == "TBD"


def build_payload(raw_fixtures: list[dict], listings: list[dict] | None,
                  now: dt.datetime | None = None, stale: bool = False,
                  broadcast_enabled: bool = True) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    now_local = now.astimezone(LONDON)

    # Hold the current fixture through kickoff + N minutes (plan §12.1) —
    # a blank flip mid-match is worse than a slightly stale card.
    hold = dt.timedelta(minutes=config.HOLD_PAST_KICKOFF_MIN)
    upcoming = sorted(
        (fx for fx in raw_fixtures if _kickoff_utc(fx) + hold > now),
        key=_kickoff_utc,
    )

    payload = {
        "generated_display": now_local.strftime("%-d %b, %H:%M"),
        "sources": {
            "fixtures": "api-football" if config.FIXTURES_SOURCE == "api" else "stub",
            "broadcast": "uk-listings" if broadcast_enabled else "disabled",
        },
        "stale": stale,
        "team": config.TEAM_NAME,
        "team_initials": initials(config.TEAM_NAME),
        "next": None,
        "on_deck": [],
    }
    if not upcoming:
        return payload

    fx = upcoming[0]
    kick_utc = _kickoff_utc(fx)
    kick_local = kick_utc.astimezone(LONDON)
    comp_raw = fx["league"]["name"]
    comp = COMP_DISPLAY.get(comp_raw, comp_raw)
    is_home = fx["teams"]["home"]["id"] == config.TEAM_ID
    tbc = _tbc(fx)
    bc = join.broadcast_for(kick_utc, comp, listings)

    payload["next"] = {
        "competition": comp,
        "round": _display_round(fx["league"].get("round")),
        "is_home": is_home,
        "venue_tag": "Home" if is_home else "Away",
        "home": _team(fx["teams"]["home"]),
        "away": _team(fx["teams"]["away"]),
        "day": kick_local.strftime("%A"),
        "date": kick_local.strftime("%-d %b"),
        "time": "TBC" if tbc else kick_local.strftime("%H:%M"),
        "venue": (fx["fixture"].get("venue") or {}).get("name") or "",
        "countdown": _countdown(kick_local, now_local),
        "tbc": tbc,
        "broadcast": bc,
    }

    for fx in upcoming[1:4]:
        k_utc = _kickoff_utc(fx)
        k = k_utc.astimezone(LONDON)
        home = fx["teams"]["home"]["id"] == config.TEAM_ID
        opp = fx["teams"]["away" if home else "home"]["name"]
        c_raw = fx["league"]["name"]
        c = COMP_DISPLAY.get(c_raw, c_raw)
        b = join.broadcast_for(k_utc, c, listings)
        if b["state"] == "available" or b["state"] == "unavailable":
            chan, owned = short_name(b["primary"]), b["owned"]
        elif b["state"] == "blackout":
            chan, owned = "Blackout", False
        elif b["state"] == "tbc":
            chan, owned = "TBC", False
        else:
            chan, owned = None, False
        payload["on_deck"].append({
            "when": k.strftime("%a %-d %b") + (" · TBC" if _tbc(fx) else k.strftime(" · %H:%M")),
            "opponent": rail_name(opp),
            "ha": "H" if home else "A",
            "competition": c,
            "channel_short": chan,
            "owned": owned,
        })

    return payload
