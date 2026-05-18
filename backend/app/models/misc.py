from sqlmodel import SQLModel


class IPLookupResponse(SQLModel):
    ip: str
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    region_name: str | None = None
    region_code: str | None = None


class IPLookupRequest(SQLModel):
    addresses: list[str]
