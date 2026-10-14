"""Minimal Supabase client (PostgREST + Storage) built on `requests`.

Server-side only. It uses the project's *secret* key (sb_secret_...) or the legacy
service_role key. Those keys bypass Row Level Security, so they must never be
sent to the browser or committed to git.
"""
import os
import re
from urllib.parse import quote

import requests

TIMEOUT = 12


class SupabaseError(RuntimeError):
    """Supabase returned an error, or is not configured."""


def _url():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise SupabaseError("SUPABASE_URL is not set")
    return url


def _key():
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise SupabaseError("SUPABASE_SECRET_KEY is not set")
    return key


def _bucket():
    return os.environ.get("SUPABASE_BUCKET", "lms-files")


def _headers(extra=None):
    key = _key()
    headers = {"apikey": key}
    # New keys (sb_secret_...) are not JWTs: send them in `apikey` only.
    # Legacy service_role keys are JWTs and are also sent as a bearer token.
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    headers.update(extra or {})
    return headers


def _request(method, url, headers=None, **kwargs):
    try:
        resp = requests.request(method, url, headers=_headers(headers), timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise SupabaseError(f"Could not reach Supabase: {exc}") from exc
    if not resp.ok:
        raise SupabaseError(f"Supabase {resp.status_code}: {resp.text[:300]}")
    return resp


# ---------------------------------------------------------------- database
def _norm(filters):
    """filters: {"col": value} (equality) or [("col", "op", value), ...]."""
    if not filters:
        return []
    if isinstance(filters, dict):
        return [(col, "eq", val) for col, val in filters.items()]
    return list(filters)


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _in_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _params(filters):
    """Build PostgREST filters. Values are never trusted: id columns must be real UUIDs
    (anything else becomes the nil UUID, i.e. matches nothing) and `in` lists are quoted."""
    out = []
    for col, op, val in _norm(filters):
        is_id = col == "id" or col.endswith("_id")
        if op == "in":
            items = [str(v) if not is_id or _UUID_RE.match(str(v)) else _NIL_UUID for v in val]
            val = "(" + ",".join(_in_quote(v) for v in items) + ")"
        elif val is None and op == "eq":
            op, val = "is", "null"
        elif isinstance(val, bool):
            val = "true" if val else "false"
        elif is_id and not _UUID_RE.match(str(val)):
            val = _NIL_UUID
        out.append((col, f"{op}.{val}"))
    return out

def select(table, *, filters=None, columns="*", order=None, limit=None):
    params = [("select", columns)] + _params(filters)
    if order:
        params.append(("order", order))
    if limit:
        params.append(("limit", str(limit)))
    return _request("GET", f"{_url()}/rest/v1/{table}", params=params).json()


def one(table, **eq):
    rows = select(table, filters=eq, limit=1)
    return rows[0] if rows else None


def insert(table, row):
    resp = _request("POST", f"{_url()}/rest/v1/{table}", json=row,
                    headers={"Prefer": "return=representation"})
    return resp.json()[0]


def insert_many(table, rows):
    if not rows:
        return []
    resp = _request("POST", f"{_url()}/rest/v1/{table}", json=rows,
                    headers={"Prefer": "return=representation"})
    return resp.json()


def update(table, values, *, filters):
    if not _norm(filters):
        raise SupabaseError("Refusing to UPDATE without filters")
    resp = _request("PATCH", f"{_url()}/rest/v1/{table}", params=_params(filters), json=values,
                    headers={"Prefer": "return=representation"})
    return resp.json()


def delete(table, *, filters):
    if not _norm(filters):
        raise SupabaseError("Refusing to DELETE without filters")
    resp = _request("DELETE", f"{_url()}/rest/v1/{table}", params=_params(filters),
                    headers={"Prefer": "return=representation"})
    return resp.json()


# ----------------------------------------------------------------- storage
def _object_path(path):
    return "/".join(quote(part, safe="") for part in path.split("/"))


def upload(path, data, content_type="application/octet-stream"):
    _request("POST", f"{_url()}/storage/v1/object/{_bucket()}/{_object_path(path)}", data=data,
             headers={"Content-Type": content_type, "x-upsert": "true"})


def signed_url(path, download_as=None, expires=300):
    resp = _request("POST", f"{_url()}/storage/v1/object/sign/{_bucket()}/{_object_path(path)}",
                    json={"expiresIn": expires})
    signed = resp.json()["signedURL"]
    url = f"{_url()}/storage/v1{signed}" if signed.startswith("/") else signed
    if download_as:
        url += ("&" if "?" in url else "?") + "download=" + quote(download_as)
    return url


def remove_files(paths):
    paths = [p for p in paths if p]
    if paths:
        _request("DELETE", f"{_url()}/storage/v1/object/{_bucket()}", json={"prefixes": paths})
