"""Email notification system for high-value arbitrage alerts."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from ..config import settings
from ..models import ArbitrageOpportunity

logger = logging.getLogger(__name__)


def format_alert_html(opportunities: list[ArbitrageOpportunity]) -> str:
    """Format opportunities into a clean HTML email."""
    rows = ""
    for opp in opportunities:
        me = opp.matched_event
        color = (
            "#22c55e" if opp.category == "strong"
            else "#eab308" if opp.category == "moderate"
            else "#94a3b8"
        )
        rows += f"""
        <tr style="border-bottom: 1px solid #334155;">
            <td style="padding: 12px; color: #e2e8f0;">{me.sport.value.upper()}</td>
            <td style="padding: 12px; color: #e2e8f0;">{me.normalized_name}</td>
            <td style="padding: 12px; color: {color}; font-weight: bold;">{opp.edge_percent:+.1f}%</td>
            <td style="padding: 12px; color: #e2e8f0; font-size: 13px;">{opp.recommendation}</td>
        </tr>
        """

    return f"""
    <html>
    <body style="background: #0f172a; color: #e2e8f0; font-family: -apple-system, sans-serif; padding: 24px;">
        <h2 style="color: #38bdf8; margin-bottom: 4px;">Sports Arb Finder — Alert</h2>
        <p style="color: #94a3b8; margin-top: 0;">
            {len(opportunities)} high-value opportunities detected at {datetime.utcnow().strftime('%H:%M UTC')}
        </p>
        <table style="width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px;">
            <thead>
                <tr style="border-bottom: 2px solid #334155;">
                    <th style="padding: 12px; text-align: left; color: #94a3b8;">Sport</th>
                    <th style="padding: 12px; text-align: left; color: #94a3b8;">Event</th>
                    <th style="padding: 12px; text-align: left; color: #94a3b8;">Edge</th>
                    <th style="padding: 12px; text-align: left; color: #94a3b8;">Action</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        <p style="color: #64748b; font-size: 12px; margin-top: 16px;">
            This is an automated alert from Sports Arb Finder. Odds change rapidly — verify before acting.
        </p>
    </body>
    </html>
    """


async def send_alert_email(opportunities: list[ArbitrageOpportunity]) -> bool:
    """Send an email alert for high-value arbitrage opportunities."""
    if not settings.SMTP_USER or not settings.ALERT_EMAIL_TO:
        logger.warning("Email not configured — skipping alert")
        return False

    if not opportunities:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"🏈 Arb Alert: {len(opportunities)} opportunities "
            f"(best: {opportunities[0].edge_percent:+.1f}%)"
        )
        msg["From"] = settings.SMTP_USER
        msg["To"] = settings.ALERT_EMAIL_TO

        # Plain text fallback
        plain = "Sports Arb Finder Alert\n\n"
        for opp in opportunities:
            plain += (
                f"• {opp.matched_event.sport.value.upper()} | "
                f"{opp.matched_event.normalized_name} | "
                f"Edge: {opp.edge_percent:+.1f}% | "
                f"{opp.recommendation}\n"
            )

        html = format_alert_html(opportunities)

        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)

        logger.info(f"Alert email sent to {settings.ALERT_EMAIL_TO}")
        return True

    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
        return False
