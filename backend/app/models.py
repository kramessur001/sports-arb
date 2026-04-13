"""Data models for sports arbitrage finder."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Sport(str, Enum):
    NFL = "nfl"
    NBA = "nba"
    MLB = "mlb"
    NHL = "nhl"
    EPL = "epl"


class MarketType(str, Enum):
    MONEYLINE = "moneyline"
    OVER_UNDER = "over_under"


class Platform(str, Enum):
    KALSHI = "kalshi"
    POLYMARKET = "polymarket"
    DRAFTKINGS = "draftkings"
    FANDUEL = "fanduel"


@dataclass
class MarketOdds:
    """Represents odds for one side of a bet on a specific platform."""
    platform: Platform
    event_id: str  # platform-specific ID
    event_name: str  # raw event name from platform
    sport: Sport
    market_type: MarketType
    selection: str  # e.g., "Lakers Win", "Over 210.5"
    probability: float  # implied probability 0-1
    american_odds: int  # American odds format
    decimal_odds: float  # Decimal odds format
    raw_price: Optional[float] = None  # raw price (e.g., Kalshi contract price)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    url: Optional[str] = None  # link to the bet on the platform


@dataclass
class MatchedEvent:
    """An event matched across platforms."""
    match_id: str
    sport: Sport
    normalized_name: str  # e.g., "Lakers vs Celtics"
    event_date: Optional[datetime] = None
    market_type: MarketType = MarketType.MONEYLINE
    prediction_market: Optional[MarketOdds] = None  # Kalshi/Polymarket
    sportsbook: Optional[MarketOdds] = None  # DK/FD
    match_confidence: float = 0.0  # 0-1 confidence in the match


@dataclass
class ArbitrageOpportunity:
    """A detected arbitrage or edge opportunity."""
    matched_event: MatchedEvent
    edge_percent: float  # positive = prediction market underpriced
    prediction_market_prob: float
    sportsbook_implied_prob: float
    recommendation: str  # clear action to take
    expected_value: float  # EV per dollar wagered
    category: str  # "strong", "moderate", "slight"
    timestamp: datetime = field(default_factory=datetime.utcnow)


def american_to_probability(american_odds: int) -> float:
    """Convert American odds to implied probability."""
    if american_odds > 0:
        return 100 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)


def probability_to_american(prob: float) -> int:
    """Convert probability to American odds."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-prob / (1 - prob) * 100)
    else:
        return int((1 - prob) / prob * 100)


def probability_to_decimal(prob: float) -> float:
    """Convert probability to decimal odds."""
    if prob <= 0:
        return 0.0
    return round(1 / prob, 3)
