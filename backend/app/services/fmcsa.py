from app.schemas import CarrierSnapshot


def score_carrier(
    snapshot: CarrierSnapshot | None, mc: str | None = None
) -> tuple[str, list[str]]:
    if snapshot is None:
        return "red", [f"No FMCSA record for MC {mc or 'unknown'}"]

    red: list[str] = []
    yellow: list[str] = []
    if snapshot.allowed_to_operate != "Y":
        red.append("Not authorized to operate")
    if snapshot.out_of_service_date:
        red.append(f"Out-of-service order on {snapshot.out_of_service_date}")
    if snapshot.safety_rating == "U":
        red.append("Unsatisfactory safety rating")
    if (
        snapshot.authority_status is not None
        and snapshot.authority_status.upper() not in {"A", "ACTIVE"}
    ):
        red.append("Operating authority not active")
    if red:
        return "red", red

    if snapshot.safety_rating == "C":
        yellow.append("Conditional safety rating")
    if not snapshot.bipd_on_file_amount:
        yellow.append("No liability insurance on file")
    elif (
        snapshot.bipd_required_amount is not None
        and snapshot.bipd_on_file_amount < snapshot.bipd_required_amount
    ):
        yellow.append("Liability insurance below required amount")
    if yellow:
        return "yellow", yellow
    if snapshot.safety_rating is None:
        return "green", ["Not rated (common for smaller carriers)"]
    return "green", []
