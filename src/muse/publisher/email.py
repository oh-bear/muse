from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
import structlog
from jinja2 import Template

logger = structlog.get_logger()

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


@dataclass
class EmailPublisher:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    recipients: list[str]

    async def send_weekly_digest(
        self,
        opportunities: list[dict[str, Any]],
        weekly_summary: str,
        signal_count: int,
        week_label: str,
    ) -> None:
        if not self.smtp_host:
            logger.info("email_skipped", reason="no smtp_host configured")
            return

        template_path = TEMPLATE_DIR / "weekly_digest.html"
        template = Template(template_path.read_text())

        html = template.render(
            opportunities=opportunities,
            weekly_summary=weekly_summary,
            signal_count=signal_count,
            week_label=week_label,
        )

        msg = EmailMessage()
        msg["Subject"] = f"Muse Weekly Insights — {week_label}"
        msg["From"] = self.smtp_user
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(f"Muse Weekly: {len(opportunities)} opportunities from {signal_count} signals.")
        msg.add_alternative(html, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=self.smtp_host,
            port=self.smtp_port,
            username=self.smtp_user,
            password=self.smtp_password,
            start_tls=True,
        )

        logger.info("email_weekly_sent", recipients=len(self.recipients), opportunities=len(opportunities))

    async def send_monthly_ideas(
        self,
        ideas: list[dict[str, Any]],
        monthly_summary: str,
        opportunity_count: int,
        month_label: str,
    ) -> None:
        if not self.smtp_host:
            logger.info("email_skipped", reason="no smtp_host configured")
            return

        template_path = TEMPLATE_DIR / "monthly_ideas.html"
        template = Template(template_path.read_text())

        html = template.render(
            ideas=ideas,
            monthly_summary=monthly_summary,
            opportunity_count=opportunity_count,
            month_label=month_label,
        )

        msg = EmailMessage()
        msg["Subject"] = f"Muse Monthly Ideas — {month_label}"
        msg["From"] = self.smtp_user
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(f"Muse Monthly: {len(ideas)} ideas from {opportunity_count} opportunities.")
        msg.add_alternative(html, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=self.smtp_host,
            port=self.smtp_port,
            username=self.smtp_user,
            password=self.smtp_password,
            start_tls=True,
        )

        logger.info("email_monthly_sent", recipients=len(self.recipients), ideas=len(ideas))
