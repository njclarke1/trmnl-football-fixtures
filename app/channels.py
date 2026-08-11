"""Channel string → family mapping and owned-channel filtering.

Data-driven, not hardcoded logic: broadcasters rename constantly
(BT Sport → TNT inside three years). Add a prefix, don't touch code.
"""
import re

from . import config

# Longest-prefix wins. Lowercased match against the start of the channel string.
FAMILY_PREFIXES: list[tuple[str, str]] = [
    ("sky sports", "sky"),
    ("sky ", "sky"),
    ("tnt sports", "tnt"),
    ("bt sport", "tnt"),           # legacy name, same subscription family
    ("discovery+", "tnt"),         # TNT's streaming wrapper
    ("bbc", "bbc"),
    ("itv", "itv"),
    ("stv", "itv"),
    ("channel 4", "channel4"),
    ("e4", "channel4"),
    ("channel 5", "channel5"),
    ("5action", "channel5"),
    ("s4c", "s4c"),
    ("amazon", "amazon"),
    ("prime video", "amazon"),
    ("premier sports", "premiersports"),
    ("dazn", "dazn"),
    ("lfctv", "clubtv"),
    ("mutv", "clubtv"),
    ("chelsea tv", "clubtv"),
    ("all red video", "clubtv"),
    ("hbo max", "hbomax"),
    ("apple tv", "apple"),
    ("youtube", "youtube"),
    ("talksport", "radio"),
    ("bbc radio", "radio"),
]

# Rail / compact abbreviations. Prefix match, longest first.
SHORT_NAMES: list[tuple[str, str]] = [
    ("sky sports main event", "Sky ME"),
    ("sky sports premier league", "Sky PL"),
    ("sky sports football", "Sky Foot"),
    ("sky sports ultra hdr", "Sky UHD"),
    ("sky sports+", "Sky+"),
    ("tnt sports ultimate", "TNT Ult"),
    ("tnt sports 1", "TNT 1"),
    ("tnt sports 2", "TNT 2"),
    ("tnt sports 3", "TNT 3"),
    ("tnt sports 4", "TNT 4"),
    ("bbc one", "BBC One"),
    ("bbc two", "BBC Two"),
    ("bbc iplayer", "iPlayer"),
    ("itv1", "ITV1"),
    ("itv4", "ITV4"),
    ("itvx", "ITVX"),
    ("channel 4", "Ch4"),
    ("channel 5", "Ch5"),
    ("amazon prime video", "Amazon"),
    ("prime video", "Amazon"),
    ("premier sports 1", "Prem Sp 1"),
    ("premier sports 2", "Prem Sp 2"),
    ("all red video", "ARV"),
    ("hbo max", "HBO Max"),
    ("lfctv", "LFCTV"),
]

_WORD = re.compile(r"[a-z0-9+]")


def family_of(channel: str) -> str | None:
    c = channel.strip().lower()
    for prefix, fam in FAMILY_PREFIXES:
        if c.startswith(prefix):
            return fam
    return None


def looks_like_channel(text: str) -> bool:
    """Used by the listings parser to decide whether a text node is a channel.
    Known-family prefix, or short branded token (≤ 40 chars, no sentence
    punctuation) immediately following other channels is accepted."""
    if len(text) > 40 or text.endswith((".", "?", "!")):
        return False
    return family_of(text) is not None


def is_owned(channel: str) -> bool:
    fam = family_of(channel)
    return fam is not None and fam in config.OWNED_CHANNELS


def short_name(channel: str) -> str:
    c = channel.strip().lower()
    for prefix, short in SHORT_NAMES:
        if c.startswith(prefix):
            return short
    return channel if len(channel) <= 12 else channel[:11] + "…"


def split_broadcast(channels: list[str]) -> dict:
    """Order channels owned-first, pick a primary, and classify.

    Returns {state, primary, others, owned, status_label} — the shape the
    template's broadcast band consumes (payload contract §3)."""
    if not channels:
        return {"state": "tbc", "primary": None, "others": [],
                "owned": False, "status_label": None, "note": None}

    owned = [c for c in channels if is_owned(c)]
    unowned = [c for c in channels if not is_owned(c)]
    ordered = owned + unowned
    primary = ordered[0]
    others = ordered[1:]

    if owned:
        return {"state": "available", "primary": primary, "others": others,
                "owned": True, "status_label": "You have this", "note": None}
    return {"state": "unavailable", "primary": primary, "others": others,
            "owned": False, "status_label": "Not on your channels", "note": None}
