"""Fetcher for Kalshi prediction market odds."""
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


def _detect_bet_category(title: str) -> str:
    """Detect bet category from Kalshi event/market title."""
    title_lower = title.lower()
    championship_kw = [
        "win the", "champion", "stanley cup", "super bowl",
        "world series", "finals", "win nba", "win nfl",
        "win mlb", "win nhl",
    ]
    position_kw = [
        "finish in", "place in", "make playoffs", "relegated",
        "top 4", "qualify for", "seed",
    ]
    award_kw = [
        "mvp", "rookie of", "defensive player", "most improved",
        "cy young", "heisman",
    ]
    game_kw = [
        "beat", "defeat", "vs", "versus", "game",
        "win against", "win on",
    ]
    # Check award FIRST (most specific — "win NBA MVP" shouldn't match "win NBA")
    if any(kw in title_lower for kw in award_kw):
        return "award"
    if any(kw in title_lower for kw in championship_kw):
        return "championship"
    if any(kw in title_lower for kw in position_kw):
        return "position"
    if any(kw in title_lower for kw in game_kw):
        return "game"
    return "other"


# Sport detection keywords for Kalshi markets
SPORT_KEYWORDS = {
    Sport.NFL: ["nfl", "football", "super bowl"],
    Sport.NBA: ["nba", "basketball", "championship"],
    Sport.MLB: ["mlb", "baseball", "world series"],
    Sport.NHL: ["nhl", "hockey", "stanley cup"],
    Sport.EPL: ["epl", "premier league", "soccer"],
}


def detect_sport(title: str) -> Optional[Sport]:
    """Detect sport from event title using keyword matching."""
    title_lower = title.lower()

    for sport, keywords in SPORT_KEYWORDS.items():
        if any(keyword in title_lower for keyword in keywords):
            return sport

    return None


class KalshiFetcher:
    """Fetcher for Kalshi prediction market odds."""

    def __init__(self):
        """Initialize the Kalshi fetcher."""
        self.base_url = settings.KALSHI_API_BASE
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

    async def _fetch_json(self, url: str, params: dict = None) -> Optional[dict]:
        """Fetch JSON from Kalshi API."""
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

    async def _fetch_events(self) -> list[dict]:
        """Fetch all open events from Kalshi API."""
        cache_key = "kalshi_events"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        url = f"{self.base_url}/events"
        params = {
            "status": "open",
            "limit": 100,
        }

        data = await self._fetch_json(url, params=params)
        if not data or "events" not in data:
            logger.warning("No events data from Kalshi")
            return []

        events = data.get("events", [])
        self._set_cache(cache_key, events)
        logger.info(f"Fetched {len(events)} events from Kalshi")
        return events

    async def _fetch_markets_for_event(self, event_ticker: str) -> list[dict]:
        """Fetch markets for a specific event."""
        cache_key = f"kalshi_markets_{event_ticker}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        url = f"{self.base_url}/markets"
        params = {
            "event_ticker": event_ticker,
            "status": "open",
        }

        data = await self._fetch_json(url, params=params)
        if not data or "markets" not in data:
            logger.debug(f"No markets for event {event_ticker}")
            return []

        markets = data.get("markets", [])
        self._set_cache(cache_key, markets)
        return markets

    def _price_to_probability(self, price: float) -> float:
        """Convert Kalshi contract price (0.00 to 1.00 in dollars) to probability."""
        if price < 0 or price > 1.0:
            logger.warning(f"Invalid contract price: {price}")
            return 0.5
        return float(price)

    def _get_price(self, yes_bid: Optional[float], yes_ask: Optional[float], last_price: Optional[float]) -> Optional[float]:
        """Get the best price estimate from available prices."""
        # Prefer midpoint if both bid and ask available
        if yes_bid is not None and yes_ask is not None:
            return (yes_bid + yes_ask) / 2.0

        # Fall back to ask or bid
        if yes_ask is not None:
            return yes_ask
        if yes_bid is not None:
            return yes_bid

        # Last resort: last price
        if last_price is not None:
            return last_price

        return None

    def _create_market_odds(
        self,
        event: dict,
        market: dict,
        probability: float,
        sport: Sport,
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from Kalshi market data."""
        try:
            event_ticker = event.get("event_ticker", "")
            event_title = event.get("title", "")
            market_ticker = market.get("ticker", "")

            if not event_ticker or not event_title or not market_ticker:
                return None

            # Validate probability
            if probability <= 0 or probability >= 1:
                return None

            # Determine market type from market title
            market_title = market.get("title", "").lower()
            if "over" in market_title or "under" in market_title:
                market_type = MarketType.OVER_UNDER
            else:
                market_type = MarketType.MONEYLINE

            american_odds = probability_to_american(probability)
            decimal_odds = probability_to_decimal(probability)

            # Build URL
            url = f"https://kalshi.com/markets/{market_ticker}"

            # Detect bet category from event title + market title
            bet_category = _detect_bet_category(
                event_title + " " + market.get("title", "")
            )

            return MarketOdds(
                platform=Platform.KALSHI,
                event_id=event_ticker,
                event_name=event_title,
                sport=sport,
                market_type=market_type,
                selection="Yes",  # Kalshi markets are binary yes/no
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
        """Fetch odds from Kalshi for specified sport or all sports.

        Fetches all open events, filters to sports category, then fetches markets
        for each sports event. Returns MarketOdds for "Yes" side only.
        """
        logger.info(f"Fetching Kalshi odds for sport: {sport}")

        odds_list = []

        try:
            # Fetch all open events
            events = await self._fetch_events()

            if not events:
                logger.warning("No Kalshi events found")
                return []

            logger.info(f"Found {len(events)} total Kalshi events")

            # Filter for sports events
            sports_events = []
            for event in events:
                # Check if event is in sports category
                category = event.get("category", "").lower()
                if category != "sports":
                    continue

                # Detect sport from title
                detected_sport = detect_sport(event.get("title", ""))
                if not detected_sport:
                    continue

                # Filter by requested sport if specified
                if sport and detected_sport != sport:
                    continue

                sports_events.append((event, detected_sport))

            logger.info(f"Found {len(sports_events)} sports events")

            # Process each sports event
            for event, detected_sport in sports_events:
                try:
                    event_ticker = event.get("event_ticker")
                    if not event_ticker:
                        continue

                    # Fetch markets for this event
                    markets = await self._fetch_markets_for_event(event_ticker)

                    if not markets:
                        continue

                    # Process each market
                    for market in markets:
                        try:
                            yes_bid = market.get("yes_bid_dollars")
                            yes_ask = market.get("yes_ask_dollars")
                            last_price = market.get("last_price_dollars")

                            # Get best price estimate
                            price = self._get_price(yes_bid, yes_ask, last_price)
                            if price is None:
                                continue

                            # Convert price to probability
                            probability = self._price_to_probability(price)

                            # Create market odds
                            market_odds = self._create_market_odds(
                                event=event,
                                market=market,
                                probability=probability,
                                sport=detected_sport,
                            )

                            if market_odds:
                                odds_list.append(market_odds)

                        except Exception as e:
                            logger.debug(f"Error processing market: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"Error processing event {event.get('event_ticker')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} Kalshi odds for sport {sport}")
        return odds_list


async def fetch_kalshi_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Fetch Kalshi prediction market odds.

    Fetches all open sports events, then fetches markets for each event.
    Returns MarketOdds for the "Yes" outcome with prices derived from
    yes_ask_dollars or the midpoint of yes_bid and yes_ask.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from Kalshi prediction market
    """
    fetcher = KalshiFetcher()
    return await fetcher.fetch_odds(sport)
