# Septaneuron Intern Portal — setup

The portal lives at **/portal** inside your existing Flask site (same repo, same Vercel project, same CSS tokens).

```
lms/                  Flask blueprint (auth, intern, admin, Supabase client, mailer)
templates/lms/        Portal pages        static/assets/css/lms.css   Portal styles
supabase/schema.sql   Tables, RLS, private storage bucket, starter domains
scripts/seed_super_admin.py   Creates your own super-admin login
tests/test_lms.py     pytest suite (runs without network)
```

## 1. Supabase

1. supabase.com → **New project**. Pick the region closest to your interns (Singapore or Mumbai for Pakistan). Save the database password somewhere safe.
2. **SQL Editor → New query**, paste all of `supabase/schema.sql`, **Run**. This creates `domains`, `users`, `tasks`, `submissions`, turns Row Level Security on (no policies, so the public key can read nothing), creates the private `lms-files` storage bucket, and seeds four domains: Web Development, Python Programming, AI & Machine Learning, AI Automation.
3. **Project Settings → API Keys**: create a **secret key** (`sb_secret_...`) if you don't have one. Legacy `service_role` keys also work, but Supabase is deprecating them by the end of 2026. You do **not** need the publishable/anon key: the browser never talks to Supabase.
4. Copy the **Project URL** (`https://<ref>.supabase.co`).

The secret key bypasses RLS. It lives only in Vercel/`.env`. Never put it in templates or JavaScript, and rotate it from the same page if it ever leaks.

## 2. Environment variables

See `.env.example`. Required: `FLASK_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `PORTAL_BASE_URL`.
Generate the Flask key with `python -c "import secrets; print(secrets.token_hex(32))"`. On Vercel the portal refuses to run if `FLASK_SECRET_KEY` is missing.

**Email**: with Gmail/Google Workspace, turn on 2-Step Verification, then Google Account → Security → **App passwords**, and use that 16-character code as `SMTP_PASSWORD`. Use a dedicated sender address (e.g. internships@yourdomain). Gmail allows roughly 500 recipients/day (Workspace about 2,000). For more volume, any SMTP relay works with the same variables (Brevo, Resend SMTP, SendGrid...).

## 3. First run (local)

```bash
cd flask-app
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill it in
pip install python-dotenv   # only needed so the seed script/Flask can read .env
python scripts/seed_super_admin.py you@septaneuron.com "Your Name"
python app.py               # http://127.0.0.1:5000/portal
```

## 4. Deploy on Vercel

1. Push the repo to GitHub. Vercel → **Add New → Project** → import it. Your existing `vercel.json` already routes everything to `app.py`.
2. **Settings → Environment Variables**: add everything from step 2 (Production, and Preview if you use it).
3. **Settings → Functions → Function Region**: choose the region nearest your Supabase project (every page makes a few database calls; matching regions keeps it fast).
4. Deploy, open `https://your-domain/portal`, sign in with the super-admin account.

## 5. Running the program

1. **Team** (super admin): add any extra domains, then create one admin per domain with a temporary password (min 10 chars). Admins must change it at first login.
2. Each domain admin → **Interns**: add interns one by one or paste a list (`email, Full Name` per line). Accounts start with the temporary password (`Septa@CNIC` unless you set `DEFAULT_INTERN_PASSWORD`) and each intern must choose their own on first sign-in.
3. Admin → **Tasks → New task**: title, instructions, deadline (Pakistan time), points, optional attachment. Tick "Email interns" and every active intern **in that domain only** gets the email. If email fails the task is still saved; use **Resend email** after fixing SMTP.
4. Interns see only their domain's tasks, submit a link and/or file (and note), and can resubmit until approved. Admins approve or request changes with a score and feedback.

## Limits and design notes

* **Uploads are capped at 4 MB** (Vercel limits request bodies to about 4.5 MB). Interns can paste GitHub/Drive links for anything larger. For bigger files later, switch to Supabase signed upload URLs so the browser uploads directly.
* Emails go out in one BCC batch per 50 interns during the request, so they never see each other's addresses and the request stays inside Vercel's time limit.
* Passwords are PBKDF2-hashed. Five wrong passwords lock an account for 15 minutes. Deactivating a user locks them out immediately. All forms use CSRF tokens and file types are whitelisted.
* Times display in Pakistan Standard Time (UTC+5).
* Interns' emails are not restricted to Gmail unless you set `INTERN_EMAIL_DOMAINS=gmail.com`.

## Tests

```bash
pip install pytest && python -m pytest tests -q
```
