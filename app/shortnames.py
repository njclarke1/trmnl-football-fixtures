"""Club display names for constrained widths (plan §11 long-name risk)."""

# API-Football name -> compact display name for the on-deck rail
SHORT = {
    "Nottingham Forest": "Nott'm Forest",
    "AFC Bournemouth": "Bournemouth",
    "Wolverhampton Wanderers": "Wolves",
    "Tottenham Hotspur": "Spurs",
    "Manchester United": "Man Utd",
    "Manchester City": "Man City",
    "Newcastle United": "Newcastle",
    "Sheffield United": "Sheff Utd",
    "West Ham United": "West Ham",
    "Brighton & Hove Albion": "Brighton",
    "Crystal Palace": "C Palace",
    "Borussia Dortmund": "Dortmund",
    "Bayern München": "Bayern",
    "Bayern Munich": "Bayern",
    "Paris Saint Germain": "PSG",
    "Atletico Madrid": "Atlético",
    "Real Sociedad": "R Sociedad",
    "Bayer Leverkusen": "Leverkusen",
    "Inter Milan": "Inter",
    "AC Milan": "Milan",
}

# Full-name panel: names longer than this get the .long font step-down class
LONG_NAME_THRESHOLD = 14


def rail_name(name: str) -> str:
    return SHORT.get(name, name)


def is_long(name: str) -> bool:
    return len(name) > LONG_NAME_THRESHOLD


def initials(name: str) -> str:
    """3-letter fallback shown inside the crest circle if the image is missing."""
    words = [w for w in name.replace("&", " ").split() if w[0].isalpha()]
    if not words:
        return name[:3].upper()
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0] for w in words[:3]).upper()
