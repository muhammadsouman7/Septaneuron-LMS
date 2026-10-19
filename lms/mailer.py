"""Task notification emails over SMTP (Gmail, Google Workspace, Brevo, Resend SMTP, ...)."""
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

BATCH = 50  # recipients per message (Gmail allows up to 100 per message)


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


def send_task_email(task, domain_name, recipients, link, updated=False, failed=None):
    """Email every address in `recipients` (BCC, so interns never see each other).
    Returns the number of recipients mailed. Raises MailError on failure."""
    cfg = _cfg()
    if not recipients:
        return 0
    text, html = _body(task, domain_name, link, updated)
    subject = f"[{domain_name}] {'Task updated' if updated else 'New task'}: {task['title']}"
    sent = 0
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            for i in range(0, len(recipients), BATCH):
                chunk = recipients[i:i + BATCH]
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = formataddr((cfg["name"], cfg["from"]))
                msg["To"] = formataddr((cfg["name"], cfg["from"]))
                msg["Bcc"] = ", ".join(chunk)
                msg.set_content(text)
                msg.add_alternative(html, subtype="html")
                refused = smtp.send_message(msg) or {}  # only the addresses the server rejected
                if refused and failed is not None:
                    failed.extend(refused)
                sent += len(chunk) - len(refused)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Email failed after {sent} recipient(s): {exc}") from exc
    return sent
