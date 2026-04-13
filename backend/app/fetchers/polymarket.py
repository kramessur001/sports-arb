"""Fetcher for Polymarket prediction market odds."""
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from backend.app.config import settings
from backend.app.models import (
    MarketOdds,
    MarketType,
    Platform,
    Sport,
    probability_to_american,
    probability_to_decimal,
)

logger = logging.getLogger(__name__)


# Sport detection keywords for Polymarket markets
SPORT_KEYWORDS = {
    Sport.NFL: ["nfl", "football", "super bowl", "sb"],
    Sport.NBA: ["nba", "basketball", "finals", "championship"],
    Sport.MLB: ["mlb", "baseball", "world series"],
    Sport.NHL: ["nhl", "hockey", "stanley cup"],
    Sport.EPL: ["epl", "premier league", "soccer"],
}


def _detect_bet_category(question_lower: str) -> str:
    """Detect what kind of bet this is from the question text."""
    championship_kw = [
        "win the", "win nba", "win nfl", "win mlb", "win nhl",
        "stanley cup", "super bowl", "world series", "finals",
        "championship", "champion", "win the 202",
    ]
    position_kw = [
        "finish in", "place in", "make playoffs", "make the playoffs",
        "relegated", "promotion", "top 4", "top four",
        "qualify for", "clinch", "seed",
    ]
    award_kw = [
        "mvp", "rookie of", "defensive player", "most improved",
        "ballon d'or", "golden boot", "cy young", "heisman",
    ]
    game_kw = [
        "beat", "defeat", "vs", "versus", "game",
        "win against", "win on",
    ]

    # Check award FIRST (most specific — "win NBA MVP" shouldn't match "win NBA")
    if any(kw in question_lower for kw in award_kw):
        return "award"
    if any(kw in question_lower for kw in championship_kw):
        return "championship"
    if any(kw in question_lower for kw in position_kw):
        return "position"
    if any(kw in question_lower for kw in game_kw):
        return "game"
    return "other"


def detect_sport(question: str) -> Optional[Sport]:
    """Detect sport from market question text using keyword matching."""
    question_lower = question.lower()

    for sport, keywords in SPORT_KEYWORDS.items():
        if any(keyword in question_lower for keyword in keywords):
            return sport

    return None


