"""Fetcher for FanDuel sportsbook odds."""
import json
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx

from backend.app.config import settings
from backend.app.models import MarketOdds, MarketType, Platform, Sport, american_to_probability, probability_to_decimal

logger = logging.getLogger(__name__)


class FanDuelFetcher:
    """Fetcher for FanDuel sportsbook odds."""

    def __init__(self):
        """Initialize the FanDuel fetcher."""
        self.base_url = settings.FANDUEL_API_BASE
        self.timeout = settings.REQUEST_TIMEOUT
        self.user_agent = settings.USER_AGENT
        self._cache = {}
        self._cache_times = {}
        # Map sports to FanDuel category identifiers
        self.sport_categories = {
            "nfl": "nfl",
            "nba": "nba",
            "mlb": "mlb",
            "nhl": "nhl",
            "epl": "soccer",  # FanDuel uses "soccer" for EPL
        }

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
        """Fetch JSON from FanDuel API."""
        url = urljoin(self.base_url, endpoint)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Referer": "https://nj.sportsbook.fanduel.com/",
        }

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
        """Fetch events from FanDuel API."""
        cache_key = f"fanduel_events_{sport}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        all_events = []

        try:
            # Determine which sports to fetch
            sports_to_fetch = []
            if sport:
                sport_key = sport.value.lower()
                if sport_key in self.sport_categories:
                    sports_to_fetch = [sport_key]
            else:
                sports_to_fetch = list(self.sport_categories.keys())

            for sport_key in sports_to_fetch:
                sport_category = self.sport_categories.get(sport_key)
                if not sport_category:
                    continue

                try:
                    # Primary endpoint pattern for FanDuel content-managed pages
                    params = {
                        "page": sport_category.upper(),
                    }
                    endpoint = "/content-managed-page"
                    data = await self._fetch_json(endpoint, params=params)

                    if data:
                        events = []
                        # FanDuel API structure: events may be in different response formats
                        if "events" in data:
                            events = data.get("events", [])
                        elif "eventGroups" in data:
                            # Alternative: events organized by groups
                            for group in data.get("eventGroups", []):
                                if "events" in group:
                                    events.extend(group["events"])
                        elif "competitions" in data:
                            # Some sports may use competitions instead
                            for comp in data.get("competitions", []):
                                if "events" in comp:
                                    events.extend(comp["events"])

                        if events:
                            all_events.extend(events)
                            logger.info(f"Found {len(events)} FanDuel events for {sport_key}")
                            continue

                    # Try alternative endpoint pattern
                    endpoint = f"/v2/{sport_category}/events"
                    data = await self._fetch_json(endpoint)

                    if data and "events" in data:
                        events = data.get("events", [])
                        if events:
                            all_events.extend(events)
                            logger.info(f"Found {len(events)} FanDuel events for {sport_key} (alt endpoint)")

                except Exception as e:
                    logger.warning(f"Error fetching FanDuel events for {sport_key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error fetching FanDuel events: {e}")

        self._set_cache(cache_key, all_events)
        return all_events

    def _extract_odds(self, runner: dict) -> tuple[Optional[int], Optional[float]]:
        """Extract American odds and decimal odds from FanDuel runner."""
        try:
            # FanDuel provides odds in winRunnerOdds object
            win_odds = runner.get("winRunnerOdds", {})

            # Try American display odds first
            odds_american = win_odds.get("americanDisplayOdds")
            odds_decimal = win_odds.get("decimalOdds")

            # Fallback to other possible field names
            if not odds_american:
                odds_american = runner.get("americanOdds")
            if not odds_decimal:
                odds_decimal = runner.get("decimalOdds")

            return odds_american, odds_decimal
        except Exception as e:
            logger.warning(f"Error extracting odds from runner: {e}")
            return None, None

    def _detect_market_type(self, market_name: str = "", runner_name: str = "") -> MarketType:
        """Detect market type from market or runner names."""
        combined = f"{market_name} {runner_name}".lower()

        if "over" in combined or "under" in combined or "total" in combined:
            return MarketType.OVER_UNDER
        else:
            return MarketType.MONEYLINE

    def _extract_moneyline_selection(self, runner_name: str) -> str:
        """Extract clean selection name for moneyline markets."""
        # Remove common suffixes
        name = runner_name.replace(" Win", "").replace(" Victory", "").strip()
        return name

    def _extract_ou_selection(self, runner_name: str, market_name: str = "") -> str:
        """Extract clean selection name for over/under markets."""
        combined = f"{market_name} {runner_name}".lower()

        if "over" in combined:
            # Try to extract the total line if present
            parts = runner_name.split()
            if len(parts) > 0 and parts[-1].replace(".", "").replace("-", "").isdigit():
                return f"Over {parts[-1]}"
            return "Over"
        elif "under" in combined:
            parts = runner_name.split()
            if len(parts) > 0 and parts[-1].replace(".", "").replace("-", "").isdigit():
                return f"Under {parts[-1]}"
            return "Under"

        return runner_name

    def _create_market_odds(
        self,
        event: dict,
        market: dict,
        runner: dict,
        sport: Sport,
        american_odds: int,
        decimal_odds: float,
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from FanDuel market data."""
        try:
            event_id = str(event.get("eventId", "") or event.get("id", ""))
            event_name = event.get("name", "")
            runner_name = runner.get("name", "")
            market_name = market.get("name", "")

            if not event_id or not event_name:
                return None

            # Detect market type
            market_type = self._detect_market_type(market_name, runner_name)

            # Determine selection
            if market_type == MarketType.OVER_UNDER:
                selection = self._extract_ou_selection(runner_name, market_name)
            else:
                selection = self._extract_moneyline_selection(runner_name)

            # Calculate probability from American odds
            if american_odds:
                probability = american_to_probability(american_odds)
            elif decimal_odds:
                probability = 1 / decimal_odds if decimal_odds > 0 else 0.5
            else:
                return None

            # FanDuel event URL pattern (may vary by sport)
            url = f"https://nj.sportsbook.fanduel.com/event/{event_id}"

            return MarketOdds(
                platform=Platform.FANDUEL,
                event_id=event_id,
                event_name=event_name,
                sport=sport,
                market_type=market_type,
                selection=selection,
                probability=probability,
                american_odds=american_odds or 0,
                decimal_odds=decimal_odds or probability_to_decimal(probability),
                raw_price=None,
                timestamp=datetime.utcnow(),
                url=url,
            )
        except Exception as e:
            logger.error(f"Error creating MarketOdds from FanDuel data: {e}")
            return None

    def _infer_sport(self, event_name: str, event_id: str = "") -> Sport:
        """Infer sport from event name or ID."""
        event_text = f"{event_name} {event_id}".lower()

        # Check for each sport
        if any(keyword in event_text for keyword in ["nfl", "football"]):
            return Sport.NFL
        elif any(keyword in event_text for keyword in ["nba", "basketball"]):
            return Sport.NBA
        elif any(keyword in event_text for keyword in ["mlb", "baseball"]):
            return Sport.MLB
        elif any(keyword in event_text for keyword in ["nhl", "hockey"]):
            return Sport.NHL
        elif any(keyword in event_text for keyword in ["epl", "premier league", "soccer", "football"]):
            return Sport.EPL

        # Default to NFL if cannot determine
        return Sport.NFL

    async def fetch_odds(self, sport: Optional[Sport] = None) -> list[MarketOdds]:
        """Fetch odds from FanDuel for specified sport or all sports."""
        logger.info(f"Fetching FanDuel odds for sport: {sport}")

        odds_list = []

        try:
            # Get events
            events = await self._fetch_events(sport)

            if not events:
                logger.warning(f"No FanDuel events found for sport {sport}")
                return []

            logger.info(f"Found {len(events)} FanDuel events for sport {sport}")

            # Process each event
            for event in events:
                try:
                    event_id = event.get("eventId") or event.get("id")
                    if not event_id:
                        continue

                    event_name = event.get("name", "")
                    if not event_name:
                        continue

                    # Get markets from the event
                    markets = event.get("markets", [])
                    if not markets:
                        continue

                    # Process each market
                    for market in markets:
                        try:
                            runners = market.get("runners", [])
                            if not runners:
                                continue

                            # Process each runner (side of the bet)
                            for runner in runners:
                                try:
                                    runner_name = runner.get("name")
                                    if not runner_name:
                                        continue

                                    # Extract odds
                                    american_odds, decimal_odds = self._extract_odds(runner)
                                    if not american_odds and not decimal_odds:
                                        continue

                                    # Determine sport
                                    event_sport = sport or self._infer_sport(event_name, str(event_id))

                                    # Create market odds
                                    market_odds = self._create_market_odds(
                                        event=event,
                                        market=market,
                                        runner=runner,
                                        sport=event_sport,
                                        american_odds=american_odds,
                                        decimal_odds=decimal_odds,
                                    )

                                    if market_odds:
                                        odds_list.append(market_odds)

                                except Exception as e:
                                    logger.warning(f"Error processing FanDuel runner: {e}")
                                    continue

                        except Exception as e:
                            logger.warning(f"Error processing FanDuel market: {e}")
                            continue

                except Exception as e:
                    logger.error(f"Error processing FanDuel event {event.get('eventId')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} odds from FanDuel")
        return odds_list


async def fetch_fanduel_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Public function to fetch FanDuel odds.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from FanDuel sportsbook
    """
    fetcher = FanDuelFetcher()
    return await fetcher.fetch_odds(sport)
