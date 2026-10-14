"""Create the first super admin (run once, locally, after applying supabase/schema.sql).

    python scripts/seed_super_admin.py you@septaneuron.com "Your Name"

Reads SUPABASE_URL and SUPABASE_SECRET_KEY from your environment or .env, and asks for the password.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from lms import supa  # noqa: E402
from lms.utils import hash_password  # noqa: E402


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    email, name = sys.argv[1].strip().lower(), sys.argv[2].strip()
    password = getpass.getpass("Password (min 10 chars): ")
    if len(password) < 10 or password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords must match and be at least 10 characters.")
    if supa.one("users", email=email):
        sys.exit(f"{email} already exists.")
    supa.insert("users", {"email": email, "full_name": name, "password_hash": hash_password(password),
                          "role": "super_admin", "must_change_password": False})
    print(f"Super admin created: {email}")


if __name__ == "__main__":
    main()
