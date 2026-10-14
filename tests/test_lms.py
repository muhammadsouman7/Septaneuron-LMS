"""End-to-end tests for the portal using an in-memory stand-in for lms.supa (no network)."""
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")

import pytest  # noqa: E402

import lms.supa as supa  # noqa: E402
from lms import mailer  # noqa: E402
from lms.utils import hash_password  # noqa: E402


class FakeDB:
    def __init__(self):
        self.t = {"domains": [], "users": [], "tasks": [], "submissions": []}
        self.files = {}
        self.removed = []

    @staticmethod
    def _match(row, filters):
        for col, op, val in supa._norm(filters):
            v = row.get(col)
            if op == "eq" and v != val:
                return False
            if op == "in" and v not in val:
                return False
        return True

    def select(self, table, *, filters=None, columns="*", order=None, limit=None):
        rows = [dict(r) for r in self.t[table] if self._match(r, filters)]
        if order:
            col, direction = order.split(".")[:2]
            rows.sort(key=lambda r: (r.get(col) is None, r.get(col) or ""), reverse=direction == "desc")
        return rows[:limit] if limit else rows

    def one(self, table, **eq):
        rows = self.select(table, filters=eq, limit=1)
        return rows[0] if rows else None

    def insert(self, table, row):
        row = dict(row)
        row.setdefault("id", str(uuid.uuid4()))
        defaults = {"users": {"is_active": True, "failed_attempts": 0, "locked_until": None, "must_change_password": True},
                    "tasks": {"emailed_count": 0, "email_error": None, "description": ""},
                    "submissions": {"score": None, "feedback": None}}
        for k, v in defaults.get(table, {}).items():
            row.setdefault(k, v)
        for col in ("email",) if table == "users" else ("slug",) if table == "domains" else ():
            if any(r[col] == row[col] for r in self.t[table]):
                raise supa.SupabaseError("Supabase 409: 23505 duplicate")
        self.t[table].append(row)
        return dict(row)

    def insert_many(self, table, rows):
        return [self.insert(table, r) for r in rows]

    def update(self, table, values, *, filters):
        out = []
        for r in self.t[table]:
            if self._match(r, filters):
                r.update(values)
                out.append(dict(r))
        return out

    def delete(self, table, *, filters):
        gone = [r for r in self.t[table] if self._match(r, filters)]
        self.t[table] = [r for r in self.t[table] if r not in gone]
        if table == "tasks":
            ids = {g["id"] for g in gone}
            self.t["submissions"] = [s for s in self.t["submissions"] if s["task_id"] not in ids]
        return gone


@pytest.fixture()
def env(monkeypatch):
    db = FakeDB()
    for name in ("select", "one", "insert", "insert_many", "update", "delete"):
        monkeypatch.setattr(supa, name, getattr(db, name))
    monkeypatch.setattr(supa, "upload", lambda path, data, ctype="": db.files.__setitem__(path, data))
    monkeypatch.setattr(supa, "remove_files", lambda paths: db.removed.extend(paths))
    monkeypatch.setattr(supa, "signed_url", lambda path, download_as=None, expires=300: f"https://files.test/{path}")
    sent = []
    monkeypatch.setattr(mailer, "send_task_email",
                        lambda task, domain, recipients, link, updated=False: sent.append((task, domain, recipients, link, updated)) or len(recipients))
    from app import app
    app.config.update(TESTING=True)
    web = db.insert("domains", {"slug": "web", "name": "Web Development"})
    py = db.insert("domains", {"slug": "python", "name": "Python Programming"})
    pw = hash_password("Adm1n-Passw0rd!")
    db.insert("users", {"email": "root@x.com", "full_name": "Root", "password_hash": pw, "role": "super_admin", "must_change_password": False})
    db.insert("users", {"email": "webadmin@x.com", "full_name": "Web Admin", "password_hash": pw, "role": "admin", "domain_id": web["id"], "must_change_password": False})
    db.insert("users", {"email": "pyadmin@x.com", "full_name": "Py Admin", "password_hash": pw, "role": "admin", "domain_id": py["id"], "must_change_password": False})
    return {"db": db, "app": app, "web": web, "py": py, "sent": sent}


class Client:
    def __init__(self, app):
        self.c = app.test_client()

    def token(self, path="/portal/login"):
        html = self.c.get(path).get_data(as_text=True)
        m = re.search(r'name="_csrf" value="([^"]+)"', html)
        return m.group(1) if m else ""

    def post(self, path, data=None, token_from="/portal/account/password", **kw):
        data = dict(data or {})
        data["_csrf"] = self.token(token_from)
        return self.c.post(path, data=data, **kw)

    def login(self, email, password):
        return self.c.post("/portal/login", data={"email": email, "password": password, "_csrf": self.token()})


