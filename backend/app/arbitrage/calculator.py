"""
Arbitrage and edge detection engine.

Compares implied probabilities between prediction markets and sportsbooks
to find mispricing opportunities.

Key concept:
- If Kalshi prices "Lakers Win" at 55¢ (55% implied probability)
- But DraftKings has Lakers moneyline at -180 (64.3% implied probability)
- That's a +9.3% edge → BUY on Kalshi

The sportsbook line is generally considered the "sharp" price because
of the massive volume and professional bettor activity. When a prediction
market price diverges significantly from the sportsbook implied probability,
that's a potential opportunity.
"""

import logging
from datetime import datetime

from ..models import (
    MatchedEvent, ArbitrageOpportunity, MarketType
)

logger = logging.getLogger(__name__)


def calculate_edge(
    prediction_prob: float,
    sportsbook_prob: float,
) -> float:
    """
    Calculate the edge percentage.
    Positive = prediction market is underpriced (buy opportunity).
    Negative = prediction market is overpriced (sell/no opportunity).
    """
    return (sportsbook_prob - prediction_prob) * 100


def calculate_expected_value(
    prediction_prob: float,
    sportsbook_prob: float,
) -> float:
    """
    Calculate expected value per dollar wagered.
    Uses sportsbook probability as the "true" probability.

    If you buy a contract at prediction_prob price, and the true probability
    of winning is sportsbook_prob:
    EV = (sportsbook_prob * payout) - cost
    For a $1 contract at prediction_prob cents:
    EV = (sportsbook_prob * $1) - prediction_prob
    """
    payout = 1.0  # $1 payout on a correct prediction
    cost = prediction_prob  # cost of the contract
    ev = (sportsbook_prob * payout) - cost
    return round(ev, 4)


def categorize_edge(edge_percent: float) -> str:
    """Categorize the strength of an edge."""
    abs_edge = abs(edge_percent)
    if abs_edge >= 10:
        return "strong"
    elif abs_edge >= 5:
        return "moderate"
    elif abs_edge >= 2:
        return "slight"
    else:
        return "minimal"


def build_recommendation(
    matched: MatchedEvent,
    edge_percent: float,
    pm_prob: float,
    sb_prob: float,
) -> str:
    """Build a clear, actionable recommendation string."""
    pm = matched.prediction_market
    sb = matched.sportsbook

    if not pm or not sb:
        return "Insufficient data for recommendation."

    pm_platform = pm.platform.value.title()
    sb_platform = sb.platform.value.title()

    if edge_percent > 0:
        # Prediction market is underpriced → BUY
        direction = "BUY"
        action = f"BUY \"{pm.selection}\" on {pm_platform}"
        price_info = f"at {pm_prob*100:.1f}¢"
        compare = (
            f"{sb_platform} implies {sb_prob*100:.1f}% "
            f"(odds: {sb.american_odds:+d})"
        )
        edge_info = f"Edge: +{edge_percent:.1f}%"
    else:
        # Prediction market is overpriced → SELL / fade
        direction = "SELL"
        action = f"SELL / fade \"{pm.selection}\" on {pm_platform}"
        price_info = f"at {pm_prob*100:.1f}¢"
        compare = (
            f"{sb_platform} implies only {sb_prob*100:.1f}% "
            f"(odds: {sb.american_odds:+d})"
        )
        edge_info = f"Edge: {edge_percent:.1f}%"

    return f"{action} {price_info} — {compare}. {edge_info}"


class ArbitrageCalculator:
    """Finds arbitrage and edge opportunities from matched events."""

    def __init__(self, min_edge_percent: float = 1.0):
        self.min_edge_percent = min_edge_percent

    def find_opportunities(
        self,
        matched_events: list[MatchedEvent],
    ) -> list[ArbitrageOpportunity]:
        """
        Analyze matched events and return arbitrage opportunities
        sorted by edge size (biggest first).
        """
        opportunities: list[ArbitrageOpportunity] = []

        for matched in matched_events:
            pm = matched.prediction_market
            sb = matched.sportsbook

            if not pm or not sb:
                continue

            # Both sides must have valid probabilities
            if pm.probability <= 0 or sb.probability <= 0:
                continue

            edge = calculate_edge(pm.probability, sb.probability)

            # Only include if edge exceeds threshold
            if abs(edge) < self.min_edge_percent:
                continue

            ev = calculate_expected_value(pm.probability, sb.probability)
            category = categorize_edge(edge)
            recommendation = build_recommendation(
                matched, edge, pm.probability, sb.probability
            )

            opp = ArbitrageOpportunity(
                matched_event=matched,
                edge_percent=round(edge, 2),
                prediction_market_prob=pm.probability,
                sportsbook_implied_prob=sb.probability,
                recommendation=recommendation,
                expected_value=ev,
                category=category,
                timestamp=datetime.utcnow(),
            )
            opportunities.append(opp)

            logger.debug(
                f"Found {category} edge: {edge:+.1f}% on "
                f"'{matched.normalized_name}'"
            )

        # Sort by absolute edge, biggest first
        opportunities.sort(key=lambda o: abs(o.edge_percent), reverse=True)

        logger.info(
            f"Found {len(opportunities)} opportunities "
            f"(min edge: {self.min_edge_percent}%)"
        )
        return opportunities
