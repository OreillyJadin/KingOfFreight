from sqlalchemy.orm import Session

from app.integrations.email import EmailProvider
from app.integrations.sms import SmsProvider
from app.models import Communication, Load, utcnow


def send_outbound(
    db: Session,
    load: Load,
    channel: str,
    to: str,
    subject: str | None,
    body: str,
    tag: str,
    sms: SmsProvider,
    email: EmailProvider,
) -> Communication:
    external_id = (
        sms.send(to, body) if channel == "sms" else email.send(to, subject or "", body)
    )
    communication = Communication(
        load_id=load.id,
        carrier_id=load.carrier_id,
        channel=channel,
        direction="outbound",
        from_addr=None,
        to_addr=to,
        subject=subject,
        content=body,
        tag=tag,
        external_id=external_id,
        created_at=utcnow(),
    )
    db.add(communication)
    return communication
