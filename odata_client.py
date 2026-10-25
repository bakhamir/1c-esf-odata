"""Read-only 1C:Fresh OData v3 client. No mutation methods are implemented."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


MAX_BYTES = 64 * 1024 * 1024
DEFAULT_APPLICATION_URL = "https://1cfresh.kz/a/ea38/116539/ru/"


class ODataError(Exception):
    pass


def service_url(application_url: str) -> str:
    parsed = urllib.parse.urlsplit(application_url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Application URL must be an HTTPS URL without embedded credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Application URL must not include query parameters or fragments")
    path = parsed.path.rstrip("/")
    if path.endswith("/ru") or path.endswith("/kk") or path.endswith("/en"):
        path = path.rsplit("/", 1)[0]
    if not path.startswith("/a/"):
        raise ValueError("Expected a 1C:Fresh application path beginning with /a/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path + "/odata/standard.odata/", "", ""))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ODataError(f"HTTP redirect {code} refused; credentials were not forwarded")


@dataclass
class ReadOnlyOData:
    application_url: str
    username: str
    password: str
    timeout: float = 20.0

    def __post_init__(self):
        if not self.username or not self.password:
            raise ValueError("Set both ONEC_ODATA_USERNAME and ONEC_ODATA_PASSWORD")
        self.base = service_url(self.application_url)
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, resource: str, params: dict[str, str | int] | None = None) -> bytes:
        # A resource is a single OData entity set or $metadata, never a full URL.
        if not resource or resource.startswith("/") or "/" in resource or "?" in resource or "#" in resource:
            raise ValueError("Resource must be a single OData path segment")
        # 1C uses Cyrillic in entity-set names such as Document_ЭСФ.
        if resource != "$metadata" and not resource.isidentifier():
            raise ValueError("Resource has invalid characters")
        encoded = urllib.parse.urlencode(params or {}, quote_via=urllib.parse.quote)
        url = self.base + urllib.parse.quote(resource, safe="$") + ("?" + encoded if encoded else "")
        token = base64.b64encode((self.username + ":" + self.password).encode("utf-8")).decode("ascii")
        request = urllib.request.Request(url, headers={
            "Authorization": "Basic " + token,
            "Accept": "application/json, application/xml;q=0.9, */*;q=0.1",
            "User-Agent": "one-c-esf-readonly/0.1",
        }, method="GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ODataError(f"Unexpected HTTP status {response.status}")
                data = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            guidance = "Check account credentials and published OData permissions" if e.code in (401, 403) else "Check the application path and service availability"
            raise ODataError(f"HTTP {e.code}. {guidance}.") from None
        except urllib.error.URLError as e:
            raise ODataError(f"Connection failed ({type(e.reason).__name__}); check network/TLS/hostname") from None
        if len(data) > MAX_BYTES:
            raise ODataError("Response exceeded the 64 MiB safety limit")
        return data


def entity_sets(xml_bytes: bytes) -> list[str]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ODataError("$metadata is not parseable XML") from e
    return sorted({element.attrib["Name"] for element in root.iter()
                   if element.tag.rsplit("}", 1)[-1] == "EntitySet" and "Name" in element.attrib})


def entity_schema(xml_bytes: bytes, set_name: str) -> dict:
    """Return the declared metadata fields for an EntitySet without reading records."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ODataError("$metadata is not parseable XML") from e
    type_name = None
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "EntitySet" and element.get("Name") == set_name:
            type_name = element.get("EntityType", "").rsplit(".", 1)[-1]
            break
    if not type_name:
        raise ODataError("EntitySet not declared in $metadata")
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "EntityType" and element.get("Name") == type_name:
            fields = []
            for child in element:
                kind = child.tag.rsplit("}", 1)[-1]
                if kind in ("Property", "NavigationProperty"):
                    fields.append({"name": child.get("Name"), "type": child.get("Type", "navigation" if kind == "NavigationProperty" else "unknown"), "kind": kind})
            return {"entity": set_name, "entity_type": type_name, "fields": fields}
    raise ODataError("EntityType not found in $metadata")


def parse_collection(payload: bytes) -> list[dict]:
    try:
        obj = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ODataError("OData response is not JSON") from e
    # 1C may return OData v3 verbose JSON or JSON Light.
    if isinstance(obj, dict):
        data = obj.get("d", obj)
        if isinstance(data, dict):
            data = data.get("results", data.get("value", data))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            return [data]
    raise ODataError("Unrecognized JSON collection format")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only discovery of 1C:Fresh OData metadata and one sample object")
    parser.add_argument("command", choices=["entities", "schema", "sample"])
    parser.add_argument("--app-url", default=os.getenv("ONEC_APP_URL", DEFAULT_APPLICATION_URL))
    parser.add_argument("--match", default="", help="Case-insensitive substring to filter entity names")
    parser.add_argument("--entity", help="Exact entity set name returned by the 'entities' command")
    parser.add_argument("--filter", dest="odata_filter", help="Explicit OData $filter expression for sample")
    parser.add_argument("--fields", help="Comma-separated selected field names for sample (requires --show-values)")
    parser.add_argument("--show-values", action="store_true", help="Show actual fields for one record (private data)")
    parser.add_argument("--output", help="Write UTF-8 JSON to this local path (avoids PowerShell encoding problems)")
    args = parser.parse_args(argv)
    if args.command in ("sample", "schema") and not args.entity:
        parser.error(f"{args.command} requires --entity (from 'entities')")
    if args.fields and (args.command != "sample" or not args.show_values):
        parser.error("--fields requires sample --show-values")
    try:
        client = ReadOnlyOData(args.app_url, os.getenv("ONEC_ODATA_USERNAME", ""), os.getenv("ONEC_ODATA_PASSWORD", ""))
        metadata = client.get("$metadata")
        available = entity_sets(metadata)
        if args.command == "entities":
            selected = [name for name in available if args.match.casefold() in name.casefold()]
            result = {"service": client.base, "entity_sets_total": len(available), "matches": selected}
        elif args.command == "schema":
            if args.entity not in available:
                raise ODataError("Entity set not present in $metadata; use 'entities' to identify the exact name")
            result = entity_schema(metadata, args.entity)
        else:
            if args.entity not in available:
                raise ODataError("Entity set not present in $metadata; use 'entities' to identify the exact name")
            params: dict[str, str | int] = {"$format": "json", "$top": 1}
            names = [part.strip() for part in args.fields.split(",")] if args.fields else []
            if names:
                valid = {field["name"] for field in entity_schema(metadata, args.entity)["fields"]}
                if any(not name or name not in valid for name in names):
                    raise ODataError("Unknown field in --fields; use schema to obtain exact field names")
                params["$select"] = ",".join(names)
            if args.odata_filter:
                params["$filter"] = args.odata_filter
            rows = parse_collection(client.get(args.entity, params))
            if not rows:
                result = {"entity": args.entity, "rows_returned": 0, "note": "No rows matched; no data was modified"}
            elif args.show_values:
                result = rows[0]
            else:
                result = {"entity": args.entity, "rows_returned": len(rows), "field_names": sorted(rows[0])}
        rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
            print(f"Saved UTF-8 JSON: {args.output}")
        else:
            print(rendered)
        return 0
    except (ODataError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
