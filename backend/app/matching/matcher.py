"""
Fuzzy matching engine for cross-platform sports event matching.

This is the hardest part of the system. Prediction markets (Kalshi, Polymarket)
and sportsbooks (DraftKings, FanDuel) use completely different naming conventions:

  Kalshi:      "Will the Lakers win vs Celtics on 4/15?"
  Polymarket:  "LA Lakers to beat Boston Celtics"
  DraftKings:  "Los Angeles Lakers @ Boston Celtics"
  FanDuel:     "LA Lakers @ BOS Celtics"

Strategy:
1. Normalize team names via a comprehensive lookup table
2. Extract team pairs + date from each market
3. Match by sport + date + team pair (order-independent)
4. Fall back to fuzzy string matching for edge cases
5. Assign confidence scores to every match
"""

import logging
import re
import hashlib
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional

from ..models import (
    MarketOdds, MatchedEvent, Sport, MarketType, Platform
)

logger = logging.getLogger(__name__)

# ─── Comprehensive team name normalization table ──────────────────────────────
# Maps every known variant → canonical name

TEAM_ALIASES: dict[str, str] = {
    # NFL
    "arizona cardinals": "cardinals", "ari cardinals": "cardinals", "az cardinals": "cardinals",
    "atlanta falcons": "falcons", "atl falcons": "falcons",
    "baltimore ravens": "ravens", "bal ravens": "ravens", "blt ravens": "ravens",
    "buffalo bills": "bills", "buf bills": "bills",
    "carolina panthers": "panthers", "car panthers": "panthers",
    "chicago bears": "bears", "chi bears": "bears",
    "cincinnati bengals": "bengals", "cin bengals": "bengals", "cincy bengals": "bengals",
    "cleveland browns": "browns", "cle browns": "browns",
    "dallas cowboys": "cowboys", "dal cowboys": "cowboys",
    "denver broncos": "broncos", "den broncos": "broncos",
    "detroit lions": "lions", "det lions": "lions",
    "green bay packers": "packers", "gb packers": "packers",
    "houston texans": "texans", "hou texans": "texans",
    "indianapolis colts": "colts", "ind colts": "colts", "indy colts": "colts",
    "jacksonville jaguars": "jaguars", "jax jaguars": "jaguars", "jags": "jaguars",
    "kansas city chiefs": "chiefs", "kc chiefs": "chiefs",
    "las vegas raiders": "raiders", "lv raiders": "raiders", "la raiders": "raiders",
    "los angeles chargers": "chargers", "la chargers": "chargers", "lac chargers": "chargers",
    "los angeles rams": "rams", "la rams": "rams", "lar rams": "rams",
    "miami dolphins": "dolphins", "mia dolphins": "dolphins",
    "minnesota vikings": "vikings", "min vikings": "vikings",
    "new england patriots": "patriots", "ne patriots": "patriots", "pats": "patriots",
    "new orleans saints": "saints", "no saints": "saints", "nola saints": "saints",
    "new york giants": "giants", "ny giants": "giants", "nyg giants": "giants",
    "new york jets": "jets", "ny jets": "jets", "nyj jets": "jets",
    "philadelphia eagles": "eagles", "phi eagles": "eagles", "philly eagles": "eagles",
    "pittsburgh steelers": "steelers", "pit steelers": "steelers", "pitt steelers": "steelers",
    "san francisco 49ers": "49ers", "sf 49ers": "49ers", "niners": "49ers",
    "seattle seahawks": "seahawks", "sea seahawks": "seahawks",
    "tampa bay buccaneers": "buccaneers", "tb buccaneers": "buccaneers", "bucs": "buccaneers",
    "tennessee titans": "titans", "ten titans": "titans",
    "washington commanders": "commanders", "was commanders": "commanders", "wsh commanders": "commanders",

    # NBA
    "atlanta hawks": "hawks", "atl hawks": "hawks",
    "boston celtics": "celtics", "bos celtics": "celtics",
    "brooklyn nets": "nets", "bkn nets": "nets", "bk nets": "nets",
    "charlotte hornets": "hornets", "cha hornets": "hornets",
    "chicago bulls": "bulls", "chi bulls": "bulls",
    "cleveland cavaliers": "cavaliers", "cle cavaliers": "cavaliers", "cavs": "cavaliers",
    "dallas mavericks": "mavericks", "dal mavericks": "mavericks", "mavs": "mavericks",
    "denver nuggets": "nuggets", "den nuggets": "nuggets",
    "detroit pistons": "pistons", "det pistons": "pistons",
    "golden state warriors": "warriors", "gs warriors": "warriors", "gsw warriors": "warriors",
    "houston rockets": "rockets", "hou rockets": "rockets",
    "indiana pacers": "pacers", "ind pacers": "pacers",
    "los angeles clippers": "clippers", "la clippers": "clippers", "lac clippers": "clippers",
    "los angeles lakers": "lakers", "la lakers": "lakers", "lal lakers": "lakers",
    "memphis grizzlies": "grizzlies", "mem grizzlies": "grizzlies",
    "miami heat": "heat", "mia heat": "heat",
    "milwaukee bucks": "bucks", "mil bucks": "bucks",
    "minnesota timberwolves": "timberwolves", "min timberwolves": "timberwolves", "wolves": "timberwolves",
    "new orleans pelicans": "pelicans", "no pelicans": "pelicans", "nola pelicans": "pelicans",
    "new york knicks": "knicks", "ny knicks": "knicks", "nyk knicks": "knicks",
    "oklahoma city thunder": "thunder", "okc thunder": "thunder",
    "orlando magic": "magic", "orl magic": "magic",
    "philadelphia 76ers": "76ers", "phi 76ers": "76ers", "philly 76ers": "76ers", "sixers": "76ers",
    "phoenix suns": "suns", "phx suns": "suns",
    "portland trail blazers": "trail blazers", "por trail blazers": "trail blazers", "blazers": "trail blazers",
    "sacramento kings": "kings", "sac kings": "kings",
    "san antonio spurs": "spurs", "sa spurs": "spurs",
    "toronto raptors": "raptors", "tor raptors": "raptors",
    "utah jazz": "jazz", "uta jazz": "jazz",
    "washington wizards": "wizards", "was wizards": "wizards", "wsh wizards": "wizards",

    # MLB
    "arizona diamondbacks": "diamondbacks", "ari diamondbacks": "diamondbacks", "dbacks": "diamondbacks",
    "atlanta braves": "braves", "atl braves": "braves",
    "baltimore orioles": "orioles", "bal orioles": "orioles",
    "boston red sox": "red sox", "bos red sox": "red sox",
    "chicago cubs": "cubs", "chi cubs": "cubs", "chc cubs": "cubs",
    "chicago white sox": "white sox", "chi white sox": "white sox", "chw white sox": "white sox",
    "cincinnati reds": "reds", "cin reds": "reds",
    "cleveland guardians": "guardians", "cle guardians": "guardians",
    "colorado rockies": "rockies", "col rockies": "rockies",
    "detroit tigers": "tigers", "det tigers": "tigers",
    "houston astros": "astros", "hou astros": "astros",
    "kansas city royals": "royals", "kc royals": "royals",
    "los angeles angels": "angels", "la angels": "angels", "laa angels": "angels",
    "los angeles dodgers": "dodgers", "la dodgers": "dodgers", "lad dodgers": "dodgers",
    "miami marlins": "marlins", "mia marlins": "marlins",
    "milwaukee brewers": "brewers", "mil brewers": "brewers",
    "minnesota twins": "twins", "min twins": "twins",
    "new york mets": "mets", "ny mets": "mets", "nym mets": "mets",
    "new york yankees": "yankees", "ny yankees": "yankees", "nyy yankees": "yankees",
    "oakland athletics": "athletics", "oak athletics": "athletics", "a's": "athletics",
    "philadelphia phillies": "phillies", "phi phillies": "phillies",
    "pittsburgh pirates": "pirates", "pit pirates": "pirates",
    "san diego padres": "padres", "sd padres": "padres",
    "san francisco giants": "sf giants", "sf giants": "sf giants",
    "seattle mariners": "mariners", "sea mariners": "mariners",
    "st louis cardinals": "stl cardinals", "stl cardinals": "stl cardinals", "st. louis cardinals": "stl cardinals",
    "tampa bay rays": "rays", "tb rays": "rays",
    "texas rangers": "rangers", "tex rangers": "rangers",
    "toronto blue jays": "blue jays", "tor blue jays": "blue jays",
    "washington nationals": "nationals", "was nationals": "nationals", "nats": "nationals",

    # NHL
    "anaheim ducks": "ducks", "ana ducks": "ducks",
    "arizona coyotes": "coyotes", "ari coyotes": "coyotes", "utah hockey club": "utah hc",
    "boston bruins": "bruins", "bos bruins": "bruins",
    "buffalo sabres": "sabres", "buf sabres": "sabres",
    "calgary flames": "flames", "cgy flames": "flames",
    "carolina hurricanes": "hurricanes", "car hurricanes": "hurricanes", "canes": "hurricanes",
    "chicago blackhawks": "blackhawks", "chi blackhawks": "blackhawks",
    "colorado avalanche": "avalanche", "col avalanche": "avalanche", "avs": "avalanche",
    "columbus blue jackets": "blue jackets", "cbj blue jackets": "blue jackets",
    "dallas stars": "stars", "dal stars": "stars",
    "detroit red wings": "red wings", "det red wings": "red wings",
    "edmonton oilers": "oilers", "edm oilers": "oilers",
    "florida panthers": "fl panthers", "fla panthers": "fl panthers",
    "los angeles kings": "la kings", "la kings": "la kings",
    "minnesota wild": "wild", "min wild": "wild",
    "montreal canadiens": "canadiens", "mtl canadiens": "canadiens", "habs": "canadiens",
    "nashville predators": "predators", "nsh predators": "predators", "preds": "predators",
    "new jersey devils": "devils", "nj devils": "devils", "njd devils": "devils",
    "new york islanders": "islanders", "ny islanders": "islanders", "nyi islanders": "islanders",
    "new york rangers": "ny rangers", "nyr rangers": "ny rangers",
    "ottawa senators": "senators", "ott senators": "senators", "sens": "senators",
    "philadelphia flyers": "flyers", "phi flyers": "flyers",
    "pittsburgh penguins": "penguins", "pit penguins": "penguins", "pens": "penguins",
    "san jose sharks": "sharks", "sj sharks": "sharks",
    "seattle kraken": "kraken", "sea kraken": "kraken",
    "st louis blues": "blues", "stl blues": "blues", "st. louis blues": "blues",
    "tampa bay lightning": "lightning", "tb lightning": "lightning", "bolts": "lightning",
    "toronto maple leafs": "maple leafs", "tor maple leafs": "maple leafs", "leafs": "maple leafs",
    "vancouver canucks": "canucks", "van canucks": "canucks",
    "vegas golden knights": "golden knights", "vgk golden knights": "golden knights",
    "washington capitals": "capitals", "was capitals": "capitals", "caps": "capitals",
    "winnipeg jets": "wpg jets",

    # EPL
    "arsenal": "arsenal", "arsenal fc": "arsenal",
    "aston villa": "aston villa", "aston villa fc": "aston villa",
    "bournemouth": "bournemouth", "afc bournemouth": "bournemouth",
    "brentford": "brentford", "brentford fc": "brentford",
    "brighton": "brighton", "brighton & hove albion": "brighton", "brighton and hove albion": "brighton",
    "burnley": "burnley", "burnley fc": "burnley",
    "chelsea": "chelsea", "chelsea fc": "chelsea",
    "crystal palace": "crystal palace", "crystal palace fc": "crystal palace",
    "everton": "everton", "everton fc": "everton",
    "fulham": "fulham", "fulham fc": "fulham",
    "ipswich town": "ipswich", "ipswich": "ipswich",
    "leicester city": "leicester", "leicester": "leicester",
    "liverpool": "liverpool", "liverpool fc": "liverpool",
    "luton town": "luton", "luton": "luton",
    "manchester city": "man city", "man city": "man city", "manchester city fc": "man city", "mcfc": "man city",
    "manchester united": "man utd", "man utd": "man utd", "manchester united fc": "man utd", "mufc": "man utd", "man united": "man utd",
    "newcastle united": "newcastle", "newcastle": "newcastle", "nufc": "newcastle",
    "nottingham forest": "nott forest", "nott'm forest": "nott forest", "nott forest": "nott forest",
    "sheffield united": "sheffield utd", "sheffield utd": "sheffield utd",
    "tottenham hotspur": "tottenham", "tottenham": "tottenham", "spurs fc": "tottenham", "thfc": "tottenham",
    "west ham united": "west ham", "west ham": "west ham", "whu": "west ham",
    "wolverhampton wanderers": "wolves fc", "wolves": "wolves fc", "wolverhampton": "wolves fc",
}

