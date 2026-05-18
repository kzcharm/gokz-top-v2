import ipaddress
import socket
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from app.core.regions import get_region_code_for_country, get_region_name
from app.models.misc import IPLookupRequest, IPLookupResponse
from app.services.geoip import lookup_geoip_details

router = APIRouter(prefix="/misc", tags=["misc"])


def _resolve_address_to_ip(address: str) -> str:
    normalized = address.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Unable to resolve address: ")

    try:
        return ipaddress.ip_address(normalized).compressed
    except ValueError:
        pass

    try:
        addrinfo = socket.getaddrinfo(
            normalized,
            None,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to resolve address: {address}",
        ) from exc

    for _, _, _, _, sockaddr in addrinfo:
        if not sockaddr:
            continue
        resolved_ip = sockaddr[0]
        try:
            return ipaddress.ip_address(resolved_ip).compressed
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail=f"Unable to resolve address: {address}",
    )


def _lookup_ip_geo(address: str) -> IPLookupResponse:
    ip = _resolve_address_to_ip(address)
    location = lookup_geoip_details(ip)
    country_code = location.country_code if location is not None else None
    region_code = get_region_code_for_country(country_code)
    region_name = get_region_name(region_code)
    return IPLookupResponse(
        ip=ip,
        country=location.country_name if location is not None else None,
        country_code=country_code,
        region=location.subdivision_name if location is not None else None,
        city=location.city_name if location is not None else None,
        region_name=region_name,
        region_code=region_code,
    )


@router.post("/ip", response_model=list[IPLookupResponse])
async def lookup_ip_list(body: IPLookupRequest) -> list[IPLookupResponse]:
    return [_lookup_ip_geo(address) for address in body.addresses]


@router.get("/ip/{address}", response_model=IPLookupResponse)
async def lookup_ip(
    address: Annotated[str, Path()],
) -> IPLookupResponse:
    return _lookup_ip_geo(address)
