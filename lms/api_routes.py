"""Server-to-server API used by n8n (not the browser)."""
import hmac
import os
import re
import secrets

from flask import Blueprint, jsonify, request

from . import mailer, supa
from .admin_routes import _create_interns
from .utils import EMAIL_RE

# Separate blueprint on purpose: the /portal blueprint forces CSRF on every POST.
api_bp = Blueprint("lms_api", __name__, url_prefix="/api/v1")


def _norm(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _find_domain(value):
    """Match the form's 'Domain' answer to a row in `domains` (by name or slug)."""
    key = _norm(value)
    if not key:
        return None
    for d in supa.select("domains"):
        if key in (d["slug"], _norm(d["name"])):
            return d
    return None


@api_bp.route("/users/create", methods=["POST"])
def create_intern():
    expected = os.environ.get("N8N_API_KEY", "")
    if not expected:
        return jsonify(status="error", message="N8N_API_KEY is not configured"), 503
    if not hmac.compare_digest(request.headers.get("X-API-Key", ""), expected):
        return jsonify(status="error", message="Unauthorized"), 401

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:100]
    email = (data.get("email") or "").strip().lower()
    if not name or not EMAIL_RE.match(email):
        return jsonify(status="error", message="Valid name and email are required"), 400

    domain = _find_domain(data.get("domain"))
    if not domain:
        names = [d["name"] for d in supa.select("domains")]
        return jsonify(status="error",
                       message=f"Unknown domain '{data.get('domain')}'. Use one of: {names}"), 400

    temp_password = secrets.token_urlsafe(9) + "aA1!"   # unique per intern
    made, added, skipped, invalid = _create_interns([(name, email)], domain["id"], temp_password)

    if invalid:
        return jsonify(status="error", message="Email not allowed"), 400
    if skipped:
        return jsonify(status="exists", message="User is already in this domain")

    base = os.environ.get("PORTAL_BASE_URL", "").rstrip("/") or request.host_url.rstrip("/")
    login_url = f"{base}/portal/login"
    email_sent = True
    try:
        mailer.send_welcome_email(name, email, domain["name"], login_url,
                                  temp_password if made else None)
    except mailer.MailError:
        email_sent = False   # account exists; admin can reset password from the portal

    return jsonify(status="success" if made else "added_to_domain", email_sent=email_sent)