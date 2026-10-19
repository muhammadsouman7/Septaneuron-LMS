import os
import re
import uuid

from flask import abort, flash, redirect, render_template, request, url_for

from . import bp, mailer, supa
from .auth import admin_required, current_user, super_required
from .utils import (EMAIL_RE, check_upload, default_password, fmt_dt, fmt_input, hash_password,
                    local_input_to_utc, now_utc, storage_key)


# ------------------------------------------------------------------ helpers
def _domains_for(user):
    if user["role"] == "super_admin":
        return supa.select("domains", order="name.asc")
    return supa.select("domains", filters={"id": user["domain_id"]})


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
    """Domain the page is scoped to. Domain admins are always locked to their own;
    a super admin may pick one with ?domain=<id> or see everything (None)."""
    user = current_user()
    if user["role"] == "admin":
        return user["domain_id"]
    return source.get("domain") or source.get("domain_id") or None


def require_domain(domain_id):
    user = current_user()
    if user["role"] == "admin" and domain_id != user["domain_id"]:
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
    return {"title": title, "description": form.get("description", "").strip()[:8000],
            "due_at": due, "max_points": points}, None


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
    note = f"The mail server rejected {len(failed)} address(es): {', '.join(failed[:5])}." if failed else None
    supa.update("tasks", {"emailed_count": sent, "emailed_at": now_utc().isoformat() if sent else None,
                          "email_error": error or note}, filters={"id": task["id"]})
    if error:
        flash(f"Task saved, but the email was not sent: {error}", "warn")
    elif note:
        flash(f"Email sent to {sent} intern{'s' if sent != 1 else ''}. {note}", "warn")
    else:
        flash(f"Email sent to {sent} intern{'s' if sent != 1 else ''}.", "success")


@bp.route("/admin/tasks/new", methods=["GET", "POST"])
@admin_required
def admin_task_new():
    user = current_user()
    domains = visible_domains()
    if request.method == "POST":
        domain_id = user["domain_id"] if user["role"] == "admin" else request.form.get("domain_id")
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


def _create_interns(entries, domain_id, password):
    """New emails get an account; an email that already has an intern account is simply added to
    this domain (so one person can be in several domains). Returns (created, added, skipped, invalid)."""
    emails = [e for _, e in entries if EMAIL_RE.match(e)]
    existing = {u["email"]: u for u in supa.select("users", filters=[("email", "in", emails)],
                                                   columns="id,email,role")} if emails else {}
    members = {i["id"] for i in interns_in(domain_id, "id")}
    pw_hash = hash_password(password)  # hashed once: identical temporary password for the whole batch
    rows, add_ids, skipped, invalid, seen = [], [], [], [], set()
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
        else:
            seen.add(email)
            rows.append({"email": email, "full_name": name, "password_hash": pw_hash, "role": "intern",
                         "domain_id": domain_id, "must_change_password": True})
    created = supa.insert_many("users", rows)
    supa.insert_many("intern_domains", [{"user_id": u["id"], "domain_id": domain_id} for u in created]
                     + [{"user_id": uid, "domain_id": domain_id} for uid in add_ids])
    return len(created), len(add_ids), skipped, invalid


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
    user = current_user()
    domain_id = user["domain_id"] if user["role"] == "admin" else request.form.get("domain_id")
    if not domain_id or not supa.one("domains", id=domain_id):
        abort(400, "Choose a domain.")
    return domain_id


@bp.route("/admin/interns/add", methods=["POST"])
@admin_required
def admin_intern_add():
    domain_id = _form_domain()
    name = request.form.get("full_name", "").strip()[:100]
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "") or default_password()
    if not name or not _allowed_email(email):
        flash("Enter the intern's name and a valid email address.", "error")
    elif len(password) < 8:
        flash("A custom password must be at least 8 characters.", "error")
    else:
        made, added, skipped, _ = _create_interns([(name, email)], domain_id, password)
        if made:
            flash(f"Account created for {email}.", "success")
        elif added:
            flash(f"{email} already had an account, so they were added to this domain (same password).", "success")
        else:
            flash(f"{email} is already in this domain.", "warn")
    return redirect(url_for("lms.admin_interns", domain=domain_id))


