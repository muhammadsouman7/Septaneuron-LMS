"""Task notification emails over SMTP (Gmail, Google Workspace, Brevo, Resend SMTP, ...)."""
import os
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape

WORKERS = 4  # parallel SMTP connections (each intern still gets their own personal message)


class MailError(RuntimeError):
    pass


def _cfg():
    cfg = {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
    }
    cfg["from"] = os.environ.get("MAIL_FROM") or cfg["user"]
    cfg["name"] = os.environ.get("MAIL_FROM_NAME", "Septaneuron Internships")
    if not (cfg["user"] and cfg["password"] and cfg["from"]):
        raise MailError("Email is not configured (set SMTP_USER, SMTP_PASSWORD and MAIL_FROM).")
    return cfg


def _body(task, domain_name, link, updated):
    headline = "A task was updated" if updated else "You have a new task"
    due = task["due_text"]
    desc = (task.get("description") or "").strip()
    snippet = (desc[:280] + "…") if len(desc) > 280 else desc
    text = (f"{headline} in {domain_name}\n\n{task['title']}\nDeadline: {due}\n\n{snippet}\n\n"
            f"Open it in the portal: {link}\n\n— Septaneuron Internship Program")
    html = f"""<div style="background:#05080a;padding:32px 12px;font-family:Inter,Segoe UI,Arial,sans-serif">
<div style="max-width:560px;margin:0 auto;background:#0b1217;border:1px solid #1c2a31;border-radius:16px;padding:32px;color:#f2f6f7">
<p style="margin:0 0 6px;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#07c0cd">{escape(domain_name)}</p>
<h1 style="margin:0 0 18px;font-size:22px;font-weight:500">{escape(headline)}</h1>
<h2 style="margin:0 0 8px;font-size:18px;font-weight:600">{escape(task['title'])}</h2>
<p style="margin:0 0 16px;font-size:13px;color:#9fb0b6">Deadline: {escape(due)}</p>
<p style="margin:0 0 24px;font-size:14px;line-height:1.6;color:#c4d0d4;white-space:pre-wrap">{escape(snippet)}</p>
<a href="{escape(link)}" style="display:inline-block;background:#07c0cd;color:#05080a;font-weight:600;font-size:14px;text-decoration:none;padding:12px 22px;border-radius:999px">View task</a>
<p style="margin:28px 0 0;font-size:12px;color:#6d7f86">Septaneuron Internship Program</p>
</div></div>"""
    return text, html


def _reason(exc):
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        text = "; ".join(f"{c} {m.decode(errors='replace') if isinstance(m, bytes) else m}" for c, m in exc.recipients.values())
    else:
        err = getattr(exc, "smtp_error", None)
        if err:
            text = f"{getattr(exc, 'smtp_code', '')} {err.decode(errors='replace') if isinstance(err, bytes) else err}"
        else:
            text = str(exc) or exc.__class__.__name__
    return " ".join(text.split())[:110]


def _message(cfg, subject, text, html, to):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["name"], cfg["from"]))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=cfg["from"].rsplit("@", 1)[-1])
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _send_group(cfg, subject, text, html, group):
    """One SMTP connection, one personal message per intern. Returns (sent, [(address, reason), ...])."""
    sent, bad = 0, []
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as smtp:
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            for addr in group:
                try:
                    smtp.send_message(_message(cfg, subject, text, html, addr))
                    sent += 1
                except smtplib.SMTPServerDisconnected:
                    raise
                except smtplib.SMTPException as exc:  # this one address failed; keep going
                    bad.append((addr, _reason(exc)))
    except (smtplib.SMTPException, OSError) as exc:  # connection/login problem: the rest of the group failed
        bad += [(addr, _reason(exc)) for addr in group[sent + len(bad):]]
    return sent, bad


def send_task_email(task, domain_name, recipients, link, updated=False, failed=None):
    """Email every address in `recipients`, each as its own message (better deliverability than one
    big BCC, and a failure shows exactly which address and why). Returns how many were sent;
    `failed`, if given, is filled with "address (reason)" for the ones that were not.
    Raises MailError only when nothing could be sent."""
    cfg = _cfg()
    if not recipients:
        return 0
    text, html = _body(task, domain_name, link, updated)
    subject = f"[{domain_name}] {'Task updated' if updated else 'New task'}: {task['title']}"
    n = min(WORKERS, len(recipients))
    groups = [recipients[i::n] for i in range(n)]
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(lambda g: _send_group(cfg, subject, text, html, g), groups))
    sent = sum(ok for ok, _ in results)
    bad = [pair for _, pairs in results for pair in pairs]
    if failed is not None:
        failed.extend(f"{addr} ({why})" for addr, why in bad)
    if not sent:
        raise MailError(f"Email failed: {bad[0][1] if bad else 'unknown error'}")
    return sent

def send_welcome_email(name, email, domain_name, login_url, temp_password=None):
    """Welcome mail with login link (+ temporary password for brand-new accounts)."""
    cfg = _cfg()
    if temp_password:
        pw_text = f"Temporary password: {temp_password}\nYou will be asked to choose your own password at first login."
        pw_html = (f'<p style="margin:0 0 16px;font-size:14px;color:#c4d0d4">Temporary password: '
                   f'<b style="color:#f2f6f7">{escape(temp_password)}</b><br>'
                   f'You will be asked to choose your own password at first login.</p>')
    else:
        pw_text = "You already had an account, so use your existing password."
        pw_html = f'<p style="margin:0 0 16px;font-size:14px;color:#c4d0d4">{pw_text}</p>'

    subject = f"Welcome to Septaneuron Internships: {domain_name}"
    text = (f"Hi {name},\n\nYour intern portal account for {domain_name} is ready.\n\n"
            f"Login: {login_url}\nEmail: {email}\n{pw_text}\n\n— Septaneuron Internship Program")
    html = f"""<div style="background:#05080a;padding:32px 12px;font-family:Inter,Segoe UI,Arial,sans-serif">
<div style="max-width:560px;margin:0 auto;background:#0b1217;border:1px solid #1c2a31;border-radius:16px;padding:32px;color:#f2f6f7">
<p style="margin:0 0 6px;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#07c0cd">{escape(domain_name)}</p>
<h1 style="margin:0 0 18px;font-size:22px;font-weight:500">Welcome, {escape(name)}!</h1>
<p style="margin:0 0 8px;font-size:14px;color:#c4d0d4">Email: {escape(email)}</p>
{pw_html}
<a href="{escape(login_url)}" style="display:inline-block;background:#07c0cd;color:#05080a;font-weight:600;font-size:14px;text-decoration:none;padding:12px 22px;border-radius:999px">Open portal</a>
<p style="margin:28px 0 0;font-size:12px;color:#6d7f86">Septaneuron Internship Program</p>
</div></div>"""
    sent, bad = _send_group(cfg, subject, text, html, [email])
    if not sent:
        raise MailError(f"Email failed: {bad[0][1] if bad else 'unknown error'}")