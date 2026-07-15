import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from typing import Any, Dict

from config import settings
from src.services.base import BaseService

_ASCII_ART_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "ascii-art.txt")


def _load_ascii_art() -> str:
    try:
        with open(_ASCII_ART_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def send_fire_alert(to_emails, house_label: str, device_id: str) -> None:
    recipients = [e for e in (to_emails or []) if e]
    if not recipients:
        return
    if not settings.SMTP_HOST:
        print(f"[NOTIFY] SMTP_HOST not configured — skipping fire alert for {device_id} "
              f"({len(recipients)} recipient(s) would have been notified)")
        return

    art = _load_ascii_art()
    subject = f"Fire Alarm Triggered! — {house_label}"

    plain_body = (
        f"The fire alarm for '{house_label}' (device {device_id}) has just been triggered.\n"
        f"Trauma Team and Fire Squad have been dispatched to the house location.\n"
        f"All fees will be charged to your account.\n"
        f"\n{art}\n"
    )

    html_body = (
        f"<p>The fire alarm for '{escape(house_label)}' (device {escape(device_id)}) "
        f"has just been triggered.<br>"
        f"Trauma Team and Fire Squad have been dispatched to the house location.<br>"
        f"All fees will be charged to your account.</p>"
        f"<pre style=\"font-family: 'Courier New', Courier, monospace; "
        f"line-height: 1.15; white-space: pre;\">{escape(art)}</pre>"
    )

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls(context=context)
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            for addr in recipients:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = settings.ALERT_FROM_EMAIL
                msg["To"] = addr
                msg.set_content(plain_body)
                msg.add_alternative(html_body, subtype="html")
                server.send_message(msg)
        print(f"[NOTIFY] Fire alert sent to {len(recipients)} recipient(s) for {device_id}")
    except Exception as exc:
        print(f"[NOTIFY] Failed to send fire alert for {device_id}: {exc}")


class FireNotificationService(BaseService):
    def execute(self, data: Dict, dr_type: str = None, attribute: str = None,
                action: str = None, **kwargs) -> Any:
        if action != "notify_fire":
            raise ValueError(f"Unknown action for FireNotificationService: {action}")
        emails = kwargs.get("emails") or []
        house_label = kwargs.get("house_label") or "your device"
        device_id = kwargs.get("device_id")
        send_fire_alert(emails, house_label, device_id)
        return {"notified": len(emails)}
