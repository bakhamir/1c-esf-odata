"""Opt-in one-field PATCH transport. NEVER retries mutations automatically."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from odata_client import NoRedirect, ODataError, ReadOnlyOData


def patch_contract(client: ReadOnlyOData, esf_key: str, contract_key: str) -> int:
    """Send exactly one PATCH for only ДоговорПоставки_Key. Caller owns safeguards."""
    entity = urllib.parse.quote("Document_ЭСФ", safe="")
    suffix = f"(guid'{esf_key}')?$format=json"
    url = client.base + entity + suffix
    token = base64.b64encode((client.username + ":" + client.password).encode("utf-8")).decode("ascii")
    payload = json.dumps({"ДоговорПоставки_Key": contract_key}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="PATCH", headers={
        "Authorization": "Basic " + token,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": "one-c-esf-single-field-executor/0.1",
    })
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=30) as response:
            if response.status not in (200, 204):
                raise ODataError(f"Unexpected PATCH status {response.status}; verify by GET before any retry")
            return response.status
    except urllib.error.HTTPError as e:
        raise ODataError(f"PATCH HTTP {e.code}; state unknown until verified by GET") from None
    except urllib.error.URLError as e:
        raise ODataError("PATCH transport error; state unknown, DO NOT retry blindly") from e
