import os
from datetime import timedelta

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from . import bp, supa
from .auth import ADMIN_ROLES, check_csrf, csrf_token, current_user, login_required, safe_next
from .utils import EMAIL_RE, hash_password, now_utc, parse_ts, password_error

MAX_FAILS = 5
LOCK_MINUTES = 15
_DUMMY_HASH = hash_password("not-a-real-password")  # keeps timing similar for unknown emails


@bp.context_processor
def inject():
    return {"csrf_token": csrf_token, "me": current_user}


@bp.before_request
def guard():
    if os.environ.get("VERCEL") and current_app.secret_key == "change-this-development-secret":
        abort(503)  # refuse to run the portal with the public development secret
    if request.method == "POST":
        check_csrf()
    user = current_user()
    if (user and user["must_change_password"]
            and request.endpoint not in ("lms.change_password", "lms.logout")):
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


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("lms.home"))
    if request.method == "GET":
        return render_template("lms/login.html", email="", next=request.args.get("next", ""))

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    nxt = safe_next(request.form.get("next"))
    row = supa.one("users", email=email) if EMAIL_RE.match(email) else None

    locked = parse_ts(row.get("locked_until")) if row else None
    if locked and locked > now_utc():
        flash("Too many failed attempts. Please wait a few minutes and try again.", "error")
        return render_template("lms/login.html", email=email, next=nxt or ""), 429

    ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password)
    if not (row and ok and row["is_active"]):
        if row:
            fails = row["failed_attempts"] + 1
            values = {"failed_attempts": fails}
            if fails >= MAX_FAILS:
                values = {"failed_attempts": 0,
                          "locked_until": (now_utc() + timedelta(minutes=LOCK_MINUTES)).isoformat()}
            supa.update("users", values, filters={"id": row["id"]})
        flash("Invalid email or password.", "error")
        return render_template("lms/login.html", email=email, next=nxt or ""), 401

    supa.update("users", {"failed_attempts": 0, "locked_until": None,
                          "last_login_at": now_utc().isoformat()}, filters={"id": row["id"]})
    session.clear()
    session.permanent = True
    session["uid"] = row["id"]
    csrf_token()
    if row["must_change_password"]:
        return redirect(url_for("lms.change_password"))
    return redirect(nxt or url_for("lms.home"))


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("lms.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    user = current_user()
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
        if error:
            flash(error, "error")
        else:
            supa.update("users", {"password_hash": hash_password(new), "must_change_password": False},
                        filters={"id": user["id"]})
            flash("Password updated.", "success")
            return redirect(url_for("lms.home"))
    return render_template("lms/change_password.html", forced=user["must_change_password"])
