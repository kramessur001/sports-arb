"""Fetcher for FanDuel sportsbook odds."""
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
    american_to_probability,
    probability_to_decimal,
)

logger = logging.getLogger(__name__)


class FanDuelFetcher:
    """Fetcher for FanDuel sportsbook odds."""

    def __init__(self):
        """Initialize the FanDuel fetcher."""
        self.base_url = "https://sbapi.nj.sportsbook.fanduel.com/api"
        self.timeout = settings.REQUEST_TIMEOUT
        self.user_agent = settings.USER_AGENT
        self._cache = {}
        self._cache_times = {}
        # Map sports to FanDuel custom page IDs
        self.sport_pages = {
            Sport.NFL: "nfl",
            Sport.NBA: "nba",
            Sport.MLB: "mlb",
            Sport.NHL: "nhl",
            Sport.EPL: "soccer",
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

    async def _fetch_json(self, url: str, params: dict = None) -> Optional[dict]:
        """Fetch JSON from FanDuel API."""
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

    async def _fetch_markets_for_sport(self, sport: Sport) -> list[dict]:
        """Fetch markets for a specific sport from FanDuel API."""
        cache_key = f"fanduel_markets_{sport.value}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        markets = []

        try:
            # Get the custom page ID for this sport
            page_id = self.sport_pages.get(sport)
            if not page_id:
                logger.warning(f"No page ID found for sport {sport}")
                return []

            # Fetch from CUSTOM endpoint with custom page ID
            url = f"{self.base_url}/content-managed-page"
            params = {
                "page": "CUSTOM",
                "customPageId": page_id,
                "_ak": "FhMFpcPWXMeyZxOx",
            }

            data = await self._fetch_json(url, params=params)

            if not data:
                logger.warning(f"No data from FanDuel for sport {sport}")
                return []

            # Extract events and markets from attachments
            attachments = data.get("attachments", {})
            if not attachments:
                logger.warning(f"No attachments in FanDuel response for {sport}")
                return []

            events_dict = attachments.get("events", {})
            markets_dict = attachments.get("markets", {})

            # Convert markets dict to list and enrich with event info
            for market_id, market_data in markets_dict.items():
                market_data["id"] = market_id
                markets.append(market_data)

            logger.info(f"Found {len(markets)} markets for {sport}")

        except Exception as e:
            logger.error(f"Error fetching FanDuel markets for {sport}: {e}")

        self._set_cache(cache_key, markets)
        return markets

    def _extract_odds(self, runner: dict) -> tuple[Optional[int], Optional[float]]:
        """Extract American and decimal odds from FanDuel runner."""
        try:
            # Navigate the nested odds structure
            win_runner_odds = runner.get("winRunnerOdds", {})

            # American odds from americanDisplayOdds
            american_display = win_runner_odds.get("americanDisplayOdds", {})
            american_odds = american_display.get("americanOdds")

            # Decimal odds from decimalOdds
            decimal_odds_obj = win_runner_odds.get("decimalOdds", {})
            decimal_odds = decimal_odds_obj.get("decimalOdds")

            # Convert to proper types
            if american_odds is not None:
                american_odds = int(american_odds)
            if decimal_odds is not None:
                decimal_odds = float(decimal_odds)

            return american_odds, decimal_odds
        except Exception as e:
            logger.warning(f"Error extracting odds from runner: {e}")
            return None, None

    def _detect_market_type(self, market_name: str = "") -> MarketType:
        """Detect market type from market name."""
        market_lower = market_name.lower()

        if "over" in market_lower or "under" in market_lower or "total" in market_lower:
            return MarketType.OVER_UNDER
        else:
            return MarketType.MONEYLINE

    def _create_market_odds(
        self,
        event_id: str,
        event_name: str,
        runner_name: str,
        market_name: str,
        sport: Sport,
        american_odds: Optional[int],
        decimal_odds: Optional[float],
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from FanDuel market data."""
        try:
            if not event_id or not event_name:
                return None

            # Calculate probability from available odds
            if american_odds:
                probability = american_to_probability(american_odds)
            elif decimal_odds and decimal_odds > 0:
                probability = 1 / decimal_odds
            else:
                return None

            # Ensure probability is valid
            if probability <= 0 or probability >= 1:
                return None

            # Detect market type
            market_type = self._detect_market_type(market_name)

            # Use runner name as selection (team or over/under)
            selection = runner_name.strip()

            # Build URL
            url = f"https://nj.sportsbook.fanduel.com/event/{event_id}"

            # Calculate American and decimal odds if not already present
            if not american_odds:
                american_odds = 0
            if not decimal_odds:
                decimal_odds = probability_to_decimal(probability)

            return MarketOdds(
                platform=Platform.FANDUEL,
                event_id=str(event_id),
                event_name=event_name,
                sport=sport,
                market_type=market_type,
                selection=selection,
                probability=probability,
                american_odds=american_odds,
                decimal_odds=decimal_odds,
                raw_price=None,
                timestamp=datetime.utcnow(),
                url=url,
            )
        except Exception as e:
            logger.error(f"Error creating MarketOdds from FanDuel data: {e}")
            return None

    async def fetch_odds(self, sport: Optional[Sport] = None) -> list[MarketOdds]:
        """Fetch odds from FanDuel for specified sport or all sports."""
        logger.info(f"Fetching FanDuel odds for sport: {sport}")

        odds_list = []

        try:
            # Determine which sports to fetch
            sports_to_fetch = [sport] if sport else list(self.sport_pages.keys())

            for target_sport in sports_to_fetch:
                try:
                    # Fetch markets for this sport
                    markets = await self._fetch_markets_for_sport(target_sport)

                    if not markets:
                        logger.debug(f"No FanDuel markets found for {target_sport}")
                        continue

                    logger.info(f"Found {len(markets)} markets for {target_sport}")

                    # Process each market — only OUTRIGHT WINNER markets
                    # Polymarket has "Will X win the championship?" so we match
                    # against FanDuel's championship/outright winner markets ONLY.
                    # Exclude exact results, conference winners, player awards, etc.
                    WINNER_KEYWORDS = [
                        "finals winner", "championship", "champion",
                        "stanley cup 2", "super bowl 2", "world series 2",
                        "to win",
                    ]
                    EXCLUDE_KEYWORDS = [
                        "exact result", "conference", "division",
                        "first time", "first-time", "to make playoffs",
                        "mvp", "trophy", "player of", "coach of",
                        "rookie", "improved", "sixth man",
                        "award", "pick", "draft", "advance to",
                        "finalists", "matchup", "double chance",
                        "state of", "winning league",
                    ]

                    for market in markets:
                        try:
                            market_id = market.get("id", "")
                            market_name = market.get("marketName", "")
                            event_id = market.get("eventId", "")
                            runners = market.get("runners", [])

                            if not market_id or not event_id or not runners:
                                continue

                            # Filter: only keep outright winner markets
                            market_lower = market_name.lower()
                            is_winner = any(kw in market_lower for kw in WINNER_KEYWORDS)
                            is_excluded = any(kw in market_lower for kw in EXCLUDE_KEYWORDS)
                            if not is_winner or is_excluded:
                                continue

                            # Include market name in event_name for better matching context
                            event_name = market_name or f"Event {event_id}"

                            # Process each runner (team/side)
                            for runner in runners:
                                try:
                                    runner_name = runner.get("runnerName", "")
                                    if not runner_name:
                                        continue

                                    # Extract odds
                                    american_odds, decimal_odds = self._extract_odds(runner)
                                    if american_odds is None and decimal_odds is None:
                                        continue

                                    # Create market odds
                                    market_odds = self._create_market_odds(
                                        event_id=event_id,
                                        event_name=event_name,
                                        runner_name=runner_name,
                                        market_name=market_name,
                                        sport=target_sport,
                                        american_odds=american_odds,
                                        decimal_odds=decimal_odds,
                                    )

                                    if market_odds:
                                        odds_list.append(market_odds)

                                except Exception as e:
                                    logger.debug(f"Error processing FanDuel runner: {e}")
                                    continue

                        except Exception as e:
                            logger.debug(f"Error processing FanDuel market: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"Error fetching FanDuel markets for {target_sport}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} FanDuel odds for sport {sport}")
        return odds_list


async def fetch_fanduel_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Fetch FanDuel sportsbook odds.

    Uses the content-managed page endpoint with custom page IDs for each sport.
    Extracts markets with runners (teams) and converts American odds to
    implied probability.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from FanDuel sportsbook
    """
    fetcher = FanDuelFetcher()
    return await fetcher.fetch_odds(sport)