class PolymarketFetcher:
    """Fetcher for Polymarket prediction market odds."""

    def __init__(self):
        """Initialize the Polymarket fetcher."""
        self.gamma_api_url = settings.POLYMARKET_GAMMA_API
        self.timeout = settings.REQUEST_TIMEOUT
        self.user_agent = settings.USER_AGENT
        self._cache = {}
        self._cache_times = {}

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        if key not in self._cache_times:
            return False
        age = (datetime.utcnow() - self._cache_times[key]).total_seconds()
        return age < settings.CACHE_TTL

    def _get_cached(self, key: str):
        """Get cached data if valid."""
        if self._is_cache_valid(key):
            return self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        """Cache data with timestamp."""
        self._cache[key] = data
        self._cache_times[key] = datetime.utcnow()

    async def _fetch_json(self, url: str, params: dict = None) -> Optional[list]:
        """Fetch JSON from Polymarket Gamma API."""
        headers = {"User-Agent": self.user_agent}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout fetching {url}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error from {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            return None

    async def _fetch_all_markets(self) -> list[dict]:
        """Fetch all sports markets from Polymarket by paginating through results."""
        cache_key = "polymarket_all_markets"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        all_markets = []
        url = f"{self.gamma_api_url}/markets"

        # Fetch 600 markets (6 pages of 100) with active and closed filters
        for offset in range(0, 600, 100):
            params = {
                "limit": 100,
                "active": "true",
                "closed": "false",
                "offset": offset,
            }

            markets = await self._fetch_json(url, params=params)
            if not markets:
                logger.warning(f"No markets returned at offset {offset}")
                break

            all_markets.extend(markets)
            logger.info(f"Fetched {len(markets)} markets at offset {offset}")

        self._set_cache(cache_key, all_markets)
        return all_markets

    def _parse_outcomes(self, outcomes_json: str) -> list[str]:
        """Parse JSON string of outcomes into list."""
        try:
            if isinstance(outcomes_json, str):
                return json.loads(outcomes_json)
            elif isinstance(outcomes_json, list):
                return outcomes_json
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def _parse_prices(self, prices_json: str) -> list[str]:
        """Parse JSON string of prices into list."""
        try:
            if isinstance(prices_json, str):
                return json.loads(prices_json)
            elif isinstance(prices_json, list):
                return prices_json
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def _create_market_odds(
        self,
        market: dict,
        outcome_name: str,
        probability: float,
        sport: Sport,
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from Polymarket market data."""
        try:
            market_id = market.get("id", "")
            market_slug = market.get("slug", "")
            question = market.get("question", "")

            if not market_id or not question:
                return None

            # Validate probability is in valid range
            if probability <= 0 or probability >= 1:
                return None

            # Determine market type based on question
            question_lower = question.lower()
            if "over" in question_lower or "under" in question_lower:
                market_type = MarketType.OVER_UNDER
            else:
                market_type = MarketType.MONEYLINE

            # Categorize the bet type
            bet_category = _detect_bet_category(question_lower)

            american_odds = probability_to_american(probability)
            decimal_odds = probability_to_decimal(probability)

            # Build URL
            url = f"https://polymarket.com/event/{market_slug}" if market_slug else None

            return MarketOdds(
                platform=Platform.POLYMARKET,
                event_id=market_id,
                event_name=question,
                sport=sport,
                market_type=market_type,
                selection=outcome_name,
                probability=probability,
                american_odds=american_odds,
                decimal_odds=decimal_odds,
                bet_category=bet_category,
                raw_price=probability,
                timestamp=datetime.utcnow(),
                url=url,
            )
        except Exception as e:
            logger.error(f"Error creating MarketOdds: {e}")
            return None

    async def fetch_odds(self, sport: Optional[Sport] = None) -> list[MarketOdds]:
        """Fetch odds from Polymarket for specified sport or all sports."""
        logger.info(f"Fetching Polymarket odds for sport: {sport}")

        odds_list = []

        try:
            # Get all markets
            markets = await self._fetch_all_markets()

            if not markets:
                logger.warning("No Polymarket markets found")
                return []

            logger.info(f"Total markets fetched: {len(markets)}")

            # Process each market
            for market in markets:
                try:
                    question = market.get("question", "")
                    outcomes_json = market.get("outcomes", "[]")
                    prices_json = market.get("outcomePrices", "[]")

                    # Detect sport from question
                    detected_sport = detect_sport(question)
                    if not detected_sport:
                        continue

                    # Filter by requested sport if specified
                    if sport and detected_sport != sport:
                        continue

                    # Parse outcomes and prices
                    outcomes = self._parse_outcomes(outcomes_json)
                    prices = self._parse_prices(prices_json)

                    # Validate we have matching outcomes and prices
                    if not outcomes or not prices or len(outcomes) != len(prices):
                        logger.warning(
                            f"Mismatched outcomes ({len(outcomes)}) and prices ({len(prices)}) "
                            f"for market {market.get('id')}"
                        )
                        continue

                    # Process "Yes" outcome (first outcome at index 0)
                    if len(prices) > 0:
                        try:
                            price = float(prices[0])
                            outcome_name = outcomes[0] if len(outcomes) > 0 else "Yes"

                            market_odds = self._create_market_odds(
                                market=market,
                                outcome_name=outcome_name,
                                probability=price,
                                sport=detected_sport,
                            )

                            if market_odds:
                                odds_list.append(market_odds)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid price format: {e}")
                            continue

                except Exception as e:
                    logger.error(f"Error processing market {market.get('id')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} Polymarket odds for sport {sport}")
        return odds_list


async def fetch_polymarket_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Fetch Polymarket prediction market odds.

    Fetches up to 600 sports markets, filters by keyword matching in the question
    field, and returns MarketOdds for the "Yes" outcome.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from Polymarket prediction market
    """
    fetcher = PolymarketFetcher()
    return await fetcher.fetch_odds(sport)
