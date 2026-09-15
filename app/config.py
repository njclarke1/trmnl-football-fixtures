"""Central configuration. Everything user-specific is env-driven — nothing hardcoded."""
import os


def _bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# --- fixtures source -------------------------------------------------------
# football-data.org v4 (free tier: PL + CL current season, forever, no card)
FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
TEAM_ID = int(os.environ.get("TEAM_ID", "64"))            # Liverpool on football-data.org
TEAM_NAME = os.environ.get("TEAM_NAME", "Liverpool")
FIXTURE_COUNT = int(os.environ.get("FIXTURE_COUNT", "6"))

# "api" (live) or "stub" (serve tests/fixtures JSON — offline dev / demo renders)
FIXTURES_SOURCE = os.environ.get("FIXTURES_SOURCE", "api")
STUB_DIR = os.environ.get("STUB_DIR", "/app/tests/fixtures")

# --- broadcast source ------------------------------------------------------
# Ships DISABLED by default (plan §5.4). Enable in local .env only.
ENABLE_BROADCAST = _bool("ENABLE_BROADCAST", "0")
LISTINGS_URL = os.environ.get(
    "LISTINGS_URL", "https://www.live-footballontv.com/liverpool-on-tv.html"
)
CONTACT = os.environ.get("CONTACT", "")
USER_AGENT = f"trmnl-football-fixtures/1.0 (personal e-ink display{'; ' + CONTACT if CONTACT else ''})"

# --- cup back-fill ---------------------------------------------------------
# football-data.org carries no domestic cups at any tier, so cup ties never
# arrive from the fixtures API. Promote orphan broadcast-listing rows in these
# competitions into fixtures (app/cupfill.py). Requires ENABLE_BROADCAST.
# Only *televised* ties are recoverable this way — see cupfill.py docstring.
CUP_FILL_COMPS = [
    c.strip()
    for c in os.environ.get(
        "CUP_FILL_COMPS",
        "League Cup,Carabao Cup,EFL Cup,FA Cup,"
        "Community Shield,FA Community Shield,UEFA Super Cup",
    ).split(",")
    if c.strip()
]

# --- owned channels --------------------------------------------------------
OWNED_CHANNELS = [
    c.strip().lower()
    for c in os.environ.get("OWNED_CHANNELS", "sky,tnt,bbc,itv,channel4,channel5,s4c").split(",")
    if c.strip()
]

# --- behaviour -------------------------------------------------------------
TZ = os.environ.get("DISPLAY_TZ", "Europe/London")
CACHE_TTL = int(os.environ.get("CACHE_TTL", "10800"))      # 3 h
HOLD_PAST_KICKOFF_MIN = int(os.environ.get("HOLD_PAST_KICKOFF_MIN", "120"))  # plan §12.1
CACHE_DIR = os.environ.get("CACHE_DIR", "/app/cache")

# Absolute base for crest URLs in the payload (LaraPaper's renderer must be
# able to reach it — use the NAS LAN address, not localhost).
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://192.168.68.111:3458").rstrip("/")

# --- crest pipeline --------------------------------------------------------
CREST_SIZE = int(os.environ.get("CREST_SIZE", "86"))
CREST_URL_TMPL = os.environ.get(
    "CREST_URL_TMPL", "https://crests.football-data.org/{id}.png"
)
# Per-crest override: team_id -> "dither" (default is threshold). Plan §6.
CREST_DITHER_IDS = {
    int(x) for x in os.environ.get("CREST_DITHER_IDS", "").split(",") if x.strip().isdigit()
}
