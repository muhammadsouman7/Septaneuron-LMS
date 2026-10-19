import os
import re
import uuid

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from . import bp, supa
from .auth import ADMIN_ROLES, current_user, login_required, my_domain_ids, roles_required
from .utils import MAX_ZIP_BYTES, check_zip_bytes, now_utc, parse_ts, storage_key, valid_url


def task_state(task, sub, now=None):
    now = now or now_utc()
    due = parse_ts(task.get("due_at"))
    status = sub["status"] if sub else "pending"
    return {"status": status, "due": due,
            "overdue": bool(due and due < now and status in ("pending", "needs_revision"))}


@bp.route("/dashboard")
@roles_required("intern")
def dashboard():
    user = current_user()
    ids = my_domain_ids(user)
    domains, tasks, subs = supa.parallel(
        lambda: supa.select("domains", filters=[("id", "in", ids)], order="name.asc"),
        lambda: supa.select("tasks", filters=[("domain_id", "in", ids)], order="due_at.asc.nullslast"),
        lambda: supa.select("submissions", filters={"intern_id": user["id"]}))
    subs = {s["task_id"]: s for s in subs}
    dnames = {d["id"]: d["name"] for d in domains}
    now = now_utc()
    rows = [{"task": t, "sub": subs.get(t["id"]), "state": task_state(t, subs.get(t["id"]), now),
             "domain": dnames.get(t["domain_id"], "")} for t in tasks]

    scored = [(r["sub"]["score"], r["task"]["max_points"]) for r in rows
              if r["sub"] and r["sub"].get("score") is not None]
    stats = {
        "assigned": len(rows),
        "todo": sum(r["state"]["status"] in ("pending", "needs_revision") for r in rows),
        "review": sum(r["state"]["status"] == "submitted" for r in rows),
        "done": sum(r["state"]["status"] == "approved" for r in rows),
        "avg": round(100 * sum(s for s, _ in scored) / sum(m for _, m in scored)) if scored else None,
    }
    view = request.args.get("view", "todo")
    groups = {"todo": ("pending", "needs_revision"), "submitted": ("submitted", "approved")}
    if view in groups:
        rows = [r for r in rows if r["state"]["status"] in groups[view]]
    else:
        view = "all"
    return render_template("lms/intern/dashboard.html", rows=rows, stats=stats, view=view, domains=domains)


def _task_for_intern(task_id):
    user = current_user()
    task = supa.one("tasks", id=task_id)
    if not task or task["domain_id"] not in my_domain_ids(user):
        abort(404)
    return task


@bp.route("/tasks/<task_id>")
@login_required
def task_view(task_id):
    user = current_user()
    if user["role"] in ADMIN_ROLES:
        return redirect(url_for("lms.admin_task", task_id=task_id))
    task = _task_for_intern(task_id)
    sub, domain = supa.parallel(
        lambda: supa.one("submissions", task_id=task["id"], intern_id=user["id"]),
        lambda: supa.one("domains", id=task["domain_id"]))
    return render_template("lms/intern/task.html", task=task, sub=sub, domain=domain,
                           state=task_state(task, sub))


@bp.route("/tasks/<task_id>/upload-url", methods=["POST"])
@roles_required("intern")
def upload_url(task_id):
    """Step 1 of a zip submission: hand the browser a one-time Supabase upload URL, so the file
    goes straight to storage and never has to fit through our server's request-size limit."""
    user = current_user()
    task = _task_for_intern(task_id)
    name = secure_filename(request.form.get("filename", ""))
    try:
        size = int(request.form.get("size", "0"))
    except ValueError:
        size = 0
    if not name or len(name) > 120 or not name.lower().endswith(".zip") or name.lower().count(".zip") != 1:
        return jsonify(error="Only .zip files are accepted."), 400
    if not 0 < size <= MAX_ZIP_BYTES:
        return jsonify(error=f"The zip must be smaller than {MAX_ZIP_BYTES // 1_000_000} MB."), 400
    path = storage_key(f"submissions/{task['id']}/{user['id']}", name)
    try:
        url = supa.create_signed_upload(path)
    except supa.SupabaseError:
        return jsonify(error="Could not start the upload. Please try again."), 503
    return jsonify(url=url, path=path, apikey=os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""))


