import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import abort, flash, redirect, render_template, request, url_for
from . import bp, mailer, supa
from .auth import admin_domain_ids, admin_required, current_user, super_required
from .utils import (EMAIL_RE, attempt_key, check_upload, default_password, fmt_dt, fmt_input, hash_password,
                    hash_temp_password, local_input_to_utc, now_utc, storage_key, temp_password)


# ------------------------------------------------------------------ helpers
_NIL = "00000000-0000-0000-0000-000000000000"  # matches nothing (admin with no domain assigned)


def _domains_for(user):
    ids = admin_domain_ids(user)
    if ids is None:
        return supa.select("domains", order="name.asc")
    return supa.select("domains", filters=[("id", "in", ids)], order="name.asc") if ids else []


def visible_domains():
    return _domains_for(current_user())


def interns_in(domain_id, columns="id,is_active", order=None, active_only=False):
    """Interns of one domain (or of every domain when domain_id is None). Each row carries
    `intern_domains`: the domain(s) it belongs to. One query, however many interns there are."""
    filters = [("role", "eq", "intern")]
    if active_only:
        filters.append(("is_active", "eq", True))
    if domain_id:
        filters.append(("intern_domains.domain_id", "eq", domain_id))
        return supa.select("users", columns=f"{columns},intern_domains!inner(domain_id)", filters=filters, order=order)
    return supa.select("users", columns=f"{columns},intern_domains(domain_id)", filters=filters, order=order)


def scope_domain(source):
    """Domain the page is scoped to. A domain admin is always locked to ONE of their own domains
    (the one picked with ?domain=, else their first); a super admin may pick any or see all (None)."""
    ids = admin_domain_ids(current_user())
    wanted = source.get("domain") or source.get("domain_id") or None
    if ids is None:
        return wanted
    if wanted in ids:
        return wanted
    return ids[0] if ids else _NIL


def require_domain(domain_id):
    ids = admin_domain_ids(current_user())
    if ids is not None and domain_id not in ids:
        abort(404)


def _flt(domain_id, **extra):
    f = dict(extra)
    if domain_id:
        f["domain_id"] = domain_id
    return f


def _get_task(task_id):
    task = supa.one("tasks", id=task_id)
    if not task:
        abort(404)
    require_domain(task["domain_id"])
    return task


def _friendly(err):
    text = str(err)
    return "That already exists." if ("23505" in text or "409" in text) else "Database error. Please try again."


# ----------------------------------------------------------------- overview
@bp.route("/admin")
@admin_required
def admin_overview():
    user = current_user()
    domain_id = scope_domain(request.args)
    domains, interns, tasks, pending = supa.parallel(
        lambda: _domains_for(user),
        lambda: interns_in(domain_id, "id,is_active"),
        lambda: supa.select("tasks", filters=_flt(domain_id), columns="id,domain_id"),
        lambda: supa.select("submissions", filters=_flt(domain_id, status="submitted"), order="submitted_at.asc"))
    shown = pending[:10]
    names, titles = ({}, {})
    if shown:
        found_users, found_tasks = supa.parallel(
            lambda: supa.select("users", filters=[("id", "in", [s["intern_id"] for s in shown])], columns="id,full_name,email"),
            lambda: supa.select("tasks", filters=[("id", "in", [s["task_id"] for s in shown])], columns="id,title"))
        names = {u["id"]: u for u in found_users}
        titles = {t["id"]: t for t in found_tasks}
    breakdown = [{
        "domain": d,
        "interns": sum(1 for i in interns if i["is_active"] and any(l["domain_id"] == d["id"] for l in i["intern_domains"])),
        "tasks": sum(t["domain_id"] == d["id"] for t in tasks),
        "pending": sum(s["domain_id"] == d["id"] for s in pending),
    } for d in domains if not domain_id or d["id"] == domain_id]
    return render_template("lms/admin/overview.html", domains=domains, domain_id=domain_id, shown=shown,
                           names=names, titles=titles, breakdown=breakdown,
                           stats={"interns": sum(bool(i["is_active"]) for i in interns), "tasks": len(tasks),
                                  "pending": len(pending)})


