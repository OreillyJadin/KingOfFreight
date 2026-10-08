from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import BrokerSettings


@dataclass(frozen=True)
class BrokerPrefs:
    broker_name: str
    broker_company: str
    broker_timezone: str
    checkin_offset_minutes: int
    no_reply_alert_minutes: int
    checkin_default_channel: str


def default_prefs() -> BrokerPrefs:
    settings = get_settings()
    return BrokerPrefs(
        broker_name=settings.broker_name,
        broker_company=settings.broker_company,
        broker_timezone=settings.broker_timezone,
        checkin_offset_minutes=settings.checkin_offset_minutes,
        no_reply_alert_minutes=settings.no_reply_alert_minutes,
        checkin_default_channel=settings.checkin_default_channel,
    )


def get_prefs(db: Session) -> BrokerPrefs:
    defaults = default_prefs()
    row = db.get(BrokerSettings, 1)
    if row is None:
        return defaults
    return BrokerPrefs(
        broker_name=row.broker_name or defaults.broker_name,
        broker_company=row.broker_company or defaults.broker_company,
        broker_timezone=row.broker_timezone or defaults.broker_timezone,
        checkin_offset_minutes=(
            row.checkin_offset_minutes
            if row.checkin_offset_minutes is not None
            else defaults.checkin_offset_minutes
        ),
        no_reply_alert_minutes=(
            row.no_reply_alert_minutes
            if row.no_reply_alert_minutes is not None
            else defaults.no_reply_alert_minutes
        ),
        checkin_default_channel=(
            row.checkin_default_channel or defaults.checkin_default_channel
        ),
    )
