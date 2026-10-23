"""Add browser replay access without replacing unrelated R2 CORS rules."""

import argparse
import asyncio
import base64
import hashlib
import logging
import os
from xml.etree import ElementTree as ET

import httpx

from app.services import r2_storage


async def configure(origins: list[str]) -> None:
    config = r2_storage.get_r2_storage_config()
    if config is None:
        raise RuntimeError("R2 credentials and public URL are required")
    if not origins or any(
        not origin.startswith(("https://", "http://localhost:")) for origin in origins
    ):
        raise ValueError("Supply explicit HTTPS viewer origins")
    host = f"{config.account_id}.r2.cloudflarestorage.com"
    path = f"/{config.bucket_name}"
    url = f"https://{host}{path}?cors="
    headers = r2_storage._build_signed_headers(
        config=config,
        method="GET",
        canonical_uri=path,
        headers={"host": host},
        payload_hash=hashlib.sha256(b"").hexdigest(),
        canonical_query_string="cors=",
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        namespace = "http://s3.amazonaws.com/doc/2006-03-01/"
        if response.status_code == 404:
            root = ET.Element(f"{{{namespace}}}CORSConfiguration")
        else:
            response.raise_for_status()
            root = ET.fromstring(response.content)
        tag_prefix = root.tag.removesuffix("CORSConfiguration")
        for rule in root.findall(f"{tag_prefix}CORSRule"):
            allowed_origins = {
                node.text for node in rule.findall(f"{tag_prefix}AllowedOrigin")
            }
            methods = {node.text for node in rule.findall(f"{tag_prefix}AllowedMethod")}
            if ("*" in allowed_origins or set(origins) <= allowed_origins) and {
                "GET",
                "HEAD",
            } <= methods:
                logging.warning("Existing CORS rules already allow replay viewers")
                return
        rule = ET.SubElement(root, f"{tag_prefix}CORSRule")
        for origin in origins:
            ET.SubElement(rule, f"{tag_prefix}AllowedOrigin").text = origin
        for method in ("GET", "HEAD"):
            ET.SubElement(rule, f"{tag_prefix}AllowedMethod").text = method
        for header in ("Content-Length", "Content-Type", "ETag"):
            ET.SubElement(rule, f"{tag_prefix}ExposeHeader").text = header
        ET.SubElement(rule, f"{tag_prefix}MaxAgeSeconds").text = "3600"
        body = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        headers = r2_storage._build_signed_headers(
            config=config,
            method="PUT",
            canonical_uri=path,
            headers={
                "host": host,
                "content-type": "application/xml",
                "content-md5": base64.b64encode(
                    hashlib.md5(body, usedforsecurity=False).digest()
                ).decode(),
            },
            payload_hash=hashlib.sha256(body).hexdigest(),
            canonical_query_string="cors=",
        )
        response = await client.put(url, content=body, headers=headers)
        response.raise_for_status()
        logging.warning("Added replay viewer CORS rule for %s", ", ".join(origins))


async def configure_with_api_token(origins: list[str], token_env: str) -> None:
    config = r2_storage.get_r2_storage_config()
    token = os.environ.get(token_env)
    if config is None or not token:
        raise RuntimeError("R2 configuration and the named API token are required")
    url = f"https://api.cloudflare.com/client/v4/accounts/{config.account_id}/r2/buckets/{config.bucket_name}/cors"
    async with httpx.AsyncClient(
        timeout=30, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        response = await client.get(url)
        if response.status_code == 404 and any(
            error.get("code") == 10059 for error in response.json().get("errors", [])
        ):
            rules = []
        else:
            response.raise_for_status()
            rules = response.json().get("result", {}).get("rules", [])
        for rule in rules:
            allowed = rule.get("allowed", {})
            if (
                "*" in allowed.get("origins", [])
                or set(origins) <= set(allowed.get("origins", []))
            ) and {"GET", "HEAD"} <= set(allowed.get("methods", [])):
                logging.warning("Existing CORS rules already allow replay viewers")
                return
        rules.append(
            {
                "id": "gokz-top-record-replays",
                "allowed": {"methods": ["GET", "HEAD"], "origins": origins},
                "exposeHeaders": ["Content-Length", "Content-Type", "ETag"],
                "maxAgeSeconds": 3600,
            }
        )
        response = await client.put(url, json={"rules": rules})
        response.raise_for_status()
        if not response.json().get("success"):
            raise RuntimeError("Cloudflare did not acknowledge the CORS update")
        logging.warning(
            "Added replay viewer CORS access to configured bucket %s",
            config.bucket_name,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", action="append", required=True)
    parser.add_argument(
        "--api-token-env",
        help="Environment variable containing a Cloudflare bucket-administration token",
    )
    args = parser.parse_args()
    asyncio.run(
        configure_with_api_token(args.origin, args.api_token_env)
        if args.api_token_env
        else configure(args.origin)
    )


if __name__ == "__main__":
    main()
