import io
import os
import re
import stat
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from . import bp

PKT = timezone(timedelta(hours=5))  # Pakistan Standard Time, no DST
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
MAX_UPLOAD_BYTES = 4_000_000  # Vercel caps request bodies at 4.5 MB
ALLOWED_EXT = {
    "pdf", "zip", "txt", "md", "csv", "json", "ipynb", "py", "js", "html", "css", "sql",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "png", "jpg", "jpeg", "gif", "webp", "mp4", "mov",
}


def default_password():
    return os.environ.get("DEFAULT_INTERN_PASSWORD", "Intern@Septaneuron")


def hash_password(password):
    return generate_password_hash(password, method="pbkdf2:sha256:600000")


def now_utc():
    return datetime.now(timezone.utc)


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).replace("Z", "+00:00").replace(" ", "T")
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s)
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def local_input_to_utc(text):
    """<input type=datetime-local> (entered in Pakistan time) -> UTC ISO string."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M").replace(tzinfo=PKT)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def valid_url(url):
    return bool(re.match(r"^https?://[^\s]+\.[^\s]+$", url or "", re.I)) and len(url) <= 500


def check_upload(storage):
    """Return (data, filename, content_type, error). storage may be empty."""
    if not storage or not storage.filename:
        return None, None, None, None
    name = storage.filename
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT:
        return None, None, None, f"'.{ext or '?'}' files are not allowed."
    data = storage.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return None, None, None, "File is larger than 4 MB. Please share a link (GitHub / Drive) instead."
    return data, name, storage.mimetype or "application/octet-stream", None

# ---- zip-only uploads for intern submissions (the browser uploads straight to Supabase Storage)
MAX_ZIP_BYTES = 50_000_000           # per zip; Supabase's free plan caps a single file at 50 MB
MAX_ZIP_ENTRIES = 5000
MAX_ZIP_UNCOMPRESSED = 500_000_000   # total size once extracted
MAX_ZIP_RATIO = 100                  # per-file compression ratio (zip-bomb guard)
BLOCKED_IN_ZIP = {"exe", "dll", "msi", "scr", "com", "bat", "cmd", "vbs", "vbe", "wsf", "lnk",
                  "pif", "reg", "apk", "hta", "cpl", "ps1"}


def check_zip_bytes(data, filename):
    """Return (data, filename, content_type, error). Accepts only a real, safe .zip."""
    name = secure_filename(filename or "")
    if not name or len(name) > 120 or not name.lower().endswith(".zip") or name.lower().count(".zip") != 1:
        return None, None, None, "Only .zip files are accepted."
    if len(data) > MAX_ZIP_BYTES:
        return None, None, None, f"The zip is larger than {MAX_ZIP_BYTES // 1_000_000} MB."
    if not data.startswith(b"PK\x03\x04"):  # magic bytes, so a renamed .exe/.pdf is rejected
        return None, None, None, "That file is not a valid zip archive."
    try:
        infos = zipfile.ZipFile(io.BytesIO(data)).infolist()
    except (zipfile.BadZipFile, NotImplementedError, ValueError):
        return None, None, None, "That file is not a valid zip archive."
    if not infos or len(infos) > MAX_ZIP_ENTRIES:
        return None, None, None, f"The zip must contain between 1 and {MAX_ZIP_ENTRIES} files."
    total = 0
    for i in infos:
        n = i.filename
        parts = n.replace("\\", "/").split("/")
        if n.startswith(("/", "\\")) or ".." in parts or re.match(r"^[A-Za-z]:", n) or "\x00" in n:
            return None, None, None, "The zip contains unsafe file paths."
        if i.flag_bits & 0x1:
            return None, None, None, "Password-protected zips are not allowed."
        if stat.S_ISLNK(i.external_attr >> 16):
            return None, None, None, "The zip contains symbolic links, which are not allowed."
        total += i.file_size
        if total > MAX_ZIP_UNCOMPRESSED or (i.compress_size and i.file_size > 1_000_000
                                            and i.file_size / i.compress_size > MAX_ZIP_RATIO):
            return None, None, None, "The zip expands to an unreasonable size."
        ext = n.rsplit(".", 1)[-1].lower() if "." in n else ""
        if not i.is_dir() and ext in BLOCKED_IN_ZIP:
            return None, None, None, f"The zip contains a blocked file type (.{ext})."
    return data, name, "application/zip", None


def password_error(new, current="", email=""):
    """Password policy for the forced/voluntary change. Returns a message or None."""
    if len(new) < 8 or len(new) > 128:
        return "Use between 8 and 128 characters."
    if not (re.search(r"[a-z]", new) and re.search(r"[A-Z]", new)
            and re.search(r"\d", new) and re.search(r"[^A-Za-z0-9]", new)):
        return "Use uppercase, lowercase, a number and a symbol."
    if new == current or new == default_password():
        return "Choose a password different from the temporary one."
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in new.lower():
        return "Your password must not contain your email name."
    return None

def storage_key(prefix, filename):
    safe = secure_filename(filename) or ("file." + filename.rsplit(".", 1)[-1])
    return f"{prefix}/{uuid.uuid4().hex[:8]}-{safe}"


# ----------------------------------------------------------- jinja helpers
@bp.app_template_filter("dt")
def fmt_dt(value, with_time=True):
    d = parse_ts(value)
    if not d:
        return "—"
    return d.astimezone(PKT).strftime("%d %b %Y, %I:%M %p" if with_time else "%d %b %Y")


@bp.app_template_filter("dtinput")
def fmt_input(value):
    d = parse_ts(value)
    return d.astimezone(PKT).strftime("%Y-%m-%dT%H:%M") if d else ""


@bp.app_template_filter("due_in")
def due_in(value):
    d = parse_ts(value)
    if not d:
        return "No deadline"
    secs = (d - now_utc()).total_seconds()
    days = int(abs(secs) // 86400)
    hours = int(abs(secs) % 86400 // 3600)
    span = f"{days}d" if days >= 2 else (f"{days * 24 + hours}h" if secs else "now")
    return f"Overdue by {span}" if secs < 0 else f"Due in {span}"
