# Septaneuron Flask conversion

This project converts the available React/Vite page structure into Flask and Jinja templates while preserving the original Septaneuron visual system.

## Structure.

```text
flask-app/
├── app.py
├── requirements.txt
├── vercel.json
├── templates/
│   ├── base.html
│   ├── navbar.html
│   ├── footer.html
│   ├── about.html
│   ├── contact.html
│   ├── portfolio.html
│   └── services.html
└── static/assets/
    ├── css/
    ├── js/
    ├── imgs/
    └── fonts/
```

## Run locally

```bash
cd flask-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000/
```

Routes:

```text
 /                  Home
/about             About
/contact           Contact
/portfolio         Portfolio
/services          Services
/ai-projects      Portfolio category route
/frontend-projects Portfolio category route
/fullstack-projects Portfolio category route
```

## Conversion behavior

The page markup was preserved in the generated Jinja templates. Shared layout is provided by `base.html`, `navbar.html`, and `footer.html`. The original dock-style navbar, hero canvas, footer structure, page ambient layers, page CSS, and animation scripts were restored from the supplied Septaneuron source reference. CSS and JavaScript are served through Flask's `url_for('static', filename=...)` helper.

The supplied source did not include the original font binary in the mounted workspace, so the footer will use the configured fallback font until `Ethnocentric-Regular.otf` is copied into `static/assets/fonts/`. The Septaneuron SVG logo is included at `static/assets/imgs/svgLogo/septaneuron.svg`.

## Intern portal

The LMS for internships is served under `/portal`. See `LMS_SETUP.md` for Supabase, email and Vercel setup.
