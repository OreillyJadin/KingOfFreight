import os
from collections.abc import Generator

os.environ["BROKER_PASSWORD"] = "test-password"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ENV"] = "development"
os.environ["UPLOAD_DIR"] = "/tmp/kingoffreight-test-uploads"
os.environ["SMS_PROVIDER"] = "mock"
os.environ["EMAIL_PROVIDER"] = "mock"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["FMCSA_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.integrations.email import get_email_provider
from app.integrations.fmcsa import get_fmcsa_provider
from app.integrations.llm import get_llm_provider
from app.integrations.sms import get_sms_provider
from app.main import app
from app.schemas import ReplyParse


class RecordingSms:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, body: str) -> str:
        self.sent.append((to, body))
        return f"sms-{len(self.sent)}"


class RecordingEmail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> str:
        self.sent.append((to, subject, body))
        return f"email-{len(self.sent)}"

    def fetch_new_messages(self) -> list[dict]:
        return []


class FakeLlm:
    def __init__(self, status: str = "picked_up") -> None:
        self.status = status

    def extract_bol(self, pdf_bytes: bytes, filename: str):
        from app.schemas import BolExtraction

        return BolExtraction(
            reference="TEST-BOL",
            pickup_city="Chicago",
            pickup_state="IL",
            delivery_city="Des Moines",
            delivery_state="IA",
            weight_lbs=32000,
            confidence=0.9,
            notes="mock extraction",
        )

    def parse_reply(self, reply_text: str, context: dict) -> ReplyParse:
        if self.status == "unclear":
            return ReplyParse(
                status="unclear",
                summary="Unclear reply.",
                needs_broker_attention=True,
                confidence=0.9,
            )
        return ReplyParse(
            status=self.status, summary="Driver says loaded.", confidence=0.91
        )


class FakeFmcsa:
    def lookup_mc(self, mc: str):
        from app.schemas import CarrierSnapshot

        return CarrierSnapshot(
            mc_number=mc,
            legal_name="Test Carrier",
            allowed_to_operate="Y",
            authority_status="A",
            safety_rating="S",
            insurance_on_file=True,
            bipd_on_file_amount=1_000_000,
            bipd_required_amount=750_000,
        )


@pytest.fixture()
def db() -> Generator:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def providers():
    return {
        "sms": RecordingSms(),
        "email": RecordingEmail(),
        "llm": FakeLlm(),
        "fmcsa": FakeFmcsa(),
    }


@pytest.fixture()
def client(db, providers):
    from app.db import get_db

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_sms_provider] = lambda: providers["sms"]
    app.dependency_overrides[get_email_provider] = lambda: providers["email"]
    app.dependency_overrides[get_llm_provider] = lambda: providers["llm"]
    app.dependency_overrides[get_fmcsa_provider] = lambda: providers["fmcsa"]
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/auth/login", json={"password": "test-password"}
        )
        assert response.status_code == 200
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def load_data(db):
    from datetime import timedelta

    from app.models import Carrier, Load, utcnow

    carrier = Carrier(
        mc_number="123456",
        legal_name="Reliable Freight LLC",
        flag="green",
        flag_reasons=[],
        allowed_to_operate="Y",
        authority_status="A",
        verified_at=utcnow(),
    )
    db.add(carrier)
    db.flush()
    load = Load(
        reference="TEST-100",
        status="posted",
        pickup_city="Chicago",
        pickup_state="IL",
        delivery_city="Des Moines",
        delivery_state="IA",
        pickup_datetime=utcnow() + timedelta(hours=2),
        delivery_datetime=utcnow() + timedelta(hours=8),
        customer_contact_name="Alex",
        customer_email="customer@example.com",
        customer_phone="+13125550199",
        carrier_id=carrier.id,
    )
    db.add(load)
    db.commit()
    return load, carrier