def login(env, email, password="Adm1n-Passw0rd!"):
    c = Client(env["app"])
    assert c.login(email, password).status_code == 302
    return c


def test_unauthenticated_redirects(env):
    c = env["app"].test_client()
    assert c.get("/portal/admin").headers["Location"].startswith("/portal/login")
    assert c.get("/portal/dashboard").status_code == 302
    assert c.post("/portal/logout").status_code == 400  # no CSRF token


def test_full_flow_task_email_submit_review(env):
    db, web, py = env["db"], env["web"], env["py"]
    admin = login(env, "webadmin@x.com")
    # create interns (default password, must change)
    admin.post("/portal/admin/interns/bulk", {"lines": "ali@gmail.com, Ali Khan\nsara@gmail.com\nbad-email\nali@gmail.com"}, token_from="/portal/admin/interns")
    interns = db.select("users", filters={"role": "intern"})
    assert {i["email"] for i in interns} == {"ali@gmail.com", "sara@gmail.com"}
    assert all(i["domain_id"] == web["id"] and i["must_change_password"] for i in interns)
    # an intern in another domain
    db.insert("users", {"email": "other@gmail.com", "full_name": "Other", "password_hash": hash_password("x"), "role": "intern", "domain_id": py["id"]})

    # publish a task -> only web interns are emailed
    r = admin.post("/portal/admin/tasks/new", {"title": "Build API", "description": "Do it", "max_points": "50", "notify": "1",
                                               "due_at": "2099-01-01T10:00"}, token_from="/portal/admin/tasks/new")
    assert r.status_code == 302
    task = db.select("tasks")[0]
    assert task["domain_id"] == web["id"] and task["due_at"].startswith("2099-01-01T05:00")  # 10:00 PKT == 05:00 UTC
    assert len(env["sent"]) == 1 and sorted(env["sent"][0][2]) == ["ali@gmail.com", "sara@gmail.com"]
    assert task["emailed_count"] == 2

    # intern must change the temporary password first
    ali = Client(env["app"])
    assert ali.login("ali@gmail.com", "Intern@Septaneuron").headers["Location"].endswith("/portal/account/password")
    assert ali.c.get("/portal/dashboard").status_code == 302
    r = ali.post("/portal/account/password", {"current": "Intern@Septaneuron", "new": "Intern@Septaneuron", "confirm": "Intern@Septaneuron"})
    assert r.status_code == 200 and db.one("users", email="ali@gmail.com")["must_change_password"]
    r = ali.post("/portal/account/password", {"current": "Intern@Septaneuron", "new": "Better-Pass1", "confirm": "Better-Pass1"})
    assert r.status_code == 302 and not db.one("users", email="ali@gmail.com")["must_change_password"]

    html = ali.c.get("/portal/dashboard").get_data(as_text=True)
    assert "Build API" in html
    assert "Build API" in ali.c.get(f"/portal/tasks/{task['id']}").get_data(as_text=True)

    # intern from another domain cannot see it
    db.update("users", {"must_change_password": False}, filters={"email": "other@gmail.com"})
    db.update("users", {"password_hash": hash_password("Other-Pass1")}, filters={"email": "other@gmail.com"})
    other = login(env, "other@gmail.com", "Other-Pass1")
    assert other.c.get(f"/portal/tasks/{task['id']}").status_code == 404
    assert "Build API" not in other.c.get("/portal/dashboard?view=all").get_data(as_text=True)

    # submit with a link + file; bad inputs rejected
    r = ali.post(f"/portal/tasks/{task['id']}/submit", {"link": "javascript:alert(1)"}, token_from=f"/portal/tasks/{task['id']}")
    assert not db.select("submissions")
    r = ali.post(f"/portal/tasks/{task['id']}/submit", {"link": "https://github.com/ali/api", "note": "done"}, token_from=f"/portal/tasks/{task['id']}")
    sub = db.select("submissions")[0]
    assert sub["status"] == "submitted" and sub["is_late"] is False and sub["domain_id"] == web["id"]
    r = ali.post(f"/portal/tasks/{task['id']}/submit", {"link": "https://github.com/ali/api2", "file": (__import__("io").BytesIO(b"x" * 10), "work.exe")},
                 token_from=f"/portal/tasks/{task['id']}", content_type="multipart/form-data")
    assert db.select("submissions")[0]["link_url"] == "https://github.com/ali/api"  # .exe rejected, nothing changed
    r = ali.post(f"/portal/tasks/{task['id']}/submit", {"link": "https://github.com/ali/api", "file": (__import__("io").BytesIO(b"zipdata"), "work.zip")},
                 token_from=f"/portal/tasks/{task['id']}", content_type="multipart/form-data")
    sub = db.select("submissions")[0]
    assert sub["file_name"] == "work.zip" and sub["file_path"] in db.files and len(db.select("submissions")) == 1

    # a different-domain admin can't touch it; the right admin can review
    pyadmin = login(env, "pyadmin@x.com")
    assert pyadmin.c.get(f"/portal/admin/tasks/{task['id']}").status_code == 404
    assert pyadmin.post(f"/portal/admin/submissions/{sub['id']}/review", {"decision": "approved"}, token_from="/portal/admin").status_code == 404
    assert pyadmin.c.get(f"/portal/files/submission/{sub['id']}").status_code == 404
    assert admin.c.get(f"/portal/files/submission/{sub['id']}").status_code == 302

    admin.post(f"/portal/admin/submissions/{sub['id']}/review", {"decision": "needs_revision", "feedback": ""}, token_from="/portal/admin")
    assert db.select("submissions")[0]["status"] == "submitted"  # feedback required
    admin.post(f"/portal/admin/submissions/{sub['id']}/review", {"decision": "needs_revision", "feedback": "Add tests", "score": "999"}, token_from="/portal/admin")
    assert db.select("submissions")[0]["status"] == "submitted"  # score above max
    admin.post(f"/portal/admin/submissions/{sub['id']}/review", {"decision": "needs_revision", "feedback": "Add tests", "score": "20"}, token_from="/portal/admin")
    s = db.select("submissions")[0]
    assert s["status"] == "needs_revision" and s["score"] == 20
    assert "Add tests" in ali.c.get(f"/portal/tasks/{task['id']}").get_data(as_text=True)
    ali.post(f"/portal/tasks/{task['id']}/submit", {"link": "https://github.com/ali/api3"}, token_from=f"/portal/tasks/{task['id']}")
    assert db.select("submissions")[0]["status"] == "submitted"
    admin.post(f"/portal/admin/submissions/{sub['id']}/review", {"decision": "approved", "score": "45"}, token_from="/portal/admin")
    ali.post(f"/portal/tasks/{task['id']}/submit", {"link": "https://github.com/ali/hack"}, token_from=f"/portal/tasks/{task['id']}")
    assert db.select("submissions")[0]["link_url"] == "https://github.com/ali/api3"  # approved = locked

    # delete task cascades and cleans storage
    admin.post(f"/portal/admin/tasks/{task['id']}/delete", token_from="/portal/admin")
    assert not db.select("tasks") and not db.select("submissions") and sub["file_path"] in db.removed


