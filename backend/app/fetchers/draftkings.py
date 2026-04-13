"""Fetcher for DraftKings sportsbook odds."""
import json
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx

from backend.app.config import settings
from backend.app.models import MarketOdds, MarketType, Platform, Sport, american_to_probability, probability_to_decimal

logger = logging.getLogger(__name__)


class DraftKingsFetcher:
    """Fetcher for DraftKings sportsbook odds."""

    def __init__(self):
        """Initialize the DraftKings fetcher."""
        self.base_url = settings.DRAFTKINGS_API_BASE
        self.timeout = settings.REQUEST_TIMEOUT
        self.user_agent = settings.USER_AGENT
        self._cache = {}
        self._cache_times = {}
        self.sport_ids = settings.DK_SPORT_IDS

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
        """Fetch JSON from DraftKings API."""
        url = urljoin(self.base_url, endpoint)
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Referer": "https://sportsbook-nash.draftkings.com/",
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
        """Fetch events from DraftKings API."""
        cache_key = f"draftkings_events_{sport}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        all_events = []

        try:
            # Determine which sports to fetch
            sports_to_fetch = [sport] if sport else list(self.sport_ids.keys())

            for sport_key in sports_to_fetch:
                sport_id = self.sport_ids.get(sport_key)
                if not sport_id:
                    continue

                try:
                    # Try primary endpoint pattern
                    endpoint = f"/events?sportId={sport_id}&format=json"
                    data = await self._fetch_json(endpoint)

                    if data and "events" in data:
                        events = data.get("events", [])
                        if events:
                            all_events.extend(events)
                            logger.info(f"Found {len(events)} DraftKings events for {sport_key}")
                            continue

                    # Try alternative endpoint if primary fails
                    # This is a fallback pattern based on DK API structure
                    endpoint = f"/eventgroups/{sport_id}"
                    data = await self._fetch_json(endpoint)

                    if data:
                        # Extract events from eventgroups response
                        if "events" in data:
                            events = data.get("events", [])
                            if events:
                                all_events.extend(events)
                                logger.info(f"Found {len(events)} DraftKings events for {sport_key} (alt endpoint)")
                        elif "eventGroups" in data:
                            # Some responses may have eventGroups instead
                            for group in data.get("eventGroups", []):
                                if "events" in group:
                                    all_events.extend(group["events"])

                except Exception as e:
                    logger.warning(f"Error fetching DraftKings events for {sport_key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error fetching DraftKings events: {e}")

        self._set_cache(cache_key, all_events)
        return all_events

    def _extract_odds(self, offering: dict) -> tuple[Optional[int], Optional[int]]:
        """Extract American odds and decimal odds from DraftKings offering."""
        try:
            # DraftKings provides odds in multiple formats
            odds_american = offering.get("oddsAmerican")
            odds_decimal = offering.get("oddsDecimal")

            return odds_american, odds_decimal
        except Exception as e:
            logger.warning(f"Error extracting odds: {e}")
            return None, None

    def _detect_market_type(self, outcome_name: str, offering_name: str = "") -> MarketType:
        """Detect market type from outcome or offering names."""
        combined = f"{outcome_name} {offering_name}".lower()

        if "over" in combined or "under" in combined:
            return MarketType.OVER_UNDER
        else:
            return MarketType.MONEYLINE

    def _extract_moneyline_selection(self, outcome_name: str) -> str:
        """Extract clean selection name for moneyline markets."""
        # Remove common suffixes and clean up
        name = outcome_name.replace(" Win", "").replace(" Victory", "").strip()
        return name

    def _extract_ou_selection(self, outcome_name: str, offering_name: str = "") -> str:
        """Extract clean selection name for over/under markets."""
        # Try to extract over/under and the total
        combined = f"{offering_name} {outcome_name}".lower()

        if "over" in combined:
            # Extract the total line if present
            parts = outcome_name.split()
            if len(parts) > 0:
                return f"Over {parts[-1]}" if parts[-1].replace(".", "").isdigit() else "Over"
            return "Over"
        elif "under" in combined:
            parts = outcome_name.split()
            if len(parts) > 0:
                return f"Under {parts[-1]}" if parts[-1].replace(".", "").isdigit() else "Under"
            return "Under"

        return outcome_name

    def _create_market_odds(
        self,
        event: dict,
        outcome: dict,
        offering: dict,
        sport: Sport,
        american_odds: int,
        decimal_odds: float,
    ) -> Optional[MarketOdds]:
        """Create MarketOdds object from DraftKings market data."""
        try:
            event_id = str(event.get("eventId", ""))
            event_name = event.get("name", "")
            outcome_name = outcome.get("name", "")
            offering_name = offering.get("label", "")

            if not event_id or not event_name:
                return None

            # Detect market type
            market_type = self._detect_market_type(outcome_name, offering_name)

            # Determine selection
            if market_type == MarketType.OVER_UNDER:
                selection = self._extract_ou_selection(outcome_name, offering_name)
            else:
                selection = self._extract_moneyline_selection(outcome_name)

            # Calculate probability from American odds
            if american_odds:
                probability = american_to_probability(american_odds)
            elif decimal_odds:
                probability = 1 / decimal_odds if decimal_odds > 0 else 0.5
            else:
                return None

            # DraftKings event URL pattern
            url = f"https://sportsbook-nash.draftkings.com/sports/{event_name.lower().replace(' ', '-')}"

            return MarketOdds(
                platform=Platform.DRAFTKINGS,
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
            logger.error(f"Error creating MarketOdds from DraftKings data: {e}")
            return None

    def _sport_from_event_id(self, sport_id: int) -> Optional[Sport]:
        """Get sport enum from DraftKings sport ID."""
        for sport_key, dk_id in self.sport_ids.items():
            if dk_id == sport_id:
                return Sport(sport_key)
        return None

    async def fetch_odds(self, sport: Optional[Sport] = None) -> list[MarketOdds]:
        """Fetch odds from DraftKings for specified sport or all sports."""
        logger.info(f"Fetching DraftKings odds for sport: {sport}")

        odds_list = []

        try:
            # Get events
            events = await self._fetch_events(sport)

            if not events:
                logger.warning(f"No DraftKings events found for sport {sport}")
                return []

            logger.info(f"Found {len(events)} DraftKings events for sport {sport}")

            # Process each event
            for event in events:
                try:
                    event_id = event.get("eventId")
                    if not event_id:
                        continue

                    # Get offerings (markets) from the event
                    offerings = event.get("offerings", [])
                    if not offerings:
                        continue

                    # Process each offering (market)
                    for offering in offerings:
                        try:
                            outcomes = offering.get("outcomes", [])
                            if not outcomes:
                                continue

                            # Process each outcome (side of the bet)
                            for outcome in outcomes:
                                try:
                                    outcome_name = outcome.get("name")
                                    if not outcome_name:
                                        continue

                                    # Extract odds
                                    american_odds, decimal_odds = self._extract_odds(outcome)
                                    if not american_odds and not decimal_odds:
                                        continue

                                    # Determine sport from event or use provided sport
                                    event_sport = sport
                                    if not event_sport:
                                        # Try to infer from event name
                                        event_name = event.get("name", "").lower()
                                        for sport_key in self.sport_ids.keys():
                                            if sport_key in event_name or Sport[sport_key.upper()].value in event_name:
                                                event_sport = Sport(sport_key)
                                                break

                                    if not event_sport:
                                        # Fallback to first available sport
                                        event_sport = Sport.NFL

                                    # Create market odds
                                    market_odds = self._create_market_odds(
                                        event=event,
                                        outcome=outcome,
                                        offering=offering,
                                        sport=event_sport,
                                        american_odds=american_odds,
                                        decimal_odds=decimal_odds,
                                    )

                                    if market_odds:
                                        odds_list.append(market_odds)

                                except Exception as e:
                                    logger.warning(f"Error processing DraftKings outcome: {e}")
                                    continue

                        except Exception as e:
                            logger.warning(f"Error processing DraftKings offering: {e}")
                            continue

                except Exception as e:
                    logger.error(f"Error processing DraftKings event {event.get('eventId')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in fetch_odds: {e}")

        logger.info(f"Fetched {len(odds_list)} odds from DraftKings")
        return odds_list


async def fetch_draftkings_odds(sport: Optional[Sport] = None) -> list[MarketOdds]:
    """Public function to fetch DraftKings odds.

    Args:
        sport: Optional Sport enum value to filter by specific sport

    Returns:
        List of MarketOdds objects from DraftKings sportsbook
    """
    fetcher = DraftKingsFetcher()
    return await fetcher.fetch_odds(sport)