def _discard(path):
    try:
        supa.remove_files([path])
    except supa.SupabaseError:
        pass  # an orphaned file is harmless


def _verified_upload(task, user):
    """Step 2: the zip is already in storage. Re-check it here (never trust the browser)."""
    path = request.form.get("upload_path", "").strip()
    if not path:
        return None, None, None
    prefix = f"submissions/{task['id']}/{user['id']}/"
    tail = path[len(prefix):]
    if not path.startswith(prefix) or not re.fullmatch(r"[0-9a-f]{8}-[A-Za-z0-9._-]{1,120}\.zip", tail):
        return None, None, "That upload isn't valid. Please choose the zip again."
    name = tail[9:]
    try:
        data = supa.download(path, MAX_ZIP_BYTES)
    except supa.SupabaseError:
        return None, None, "We couldn't find your uploaded file. Please upload it again."
    err = check_zip_bytes(data, name)[3]
    if err:
        _discard(path)
        return None, None, err
    return path, name, None


@bp.route("/tasks/<task_id>/submit", methods=["POST"])
@roles_required("intern")
def submit(task_id):
    user = current_user()
    task = _task_for_intern(task_id)
    sub = supa.one("submissions", task_id=task["id"], intern_id=user["id"])
    if sub and sub["status"] == "approved":
        flash("This submission was already approved, so it can't be changed.", "error")
        return redirect(url_for("lms.task_view", task_id=task_id))

    note = request.form.get("note", "").strip()[:4000]
    link = request.form.get("link", "").strip()
    new_path, filename, err = _verified_upload(task, user)
    if not err and link and not valid_url(link):
        err = "Please enter a valid link starting with http:// or https://"
    if not err and not (note or link or new_path or (sub and sub.get("file_path"))):
        err = "Add a link, a zip file or a note before submitting."
    if err:
        if new_path:
            _discard(new_path)
        flash(err, "error")
        return redirect(url_for("lms.task_view", task_id=task_id))

    now = now_utc()
    due = parse_ts(task.get("due_at"))
    values = {"note": note or None, "link_url": link or None, "status": "submitted",
              "is_late": bool(due and now > due), "submitted_at": now.isoformat()}
    if new_path:
        values.update(file_path=new_path, file_name=filename)

    if sub:
        supa.update("submissions", values, filters={"id": sub["id"]})
        if new_path and sub.get("file_path") and sub["file_path"] != new_path:
            _discard(sub["file_path"])
    else:
        supa.insert("submissions", {"id": str(uuid.uuid4()), "task_id": task["id"], "intern_id": user["id"],
                                    "domain_id": task["domain_id"], **values})
    flash("Submitted. Your mentor will review it soon." if not values["is_late"]
          else "Submitted (marked late). Your mentor will review it soon.", "success")
    return redirect(url_for("lms.task_view", task_id=task_id))


@bp.route("/files/task/<task_id>")
@login_required
def task_file(task_id):
    user = current_user()
    task = supa.one("tasks", id=task_id)
    if not task or not task.get("attachment_path"):
        abort(404)
    if user["role"] == "admin" and task["domain_id"] != user["domain_id"]:
        abort(404)
    if user["role"] == "intern" and task["domain_id"] not in my_domain_ids(user):
        abort(404)
    return redirect(supa.signed_url(task["attachment_path"], download_as=task["attachment_name"]))


@bp.route("/files/submission/<sub_id>")
@login_required
def submission_file(sub_id):
    user = current_user()
    sub = supa.one("submissions", id=sub_id)
    if not sub or not sub.get("file_path"):
        abort(404)
    allowed = {"intern": sub["intern_id"] == user["id"],
               "admin": sub["domain_id"] == user["domain_id"],
               "super_admin": True}[user["role"]]
    if not allowed:
        abort(404)
    return redirect(supa.signed_url(sub["file_path"], download_as=sub["file_name"]))