def test_lockout_and_generic_errors(env):
    c = Client(env["app"])
    for _ in range(5):
        assert c.login("webadmin@x.com", "wrong").status_code == 401
    assert c.login("webadmin@x.com", "Adm1n-Passw0rd!").status_code == 429  # locked even with right password
    assert c.login("nobody@x.com", "whatever").status_code == 401
    env["db"].update("users", {"locked_until": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}, filters={"email": "webadmin@x.com"})
    assert c.login("webadmin@x.com", "Adm1n-Passw0rd!").status_code == 302


def test_roles_and_scoping(env):
    web_admin = login(env, "webadmin@x.com")
    assert web_admin.c.get("/portal/admin/team").status_code == 302  # super admin only
    r = web_admin.post("/portal/admin/interns/add", {"full_name": "Hacker", "email": "h@gmail.com", "domain_id": env["py"]["id"]}, token_from="/portal/admin/interns")
    assert env["db"].one("users", email="h@gmail.com")["domain_id"] == env["web"]["id"]  # forced to own domain
    root = login(env, "root@x.com")
    assert root.c.get("/portal/admin/team").status_code == 200
    root.post("/portal/admin/team/admin", {"full_name": "New", "email": "n@x.com", "password": "short", "domain_id": env["py"]["id"]}, token_from="/portal/admin/team")
    assert not env["db"].one("users", email="n@x.com")
    root.post("/portal/admin/team/admin", {"full_name": "New", "email": "n@x.com", "password": "LongEnough-1", "domain_id": env["py"]["id"]}, token_from="/portal/admin/team")
    assert env["db"].one("users", email="n@x.com")["role"] == "admin"
    root.post("/portal/admin/team/domain", {"name": "Cyber Security"}, token_from="/portal/admin/team")
    assert env["db"].one("domains", slug="cyber-security")


