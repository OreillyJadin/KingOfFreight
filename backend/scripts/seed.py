import argparse
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Carrier,
    Communication,
    Load,
    LocationPing,
    ScheduledCheckIn,
    StatusUpdate,
    utcnow,
)
from app.schemas import CarrierSnapshot
from app.services.fmcsa import score_carrier


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    now = utcnow()
    with SessionLocal() as db:
        if db.scalar(select(Load.id).limit(1)) and not args.force:
            raise SystemExit("Loads already exist; pass --force to add demo data.")
        carriers = []
        fixtures = [
            ("123456", "Reliable Freight LLC", "green"),
            ("222222", "Conditional Trucking", "yellow"),
            ("444444", "Underinsured Freight", "yellow"),
        ]
        for mc, name, _ in fixtures:
            carrier = db.scalar(select(Carrier).where(Carrier.mc_number == mc))
            if carrier is None:
                snapshot = CarrierSnapshot(
                    mc_number=mc,
                    legal_name=name,
                    allowed_to_operate="Y",
                    authority_status="A",
                    safety_rating="S"
                    if mc == "123456"
                    else ("C" if mc == "222222" else None),
                    insurance_on_file=True,
                    bipd_on_file_amount=1_000_000 if mc != "444444" else 500_000,
                    bipd_required_amount=750_000,
                )
                flag, reasons = score_carrier(snapshot, mc)
                carrier = Carrier(
                    mc_number=mc,
                    legal_name=name,
                    flag=flag,
                    flag_reasons=reasons,
                    allowed_to_operate="Y",
                    authority_status="A",
                    safety_rating=snapshot.safety_rating,
                    insurance_on_file=True,
                    bipd_on_file_amount=snapshot.bipd_on_file_amount,
                    bipd_required_amount=snapshot.bipd_required_amount,
                    raw={},
                    verified_at=now,
                )
                db.add(carrier)
            carriers.append(carrier)
        db.flush()
        demo = [
            ("BOL-4821", "new", 0),
            ("KS-MO-104", "posted", 1),
            ("IL-IA-228", "booked", 2),
            ("WI-IL-992", "picked_up", 0),
            ("MN-IA-778", "in_transit", 1),
            ("MO-NE-105", "delivered", 2),
        ]
        loads: list[Load] = []
        for index, (reference, state, carrier_index) in enumerate(demo):
            pickup = now + timedelta(hours=3 + index)
            delivery = now + timedelta(hours=9 + index)
            load = Load(
                reference=reference,
                status=state,
                pickup_city=[
                    "Chicago",
                    "Kansas City",
                    "Rockford",
                    "Milwaukee",
                    "Minneapolis",
                    "St. Louis",
                ][index],
                pickup_state=["IL", "MO", "IL", "WI", "MN", "MO"][index],
                pickup_location="Midwest distribution center",
                pickup_datetime=pickup,
                delivery_city=[
                    "Des Moines",
                    "Omaha",
                    "Cedar Rapids",
                    "Chicago",
                    "Des Moines",
                    "Omaha",
                ][index],
                delivery_state=["IA", "NE", "IA", "IL", "IA", "NE"][index],
                delivery_location="Midwest receiving dock",
                delivery_datetime=delivery,
                weight_lbs=Decimal(39000 - index * 500),
                equipment_type="dry_van",
                commodity="Packaged goods",
                customer_name="Prairie Supply Co.",
                customer_contact_name="Jordan",
                customer_email="customer@example.com",
                customer_phone="+13125550199",
                customer_rate=Decimal("2400.00"),
                carrier_rate=Decimal("1950.00"),
                carrier_id=carriers[carrier_index].id,
                driver_name="Casey Driver" if state not in {"new", "posted"} else None,
                driver_phone="+13125550111" if state not in {"new", "posted"} else None,
                driver_email="driver@example.com"
                if state not in {"new", "posted"}
                else None,
                booked_at=now if state not in {"new", "posted"} else None,
                delivered_at=now - timedelta(hours=1) if state == "delivered" else None,
            )
            db.add(load)
            loads.append(load)
        db.flush()
        bol = Communication(
            load_id=loads[0].id,
            channel="email",
            direction="inbound",
            from_addr="shipper@example.com",
            subject="BOL-4821 bill of lading",
            content="Demo BOL attachment received",
            tag="bol",
            extracted={
                "reference": "BOL-4821",
                "pickup_city": "Chicago",
                "delivery_city": "Des Moines",
                "weight_lbs": 39000,
                "confidence": 0.3,
                "notes": "mock extraction",
            },
        )
        db.add(bol)
        db.flush()
        loads[0].bol_source = bol.id
        for kind, appointment in (
            ("pickup", loads[2].pickup_datetime),
            ("dropoff", loads[2].delivery_datetime),
        ):
            db.add(
                ScheduledCheckIn(
                    load_id=loads[2].id,
                    kind=kind,
                    scheduled_time=appointment,
                    send_at=appointment + timedelta(minutes=60),
                    checkin_channel="sms",
                    driver_contact=loads[2].driver_phone,
                    state="scheduled",
                )
            )
        reply_checkin = ScheduledCheckIn(
            load_id=loads[3].id,
            kind="pickup",
            scheduled_time=loads[3].pickup_datetime,
            send_at=loads[3].pickup_datetime,
            checkin_sent_at=now - timedelta(minutes=15),
            checkin_channel="sms",
            driver_contact=loads[3].driver_phone,
            state="no_reply",
            alert_raised_at=now - timedelta(minutes=15),
        )
        db.add(reply_checkin)
        db.flush()
        db.add(
            StatusUpdate(
                load_id=loads[3].id,
                status="in_transit",
                source="checkin",
                note="Driver says loaded.",
                applied=False,
                state="pending_approval",
                checkin_id=reply_checkin.id,
                customer_channel="email",
                customer_message_subject="Load update",
                customer_message_preview="Demo pending customer update.",
            )
        )
        alert = ScheduledCheckIn(
            load_id=loads[4].id,
            kind="dropoff",
            scheduled_time=loads[4].delivery_datetime,
            send_at=now - timedelta(hours=1),
            checkin_sent_at=now - timedelta(minutes=45),
            checkin_channel="sms",
            driver_contact=loads[4].driver_phone,
            state="no_reply",
            alert_raised_at=now - timedelta(minutes=15),
        )
        db.add(alert)
        db.flush()
        db.add(
            LocationPing(
                load_id=loads[4].id,
                lat=41.5868,
                lng=-93.6250,
                accuracy_m=18,
                captured_at=now,
            )
        )
        db.add_all(
            [
                Communication(
                    channel="email",
                    direction="inbound",
                    from_addr="carrier@example.com",
                    subject="Available truck for KS-MO-104",
                    content="We can cover at 2200",
                    tag="availability",
                    load_id=loads[1].id,
                ),
                Communication(
                    channel="email",
                    direction="inbound",
                    from_addr="dispatch@example.com",
                    subject="Carrier info",
                    content="MC 123456",
                    tag="mc_provided",
                    load_id=loads[1].id,
                ),
                Communication(
                    channel="sms",
                    direction="inbound",
                    from_addr="+13125550999",
                    content="Is this still available?",
                    tag="other",
                ),
            ]
        )
        db.commit()
    print("Seeded 3 carriers, 6 loads, inbox messages, check-ins, and tracking data.")


if __name__ == "__main__":
    main()
