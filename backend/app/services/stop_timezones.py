STOP_ZONES = [
    ("America/New_York", "Eastern"),
    ("America/Chicago", "Central"),
    ("America/Denver", "Mountain"),
    ("America/Phoenix", "Arizona"),
    ("America/Los_Angeles", "Pacific"),
    ("America/Anchorage", "Alaska"),
    ("Pacific/Honolulu", "Hawaii"),
    ("America/Halifax", "Atlantic"),
    ("America/St_Johns", "Newfoundland"),
    ("America/Regina", "Saskatchewan"),
]

STATE_TIMEZONES: dict[str, str] = {
    **dict.fromkeys(
        "CT DE DC FL GA IN KY ME MD MA MI NH NJ NY NC OH PA RI SC VT VA WV ON QC".split(),
        "America/New_York",
    ),
    **dict.fromkeys(
        "AL AR IL IA KS LA MN MS MO NE ND OK SD TN TX WI MB".split(),
        "America/Chicago",
    ),
    **dict.fromkeys("CO ID MT NM UT WY AB".split(), "America/Denver"),
    "AZ": "America/Phoenix",
    **dict.fromkeys("CA NV OR WA BC".split(), "America/Los_Angeles"),
    "AK": "America/Anchorage",
    "HI": "Pacific/Honolulu",
    **dict.fromkeys("NB NS PE".split(), "America/Halifax"),
    "NL": "America/St_Johns",
    "SK": "America/Regina",
}

_STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
}
_STATE_NAME_TO_CODE = {name.casefold(): code for code, name in _STATE_NAMES.items()}
_STATE_NAME_TO_CODE.update(
    {
        "newfoundland": "NL",
        "québec": "QC",
    }
)


def timezone_for_state(state: str | None) -> str | None:
    if state is None:
        return None
    value = state.strip()
    if not value:
        return None
    code = value.upper()
    if code in STATE_TIMEZONES:
        return STATE_TIMEZONES[code]
    code = _STATE_NAME_TO_CODE.get(value.casefold())
    return STATE_TIMEZONES.get(code) if code else None


def resolve_stop_timezone(
    explicit: str | None, state: str | None, broker_tz: str
) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    return timezone_for_state(state) or broker_tz
