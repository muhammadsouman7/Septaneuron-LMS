import os
from datetime import timedelta

from .utils import EMAIL_RE, MAX_ZIP_BYTES, attempt_key, hash_password, now_utc, parse_ts, password_error
from werkzeug.security import check_password_hash

from . import bp, supa
from .auth import ADMIN_ROLES, check_csrf, csrf_token, current_user, login_required, safe_next
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

EMAIL_MAX_FAILS = 5   # wrong passwords per email before the lock (change to 6 if you prefer)
IP_MAX_FAILS = 20     # wrong passwords per IP address, across any emails (stops email-guessing sprays)
LOCK_MINUTES = 15     # cool-down
# precomputed (same 600k iterations) so cold starts stay fast; keeps timing similar for unknown emails
_DUMMY_HASH = "pbkdf2:sha256:600000$GAC1TA7SM9xdVEKK$00c25e1325fb21276cf37efcda2e8f04cbf39718a7f3ab6f1d7a255b5449ce1b"


@bp.context_processor
def inject():
    return {"csrf_token": csrf_token, "me": current_user, "max_zip_mb": MAX_ZIP_BYTES // 1_000_000}


@bp.before_request
def guard():
    if os.environ.get("VERCEL") and current_app.secret_key == "change-this-development-secret":
        abort(503)  # refuse to run the portal with the public development secret
    if request.method == "POST":
        check_csrf()
    user = current_user()
    if (user and user["must_change_password"]
            and request.endpoint not in ("lms.change_password", "lms.logout", "lms.ping", "lms.session_expired")):
        return redirect(url_for("lms.change_password"))


@bp.after_request
def no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.errorhandler(supa.SupabaseError)
def supabase_down(err):
    current_app.logger.error("Supabase error: %s", err)
    return render_template("lms/error.html", title="Service unavailable",
                           message="The portal could not reach its database. Please try again in a minute."), 503


@bp.errorhandler(400)
@bp.errorhandler(404)
@bp.errorhandler(413)
@bp.errorhandler(503)
def portal_error(err):
    messages = {400: getattr(err, "description", "Bad request."),
                503: "The portal isn't configured yet (FLASK_SECRET_KEY is missing).",
                404: "We couldn't find that page.",
                413: "That upload is too large. The limit is 4 MB; share a link for bigger files."}
    return render_template("lms/error.html", title=f"Error {err.code}", message=messages[err.code]), err.code


@bp.route("/")
def home():
    user = current_user()
    if not user:
        return redirect(url_for("lms.login"))
    return redirect(url_for("lms.admin_overview" if user["role"] in ADMIN_ROLES else "lms.dashboard"))


def _fails(row, now):
    """Failures still counted: they expire after the cool-down window."""
    if not row:
        return 0
    seen = parse_ts(row.get("updated_at"))
    return row["fails"] if seen and seen > now - timedelta(minutes=LOCK_MINUTES) else 0


def _locked_minutes(rows, now):
    mins = 0
    for r in rows:
        until = parse_ts(r.get("locked_until"))
        if until and until > now:
            mins = max(mins, int((until - now).total_seconds() // 60) + 1)
    return mins


def _record_failure(email_key, ip_key, rows, now):
    """Count one failure against the email AND the IP. Returns attempts left for this email."""
    left = 0
    for key, limit in ((email_key, EMAIL_MAX_FAILS), (ip_key, IP_MAX_FAILS)):
        fails, locked = _fails(rows.get(key), now) + 1, None
        if fails >= limit:
            fails, locked = 0, (now + timedelta(minutes=LOCK_MINUTES)).isoformat()
        supa.upsert("login_attempts", {"key": key, "fails": fails, "locked_until": locked,
                                       "updated_at": now.isoformat()}, "key")
        if key == email_key:
            left = 0 if locked else limit - fails
    return left


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("lms.home"))
    if request.method == "GET":
        return render_template("lms/login.html", email="", next=request.args.get("next", ""))

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    nxt = safe_next(request.form.get("next"))
    now = now_utc()
    ekey, ikey = attempt_key("email", email), attempt_key("ip", request.remote_addr or "?")
    rows = {r["key"]: r for r in supa.select("login_attempts", filters=[("key", "in", [ekey, ikey])])}

    # Locked? Same message whether or not the email exists, so nothing leaks.
    wait = _locked_minutes(rows.values(), now)
    if wait:
        flash(f"Too many failed attempts. Please try again in {wait} minute{'s' if wait != 1 else ''}.", "error")
        return render_template("lms/login.html", email=email, next=nxt or ""), 429

    row = supa.one("users", email=email) if EMAIL_RE.match(email) else None
    ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password)
    if not (row and ok and row["is_active"]):
        left = _record_failure(ekey, ikey, rows, now)   # unknown emails are counted too
        if left:
            flash(f"Incorrect email or password. {left} attempt{'s' if left != 1 else ''} left "
                  f"before a {LOCK_MINUTES}-minute lock.", "error")
        else:
            flash(f"Too many failed attempts. Please try again in {LOCK_MINUTES} minutes.", "error")
        return render_template("lms/login.html", email=email, next=nxt or ""), 401

    supa.delete("login_attempts", filters=[("key", "eq", ekey)])
    supa.update("users", {"last_login_at": now.isoformat()}, filters={"id": row["id"]})
    session.clear()
    session.permanent = True
    session["uid"] = row["id"]
    csrf_token()
    if row["must_change_password"]:
        return redirect(url_for("lms.change_password"))
    return redirect(nxt or url_for("lms.home"))


@bp.route("/ping")
def ping():
    """Called by lms.js while the user is active; refreshes the 15-minute session."""
    if not current_user():
        return jsonify(ok=False), 401
    return jsonify(ok=True)


@bp.route("/session-expired")
def session_expired():
    """Used by lms.js when the 15 minutes run out: ends the session. ?go=1 then shows the login page."""
    session.clear()
    if request.args.get("go"):
        flash("Your session expired. Please sign in again.", "error")
        return redirect(url_for("lms.login"))
    return "", 204


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("lms.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    user = current_user()
    forced = bool(user["must_change_password"])
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("new", "")
        confirm = request.form.get("confirm", "")
        error = None
        if not check_password_hash(user["password_hash"], current):
            error = "Your current password is incorrect."
        elif new != confirm:
            error = "The new passwords don't match."
        else:
            error = password_error(new, current, user["email"])
        if error:  # stay on this screen
            flash(error, "error")
            return render_template("lms/change_password.html", forced=forced), 400
        supa.update("users", {"password_hash": hash_password(new), "must_change_password": False},
                    filters={"id": user["id"]})
        flash("Password updated successfully.", "success")
        # straight to the right dashboard (intern dashboard / admin overview)
        return redirect(url_for("lms.admin_overview" if user["role"] in ADMIN_ROLES else "lms.dashboard"))
    return render_template("lms/change_password.html", forced=forced)