# -------------------------------------------------------------------- tasks
@bp.route("/admin/tasks")
@admin_required
def admin_tasks():
    user = current_user()
    domain_id = scope_domain(request.args)
    domains, tasks, subs, interns = supa.parallel(
        lambda: _domains_for(user),
        lambda: supa.select("tasks", filters=_flt(domain_id), order="created_at.desc"),
        lambda: supa.select("submissions", filters=_flt(domain_id), columns="task_id,status"),
        lambda: interns_in(domain_id, "id", active_only=True))
    dnames = {d["id"]: d["name"] for d in domains}
    rows = []
    for t in tasks:
        mine = [s for s in subs if s["task_id"] == t["id"]]
        rows.append({"task": t, "domain": dnames.get(t["domain_id"], "—"),
                     "submitted": len(mine), "review": sum(s["status"] == "submitted" for s in mine),
                     "interns": sum(1 for i in interns if any(l["domain_id"] == t["domain_id"] for l in i["intern_domains"]))})
    return render_template("lms/admin/tasks.html", rows=rows, domains=domains, domain_id=domain_id)


def _task_values(form):
    title = form.get("title", "").strip()
    if not title or len(title) > 150:
        return None, "Give the task a title (up to 150 characters)."
    if not form.get("description", "").strip():
        return None, "Add the task instructions."
    due_raw = form.get("due_at", "").strip()
    due = local_input_to_utc(due_raw)
    if due_raw and not due:
        return None, "That deadline isn't a valid date and time."
    try:
        points = int(form.get("max_points") or 100)
    except ValueError:
        points = 0
    if not 1 <= points <= 1000:
        return None, "Max points must be between 1 and 1000."
    stype = form.get("submission_type", "code")
    if stype not in ("code", "creative"):
        return None, "Choose a valid submission type."
    return {"title": title, "description": form.get("description", "").strip()[:8000],
            "due_at": due, "max_points": points, "submission_type": stype}, None


def _notify(task, domain, updated=False):
    """Email the domain's active interns and record the outcome on the task."""
    emails = [u["email"] for u in interns_in(domain["id"], "email", active_only=True)]
    base = os.environ.get("PORTAL_BASE_URL", "").rstrip("/") or request.host_url.rstrip("/")
    link = base + url_for("lms.task_view", task_id=task["id"])
    info = {"title": task["title"], "description": task.get("description"),
            "due_text": fmt_dt(task.get("due_at")) if task.get("due_at") else "No deadline"}
    sent, error, failed = 0, None, []
    if not emails:
        error = "There are no active interns in this domain yet."
    else:
        try:
            sent = mailer.send_task_email(info, domain["name"], emails, link, updated=updated, failed=failed)
        except mailer.MailError as exc:
            error = str(exc)
    note = f"Not delivered to {len(failed)}: {'; '.join(failed[:3])}{'…' if len(failed) > 3 else ''}." if failed else None
    supa.update("tasks", {"emailed_count": sent, "emailed_at": now_utc().isoformat() if sent else None,
                          "email_error": error or note}, filters={"id": task["id"]})
    who = ", ".join(emails[:6]) + (f" and {len(emails) - 6} more" if len(emails) > 6 else "")
    if error:
        flash(f"Task saved, but the email was not sent: {error}", "warn")
    elif note:
        flash(f"Email sent to {sent} of {len(emails)} {domain['name']} interns. {note}", "warn")
    else:
        flash(f"Email sent to {sent} {domain['name']} intern{'s' if sent != 1 else ''}: {who}.", "success")


@bp.route("/admin/tasks/new", methods=["GET", "POST"])
@admin_required
def admin_task_new():
    user = current_user()
    domains = visible_domains()
    if request.method == "POST":
        domain_id = request.form.get("domain_id") or scope_domain({})
        domain = next((d for d in domains if d["id"] == domain_id), None)
        values, error = _task_values(request.form)
        data, fname, ctype, upload_error = check_upload(request.files.get("attachment"))
        error = error or upload_error or (None if domain else "Choose a domain.")
        if error:
            flash(error, "error")
            return render_template("lms/admin/task_form.html", task=request.form.to_dict(), domains=domains,
                                   editing=False, due_value=request.form.get("due_at", ""),
                                   domain_id=domain_id), 400
        task_id = str(uuid.uuid4())
        if data is not None:
            path = storage_key(f"tasks/{task_id}", fname)
            supa.upload(path, data, ctype)
            values.update(attachment_path=path, attachment_name=fname)
        task = supa.insert("tasks", {"id": task_id, "domain_id": domain["id"], "created_by": user["id"], **values})
        if request.form.get("notify"):
            _notify(task, domain)
        else:
            flash("Task created (no email sent).", "success")
        return redirect(url_for("lms.admin_task", task_id=task_id))
    return render_template("lms/admin/task_form.html", task={"notify": "1"}, domains=domains, editing=False,
                           due_value="", domain_id=scope_domain(request.args))


