"""Fetcher for DraftKings sportsbook odds via The Odds API."""
import json
import logging
import os
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


class DraftKingsFetcher:
    """Fetcher for DraftKings sportsbook odds via The Odds API."""

    def __init__(self):
        """Initialize the DraftKings fetcher."""
        self.timeout = settings.REQUEST_TIMEOUT
        self.user_agent = settings.USER_AGENT
        self._cache = {}
        self._cache_times = {}
        # Map Sport enum to The Odds API sport keys
        self.sport_keys = {
            Sport.NFL: "americanfootball_nfl",
            Sport.NBA: "basketball_nba",
            Sport.MLB: "baseball_mlb",
            Sport.NHL: "icehockey_nhl",
            Sport.EPL: "soccer_epl",
        }
        # API key from environment
        self.api_key = os.getenv("ODDS_API_KEY")

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
        """Fetch JSON from The Odds API."""
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

    async def _fetch_odds_for_sport(self, sport: Sport) -> list[dict]:
        """Fetch odds from The Odds API for a specific sport."""
        if not self.api_key:
            logger.warning("ODDS_API_KEY not set, skipping DraftKings data via The Odds API")
            return []

        cache_key = f"draftkings_{sport.value}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        sport_key = self.sport_keys.get(sport)
        if not sport_key:
            logger.warning(f"No Odds API sport key for {sport}")
            return []

        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": "us",
            "markets": "h2h,totals",
            "bookmakers": "draftkings,fanduel",
        }

        events = await self._fetch_json(url, params=params)

        if not events:
            logger.warning(f"No events from Odds API for {sport}")
            return []

        self._set_cache(cache_key, events)
        logger.info(f"Fetched {len(events)} events for {sport} from Odds API")
        return events

    def _create_market_odds(
        self,
        event: dict,
        home_team: str,
        away_team: str,
        outcome_name: str,
        decimal_odds: float,
        sport: Sport,
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from The Odds API data."""
        try:
            event_id = event.get("id", "")
            sport_key = event.get("sport_key", "")

            if not event_id:
                return None

            # Convert decimal odds to probability (1/decimal_odds)
            if decimal_odds <= 0:
                return None

            probability = 1.0 / decimal_odds

            # Validate probability
            if probability <= 0 or probability >= 1:
                return None

            # Create event name
            event_name = f"{home_team} vs {away_team}"

            # Detect market type from outcome name
            outcome_lower = outcome_name.lower()
            if "over" in outcome_lower or "under" in outcome_lower:
                market_type = MarketType.OVER_UNDER
            else:
                market_type = MarketType.MONEYLINE

            american_odds = probability_to_american(probability)
            decimal_odds_full = probability_to_decimal(probability)

            return MarketOdds(
                platform=Platform.DRAFTKINGS,
                event_id=event_id,
                event_name=event_name,
                sport=sport,
                market_type=market_type,
                selection=outcome_name,
                probability=probability,
                american_odds=american_odds,
                decimal_odds=decimal_odds_full,
                raw_price=decimal_odds,
                timestamp=datetime.utcnow(),
                url=None,  # Odds API doesn't provide direct links
            )
        except Exception as e:
            logger.error(f"Error creating MarketOdds: {e}")
            return None

    async def fetch_odds(self, sport: Optional[Sport] = None) -> list[MarketOdds]:
        """Fetch odds from The Odds API for DraftKings.

        Requires ODDS_API_KEY environment variable. If not set, returns empty list.
        """
        if not self.api_key:
            logger.warning(
                "ODDS_API_KEY env var not set. Set it for DraftKings data "
                "(free tier available at https://the-odds-api.com)"
            )
            return []

        logger.info(f"Fetching DraftKings odds via Odds API for sport: {sport}")

        odds_list = []

        try:
            # Determine which sports to fetch
            sports_to_fetch = [sport] if sport else list(self.sport_keys.keys())

            for target_sport in sports_to_fetch:
                try:
                    # Fetch events for this sport
                    events = await self._fetch_odds_for_sport(target_sport)

                    if not events:
                        logger.debug(f"No Odds API events for {target_sport}")
                        continue

                    # Process each event
                    for event in events:
                        try:
                            home_team = event.get("home_team", "")
                            away_team = event.get("away_team", "")
                            bookmakers = event.get("bookmakers", [])

                            if not bookmakers:
                                continue

                            # Find DraftKings bookmaker
                            for bookmaker in bookmakers:
                                if bookmaker.get("key") != "draftkings":
                                    continue

                                markets = bookmaker.get("markets", [])
                                for market in markets:
                                    market_key = market.get("key", "")
                                    outcomes = market.get("outcomes", [])

                                    for outcome in outcomes:
                                        try:
                                            outcome_name = outcome.get("name", "")
                                            decimal_odds = outcome.get("price")

                                            if not outcome_name or decimal_odds is None:
                                                continue

                                            decimal_odds = float(decimal_odds)

                                            market_odds = self._create_market_odds(
                                                event=event,
                                                home_team=home_team,
                                                away_team=away_team,
                                                outcome_name=outcome_name,
                                                decimal_odds=decimal_odds,
                                                sport=target_sport,
                                            )

                                            if market_odds:
                                                odds_list.append(market_odds)

                                        except Exception as e:
                                            logger.debug(f"Error processing outcome: {e}")
                                            continue

                        except Exception as e:
                            logger.debug(f"Error processing event: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"Error fetching odds for {target_sport}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} DraftKings odds via Odds API for sport {sport}")
        return odds_list


async def fetch_draftkings_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Fetch DraftKings sportsbook odds via The Odds API aggregator.

    Requires ODDS_API_KEY environment variable to be set. If not available,
    returns an empty list and logs a warning with setup instructions.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from DraftKings via The Odds API
    """
    fetcher = DraftKingsFetcher()
    return await fetcher.fetch_odds(sport)