# Build a reverse lookup: canonical name → set of aliases (for fuzzy matching)
CANONICAL_TEAMS: dict[str, set[str]] = {}
for alias, canonical in TEAM_ALIASES.items():
    CANONICAL_TEAMS.setdefault(canonical, set()).add(alias)


def normalize_team_name(raw: str) -> Optional[str]:
    """Normalize a team name to its canonical form."""
    cleaned = raw.strip().lower()
    cleaned = re.sub(r'[^\w\s]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Direct lookup
    if cleaned in TEAM_ALIASES:
        return TEAM_ALIASES[cleaned]

    # Try matching just the last word (team nickname)
    parts = cleaned.split()
    if parts:
        nickname = parts[-1]
        for alias, canonical in TEAM_ALIASES.items():
            if alias.endswith(nickname) or canonical == nickname:
                return canonical

    # Try substring matching
    for alias, canonical in TEAM_ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return canonical

    return cleaned  # return cleaned version as-is if no match


def extract_teams_from_text(text: str) -> list[str]:
    """Extract team names from a market title/description."""
    text_lower = text.lower()
    # Clean punctuation for matching
    text_clean = re.sub(r'[^\w\s]', ' ', text_lower)
    text_clean = re.sub(r'\s+', ' ', text_clean).strip()
    found = []

    # Build a combined lookup: all aliases + all canonical names
    all_names: dict[str, str] = dict(TEAM_ALIASES)
    for canonical in set(TEAM_ALIASES.values()):
        all_names[canonical] = canonical

    # Sort by length (longest first) to match most specific first
    sorted_names = sorted(all_names.keys(), key=len, reverse=True)

    matched_spans = []
    for name in sorted_names:
        # Use word-boundary matching to avoid partial matches
        pattern = r'\b' + re.escape(name) + r'\b'
        match = re.search(pattern, text_clean)
        if match:
            start, end = match.start(), match.end()
            # Check this doesn't overlap with an already-matched span
            overlaps = any(
                not (end <= ms or start >= me)
                for ms, me in matched_spans
            )
            if not overlaps:
                canonical = all_names[name]
                if canonical not in found:
                    found.append(canonical)
                    matched_spans.append((start, end))

    return found


def extract_date_from_text(text: str) -> Optional[datetime]:
    """Try to extract a date from market text."""
    patterns = [
        r'(\d{1,2})/(\d{1,2})/(\d{2,4})',  # M/D/YYYY or M/D/YY
        r'(\d{1,2})-(\d{1,2})-(\d{2,4})',  # M-D-YYYY
        r'(\w+)\s+(\d{1,2}),?\s*(\d{4})',  # Month D, YYYY
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                groups = match.groups()
                if pattern == patterns[2]:
                    return datetime.strptime(
                        f"{groups[0]} {groups[1]} {groups[2]}", "%B %d %Y"
                    )
                else:
                    m, d, y = int(groups[0]), int(groups[1]), int(groups[2])
                    if y < 100:
                        y += 2000
                    return datetime(y, m, d)
            except (ValueError, IndexError):
                continue
    return None


def compute_match_confidence(
    teams_a: list[str], teams_b: list[str],
    sport_match: bool, date_match: bool,
    text_a: str, text_b: str
) -> float:
    """Compute confidence score for a match between two markets."""
    score = 0.0

    # Team matching (most important)
    if len(teams_a) >= 1 and len(teams_b) >= 1:
        common = set(teams_a) & set(teams_b)
        if len(common) >= 2:
            score += 0.5  # Both teams match
        elif len(common) >= 1:
            score += 0.25  # One team matches

    # Sport match
    if sport_match:
        score += 0.2

    # Date match
    if date_match:
        score += 0.2

    # Fuzzy text similarity as tiebreaker
    text_sim = SequenceMatcher(None, text_a.lower(), text_b.lower()).ratio()
    score += text_sim * 0.1

    return min(score, 1.0)


def generate_match_id(sport: Sport, teams: list[str], date: Optional[datetime]) -> str:
    """Generate a deterministic match ID."""
    sorted_teams = sorted(teams)
    date_str = date.strftime("%Y%m%d") if date else "nodate"
    raw = f"{sport.value}|{'|'.join(sorted_teams)}|{date_str}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def detect_market_type(text: str) -> MarketType:
    """Detect if a market is moneyline or over/under from its text."""
    text_lower = text.lower()
    ou_patterns = [
        r'over\s*\/?\s*under', r'o/u', r'total',
        r'over\s+\d+', r'under\s+\d+',
        r'\d+\.5\s*(points|goals|runs)',
    ]
    for pattern in ou_patterns:
        if re.search(pattern, text_lower):
            return MarketType.OVER_UNDER
    return MarketType.MONEYLINE


class EventMatcher:
    """
    Matches events across prediction markets and sportsbooks.

    The matching pipeline:
    1. Group all markets by sport
    2. Within each sport, extract team names and dates
    3. Match prediction market events to sportsbook events
    4. Score each match with confidence
    5. Return only matches above threshold
    """

    def __init__(self, confidence_threshold: float = 0.45):
        self.confidence_threshold = confidence_threshold

    def match_markets(
        self,
        prediction_markets: list[MarketOdds],
        sportsbooks: list[MarketOdds],
    ) -> list[MatchedEvent]:
        """
        Match prediction market odds against sportsbook odds.
        Returns a list of MatchedEvent with both sides populated.
        """
        matches: list[MatchedEvent] = []

        # Group by sport
        pm_by_sport: dict[Sport, list[MarketOdds]] = {}
        sb_by_sport: dict[Sport, list[MarketOdds]] = {}

        for m in prediction_markets:
            pm_by_sport.setdefault(m.sport, []).append(m)
        for m in sportsbooks:
            sb_by_sport.setdefault(m.sport, []).append(m)

        # Match within each sport
        for sport in Sport:
            pm_list = pm_by_sport.get(sport, [])
            sb_list = sb_by_sport.get(sport, [])

            if not pm_list or not sb_list:
                continue

            logger.info(
                f"Matching {sport.value}: {len(pm_list)} prediction market "
                f"events vs {len(sb_list)} sportsbook events"
            )

            # Pre-process: extract teams for each market
            pm_teams = [(m, extract_teams_from_text(m.event_name)) for m in pm_list]
            sb_teams = [(m, extract_teams_from_text(m.event_name)) for m in sb_list]

            used_sb_indices: set[int] = set()

            for pm_market, pm_t in pm_teams:
                best_match_idx = -1
                best_confidence = 0.0
                best_sb_market = None

                pm_date = extract_date_from_text(pm_market.event_name)

                for idx, (sb_market, sb_t) in enumerate(sb_teams):
                    if idx in used_sb_indices:
                        continue

                    # Must be same market type (or flexible)
                    type_match = (
                        pm_market.market_type == sb_market.market_type
                        or pm_market.market_type == MarketType.MONEYLINE
                    )
                    if not type_match:
                        continue

                    sb_date = extract_date_from_text(sb_market.event_name)
                    date_match = False
                    if pm_date and sb_date:
                        date_match = abs((pm_date - sb_date).days) <= 1
                    elif not pm_date and not sb_date:
                        date_match = True  # no date info on either side

                    confidence = compute_match_confidence(
                        pm_t, sb_t,
                        sport_match=True,
                        date_match=date_match,
                        text_a=pm_market.event_name,
                        text_b=sb_market.event_name,
                    )

                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match_idx = idx
                        best_sb_market = sb_market

                if (
                    best_sb_market
                    and best_confidence >= self.confidence_threshold
                ):
                    used_sb_indices.add(best_match_idx)

                    all_teams = list(set(
                        pm_t + extract_teams_from_text(best_sb_market.event_name)
                    ))
                    pm_date = extract_date_from_text(pm_market.event_name)

                    match_id = generate_match_id(sport, all_teams, pm_date)
                    normalized = self._build_normalized_name(all_teams, sport)

                    matched = MatchedEvent(
                        match_id=match_id,
                        sport=sport,
                        normalized_name=normalized,
                        event_date=pm_date,
                        market_type=pm_market.market_type,
                        prediction_market=pm_market,
                        sportsbook=best_sb_market,
                        match_confidence=best_confidence,
                    )
                    matches.append(matched)

                    logger.debug(
                        f"Matched: '{pm_market.event_name}' ↔ "
                        f"'{best_sb_market.event_name}' "
                        f"(confidence: {best_confidence:.2f})"
                    )

        logger.info(f"Total matches found: {len(matches)}")
        return matches

    def _build_normalized_name(self, teams: list[str], sport: Sport) -> str:
        """Build a clean normalized event name."""
        if len(teams) >= 2:
            return f"{teams[0].title()} vs {teams[1].title()}"
        elif len(teams) == 1:
            return f"{teams[0].title()} ({sport.value.upper()})"
        return f"Unknown Event ({sport.value.upper()})"