@bp.route("/admin/tasks/<task_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_task_edit(task_id):
    task = _get_task(task_id)
    domains = visible_domains()
    if request.method == "POST":
        values, error = _task_values(request.form)
        data, fname, ctype, upload_error = check_upload(request.files.get("attachment"))
        error = error or upload_error
        if error:
            flash(error, "error")
            return render_template("lms/admin/task_form.html", task={**task, **request.form.to_dict()},
                                   domains=domains, editing=True, due_value=request.form.get("due_at", "")), 400
        old = task.get("attachment_path")
        if data is not None:
            path = storage_key(f"tasks/{task_id}", fname)
            supa.upload(path, data, ctype)
            values.update(attachment_path=path, attachment_name=fname)
        elif request.form.get("remove_attachment"):
            values.update(attachment_path=None, attachment_name=None)
        values["updated_at"] = now_utc().isoformat()
        task = supa.update("tasks", values, filters={"id": task_id})[0]
        if old and old != task.get("attachment_path"):
            try:
                supa.remove_files([old])
            except supa.SupabaseError:
                pass
        if request.form.get("notify"):
            _notify(task, next(d for d in domains if d["id"] == task["domain_id"]), updated=True)
        else:
            flash("Task updated.", "success")
        return redirect(url_for("lms.admin_task", task_id=task_id))
    return render_template("lms/admin/task_form.html", task=task, domains=domains, editing=True,
                           due_value=fmt_input(task.get("due_at")))


@bp.route("/admin/tasks/<task_id>")
@admin_required
def admin_task(task_id):
    task = _get_task(task_id)
    domain, interns, subs = supa.parallel(
        lambda: supa.one("domains", id=task["domain_id"]),
        lambda: interns_in(task["domain_id"], "id,full_name,email,is_active", order="full_name.asc"),
        lambda: supa.select("submissions", filters={"task_id": task_id}))
    subs = {s["intern_id"]: s for s in subs}
    rows = [{"intern": i, "sub": subs.get(i["id"])} for i in interns if i["is_active"] or i["id"] in subs]
    counts = {"interns": sum(bool(i["is_active"]) for i in interns), "submitted": len(subs),
              "review": sum(s["status"] == "submitted" for s in subs.values()),
              "approved": sum(s["status"] == "approved" for s in subs.values())}
    return render_template("lms/admin/task_detail.html", task=task, domain=domain, rows=rows, counts=counts)


@bp.route("/admin/tasks/<task_id>/resend", methods=["POST"])
@admin_required
def admin_task_resend(task_id):
    task = _get_task(task_id)
    _notify(task, supa.one("domains", id=task["domain_id"]))
    return redirect(url_for("lms.admin_task", task_id=task_id))


@bp.route("/admin/tasks/<task_id>/delete", methods=["POST"])
@admin_required
def admin_task_delete(task_id):
    task = _get_task(task_id)
    files = [s["file_path"] for s in supa.select("submissions", filters={"task_id": task_id},
                                                 columns="file_path") if s.get("file_path")]
    files.append(task.get("attachment_path"))
    supa.delete("tasks", filters={"id": task_id})  # submissions cascade
    try:
        supa.remove_files(files)
    except supa.SupabaseError:
        pass
    flash("Task and its submissions were deleted.", "success")
    return redirect(url_for("lms.admin_tasks"))


@bp.route("/admin/submissions/<sub_id>/review", methods=["POST"])
@admin_required
def admin_review(sub_id):
    sub = supa.one("submissions", id=sub_id)
    if not sub:
        abort(404)
    require_domain(sub["domain_id"])
    task = supa.one("tasks", id=sub["task_id"])
    decision = request.form.get("decision")
    feedback = request.form.get("feedback", "").strip()[:2000]
    score_raw = request.form.get("score", "").strip()
    error = None
    score = None
    if decision not in ("approved", "needs_revision"):
        error = "Choose approve or request changes."
    elif decision == "needs_revision" and not feedback:
        error = "Add feedback so the intern knows what to fix."
    if not error and score_raw:
        try:
            score = int(score_raw)
        except ValueError:
            score = -1
        if not 0 <= score <= task["max_points"]:
            error = f"Score must be between 0 and {task['max_points']}."
    if error:
        flash(error, "error")
    else:
        supa.update("submissions", {"status": decision, "score": score, "feedback": feedback or None,
                                    "reviewed_by": current_user()["id"], "reviewed_at": now_utc().isoformat()},
                    filters={"id": sub_id})
        flash("Review saved.", "success")
    return redirect(url_for("lms.admin_task", task_id=task["id"]) + f"#s-{sub_id}")


# ------------------------------------------------------------------ interns
def _allowed_email(email):
    allowed = [d.strip().lower() for d in os.environ.get("INTERN_EMAIL_DOMAINS", "").split(",") if d.strip()]
    return bool(EMAIL_RE.match(email)) and (not allowed or email.rsplit("@", 1)[1] in allowed)


def _parse_lines(text):
    entries = []
    for line in text.splitlines():
        parts = [p.strip() for p in re.split(r"[,\t;]", line, maxsplit=1) if p.strip()]
        if not parts:
            continue
        email = next((p for p in parts if "@" in p), "").lower()
        name = next((p for p in parts if "@" not in p), "") or email.split("@")[0].replace(".", " ").title()
        entries.append((name[:100], email))
    return entries


def _create_interns(entries, domain_id, password=None, creds=None):
    """New emails get an account with their OWN random temporary password (unless `password` is given,
    then everyone in the call shares it). An email that already has an intern account is just added to
    this domain. `creds`, if given, is filled with {"name","email","password"} for everyone to notify
    (password is None for people who already had an account).
    Returns (created, added, skipped, invalid)."""
    emails = [e for _, e in entries if EMAIL_RE.match(e)]
    existing = {u["email"]: u for u in supa.select("users", filters=[("email", "in", emails)],
                                                   columns="id,email,role")} if emails else {}
    members = {i["id"] for i in interns_in(domain_id, "id")}
    shared_hash = hash_password(password) if password else None
    rows, add_ids, added, skipped, invalid, seen, temp = [], [], [], [], [], set(), {}
    for name, email in entries:
        if not _allowed_email(email):
            invalid.append(email or name)
        elif email in seen:
            skipped.append(email)
        elif email in existing:
            seen.add(email)
            user = existing[email]
            if user["role"] != "intern" or user["id"] in members:
                skipped.append(email)
            else:
                add_ids.append(user["id"])
                added.append((name, email))
        else:
            seen.add(email)
            pw = password or temp_password()
            temp[email] = pw
            rows.append({"email": email, "full_name": name, "password_hash": shared_hash or hash_temp_password(pw),
                         "role": "intern", "domain_id": domain_id, "must_change_password": True})
    created = supa.insert_many("users", rows)
    supa.insert_many("intern_domains", [{"user_id": u["id"], "domain_id": domain_id} for u in created]
                     + [{"user_id": uid, "domain_id": domain_id} for uid in add_ids])
    if creds is not None:
        creds.extend({"name": u["full_name"], "email": u["email"], "password": temp[u["email"]]} for u in created)
        creds.extend({"name": n, "email": e, "password": None} for n, e in added)
    return len(created), len(add_ids), skipped, invalid


def _email_creds(creds, domain_name):
    """Send each person their login details. Returns the entries whose email failed
    (account creation is never rolled back because of a mail problem)."""
    base = os.environ.get("PORTAL_BASE_URL", "").rstrip("/") or request.host_url.rstrip("/")
    login_url = base + url_for("lms.login")

    def one(c):
        try:
            mailer.send_welcome_email(c["name"], c["email"], domain_name, login_url, c["password"])
            return None
        except Exception:  # noqa: BLE001
            return c

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [c for c in pool.map(one, creds) if c]


def _domain_names(user_id):
    ids = [l["domain_id"] for l in supa.select("intern_domains", filters={"user_id": user_id}, columns="domain_id")]
    names = [d["name"] for d in supa.select("domains", filters=[("id", "in", ids)])] if ids else []
    return ", ".join(names) or "Septaneuron"


@bp.route("/admin/interns")
@admin_required
def admin_interns():
    user = current_user()
    domain_id = scope_domain(request.args)
    domains, interns, subs = supa.parallel(
        lambda: _domains_for(user),
        lambda: interns_in(domain_id, "*", order="created_at.desc"),
        lambda: supa.select("submissions", filters=_flt(domain_id), columns="intern_id,status"))
    dnames = {d["id"]: d["name"] for d in domains}
    for i in interns:
        mine = [s for s in subs if s["intern_id"] == i["id"]]
        i["n_sub"], i["n_ok"] = len(mine), sum(s["status"] == "approved" for s in mine)
        i["domain_names"] = sorted(dnames.get(l["domain_id"], "—") for l in i["intern_domains"])
    return render_template("lms/admin/interns.html", interns=interns, domains=domains, domain_id=domain_id,
                           dnames=dnames, default_pw=default_password())


def _form_domain():
    domain_id = request.form.get("domain_id") or scope_domain({})
    ids = admin_domain_ids(current_user())
    if not domain_id or (ids is not None and domain_id not in ids) or not supa.one("domains", id=domain_id):
        abort(400, "Choose a domain.")
    return domain_id


@bp.route("/admin/interns/add", methods=["POST"])
@admin_required
def admin_intern_add():
    domain_id = _form_domain()
    name = request.form.get("full_name", "").strip()[:100]
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")  # optional override; blank = unique password, emailed
    if not name or not _allowed_email(email):
        flash("Enter the intern's name and a valid email address.", "error")
    elif password and len(password) < 8:
        flash("A custom password must be at least 8 characters.", "error")
    else:
        creds = []
        made, added, skipped, _ = _create_interns([(name, email)], domain_id, password or None, creds)
        if made or added:
            failed = _email_creds(creds, supa.one("domains", id=domain_id)["name"])
            if failed:
                pw = failed[0]["password"]
                flash(f"Account ready for {email}, but the email could not be sent. "
                      + (f"Give them this temporary password yourself: {pw}" if pw else "They already have a password."), "warn")
            else:
                flash(f"Account ready for {email}. Login details were emailed to them.", "success")
        else:
            flash(f"{email} is already in this domain.", "warn")
    return redirect(url_for("lms.admin_interns", domain=domain_id))


@bp.route("/admin/interns/bulk", methods=["POST"])
@admin_required
def admin_intern_bulk():
    domain_id = _form_domain()
    entries = _parse_lines(request.form.get("lines", ""))[:30]  # 30 per submit: each one is emailed during the request
    if not entries:
        flash("Paste at least one email address.", "error")
    else:
        creds = []
        made, added, skipped, invalid = _create_interns(entries, domain_id, None, creds)
        failed = _email_creds(creds, supa.one("domains", id=domain_id)["name"]) if creds else []
        msg = f"Created {made} account{'s' if made != 1 else ''}; login details emailed to {len(creds) - len(failed)}."
        if added:
            msg += f" Added {added} existing intern{'s' if added != 1 else ''} to this domain."
        if skipped:
            msg += f" Already in this domain: {', '.join(skipped[:8])}{'…' if len(skipped) > 8 else ''}."
        if invalid:
            msg += f" Skipped invalid: {', '.join(invalid[:8])}{'…' if len(invalid) > 8 else ''}."
        if failed:
            msg += " Email FAILED for: " + "; ".join(f"{c['email']}" + (f" (temp password {c['password']})" if c["password"] else "")
                                                     for c in failed[:5]) + ("…" if len(failed) > 5 else "") + "."
        flash(msg, "warn" if failed else ("success" if (made or added) else "warn"))
    return redirect(url_for("lms.admin_interns", domain=domain_id))


def _get_intern(user_id):
    row = supa.one("users", id=user_id)
    if not row or row["role"] != "intern":
        abort(404)
    ids = admin_domain_ids(current_user())
    if ids is not None and not supa.select("intern_domains", filters=[("user_id", "eq", row["id"]), ("domain_id", "in", ids)],
                                           columns="user_id", limit=1):
        abort(404)  # not an intern of this admin's domains
    return row


@bp.route("/admin/interns/<user_id>/reset", methods=["POST"])
@admin_required
def admin_intern_reset(user_id):
    row = _get_intern(user_id)
    pw = temp_password()
    supa.update("users", {"password_hash": hash_temp_password(pw), "must_change_password": True,
                          "failed_attempts": 0, "locked_until": None}, filters={"id": row["id"]})
    supa.delete("login_attempts", filters=[("key", "eq", attempt_key("email", row["email"]))])  # lift any lock
    failed = _email_creds([{"name": row["full_name"], "email": row["email"], "password": pw}], _domain_names(row["id"]))
    if failed:
        flash(f"Password reset for {row['email']} but the email could not be sent. Temporary password: {pw}", "warn")
    else:
        flash(f"A new temporary password was emailed to {row['email']}.", "success")
    return redirect(url_for("lms.admin_interns", domain=scope_domain(request.form)))


@bp.route("/admin/interns/<user_id>/toggle", methods=["POST"])
@admin_required
def admin_intern_toggle(user_id):
    row = _get_intern(user_id)
    supa.update("users", {"is_active": not row["is_active"]}, filters={"id": row["id"]})
    flash(f"{row['email']} was {'deactivated' if row['is_active'] else 'reactivated'}.", "success")
    return redirect(url_for("lms.admin_interns", domain=row["domain_id"]))

@bp.route("/admin/interns/<user_id>/delete", methods=["POST"])
@admin_required
def admin_intern_delete(user_id):
    """Domain admin: removes the intern from the CURRENT domain (and deletes the account if it was their only one).
    Super admin: deletes the account everywhere."""
    row = _get_intern(user_id)
    me = current_user()
    domains = [l["domain_id"] for l in supa.select("intern_domains", filters={"user_id": row["id"]}, columns="domain_id")]
    target = scope_domain(request.form) if me["role"] == "admin" else None
    if me["role"] == "admin":
        leaving, remaining = [target], [d for d in domains if d != target]
    else:
        leaving, remaining = domains or [row["domain_id"]], []
    scope = [("intern_id", "eq", row["id"]), ("domain_id", "in", leaving)]
    files = [s["file_path"] for s in supa.select("submissions", filters=scope, columns="file_path") if s.get("file_path")]
    if remaining:
        supa.delete("submissions", filters=scope)
        supa.delete("intern_domains", filters=[("user_id", "eq", row["id"]), ("domain_id", "in", leaving)])
        if row["domain_id"] in leaving:
            supa.update("users", {"domain_id": remaining[0]}, filters={"id": row["id"]})
        flash(f"{row['email']} was removed from this domain (their other domains are untouched).", "success")
    else:
        supa.delete("users", filters={"id": row["id"]})  # memberships and submissions cascade
        flash(f"{row['email']} and all their submissions were deleted.", "success")
    try:
        supa.remove_files(files)
    except supa.SupabaseError:
        pass  # orphaned files are harmless
    return redirect(url_for("lms.admin_interns", domain=target if me["role"] == "admin" else request.form.get("domain_id", "")))

# --------------------------------------------------- team (super admin only)
@bp.route("/admin/team")
@super_required
def admin_team():
    domains, admins, links = supa.parallel(
        lambda: supa.select("domains", order="name.asc"),
        lambda: supa.select("users", filters=[("role", "in", ["admin", "super_admin"])], order="created_at.asc",
                            columns="id,email,full_name,role,is_active"),
        lambda: supa.select("domain_admins", columns="domain_id,user_id"))
    dnames = {d["id"]: d["name"] for d in domains}
    known = {a["id"] for a in admins}
    by_domain = {d["id"]: [] for d in domains}
    by_user = {}
    for l in links:
        if l["domain_id"] in by_domain and l["user_id"] in known:
            by_domain[l["domain_id"]].append(l["user_id"])
            by_user.setdefault(l["user_id"], []).append(l["domain_id"])
    return render_template("lms/admin/team.html", domains=domains, admins=admins, dnames=dnames,
                           by_domain=by_domain, by_user=by_user)


def _picked_admins(form):
    """Admin ids chosen in the picker: the checklist when 'Allow multiple admins' is ticked, else the dropdown."""
    raw = form.getlist("admin_ids") if form.get("multi") else [form.get("admin_id", "")]
    raw = [r for r in raw if r]
    if not raw:
        return []
    found = supa.select("users", filters=[("id", "in", raw), ("role", "in", ["admin", "super_admin"])], columns="id")
    return [u["id"] for u in found]


def _set_domain_admins(domain_id, admin_ids):
    supa.delete("domain_admins", filters={"domain_id": domain_id})
    supa.insert_many("domain_admins", [{"domain_id": domain_id, "user_id": u} for u in admin_ids])

@bp.route("/admin/team/domain", methods=["POST"])
@super_required
def admin_domain_add():
    name = request.form.get("name", "").strip()[:60]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        flash("Enter a domain name.", "error")
        return redirect(url_for("lms.admin_team"))
    try:
        domain = supa.insert("domains", {"name": name, "slug": slug})
    except supa.SupabaseError as exc:
        flash(_friendly(exc), "error")
        return redirect(url_for("lms.admin_team"))
    ids = _picked_admins(request.form)
    _set_domain_admins(domain["id"], ids)
    flash(f"Domain '{name}' added with {len(ids)} admin{'s' if len(ids) != 1 else ''}.", "success")
    return redirect(url_for("lms.admin_team"))

@bp.route("/admin/team/domain/<domain_id>/admins", methods=["POST"])
@super_required
def admin_domain_admins(domain_id):
    domain = supa.one("domains", id=domain_id)
    if not domain:
        abort(404)
    ids = _picked_admins(request.form)
    _set_domain_admins(domain_id, ids)
    flash(f"{domain['name']}: {len(ids)} admin{'s' if len(ids) != 1 else ''} assigned.", "success")
    return redirect(url_for("lms.admin_team"))

@bp.route("/admin/team/domain/<domain_id>/delete", methods=["POST"])
@super_required
def admin_domain_delete(domain_id):
    domain = supa.one("domains", id=domain_id)
    if not domain:
        abort(404)
    has_interns = (supa.select("intern_domains", filters={"domain_id": domain_id}, columns="user_id", limit=1)
                   or supa.select("users", filters={"role": "intern", "domain_id": domain_id}, columns="id", limit=1))
    if has_interns:
        flash(f"'{domain['name']}' still has interns. Remove them from the Interns page first, then delete the domain.", "error")
        return redirect(url_for("lms.admin_team"))
    files = [t["attachment_path"] for t in supa.select("tasks", filters={"domain_id": domain_id}, columns="attachment_path")
             if t.get("attachment_path")]
    files += [s["file_path"] for s in supa.select("submissions", filters={"domain_id": domain_id}, columns="file_path")
              if s.get("file_path")]
    supa.update("users", {"domain_id": None}, filters={"domain_id": domain_id})  # admins only (no interns left)
    supa.delete("domains", filters={"id": domain_id})  # tasks, submissions and admin links cascade
    try:
        supa.remove_files(files)
    except supa.SupabaseError:
        pass
    flash(f"Domain '{domain['name']}' and its tasks were deleted.", "success")
    return redirect(url_for("lms.admin_team"))

@bp.route("/admin/team/admin", methods=["POST"])
@super_required
def admin_admin_add():
    name = request.form.get("full_name", "").strip()[:100]
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")  # optional: blank = unique password, emailed
    if not name or not EMAIL_RE.match(email):
        flash("Enter the admin's name and a valid email.", "error")
    elif password and len(password) < 10:
        flash("Admin passwords must be at least 10 characters.", "error")
    else:
        pw = password or temp_password()
        try:
            supa.insert("users", {"email": email, "full_name": name,
                                  "password_hash": hash_password(pw) if password else hash_temp_password(pw),
                                  "role": "admin", "must_change_password": True})
        except supa.SupabaseError as exc:
            flash(_friendly(exc), "error")
        else:
            failed = _email_creds([{"name": name, "email": email, "password": pw}], "Septaneuron Portal")
            if failed:
                flash(f"Admin created but the email could not be sent. Temporary password: {pw}", "warn")
            else:
                flash(f"Admin account created and login details emailed to {email}. Assign them to domains below.", "success")
    return redirect(url_for("lms.admin_team"))


def _get_admin(user_id):
    row = supa.one("users", id=user_id)
    if not row or row["role"] != "admin":
        abort(404)
    return row


@bp.route("/admin/team/<user_id>/toggle", methods=["POST"])
@super_required
def admin_admin_toggle(user_id):
    row = _get_admin(user_id)
    supa.update("users", {"is_active": not row["is_active"]}, filters={"id": row["id"]})
    flash(f"{row['email']} was {'deactivated' if row['is_active'] else 'reactivated'}.", "success")
    return redirect(url_for("lms.admin_team"))


@bp.route("/admin/team/<user_id>/password", methods=["POST"])
@super_required
def admin_admin_password(user_id):
    row = _get_admin(user_id)
    password = request.form.get("password", "")
    if len(password) < 10:
        flash("Admin passwords must be at least 10 characters.", "error")
    else:
        supa.update("users", {"password_hash": hash_password(password), "must_change_password": True,
                              "failed_attempts": 0, "locked_until": None}, filters={"id": row["id"]})
        flash(f"Password reset for {row['email']}.", "success")
    return redirect(url_for("lms.admin_team"))
