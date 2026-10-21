import os
from datetime import timedelta

import requests
try:  # local development only: load .env when python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from flask import Flask, render_template, request, send_from_directory, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-this-development-secret')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Vercel terminates TLS in front of Flask
app.config.update(
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,  # Vercel rejects request bodies above ~4.5 MB anyway
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.environ.get('VERCEL')),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

# Intern LMS (login, dashboards, admin) lives under /portal
from lms import bp as lms_bp  # noqa: E402
app.register_blueprint(lms_bp)

from lms.api_routes import api_bp  # noqa: E402
app.register_blueprint(api_bp)

# Normal pages routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template(
        'contact.html',
        web3forms_access_key=os.environ.get('WEB3FORMS_ACCESS_KEY', '7b105c50-ca2b-4d10-8715-c0a62f3580d3'),
    )

@app.route('/portfolio')
def portfolio():
    return render_template('portfolio.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/services/ai-machine-learning-development')
def service_ai_ml():
    return render_template('services/ai-machine-learning.html')

@app.route('/services/web-application-development')
def service_web_development():
    return render_template('services/web-application-development.html')

@app.route('/services/workflow-automation')
def service_automation():
    return render_template('services/workflow-automation.html')

@app.route('/services/digital-growth')
def service_digital_growth():
    return render_template('services/digital-growth.html')

@app.route('/terms-and-conditions')
def terms_and_conditions():
    return render_template('terms-and-conditions.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy-policy.html')

# End Normal Pages Routes

#Start Case Studies Pages

@app.route('/case-studies/xai-powered-deepfake-detection')
def case_study_deepfake_detection():
    return render_template('case-studies/case_study-xai-powered-deepfake-detection.html')

@app.route('/case-studies/cartoon-face-emotion-detection')
def case_study_cartoon_face_emotion_detection():
    return render_template('case-studies/case_study-cartoon-face-and-emotion-detection.html')

@app.route('/case-studies/kidney-stone-detection')
def case_study_kidney_stone_detection():
    return render_template('case-studies/case_study-kidney-stone-detection.html')

@app.route('/case-studies/face-recognition-attendance-system')
def case_study_face_recognition_attendance_system():
    return render_template('case-studies/case_study-face-recognition-attendance-system.html')

@app.route('/case-studies/bake-bliss-hub')
def case_study_bake_bliss_hub():
    return render_template('case-studies/case_study-bake-bliss-hub.html')

@app.route('/case-studies/al-wahad-traders')
def case_study_al_wahad_traders():
    return render_template('case-studies/case_study-al-wahad-traders.html')

@app.route('/case-studies/hr-recruitment-workflow')
def case_study_hr_recruitment_workflow():
    return render_template('case-studies/case_study-hr-recruitment-workflow.html')
# End Case Studies

#seo routes
@app.route('/robots.txt')
def robots():
    return send_from_directory(app.static_folder, 'robots.txt')

@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory(app.static_folder, 'sitemap.xml', mimetype='application/xml')
#end seo routes

# Custom 404 page (any unknown/broken URL lands here)
@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.after_request
def set_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com/ https://www.gstatic.com/; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; "
        "frame-src 'self' https://www.google.com; "
        "connect-src 'self' " + os.environ.get('SUPABASE_URL', '').rstrip('/') + "; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response

#Contact form submission route
SITE_ID = '97e82743-b52f-40bc-95ea-ad0df83ad0c6'

@app.route('/contact/submit', methods=['POST'])
def contact_submit():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    company = request.form.get('company', '').strip()
    service = request.form.get('service', '').strip()
    details = request.form.get('details', '').strip()
    budget = request.form.get('budget', '').strip()
    timeline = request.form.get('timeline', '').strip()

    # Honeypot check
    if request.form.get('botcheck'):
        return jsonify(ok=True)  # silently succeed for bots

    if not name or not email or not details:
        return jsonify(ok=False, message='Please fill in all required fields.'), 400

    message = f"""Company: {company}
Service: {service}
Budget: {budget}
Timeline: {timeline}

Details:
{details}"""

    try:
        r = requests.post(
            'http://server:3000/api/contact',
            headers={'Host': 'techtorio.com'},
            json={
                'name': name,
                'contact': email,
                'message': message,
                'siteId': SITE_ID,
            },
            timeout=10,
        )
        if r.ok:
            return jsonify(ok=True)
        app.logger.error(f"Lead API failed: {r.status_code} {r.text}")
        return jsonify(ok=False, message='Could not send your message. Please email us directly.'), 502
    except Exception as e:
        app.logger.error(f"Lead API request failed: {e}")
        return jsonify(ok=False, message='Could not send your message. Please email us directly.'), 502

@app.route('/leads', methods=['POST', 'OPTIONS'])
def leads_submit():
    if request.method == 'OPTIONS':
        response = jsonify(ok=True)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
        
    data = request.get_json(silent=True) or request.form
    name = data.get('name', '').strip()
    contact = data.get('contact', '').strip()
    message = data.get('message', '').strip()
    siteId = data.get('siteId', SITE_ID).strip()
    
    if not name or not contact or not message:
        return jsonify(ok=False, message='Please fill in all required fields.'), 400
        
    try:
        r = requests.post(
            'http://server:3000/api/contact',
            headers={'Host': 'techtorio.com'},
            json={
                'name': name,
                'contact': contact,
                'message': message,
                'siteId': siteId,
            },
            timeout=10,
        )
        response = jsonify(ok=r.ok)
        if not r.ok:
            response = jsonify(ok=False, message='Could not send your message.')
            response.status_code = 502
            app.logger.error(f"Lead API failed: {r.status_code} {r.text}")
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
    except Exception as e:
        app.logger.error(f"Lead API request failed: {e}")
        response = jsonify(ok=False, message='Could not send your message.')
        response.status_code = 502
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
