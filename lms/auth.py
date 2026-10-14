import functools
import hmac
import secrets
from urllib.parse import urlparse

from flask import abort, g, redirect, request, session, url_for

from . import supa

ADMIN_ROLES = ("admin", "super_admin")


def current_user():
    """The logged-in user row, re-read from the DB on every request so that
    deactivating an account takes effect immediately."""
    if "user" in g:
        return g.user
    g.user = None
    uid = session.get("uid")
    if uid:
        row = supa.one("users", id=uid)
        if row and row["is_active"]:
            g.user = row
        else:
            session.clear()
    return g.user


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    sent = request.form.get("_csrf", "")
    expected = session.get("csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Your session expired. Go back, refresh the page and try again.")


def safe_next(target):
    """Only allow same-site relative redirects."""
    if not target:
        return None
    parts = urlparse(target)
    if parts.scheme or parts.netloc or not target.startswith("/portal"):
        return None
    return target


def roles_required(*roles):
    def deco(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("lms.login", next=request.full_path.rstrip("?")))
            if user["role"] not in roles:
                return redirect(url_for("lms.home"))
            return view(*args, **kwargs)
        return wrapped
    return deco


login_required = roles_required("intern", "admin", "super_admin")
admin_required = roles_required(*ADMIN_ROLES)
super_required = roles_required("super_admin")
