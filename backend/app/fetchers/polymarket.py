"""Fetcher for Polymarket prediction market odds."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx

from backend.app.config import settings
from backend.app.models import MarketOdds, MarketType, Platform, Sport, probability_to_american, probability_to_decimal

logger = logging.getLogger(__name__)


# Sport detection keywords for Polymarket markets
SPORT_KEYWORDS = {
    Sport.NFL: ["nfl", "football", "super bowl", "sb lviii", "sb lvii", "superbowl", "nfl"],
    Sport.NBA: ["nba", "basketball", "finals", "nba championship", "mvp"],
    Sport.MLB: ["mlb", "baseball", "world series", "world championship"],
    Sport.NHL: ["nhl", "hockey", "stanley cup"],
    Sport.EPL: ["epl", "premier league", "english football", "soccer"],
}


def detect_sport(title: str, description: str = "", tags: list[str] = None) -> Optional[Sport]:
    """Detect sport from market title, description, or tags using keyword matching."""
    if tags is None:
        tags = []

    combined_text = f"{title} {description} {' '.join(tags)}".lower()

    for sport, keywords in SPORT_KEYWORDS.items():
        if any(keyword in combined_text for keyword in keywords):
            return sport

    return None


class PolymarketFetcher:
    """Fetcher for Polymarket prediction market odds."""

    def __init__(self):
        """Initialize the Polymarket fetcher."""
        self.gamma_api_url = settings.POLYMARKET_GAMMA_API
        self.clob_api_url = settings.POLYMARKET_CLOB_API
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

    async def _fetch_json(self, base_url: str, endpoint: str, params: dict = None) -> Optional[dict]:
        """Fetch JSON from Polymarket API."""
        url = urljoin(base_url, endpoint)
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

    async def _fetch_markets(self, sport: Optional[Sport] = None) -> list[dict]:
        """Fetch markets from Polymarket Gamma API."""
        cache_key = f"polymarket_markets_{sport}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        all_markets = []
        offset = 0
        limit = 100
        max_iterations = 50  # Prevent infinite loops

        while max_iterations > 0:
            params = {
                "offset": offset,
                "limit": limit,
                "active": True,  # Only active markets
            }

            data = await self._fetch_json(self.gamma_api_url, "/markets", params=params)
            if not data:
                logger.warning("No markets data from Polymarket")
                break

            markets = data if isinstance(data, list) else data.get("data", [])
            if not markets:
                break

            # Filter for sports if sport specified
            if sport:
                filtered = [m for m in markets if self._is_sports_market(m, sport)]
                all_markets.extend(filtered)
            else:
                # If no sport specified, get all sports markets
                filtered = [m for m in markets if self._is_sports_market(m, None)]
                all_markets.extend(filtered)

            offset += limit
            max_iterations -= 1

        self._set_cache(cache_key, all_markets)
        return all_markets

    def _is_sports_market(self, market: dict, sport: Optional[Sport] = None) -> bool:
        """Check if market is sports-related and optionally matches sport."""
        title = market.get("title", "")
        description = market.get("description", "")
        tags = market.get("tags", [])

        detected_sport = detect_sport(title, description, tags)

        if sport:
            return detected_sport == sport
        else:
            return detected_sport is not None

    def _parse_outcome_prices(self, market: dict) -> list[float]:
        """Parse outcome prices from market data."""
        try:
            outcome_prices_raw = market.get("outcome_prices")
            if isinstance(outcome_prices_raw, str):
                return json.loads(outcome_prices_raw)
            elif isinstance(outcome_prices_raw, list):
                return outcome_prices_raw
            else:
                return []
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Error parsing outcome_prices: {e}")
            return []

    def _parse_outcomes(self, market: dict) -> list[str]:
        """Parse outcomes from market data."""
        try:
            outcomes_raw = market.get("outcomes")
            if isinstance(outcomes_raw, str):
                return json.loads(outcomes_raw)
            elif isinstance(outcomes_raw, list):
                return outcomes_raw
            else:
                return []
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Error parsing outcomes: {e}")
            return []

    def _create_market_odds(
        self,
        market: dict,
        outcome_index: int,
        outcome_name: str,
        price: float,
        sport: Sport,
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from Polymarket market data."""
        try:
            market_id = market.get("id", "")
            market_slug = market.get("slug", "")
            title = market.get("title", "")

            if not market_id or not title:
                return None

            # Convert price to probability (prices are already in 0-1 range)
            probability = float(price)
            if probability <= 0 or probability >= 1:
                return None

            # Determine market type
            title_lower = title.lower()
            if "over" in title_lower or "under" in title_lower:
                market_type = MarketType.OVER_UNDER
            else:
                market_type = MarketType.MONEYLINE

            american_odds = probability_to_american(probability)
            decimal_odds = probability_to_decimal(probability)

            # Polymarket market URL
            url = f"https://polymarket.com/market/{market_slug}" if market_slug else None

            return MarketOdds(
                platform=Platform.POLYMARKET,
                event_id=market_id,
                event_name=title,
                sport=sport,
                market_type=market_type,
                selection=outcome_name,
                probability=probability,
                american_odds=american_odds,
                decimal_odds=decimal_odds,
                raw_price=float(price),
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
            # Get markets
            markets = await self._fetch_markets(sport)

            if not markets:
                logger.warning(f"No Polymarket markets found for sport {sport}")
                return []

            logger.info(f"Found {len(markets)} Polymarket markets for sport {sport}")

            # Process each market
            for market in markets:
                try:
                    title = market.get("title", "")
                    description = market.get("description", "")
                    tags = market.get("tags", [])

                    # Detect sport from market
                    detected_sport = detect_sport(title, description, tags)
                    if not detected_sport:
                        continue

                    # Parse outcomes and prices
                    outcomes = self._parse_outcomes(market)
                    prices = self._parse_outcome_prices(market)

                    # Validate we have matching outcomes and prices
                    if not outcomes or not prices or len(outcomes) != len(prices):
                        logger.warning(
                            f"Mismatched outcomes ({len(outcomes)}) and prices ({len(prices)}) "
                            f"for market {market.get('id')}"
                        )
                        continue

                    # Create MarketOdds for each outcome
                    for outcome_index, (outcome_name, price) in enumerate(zip(outcomes, prices)):
                        try:
                            # Skip if price is string and can't be converted
                            try:
                                price_float = float(price)
                            except (ValueError, TypeError):
                                logger.warning(f"Invalid price {price} for outcome {outcome_name}")
                                continue

                            market_odds = self._create_market_odds(
                                market=market,
                                outcome_index=outcome_index,
                                outcome_name=outcome_name,
                                price=price_float,
                                sport=detected_sport,
                            )

                            if market_odds:
                                odds_list.append(market_odds)
                        except Exception as e:
                            logger.error(f"Error processing outcome {outcome_name}: {e}")
                            continue
                except Exception as e:
                    logger.error(f"Error processing market {market.get('id')}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} odds from Polymarket")
        return odds_list


async def fetch_polymarket_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Public function to fetch Polymarket odds.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from Polymarket prediction market
    """
    fetcher = PolymarketFetcher()
    return await fetcher.fetch_odds(sport)
