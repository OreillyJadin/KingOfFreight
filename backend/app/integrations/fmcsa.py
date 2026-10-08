from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.schemas import CarrierSnapshot


class FmcsaProvider(Protocol):
    def lookup_mc(self, mc: str) -> CarrierSnapshot | None: ...


class MockFmcsaProvider:
    def lookup_mc(self, mc: str) -> CarrierSnapshot | None:
        fixtures = {
            "123456": CarrierSnapshot(
                mc_number=mc,
                dot_number="1234567",
                legal_name="Reliable Freight LLC",
                allowed_to_operate="Y",
                authority_status="A",
                safety_rating="S",
                insurance_on_file=True,
                bipd_on_file_amount=1_000_000,
                bipd_required_amount=750_000,
            ),
            "222222": CarrierSnapshot(
                mc_number=mc,
                dot_number="2222222",
                legal_name="Conditional Trucking",
                allowed_to_operate="Y",
                authority_status="A",
                safety_rating="C",
                insurance_on_file=True,
                bipd_on_file_amount=1_000_000,
                bipd_required_amount=750_000,
            ),
            "333333": CarrierSnapshot(
                mc_number=mc,
                dot_number="3333333",
                legal_name="Out of Service Carrier",
                allowed_to_operate="N",
                authority_status="I",
                safety_rating="U",
                insurance_on_file=True,
                bipd_on_file_amount=1_000_000,
                bipd_required_amount=750_000,
            ),
            "444444": CarrierSnapshot(
                mc_number=mc,
                dot_number="4444444",
                legal_name="Underinsured Freight",
                allowed_to_operate="Y",
                authority_status="A",
                safety_rating=None,
                insurance_on_file=True,
                bipd_on_file_amount=500_000,
                bipd_required_amount=750_000,
            ),
        }
        return fixtures.get(mc)


class LiveFmcsaProvider:
    """QCMobile field names are best-effort mappings and remain unverified against a live key."""

    base_url = "https://mobile.fmcsa.dot.gov/qc/services"

    def __init__(self) -> None:
        self.webkey = get_settings().fmcsa_webkey

    def _get(self, path: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/{path}", params={"webKey": self.webkey}, timeout=20
        )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("content", {})
        return content[0] if isinstance(content, list) and content else content

    def lookup_mc(self, mc: str) -> CarrierSnapshot | None:
        docket = self._get(f"carriers/docket-number/{mc}")
        if not docket:
            return None
        docket_carrier = docket.get("carrier", docket)
        dot = docket_carrier.get("dotNumber")
        if not dot:
            return None
        detail = self._get(f"carriers/{dot}")
        carrier = detail.get("carrier", detail)
        authority_result = self._get(f"carriers/{dot}/authority")
        authority = authority_result.get("authority", authority_result)
        common = authority.get("commonAuthorityStatus") or authority.get(
            "contractAuthorityStatus"
        )
        return CarrierSnapshot(
            mc_number=mc,
            dot_number=str(carrier.get("dotNumber", dot)),
            legal_name=carrier.get("legalName"),
            dba_name=carrier.get("dbaName"),
            phone=carrier.get("telephone"),
            allowed_to_operate=carrier.get("allowedToOperate"),
            authority_status=common,
            safety_rating=carrier.get("safetyRating"),
            insurance_on_file=bool(carrier.get("bipdInsuranceOnFile"))
            if carrier.get("bipdInsuranceOnFile")
            else None,
            bipd_on_file_amount=_amount(carrier.get("bipdInsuranceOnFile")),
            bipd_required_amount=_amount(
                carrier.get("bipdRequiredAmount")
                or carrier.get("bipdInsuranceRequired")
            ),
            out_of_service_date=carrier.get("oosDate"),
            raw={"docket": docket, "carrier": detail, "authority": authority_result},
        )


def _amount(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_fmcsa_provider() -> FmcsaProvider:
    return (
        LiveFmcsaProvider()
        if get_settings().fmcsa_provider == "live"
        else MockFmcsaProvider()
    )
