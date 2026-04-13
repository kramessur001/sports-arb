"""
Sports Arb Finder — FastAPI Backend

Serves both the API and the React frontend (as static files).
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from .config import settings
from .models import Sport, Platform, ArbitrageOpportunity
from .fetchers import (
    fetch_kalshi_odds,
    fetch_polymarket_odds,
    fetch_draftkings_odds,
    fetch_fanduel_odds,
)
from .matching import EventMatcher
from .arbitrage import ArbitrageCalculator
from .notifications.email_alerts import send_alert_email

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sports Arb Finder",
    description="Find arbitrage opportunities between prediction markets and sportsbooks",
    version="1.0.0",
)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize engines
matcher = EventMatcher(confidence_threshold=0.45)
calculator = ArbitrageCalculator(min_edge_percent=settings.MIN_EDGE_PERCENT)

# In-memory cache for the latest scan results
_cache = {
    "opportunities": [],
    "last_scan": None,
    "scan_in_progress": False,
}


def serialize_opportunity(opp: ArbitrageOpportunity) -> dict:
    """Convert an ArbitrageOpportunity to a JSON-serializable dict."""
    me = opp.matched_event
    pm = me.prediction_market
    sb = me.sportsbook
    return {
        "id": me.match_id,
        "sport": me.sport.value,
        "event": me.normalized_name,
        "event_date": me.event_date.isoformat() if me.event_date else None,
        "market_type": me.market_type.value,
        "match_confidence": round(me.match_confidence, 2),
        "prediction_market": {
            "platform": pm.platform.value if pm else None,
            "selection": pm.selection if pm else None,
            "probability": round(pm.probability, 4) if pm else None,
            "american_odds": pm.american_odds if pm else None,
            "decimal_odds": pm.decimal_odds if pm else None,
            "price_cents": round(pm.probability * 100, 1) if pm else None,
            "url": pm.url if pm else None,
            "raw_name": pm.event_name if pm else None,
        } if pm else None,
        "sportsbook": {
            "platform": sb.platform.value if sb else None,
            "selection": sb.selection if sb else None,
            "probability": round(sb.probability, 4) if sb else None,
            "american_odds": sb.american_odds if sb else None,
            "decimal_odds": sb.decimal_odds if sb else None,
            "url": sb.url if sb else None,
            "raw_name": sb.event_name if sb else None,
        } if sb else None,
        "edge_percent": opp.edge_percent,
        "expected_value": opp.expected_value,
        "category": opp.category,
        "recommendation": opp.recommendation,
        "timestamp": opp.timestamp.isoformat(),
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/scan")
async def scan_opportunities(
    sport: Optional[str] = Query(None, description="Filter by sport: nfl, nba, mlb, nhl, epl"),
    min_edge: float = Query(1.0, description="Minimum edge percentage"),
):
    """
    Trigger a fresh scan for arbitrage opportunities.
    Fetches data from all platforms, matches events, and calculates edges.
    """
    if _cache["scan_in_progress"]:
        return JSONResponse(
            status_code=429,
            content={"error": "Scan already in progress. Try again shortly."},
        )

    _cache["scan_in_progress"] = True

    try:
        sport_filter = Sport(sport) if sport else None

        # Fetch from all platforms concurrently
        logger.info(f"Starting scan (sport={sport}, min_edge={min_edge}%)")

        kalshi_task = fetch_kalshi_odds(sport_filter)
        polymarket_task = fetch_polymarket_odds(sport_filter)
        dk_task = fetch_draftkings_odds(sport_filter)
        fd_task = fetch_fanduel_odds(sport_filter)

        results = await asyncio.gather(
            kalshi_task, polymarket_task, dk_task, fd_task,
            return_exceptions=True,
        )

        # Collect results, handling any errors
        prediction_markets = []
        sportsbooks = []
        errors = []

        for i, (name, result) in enumerate(zip(
            ["Kalshi", "Polymarket", "DraftKings", "FanDuel"], results
        )):
            if isinstance(result, Exception):
                logger.error(f"{name} fetch failed: {result}")
                errors.append(f"{name}: {str(result)}")
            else:
                logger.info(f"{name}: {len(result)} markets fetched")
                if i < 2:  # Kalshi, Polymarket
                    prediction_markets.extend(result)
                else:  # DK, FD
                    sportsbooks.extend(result)

        # Match events across platforms
        matched = matcher.match_markets(prediction_markets, sportsbooks)

        # Find arbitrage opportunities
        calc = ArbitrageCalculator(min_edge_percent=min_edge)
        opportunities = calc.find_opportunities(matched)

        # Cache results
        _cache["opportunities"] = opportunities
        _cache["last_scan"] = datetime.utcnow().isoformat()

        # Send email alert for high-value opportunities
        high_value = [
            o for o in opportunities
            if abs(o.edge_percent) >= settings.HIGH_VALUE_EDGE_PERCENT
        ]
        if high_value:
            asyncio.create_task(send_alert_email(high_value))

        serialized = [serialize_opportunity(o) for o in opportunities]

        return {
            "opportunities": serialized,
            "meta": {
                "total_found": len(opportunities),
                "prediction_markets_fetched": len(prediction_markets),
                "sportsbooks_fetched": len(sportsbooks),
                "events_matched": len(matched),
                "scan_time": _cache["last_scan"],
                "errors": errors if errors else None,
                "sport_filter": sport,
                "min_edge": min_edge,
            },
        }

    except Exception as e:
        logger.exception("Scan failed")
        return JSONResponse(
            status_code=500,
            content={"error": f"Scan failed: {str(e)}"},
        )
    finally:
        _cache["scan_in_progress"] = False


@app.get("/api/opportunities")
async def get_cached_opportunities(
    sport: Optional[str] = Query(None),
    min_edge: float = Query(0),
    sort_by: str = Query("edge", description="Sort by: edge, sport, confidence"),
):
    """Return cached opportunities (from last scan) with optional filters."""
    opps = _cache.get("opportunities", [])

    # Filter
    filtered = []
    for opp in opps:
        if sport and opp.matched_event.sport.value != sport:
            continue
        if abs(opp.edge_percent) < min_edge:
            continue
        filtered.append(opp)

    # Sort
    if sort_by == "sport":
        filtered.sort(key=lambda o: o.matched_event.sport.value)
    elif sort_by == "confidence":
        filtered.sort(key=lambda o: o.matched_event.match_confidence, reverse=True)
    else:
        filtered.sort(key=lambda o: abs(o.edge_percent), reverse=True)

    return {
        "opportunities": [serialize_opportunity(o) for o in filtered],
        "last_scan": _cache.get("last_scan"),
        "total": len(filtered),
    }


@app.get("/api/sports")
async def get_sports():
    """Return available sports."""
    return {
        "sports": [
            {"id": s.value, "name": s.value.upper(), "label": {
                "nfl": "NFL Football",
                "nba": "NBA Basketball",
                "mlb": "MLB Baseball",
                "nhl": "NHL Hockey",
                "epl": "Premier League",
            }.get(s.value, s.value.upper())}
            for s in Sport
        ]
    }


@app.get("/api/config")
async def get_config():
    """Return frontend config."""
    return {
        "refresh_interval_ms": settings.REFRESH_INTERVAL_MS,
        "min_edge_default": settings.MIN_EDGE_PERCENT,
        "high_value_threshold": settings.HIGH_VALUE_EDGE_PERCENT,
        "email_configured": bool(settings.SMTP_USER and settings.ALERT_EMAIL_TO),
    }


# Serve React frontend (static files)
frontend_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React app for all non-API routes."""
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))
