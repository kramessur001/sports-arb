"""
Fuzzy matching engine for cross-platform sports event matching.

The key challenge: prediction markets and sportsbooks name things differently.

  Polymarket:  "Will the Colorado Avalanche win the 2026 NHL Stanley Cup?"
  FanDuel:     Runner "Colorado Avalanche" in market "Stanley Cup 2025-26 - Winner"
  Kalshi:      "Pro Hockey Champion" with market ticker KXNHL-26-COL

Strategy for FUTURES matching (the primary market type available):
1. Extract team name from each side
2. Normalize team names via lookup table
3. Match by sport + normalized team name
4. Assign confidence based on match quality

For GAME matching (if game-level odds become available):
1. Extract both team names + date
2. Match by sport + team pair + date proximity
"""

import logging
import re
import hashlib
from datetime import datetime
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
    "baltimore ravens": "ravens", "bal ravens": "ravens",
    "buffalo bills": "bills", "buf bills": "bills",
    "carolina panthers": "panthers", "car panthers": "panthers",
    "chicago bears": "bears", "chi bears": "bears",
    "cincinnati bengals": "bengals", "cin bengals": "bengals",
    "cleveland browns": "browns", "cle browns": "browns",
    "dallas cowboys": "cowboys", "dal cowboys": "cowboys",
    "denver broncos": "broncos", "den broncos": "broncos",
    "detroit lions": "lions", "det lions": "lions",
    "green bay packers": "packers", "gb packers": "packers",
    "houston texans": "texans", "hou texans": "texans",
    "indianapolis colts": "colts", "ind colts": "colts",
    "jacksonville jaguars": "jaguars", "jax jaguars": "jaguars",
    "kansas city chiefs": "chiefs", "kc chiefs": "chiefs",
    "las vegas raiders": "raiders", "lv raiders": "raiders",
    "los angeles chargers": "chargers", "la chargers": "chargers",
    "los angeles rams": "rams", "la rams": "rams",
    "miami dolphins": "dolphins", "mia dolphins": "dolphins",
    "minnesota vikings": "vikings", "min vikings": "vikings",
    "new england patriots": "patriots", "ne patriots": "patriots",
    "new orleans saints": "saints", "no saints": "saints",
    "new york giants": "giants", "ny giants": "giants",
    "new york jets": "jets", "ny jets": "jets",
    "philadelphia eagles": "eagles", "phi eagles": "eagles",
    "pittsburgh steelers": "steelers", "pit steelers": "steelers",
    "san francisco 49ers": "49ers", "sf 49ers": "49ers",
    "seattle seahawks": "seahawks", "sea seahawks": "seahawks",
    "tampa bay buccaneers": "buccaneers", "tb buccaneers": "buccaneers",
    "tennessee titans": "titans", "ten titans": "titans",
    "washington commanders": "commanders", "was commanders": "commanders",

    # NBA
    "atlanta hawks": "hawks", "atl hawks": "hawks",
    "boston celtics": "celtics", "bos celtics": "celtics",
    "brooklyn nets": "nets", "bkn nets": "nets",
    "charlotte hornets": "hornets", "cha hornets": "hornets",
    "chicago bulls": "bulls", "chi bulls": "bulls",
    "cleveland cavaliers": "cavaliers", "cle cavaliers": "cavaliers", "cavs": "cavaliers",
    "dallas mavericks": "mavericks", "dal mavericks": "mavericks", "mavs": "mavericks",
    "denver nuggets": "nuggets", "den nuggets": "nuggets",
    "detroit pistons": "pistons", "det pistons": "pistons",
    "golden state warriors": "warriors", "gs warriors": "warriors", "gsw warriors": "warriors",
    "houston rockets": "rockets", "hou rockets": "rockets",
    "indiana pacers": "pacers", "ind pacers": "pacers",
    "los angeles clippers": "clippers", "la clippers": "clippers",
    "los angeles lakers": "lakers", "la lakers": "lakers",
    "memphis grizzlies": "grizzlies", "mem grizzlies": "grizzlies",
    "miami heat": "heat", "mia heat": "heat",
    "milwaukee bucks": "bucks", "mil bucks": "bucks",
    "minnesota timberwolves": "timberwolves", "min timberwolves": "timberwolves",
    "new orleans pelicans": "pelicans", "no pelicans": "pelicans",
    "new york knicks": "knicks", "ny knicks": "knicks",
    "oklahoma city thunder": "thunder", "okc thunder": "thunder",
    "orlando magic": "magic", "orl magic": "magic",
    "philadelphia 76ers": "76ers", "phi 76ers": "76ers", "sixers": "76ers",
    "phoenix suns": "suns", "phx suns": "suns",
    "portland trail blazers": "trail blazers", "por trail blazers": "trail blazers", "blazers": "trail blazers",
    "sacramento kings": "kings", "sac kings": "kings",
    "san antonio spurs": "spurs", "sa spurs": "spurs",
    "toronto raptors": "raptors", "tor raptors": "raptors",
    "utah jazz": "jazz", "uta jazz": "jazz",
    "washington wizards": "wizards", "was wizards": "wizards",

    # MLB
    "arizona diamondbacks": "diamondbacks", "dbacks": "diamondbacks",
    "atlanta braves": "braves", "atl braves": "braves",
    "baltimore orioles": "orioles", "bal orioles": "orioles",
    "boston red sox": "red sox", "bos red sox": "red sox",
    "chicago cubs": "cubs", "chi cubs": "cubs",
    "chicago white sox": "white sox", "chi white sox": "white sox",
    "cincinnati reds": "reds", "cin reds": "reds",
    "cleveland guardians": "guardians", "cle guardians": "guardians",
    "colorado rockies": "rockies", "col rockies": "rockies",
    "detroit tigers": "tigers", "det tigers": "tigers",
    "houston astros": "astros", "hou astros": "astros",
    "kansas city royals": "royals", "kc royals": "royals",
    "los angeles angels": "angels", "la angels": "angels",
    "los angeles dodgers": "dodgers", "la dodgers": "dodgers",
    "miami marlins": "marlins", "mia marlins": "marlins",
    "milwaukee brewers": "brewers", "mil brewers": "brewers",
    "minnesota twins": "twins", "min twins": "twins",
    "new york mets": "mets", "ny mets": "mets",
    "new york yankees": "yankees", "ny yankees": "yankees",
    "oakland athletics": "athletics", "oak athletics": "athletics",
    "philadelphia phillies": "phillies", "phi phillies": "phillies",
    "pittsburgh pirates": "pirates", "pit pirates": "pirates",
    "san diego padres": "padres", "sd padres": "padres",
    "san francisco giants": "sf giants",
    "seattle mariners": "mariners", "sea mariners": "mariners",
    "st louis cardinals": "stl cardinals", "st. louis cardinals": "stl cardinals",
    "tampa bay rays": "rays", "tb rays": "rays",
    "texas rangers": "tex rangers",
    "toronto blue jays": "blue jays", "tor blue jays": "blue jays",
    "washington nationals": "nationals", "was nationals": "nationals",

    # NHL
    "anaheim ducks": "ducks", "ana ducks": "ducks",
    "boston bruins": "bruins", "bos bruins": "bruins",
    "buffalo sabres": "sabres", "buf sabres": "sabres",
    "calgary flames": "flames", "cgy flames": "flames",
    "carolina hurricanes": "hurricanes", "car hurricanes": "hurricanes", "canes": "hurricanes",
    "chicago blackhawks": "blackhawks", "chi blackhawks": "blackhawks",
    "colorado avalanche": "avalanche", "col avalanche": "avalanche", "avs": "avalanche",
    "columbus blue jackets": "blue jackets", "cbj blue jackets": "blue jackets",
    "dallas stars": "stars",
    "detroit red wings": "red wings", "det red wings": "red wings",
    "edmonton oilers": "oilers", "edm oilers": "oilers",
    "florida panthers": "fl panthers", "fla panthers": "fl panthers",
    "los angeles kings": "la kings",
    "minnesota wild": "wild", "min wild": "wild",
    "montreal canadiens": "canadiens", "mtl canadiens": "canadiens", "habs": "canadiens",
    "nashville predators": "predators", "nsh predators": "predators",
    "new jersey devils": "devils", "nj devils": "devils",
    "new york islanders": "islanders", "ny islanders": "islanders",
    "new york rangers": "ny rangers",
    "ottawa senators": "senators", "ott senators": "senators",
    "philadelphia flyers": "flyers", "phi flyers": "flyers",
    "pittsburgh penguins": "penguins", "pit penguins": "penguins",
    "san jose sharks": "sharks", "sj sharks": "sharks",
    "seattle kraken": "kraken", "sea kraken": "kraken",
    "st louis blues": "blues", "st. louis blues": "blues", "stl blues": "blues",
    "tampa bay lightning": "lightning", "tb lightning": "lightning",
    "toronto maple leafs": "maple leafs", "tor maple leafs": "maple leafs", "leafs": "maple leafs",
    "utah hockey club": "utah hc",
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
    "chelsea": "chelsea", "chelsea fc": "chelsea",
    "crystal palace": "crystal palace",
    "everton": "everton", "everton fc": "everton",
    "fulham": "fulham", "fulham fc": "fulham",
    "ipswich town": "ipswich", "ipswich": "ipswich",
    "leicester city": "leicester", "leicester": "leicester",
    "liverpool": "liverpool", "liverpool fc": "liverpool",
    "manchester city": "man city", "man city": "man city", "mcfc": "man city",
    "manchester united": "man utd", "man utd": "man utd", "mufc": "man utd", "man united": "man utd",
    "newcastle united": "newcastle", "newcastle": "newcastle", "nufc": "newcastle",
    "nottingham forest": "nott forest", "nott forest": "nott forest",
    "tottenham hotspur": "tottenham", "tottenham": "tottenham",
    "west ham united": "west ham", "west ham": "west ham",
    "wolverhampton wanderers": "wolves fc", "wolves": "wolves fc",
}

