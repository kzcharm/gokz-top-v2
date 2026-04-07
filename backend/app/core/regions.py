from __future__ import annotations

from app.models.region import RegionCode, RegionPublic, normalize_region_code

_REGION_DEFINITIONS: tuple[tuple[RegionCode, str, tuple[str, ...]], ...] = (
    (RegionCode.AF, "Africa", (
        "ZA", "EG", "NG", "KE", "MA", "DZ", "TN", "ET", "GH", "CM", "CI", "UG",
        "AO", "MZ", "MG", "SD", "SN", "ZW", "ZM", "MW", "ML", "BF", "NE", "TD",
        "LY", "SO", "ER", "DJ", "BI", "TZ", "CD", "CG", "GA", "GQ", "ST", "CV",
        "GM", "GN", "GW", "SL", "LR", "BJ", "TG", "MR", "MU", "SC", "KM", "YT",
        "RE", "SH",
    )),
    (RegionCode.AS, "Asia", (
        "JP", "KR", "IN", "ID", "TH", "VN", "PH", "MY", "SG", "PK", "BD", "LK",
        "MM", "KH", "LA", "NP", "AF", "BN", "MV", "BT", "MN",
    )),
    (RegionCode.CIS, "CIS", (
        "RU", "UA", "BY", "KZ", "UZ", "AM", "AZ", "GE", "MD", "TJ", "TM", "KG",
    )),
    (RegionCode.CN, "China", (
        "CN", "HK", "TW", "MO",
    )),
    (RegionCode.EU, "Europe", (
        "FR", "DE", "GB", "IT", "ES", "NL", "BE", "AT", "CH", "SE", "NO", "DK",
        "FI", "PL", "CZ", "IE", "PT", "GR", "HU", "RO", "BG", "HR", "SK", "SI",
        "EE", "LV", "LT", "LU", "MT", "CY", "IS", "LI", "MC", "AD", "SM", "VA",
    )),
    (RegionCode.ME, "Middle East", (
        "SA", "AE", "IL", "TR", "IQ", "IR", "JO", "LB", "KW", "QA", "OM", "YE",
        "BH", "SY", "PS",
    )),
    (RegionCode.NA, "NA", (
        "US", "CA",
    )),
    (RegionCode.OC, "Oceania", (
        "AU", "NZ", "FJ", "PG", "NC", "PF", "GU", "AS", "CK", "NU", "PN", "WS",
        "TO", "VU", "SB", "KI", "FM", "MH", "PW", "TV", "NR",
    )),
    (RegionCode.SA, "SA", (
        "BR", "AR", "CL", "CO", "PE", "VE", "EC", "BO", "PY", "UY", "CR", "PA",
        "GT", "DO", "HN", "NI", "SV", "CU", "JM", "HT", "TT", "BB", "BS", "GY",
        "SR", "GF", "FK",
    )),
)

REGION_NAME_BY_CODE: dict[str, str] = {}
REGION_COUNTRY_CODES: dict[str, tuple[str, ...]] = {}
COUNTRY_REGION_CODE: dict[str, str] = {}

for region_code, region_name, country_codes in _REGION_DEFINITIONS:
    normalized_codes = tuple(dict.fromkeys(country_codes))
    REGION_NAME_BY_CODE[region_code.value] = region_name
    REGION_COUNTRY_CODES[region_code.value] = normalized_codes
    for country_code in normalized_codes:
        if country_code in COUNTRY_REGION_CODE:
            raise RuntimeError(
                f"Country {country_code} is assigned to multiple regions: "
                f"{COUNTRY_REGION_CODE[country_code]} and {region_code.value}"
            )
        COUNTRY_REGION_CODE[country_code] = region_code.value


def list_regions() -> list[RegionPublic]:
    return [
        RegionPublic(
            code=region_code,
            name=region_name,
            country_codes=list(country_codes),
        )
        for region_code, region_name, country_codes in _REGION_DEFINITIONS
    ]


def get_region_country_codes(region_code: str | None) -> tuple[str, ...] | None:
    normalized = normalize_region_code(region_code)
    if normalized is None:
        return None
    return REGION_COUNTRY_CODES.get(normalized)


def get_region_name(region_code: str | None) -> str | None:
    normalized = normalize_region_code(region_code)
    if normalized is None:
        return None
    return REGION_NAME_BY_CODE.get(normalized)


def get_region_code_for_country(country_code: str | None) -> str | None:
    if country_code is None:
        return None
    normalized = country_code.strip().upper()
    if not normalized:
        return None
    return COUNTRY_REGION_CODE.get(normalized)


def is_valid_region_code(region_code: str | None) -> bool:
    normalized = normalize_region_code(region_code)
    return normalized in REGION_COUNTRY_CODES if normalized is not None else False