def test_deactivated_user_is_logged_out_immediately(env):
    db = env["db"]
    web_admin = login(env, "webadmin@x.com")
    db.insert("users", {"email": "z@gmail.com", "full_name": "Z", "password_hash": hash_password("Zz-Pass-123"), "role": "intern", "domain_id": env["web"]["id"], "must_change_password": False})
    z = login(env, "z@gmail.com", "Zz-Pass-123")
    assert z.c.get("/portal/dashboard").status_code == 200
    zid = db.one("users", email="z@gmail.com")["id"]
    web_admin.post(f"/portal/admin/interns/{zid}/toggle", token_from="/portal/admin/interns")
    assert z.c.get("/portal/dashboard").status_code == 302


def test_open_redirect_blocked(env):
    c = Client(env["app"])
    r = c.c.post("/portal/login", data={"email": "webadmin@x.com", "password": "Adm1n-Passw0rd!", "next": "https://evil.com", "_csrf": c.token()})
    assert "evil.com" not in r.headers["Location"] and r.headers["Location"].endswith("/portal/")


def test_public_site_still_works(env):
    c = env["app"].test_client()
    assert c.get("/").status_code == 200 and c.get("/services").status_code == 200
    assert "Disallow: /portal/" in c.get("/robots.txt").get_data(as_text=True)


def test_supa_rest_wrapper(monkeypatch):
    calls = []

    class Resp:
        ok = True
        text = ""

        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

    def fake_request(method, url, headers=None, timeout=None, **kw):
        calls.append((method, url, headers, kw))
        return Resp({"signedURL": "/object/sign/lms-files/a/b.pdf?token=t"} if "/sign/" in url else [{"id": "1"}])

    monkeypatch.setattr(supa.requests, "request", fake_request)
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co/")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_abc")
    supa.select("tasks", filters=[("domain_id", "eq", "d1"), ("id", "in", ["a", "b"]), ("is_active", "eq", True)], order="due_at.asc.nullslast", limit=5)
    method, url, headers, kw = calls[-1]
    assert url == "https://abc.supabase.co/rest/v1/tasks" and headers == {"apikey": "sb_secret_abc"}  # no Authorization for sb_ keys
    assert ("domain_id", "eq.d1") in kw["params"] and ("id", "in.(a,b)") in kw["params"] and ("is_active", "eq.true") in kw["params"]
    assert ("order", "due_at.asc.nullslast") in kw["params"] and ("limit", "5") in kw["params"]
    supa.update("users", {"locked_until": None}, filters={"id": "x"})
    assert calls[-1][0] == "PATCH" and ("id", "eq.x") in calls[-1][3]["params"]
    with pytest.raises(supa.SupabaseError):
        supa.delete("users", filters={})
    url = supa.signed_url("a/b c.pdf", download_as="my file.pdf")
    assert url == "https://abc.supabase.co/storage/v1/object/sign/lms-files/a/b.pdf?token=t&download=my%20file.pdf"
    assert calls[-1][1].endswith("/object/sign/lms-files/a/b%20c.pdf")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "eyJlegacy.jwt.key")
    supa.one("users", id="1")
    assert calls[-1][2]["Authorization"] == "Bearer eyJlegacy.jwt.key"


def test_mailer_uses_bcc_batches(monkeypatch):
    import smtplib
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, msg): sent.append(msg)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for k, v in {"SMTP_USER": "i@x.com", "SMTP_PASSWORD": "pw", "MAIL_FROM": "i@x.com"}.items():
        monkeypatch.setenv(k, v)
    task = {"title": "T <b>", "description": "d", "due_text": "tomorrow"}
    n = mailer.send_task_email(task, "Web", [f"u{i}@g.com" for i in range(120)], "https://s/t")
    assert n == 120 and len(sent) == 3
    assert "u0@g.com" in sent[0]["Bcc"] and "To" in sent[0]
    assert "&lt;b&gt;" in sent[0].get_body(("html",)).get_content()  # HTML-escaped
    monkeypatch.delenv("SMTP_PASSWORD")
    with pytest.raises(mailer.MailError):
        mailer.send_task_email(task, "Web", ["a@g.com"], "https://s/t")