@bp.route("/admin/interns/bulk", methods=["POST"])
@admin_required
def admin_intern_bulk():
    domain_id = _form_domain()
    entries = _parse_lines(request.form.get("lines", ""))[:200]
    if not entries:
        flash("Paste at least one email address.", "error")
    else:
        made, added, skipped, invalid = _create_interns(entries, domain_id, default_password())
        msg = f"Created {made} account{'s' if made != 1 else ''}."
        if added:
            msg += f" Added {added} existing intern{'s' if added != 1 else ''} to this domain."
        if skipped:
            msg += f" Already in this domain: {', '.join(skipped[:8])}{'…' if len(skipped) > 8 else ''}."
        if invalid:
            msg += f" Skipped invalid: {', '.join(invalid[:8])}{'…' if len(invalid) > 8 else ''}."
        flash(msg, "success" if (made or added) else "warn")
    return redirect(url_for("lms.admin_interns", domain=domain_id))


def _get_intern(user_id):
    row = supa.one("users", id=user_id)
    if not row or row["role"] != "intern":
        abort(404)
    me = current_user()
    if me["role"] == "admin" and not supa.select("intern_domains", filters={"user_id": row["id"], "domain_id": me["domain_id"]},
                                                   columns="user_id", limit=1):
        abort(404)  # not an intern of this admin's domain
    return row


@bp.route("/admin/interns/<user_id>/reset", methods=["POST"])
@admin_required
def admin_intern_reset(user_id):
    row = _get_intern(user_id)
    supa.update("users", {"password_hash": hash_password(default_password()), "must_change_password": True,
                          "failed_attempts": 0, "locked_until": None}, filters={"id": row["id"]})
    flash(f"{row['email']} was reset to the temporary password.", "success")
    return redirect(url_for("lms.admin_interns", domain=row["domain_id"]))


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
    """Domain admin: removes the intern from THIS domain (and deletes the account if it was their only one).
    Super admin: deletes the account everywhere."""
    row = _get_intern(user_id)
    me = current_user()
    domains = [l["domain_id"] for l in supa.select("intern_domains", filters={"user_id": row["id"]}, columns="domain_id")]
    if me["role"] == "admin":
        leaving, remaining = [me["domain_id"]], [d for d in domains if d != me["domain_id"]]
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
    return redirect(url_for("lms.admin_interns", domain=me["domain_id"] if me["role"] == "admin" else request.form.get("domain_id", "")))

# --------------------------------------------------- team (super admin only)
@bp.route("/admin/team")
@super_required
def admin_team():
    domains = supa.select("domains", order="name.asc")
    admins = supa.select("users", filters=[("role", "in", ["admin", "super_admin"])], order="created_at.asc",
                         columns="id,email,full_name,role,domain_id,is_active")
    dnames = {d["id"]: d["name"] for d in domains}
    return render_template("lms/admin/team.html", domains=domains, admins=admins, dnames=dnames)


@bp.route("/admin/team/domain", methods=["POST"])
@super_required
def admin_domain_add():
    name = request.form.get("name", "").strip()[:60]
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        flash("Enter a domain name.", "error")
    else:
        try:
            supa.insert("domains", {"name": name, "slug": slug})
            flash(f"Domain '{name}' added.", "success")
        except supa.SupabaseError as exc:
            flash(_friendly(exc), "error")
    return redirect(url_for("lms.admin_team"))


@bp.route("/admin/team/admin", methods=["POST"])
@super_required
def admin_admin_add():
    name = request.form.get("full_name", "").strip()[:100]
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    domain_id = request.form.get("domain_id", "")
    if not name or not EMAIL_RE.match(email):
        flash("Enter the admin's name and a valid email.", "error")
    elif len(password) < 10:
        flash("Admin passwords must be at least 10 characters.", "error")
    elif not supa.one("domains", id=domain_id):
        flash("Choose a domain.", "error")
    else:
        try:
            supa.insert("users", {"email": email, "full_name": name, "password_hash": hash_password(password),
                                  "role": "admin", "domain_id": domain_id, "must_change_password": True})
            flash(f"Admin account created for {email}. They must change the password at first login.", "success")
        except supa.SupabaseError as exc:
            flash(_friendly(exc), "error")
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
