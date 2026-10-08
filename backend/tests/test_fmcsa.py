from app.schemas import CarrierSnapshot
from app.services.fmcsa import score_carrier


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
