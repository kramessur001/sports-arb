"""Configuration for the sports arbitrage finder."""
import os
from typing import Optional


class Settings:
    # API Base URLs
    KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
    POLYMARKET_GAMMA_API = "https://gamma-api.polymarket.com"
    POLYMARKET_CLOB_API = "https://clob.polymarket.com"
    DRAFTKINGS_API_BASE = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1"
    FANDUEL_API_BASE = "https://sbapi.nj.sportsbook.fanduel.com/api"

    # DraftKings sport category IDs
    DK_SPORT_IDS = {
        "nfl": 88808,
        "nba": 42648,
        "mlb": 84240,
        "nhl": 42133,
        "epl": 40253,
    }

    # FanDuel sport category IDs
    FD_SPORT_IDS = {
        "nfl": 88808,
        "nba": 42648,
        "mlb": 84240,
        "nhl": 42133,
        "epl": 40253,
    }

    # Cache TTL in seconds
    CACHE_TTL = 60  # 1 minute cache for odds data

    # Arbitrage thresholds
    MIN_EDGE_PERCENT = 1.0  # Minimum edge to show
    HIGH_VALUE_EDGE_PERCENT = 5.0  # Edge threshold for email alerts

    # Email config (set via environment variables)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")

    # Refresh interval for frontend (milliseconds)
    REFRESH_INTERVAL_MS = 30000  # 30 seconds

    # Request settings
    REQUEST_TIMEOUT = 15
    USER_AGENT = "SportsArbFinder/1.0"


settings = Settings()