# Build reverse: canonical → aliases
CANONICAL_TEAMS: dict[str, set[str]] = {}
for _alias, _canonical in TEAM_ALIASES.items():
    CANONICAL_TEAMS.setdefault(_canonical, set()).add(_alias)


def normalize_team_name(raw: str) -> Optional[str]:
    """Normalize a team name to its canonical form."""
    cleaned = raw.strip().lower()
    cleaned = re.sub(r'[^\w\s]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Direct lookup
    if cleaned in TEAM_ALIASES:
        return TEAM_ALIASES[cleaned]

    # Check if it IS a canonical name
    if cleaned in CANONICAL_TEAMS:
        return cleaned

    # Try matching just the last word (nickname)
    parts = cleaned.split()
    if parts:
        nickname = parts[-1]
        for alias, canonical in TEAM_ALIASES.items():
            if canonical == nickname:
                return canonical
            if alias.endswith(nickname) and len(nickname) > 3:
                return canonical

    # Substring match
    for alias, canonical in TEAM_ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return canonical

    return cleaned


def extract_teams_from_text(text: str) -> list[str]:
    """Extract team names from market text."""
    text_clean = re.sub(r'[^\w\s]', ' ', text.lower())
    text_clean = re.sub(r'\s+', ' ', text_clean).strip()
    found = []

    # Combined lookup: aliases + canonical names
    all_names: dict[str, str] = dict(TEAM_ALIASES)
    for canonical in set(TEAM_ALIASES.values()):
        all_names[canonical] = canonical

    # Sort by length (longest first) for most specific match
    sorted_names = sorted(all_names.keys(), key=len, reverse=True)

    matched_spans = []
    for name in sorted_names:
        pattern = r'\b' + re.escape(name) + r'\b'
        match = re.search(pattern, text_clean)
        if match:
            start, end = match.start(), match.end()
            overlaps = any(not (end <= ms or start >= me) for ms, me in matched_spans)
            if not overlaps:
                canonical = all_names[name]
                if canonical not in found:
                    found.append(canonical)
                    matched_spans.append((start, end))

    return found


def generate_match_id(sport: Sport, team: str, market_context: str = "") -> str:
    """Generate a deterministic match ID for a team+sport combination."""
    raw = f"{sport.value}|{team}|{market_context}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


class EventMatcher:
    """
    Matches events across prediction markets and sportsbooks.

    For FUTURES markets (the main type available):
    - Each prediction market entry = one team's championship odds
    - Each sportsbook entry = one runner (team) in a futures market
    - Match by: same sport + same normalized team name

    For GAME markets (if available via The Odds API):
    - Match by: sport + team pair + date
    """

    def __init__(self, confidence_threshold: float = 0.4):
        self.confidence_threshold = confidence_threshold

    def match_markets(
        self,
        prediction_markets: list[MarketOdds],
        sportsbooks: list[MarketOdds],
    ) -> list[MatchedEvent]:
        """Match prediction market odds against sportsbook odds."""
        matches: list[MatchedEvent] = []

        # Group by sport
        pm_by_sport: dict[Sport, list[MarketOdds]] = {}
        sb_by_sport: dict[Sport, list[MarketOdds]] = {}

        for m in prediction_markets:
            pm_by_sport.setdefault(m.sport, []).append(m)
        for m in sportsbooks:
            sb_by_sport.setdefault(m.sport, []).append(m)

        for sport in Sport:
            pm_list = pm_by_sport.get(sport, [])
            sb_list = sb_by_sport.get(sport, [])

            if not pm_list or not sb_list:
                continue

            logger.info(
                f"Matching {sport.value}: {len(pm_list)} prediction market "
                f"entries vs {len(sb_list)} sportsbook entries"
            )

            # Build a lookup of sportsbook entries by normalized team name
            sb_by_team: dict[str, list[MarketOdds]] = {}
            for sb in sb_list:
                teams = extract_teams_from_text(sb.event_name + " " + sb.selection)
                # Also try normalizing the selection directly
                sel_normalized = normalize_team_name(sb.selection)
                all_team_names = set(teams)
                if sel_normalized:
                    all_team_names.add(sel_normalized)

                for team in all_team_names:
                    sb_by_team.setdefault(team, []).append(sb)

            # For each prediction market entry, find matching sportsbook entry
            used_sb_ids: set[str] = set()

            for pm in pm_list:
                pm_teams = extract_teams_from_text(pm.event_name + " " + pm.selection)
                pm_sel_normalized = normalize_team_name(pm.selection)
                if pm_sel_normalized:
                    pm_teams.append(pm_sel_normalized)

                # Deduplicate
                pm_teams = list(set(pm_teams))

                best_sb = None
                best_confidence = 0.0
                best_team = ""

                for team in pm_teams:
                    candidates = sb_by_team.get(team, [])
                    for sb in candidates:
                        sb_key = f"{sb.platform.value}_{sb.event_id}_{sb.selection}"
                        if sb_key in used_sb_ids:
                            continue

                        # CRITICAL: Only match if bet categories are compatible
                        # This prevents game moneylines matching against
                        # championship futures (e.g. Liverpool game vs Crystal
                        # Palace league position bet)
                        if pm.bet_category != sb.bet_category:
                            logger.debug(
                                f"Skipping category mismatch: "
                                f"PM '{pm.selection}' ({pm.bet_category}) vs "
                                f"SB '{sb.selection}' ({sb.bet_category})"
                            )
                            continue

                        # Compute confidence
                        confidence = self._compute_confidence(pm, sb, team)
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_sb = sb
                            best_team = team

                if best_sb and best_confidence >= self.confidence_threshold:
                    sb_key = f"{best_sb.platform.value}_{best_sb.event_id}_{best_sb.selection}"
                    used_sb_ids.add(sb_key)

                    match_id = generate_match_id(sport, best_team, "futures")
                    # Build a descriptive event name from sportsbook market context
                    sb_market = best_sb.event_name  # e.g. "Stanley Cup 2025-26 - Winner"
                    normalized_name = f"{best_sb.selection} to Win {sb_market}"

                    matched = MatchedEvent(
                        match_id=match_id,
                        sport=sport,
                        normalized_name=normalized_name,
                        market_type=pm.market_type,
                        prediction_market=pm,
                        sportsbook=best_sb,
                        match_confidence=best_confidence,
                    )
                    matches.append(matched)

                    logger.debug(
                        f"Matched: '{pm.selection}' ({pm.platform.value}) ↔ "
                        f"'{best_sb.selection}' ({best_sb.platform.value}) "
                        f"via team '{best_team}' (conf={best_confidence:.2f})"
                    )

        logger.info(f"Total matches found: {len(matches)}")
        return matches

    def _compute_confidence(
        self, pm: MarketOdds, sb: MarketOdds, shared_team: str
    ) -> float:
        """Compute match confidence between a PM and SB entry."""
        score = 0.0

        # Same sport (should always be true in our flow)
        if pm.sport == sb.sport:
            score += 0.3

        # Team name matched
        score += 0.4

        # Text similarity as tiebreaker
        combined_pm = (pm.event_name + " " + pm.selection).lower()
        combined_sb = (sb.event_name + " " + sb.selection).lower()
        text_sim = SequenceMatcher(None, combined_pm, combined_sb).ratio()
        score += text_sim * 0.3

        return min(score, 1.0)
