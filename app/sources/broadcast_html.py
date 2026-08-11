"""Broadcast listings parser (live-footballontv.com club page).

Deliberately class-agnostic: the site's markup classes may change season to
season, but the *content grammar* is stable — a date header, then per fixture
a kickoff time, an "A v B" line, a competition, and one text node per channel
(channels sit in separate sibling elements; flattened text concatenates them,
which is exactly why we walk individual text nodes instead).

State machine over document-order text nodes:

    DATE     "Sunday 23rd August 2026"
    TIME     "16:30"
    TEAMS    "Newcastle United v Liverpool"
    COMP     "Premier League"
    CHANNELS one node per channel, until next TIME / DATE / non-channel text

Fail-soft contract (plan §5.3): any exception in fetch/parse is caught by the
caller and degrades broadcast.state to "tbc" — it must never take down the
fixture display.
"""
import datetime as dt
import logging
import os
import re
import urllib.robotparser
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup, NavigableString

from .. import config
from ..channels import looks_like_channel

log = logging.getLogger(__name__)

DATE_RE = re.compile(
    r"^(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+(\d{1,2})(?:st|nd|rd|th)\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})$"
)
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
TEAMS_RE = re.compile(r"^(.{2,60})\s+v\s+(.{2,60})$")

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

# Skip pure-noise nodes (nav, cookie banners, headings) cheaply.
NOISE_RE = re.compile(r"^(Back to Top|My Guide|Log In|Get Started|View .*|©.*)$")

_robots_cache: dict[str, bool] = {}


def _robots_allows(url: str) -> bool:
    """Honour robots.txt (plan §5.3). Cached per-origin; permissive on fetch failure
    of robots.txt itself (standard convention)."""
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
    if origin in _robots_cache:
        return _robots_cache[origin]
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = requests.get(origin + "/robots.txt",
                         headers={"User-Agent": config.USER_AGENT}, timeout=10)
        if r.status_code == 200:
            rp.parse(r.text.splitlines())
            allowed = rp.can_fetch(config.USER_AGENT, url) and rp.can_fetch("*", url)
        else:
            allowed = True
    except requests.RequestException:
        allowed = True
    _robots_cache[origin] = allowed
    if not allowed:
        log.warning("robots.txt disallows %s — broadcast source disabled", url)
    return allowed


def fetch_listings_html() -> str:
    # Offline/debug: LISTINGS_FILE serves a saved page instead of fetching.
    listings_file = os.environ.get("LISTINGS_FILE")
    if listings_file:
        with open(listings_file) as fh:
            return fh.read()
    if not _robots_allows(config.LISTINGS_URL):
        raise PermissionError("robots.txt disallows listings URL")
    r = requests.get(config.LISTINGS_URL,
                     headers={"User-Agent": config.USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.text


def parse_listings(html: str) -> list[dict]:
    """-> [{date: date, time: "16:30", home: str, away: str,
            competition: str, channels: [str, ...]}]"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    rows: list[dict] = []
    cur_date: dt.date | None = None
    cur: dict | None = None
    state = "seek"

    def commit():
        nonlocal cur
        if cur and cur.get("home"):
            rows.append(cur)
        cur = None

    for node in soup.body.descendants if soup.body else soup.descendants:
        if not isinstance(node, NavigableString):
            continue
        text = re.sub(r"\s+", " ", str(node)).strip()
        if not text or NOISE_RE.match(text):
            continue

        m = DATE_RE.match(text)
        if m:
            commit()
            cur_date = dt.date(int(m.group(4)), MONTHS[m.group(3)], int(m.group(2)))
            state = "date"
            continue

        m = TIME_RE.match(text)
        if m and cur_date is not None:
            commit()
            cur = {"date": cur_date, "time": f"{int(m.group(1)):02d}:{m.group(2)}",
                   "home": None, "away": None, "competition": None, "channels": []}
            state = "time"
            continue

        if state == "time":
            m = TEAMS_RE.match(text)
            if m:
                cur["home"], cur["away"] = m.group(1).strip(), m.group(2).strip()
                state = "teams"
            continue

        if state == "teams":
            cur["competition"] = text
            state = "channels"
            continue

        if state == "channels":
            if looks_like_channel(text):
                cur["channels"].append(text)
            else:
                # Unknown text after channels ends the fixture block.
                commit()
                state = "seek"

    commit()
    return rows
