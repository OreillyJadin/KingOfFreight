from app.integrations.fmcsa import LiveFmcsaProvider
from app.schemas import CarrierSnapshot
from app.services.fmcsa import score_carrier


def _live_snapshot(monkeypatch, authority_status):
    payloads = {
        "carriers/docket-number/135797": {
            "carrier": {"dotNumber": 80806, "legalName": "J B HUNT TRANSPORT INC"}
        },
        "carriers/80806": {
            "carrier": {
                "dotNumber": 80806,
                "legalName": "J B HUNT TRANSPORT INC",
                "dbaName": "J B HUNT",
                "allowedToOperate": "Y",
                "safetyRating": "S",
                "bipdInsuranceOnFile": "3500",
                "bipdInsuranceRequired": "Y",
                "bipdRequiredAmount": "1000",
                "oosDate": None,
            }
        },
        "carriers/80806/authority": {
            "carrierAuthority": {
                "commonAuthorityStatus": authority_status,
                "contractAuthorityStatus": "A",
                "brokerAuthorityStatus": "A",
                "docketNumber": 135797,
                "dotNumber": 80806,
                "prefix": "MC",
            },
            "_links": {},
        },
    }
    provider = LiveFmcsaProvider()
    monkeypatch.setattr(provider, "_get", lambda path: payloads[path])
    return provider.lookup_mc("135797")


def base(**updates):
    values = dict(
        mc_number="123456",
        allowed_to_operate="Y",
        authority_status="A",
        safety_rating="S",
        bipd_on_file_amount=1_000_000,
        bipd_required_amount=750_000,
    )
    values.update(updates)
    return CarrierSnapshot(**values)


def test_red_rules_and_collects_all_reasons():
    assert score_carrier(None, "456789") == ("red", ["No FMCSA record for MC 456789"])
    flag, reasons = score_carrier(
        base(
            allowed_to_operate="N",
            out_of_service_date="2025-01-02",
            safety_rating="U",
            authority_status="I",
        )
    )
    assert flag == "red"
    assert reasons == [
        "Not authorized to operate",
        "Out-of-service order on 2025-01-02",
        "Unsatisfactory safety rating",
        "Operating authority not active",
    ]


def test_yellow_rules_and_green_unrated():
    flag, reasons = score_carrier(base(safety_rating="C", bipd_on_file_amount=0))
    assert flag == "yellow"
    assert reasons == ["Conditional safety rating", "No liability insurance on file"]
    assert score_carrier(base(bipd_on_file_amount=500_000)) == (
        "yellow",
        ["Liability insurance below required amount"],
    )
    assert score_carrier(base(safety_rating=None)) == (
        "green",
        ["Not rated (common for smaller carriers)"],
    )
    assert score_carrier(base()) == ("green", [])


def test_live_provider_parses_qcmobile_authority_payload(monkeypatch):
    snapshot = _live_snapshot(monkeypatch, "A")

    assert snapshot is not None
    assert snapshot.authority_status == "A"
    assert snapshot.legal_name == "J B HUNT TRANSPORT INC"
    assert snapshot.dot_number == "80806"
    assert snapshot.allowed_to_operate == "Y"


def test_inactive_live_authority_is_scored_red(monkeypatch):
    snapshot = _live_snapshot(monkeypatch, "I")

    assert snapshot is not None
    flag, reasons = score_carrier(snapshot)
    assert flag == "red"
    assert "Operating authority not active" in reasons
