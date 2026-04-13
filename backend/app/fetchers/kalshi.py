"""Fetcher for Kalshi prediction market odds."""
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


# Sport detection keywords for Kalshi markets
SPORT_KEYWORDS = {
    Sport.NFL: ["nfl", "football", "super bowl", "sb lviii", "sb lvii", "superbowl", "nfl"],
    Sport.NBA: ["nba", "basketball", "finals", "nba championship", "mvp"],
    Sport.MLB: ["mlb", "baseball", "world series", "world championship"],
    Sport.NHL: ["nhl", "hockey", "stanley cup"],
    Sport.EPL: ["epl", "premier league", "english football", "soccer"],
}

# Kalshi series tickers that are sports-related
SPORTS_TICKER_PATTERNS = {
    Sport.NFL: ["KXNFL", "NFL", "SB"],
    Sport.NBA: ["KXNBA", "NBA"],
    Sport.MLB: ["KXMLB", "MLB"],
    Sport.NHL: ["KXNHL", "NHL"],
    Sport.EPL: ["KXEPL", "EPL", "PL"],
}


def detect_sport(title: str, series_ticker: str = "") -> Optional[Sport]:
    """Detect sport from market title or series ticker using keyword matching."""
    combined_text = f"{title} {series_ticker}".lower()

    for sport, keywords in SPORT_KEYWORDS.items():
        if any(keyword in combined_text for keyword in keywords):
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

    async def _fetch_json(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Fetch JSON from Kalshi API."""
        url = urljoin(self.base_url, endpoint)
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

    async def _fetch_events(self, sport: Optional[Sport] = None) -> list[dict]:
        """Fetch events from Kalshi API."""
        cache_key = f"kalshi_events_{sport}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        all_events = []
        cursor = None
        page_count = 0
        max_pages = 10  # Prevent infinite loops

        while page_count < max_pages:
            params = {
                "status": "open",
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor

            data = await self._fetch_json("/events", params=params)
            if not data or "events" not in data:
                logger.warning(f"No events data in response for sport {sport}")
                break

            events = data.get("events", [])
            if not events:
                break

            # Filter for sports if sport specified
            if sport:
                filtered = [e for e in events if self._is_sports_event(e, sport)]
                all_events.extend(filtered)
            else:
                # If no sport specified, get all sports events
                filtered = [e for e in events if self._is_sports_event(e, None)]
                all_events.extend(filtered)

            cursor = data.get("cursor")
            if not cursor:
                break

            page_count += 1

        self._set_cache(cache_key, all_events)
        return all_events

    def _is_sports_event(self, event: dict, sport: Optional[Sport] = None) -> bool:
        """Check if event is sports-related and optionally matches sport."""
        title = event.get("title", "").lower()
        series_ticker = event.get("series_ticker", "").upper()

        detected_sport = detect_sport(event.get("title", ""), series_ticker)

        if sport:
            return detected_sport == sport
        else:
            return detected_sport is not None

    async def _fetch_markets_for_event(self, event_ticker: str) -> list[dict]:
        """Fetch markets for a specific event."""
        cache_key = f"kalshi_markets_{event_ticker}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        params = {
            "event_ticker": event_ticker,
            "status": "open",
            "limit": 100,
        }

        data = await self._fetch_json("/markets", params=params)
        if not data or "markets" not in data:
            logger.warning(f"No markets data for event {event_ticker}")
            return []

        markets = data.get("markets", [])
        self._set_cache(cache_key, markets)
        return markets

    def _contract_price_to_probability(self, price: int) -> float:
        """Convert Kalshi contract price (0-100 cents) to probability."""
        if price < 0 or price > 100:
            logger.warning(f"Invalid contract price: {price}")
            return 0.5
        return price / 100.0

    def _create_market_odds(
        self,
        event: dict,
        market: dict,
        contract: dict,
        selection: str,
        probability: float,
        sport: Sport,
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from Kalshi market data."""
        try:
            event_id = event.get("ticker", "")
            event_name = event.get("title", "")
            market_id = market.get("ticker", "")

            if not event_id or not event_name:
                return None

            # Determine market type
            market_title = market.get("title", "").lower()
            if "over" in market_title or "under" in market_title:
                market_type = MarketType.OVER_UNDER
            else:
                market_type = MarketType.MONEYLINE

            american_odds = probability_to_american(probability)
            decimal_odds = probability_to_decimal(probability)

            # Kalshi market URL pattern
            url = f"https://kalshi.com/markets/{market_id}"

            return MarketOdds(
                platform=Platform.KALSHI,
                event_id=event_id,
                event_name=event_name,
                sport=sport,
                market_type=market_type,
                selection=selection,
                probability=probability,
                american_odds=american_odds,
                decimal_odds=decimal_odds,
                raw_price=float(contract.get("yes_price", 0)),
                timestamp=datetime.utcnow(),
                url=url,
            )
        except Exception as e:
            logger.error(f"Error creating MarketOdds: {e}")
            return None

    async def fetch_odds(self, sport: Optional[Sport] = None) -> list[MarketOdds]:
        """Fetch odds from Kalshi for specified sport or all sports."""
        logger.info(f"Fetching Kalshi odds for sport: {sport}")

        odds_list = []

        try:
            # Get events
            events = await self._fetch_events(sport)

            if not events:
                logger.warning(f"No Kalshi events found for sport {sport}")
                return []

            logger.info(f"Found {len(events)} Kalshi events for sport {sport}")

            # Process each event
            for event in events:
                event_ticker = event.get("ticker")
                if not event_ticker:
                    continue

                # Detect sport from event
                detected_sport = detect_sport(event.get("title", ""), event.get("series_ticker", ""))
                if not detected_sport:
                    continue

                # Fetch markets for this event
                markets = await self._fetch_markets_for_event(event_ticker)

                for market in markets:
                    try:
                        # Process yes and no contracts
                        for contract_key, selection in [("YES", "Yes"), ("NO", "No")]:
                            yes_price = market.get("yes_price")
                            no_price = market.get("no_price")

                            if yes_price is None or no_price is None:
                                continue

                            # Use appropriate price
                            price = yes_price if contract_key == "YES" else no_price
                            probability = self._contract_price_to_probability(price)

                            # Create market odds
                            market_odds = self._create_market_odds(
                                event=event,
                                market=market,
                                contract=market,
                                selection=selection,
                                probability=probability,
                                sport=detected_sport,
                            )

                            if market_odds:
                                odds_list.append(market_odds)
                    except Exception as e:
                        logger.error(f"Error processing market {market.get('ticker')}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} odds from Kalshi")
        return odds_list


async def fetch_kalshi_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Public function to fetch Kalshi odds.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from Kalshi prediction market
    """
    fetcher = KalshiFetcher()
    return await fetcher.fetch_odds(sport)
