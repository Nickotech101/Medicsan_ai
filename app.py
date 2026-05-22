from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import json
import os
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
from io import BytesIO
import threading
import requests
import pdfkit

file_lock = threading.Lock()

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medicsan.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    query = db.Column(db.String(500), nullable=False)
    source = db.Column(db.String(50), nullable=False)
    time = db.Column(db.String(50), nullable=False)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    medicine = db.Column(db.String(500), nullable=False)
    generic_name = db.Column(db.String(500))
    time = db.Column(db.String(50), nullable=False)

class Analytics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    query = db.Column(db.String(500), nullable=False)
    count = db.Column(db.Integer, default=1)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ENV =================
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ================= PATHS =================
MED_DATA_PATH = os.path.join("data", "medicines.json")
HISTORY_PATH = os.path.join("data", "history.json")
FAV_PATH = os.path.join("data", "favorites.json")
ANALYTICS_PATH = os.path.join("data", "analytics.json")


# ================= HELPERS =================
def load_json(path, default):
    with file_lock:
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

def save_json(path, data):
    with file_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


MED_DB = load_json(MED_DATA_PATH, {})
load_json(HISTORY_PATH, [])
load_json(FAV_PATH, [])
load_json(ANALYTICS_PATH, {})


def add_to_history(query: str, source: str):
    query = query.strip()[:200]
    if not query or not current_user.is_authenticated:
        return

    existing = db.session.query(History).filter_by(user_id=current_user.id, query=query).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    new_h = History(
        user_id=current_user.id,
        query=query,
        source=source,
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(new_h)
    db.session.commit()
    
    # Keep only top 10
    user_hist = db.session.query(History).filter_by(user_id=current_user.id).order_by(History.id.desc()).all()
    if len(user_hist) > 10:
        for h in user_hist[10:]:
            db.session.delete(h)
        db.session.commit()


def update_analytics(query: str):
    query = query.strip().lower()
    if not query or not current_user.is_authenticated:
        return
    stat = db.session.query(Analytics).filter_by(user_id=current_user.id, query=query).first()
    if stat:
        stat.count += 1
    else:
        new_stat = Analytics(user_id=current_user.id, query=query)
        db.session.add(new_stat)
    db.session.commit()


def groq_medicine_lookup(medicine_name: str):
    if client is None:
        return None, "Groq API key missing. Add GROQ_API_KEY in .env"

    system_prompt = """
You are MediScan AI, an educational medicine information assistant.

Rules:
- Educational info only.
- Do NOT provide diagnosis, exact prescriptions, or emergency instructions.
- Dosage must be general, safe, and non-prescriptive.
- Always include warnings and suggest consulting a doctor.
- For generic_substitutes, list widely available low-cost generic equivalents with the same active ingredient. Use an empty array [] if none exist.

Return STRICT JSON only in this schema:

{
  "generic_name": "...",
  "use": "...",
  "dosage": "...",
  "side_effects": ["..."],
  "warnings": ["..."],
  "generic_substitutes": [
    { "name": "...", "active_ingredient_match": 100 }
  ]
}
"""

    user_prompt = f"""
Medicine name: {medicine_name}

Generate general educational medicine info.
Return JSON only.
"""

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.2,
        max_tokens=700,
    )

    text = completion.choices[0].message.content.strip()

    try:
        data = json.loads(text)
        required = ["generic_name", "use", "dosage", "side_effects", "warnings"]
        for k in required:
            if k not in data:
                return None, "Groq response missing fields."
        if "generic_substitutes" not in data:
            data["generic_substitutes"] = []
        return data, None
    except Exception:
        return None, "Groq returned invalid JSON. Try again."


# ================= ROUTES =================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists.')
            return redirect(url_for('register'))
            
        new_user = User(username=username, password_hash=generate_password_hash(password, method='pbkdf2:sha256'))
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Please check your login details and try again.')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/dashboard")
@login_required
def dashboard_page():
    return render_template("dashboard.html")
medicine_cache = {}

POPULAR_MEDICINES = [
    "Paracetamol",
    "Pantoprazole",
    "Pan D",
    "Paracip",
    "Dolo 650",
    "Crocin",
    "Calpol",
    "Cetirizine",
    "Sinarest",
    "Benadryl",
    "Ascoril",
    "Ibuprofen",
    "Combiflam",
    "Omeprazole",
    "Aspirin",
    "Atorvastatin",
    "Metformin",
    "Azithromycin",
    "Amoxicillin",
    "Cofsils"
]


@app.route("/api/suggestions", methods=["GET"])
def suggestions():

    query = request.args.get("q", "").strip().lower()

    if len(query) < 1:
        return jsonify({"suggestions": []})

    suggestions = []

    # =========================
    # SUPER FAST LOCAL SEARCH
    # =========================

    for medicine in POPULAR_MEDICINES:

        if medicine.lower().startswith(query):

            suggestions.append(medicine)

    # cache search
    for medicine in medicine_cache:

        if medicine.lower().startswith(query):

            suggestions.append(medicine)

    # =========================
    # FDA API SEARCH
    # =========================

    try:

        url = (
            "https://api.fda.gov/drug/label.json?"
            f"search=openfda.brand_name:{query}*&limit=10"
        )

        response = requests.get(url, timeout=0.8)

        data = response.json()

        if "results" in data:

            for item in data["results"]:

                openfda = item.get("openfda", {})

                for brand in openfda.get("brand_name", []):

                    clean_name = brand.title()

                    if len(clean_name) < 40:

                        suggestions.append(clean_name)

                        medicine_cache[clean_name] = True

                for generic in openfda.get("generic_name", []):

                    clean_name = generic.title()

                    if len(clean_name) < 40:

                        suggestions.append(clean_name)

                        medicine_cache[clean_name] = True

    except:
        pass

    # remove duplicates
    suggestions = list(dict.fromkeys(suggestions))

    return jsonify({
        "suggestions": suggestions[:10]
    })

@app.route("/api/history", methods=["GET"])
@login_required
def history_api():
    history_items = db.session.query(History).filter_by(user_id=current_user.id).order_by(History.id.desc()).all()
    history = [{"query": h.query, "source": h.source, "time": h.time} for h in history_items]
    return jsonify({"success": True, "history": history})


@app.route("/api/favorites", methods=["GET"])
@login_required
def favorites_api():
    fav_items = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.id.desc()).all()
    favs = [{"medicine": f.medicine, "generic_name": f.generic_name, "time": f.time} for f in fav_items]
    return jsonify({"success": True, "favorites": favs})


@app.route("/api/favorites/toggle", methods=["POST"])
@login_required
def favorites_toggle():
    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "error": "Invalid request body."
        }), 400
    medicine = (data.get("medicine") or "").strip().lower()
    generic_name = (data.get("generic_name") or "").strip()

    if not medicine:
        return jsonify({"success": False, "error": "Medicine missing."})

    existing = Favorite.query.filter_by(user_id=current_user.id, medicine=medicine).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"success": True, "favorited": False})

    new_fav = Favorite(
        user_id=current_user.id,
        medicine=medicine,
        generic_name=generic_name,
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(new_fav)
    db.session.commit()
    
    user_favs = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.id.desc()).all()
    if len(user_favs) > 20:
        for f in user_favs[20:]:
            db.session.delete(f)
        db.session.commit()
        
    return jsonify({"success": True, "favorited": True})


@app.route("/api/analytics", methods=["GET"])
@login_required
def analytics_api():
    stats = db.session.query(Analytics).filter_by(user_id=current_user.id).all()
    analytics_dict = {s.query: s.count for s in stats}
    top = sorted(analytics_dict.items(), key=lambda x: x[1], reverse=True)[:10]
    return jsonify({"success": True, "top": top, "all": analytics_dict})


@app.route("/api/medicine", methods=["POST"])
def medicine_info():
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "error": "Invalid or missing JSON request body."
            }), 400

        medicine = (data.get("medicine") or "").strip().lower()[:200]

        if not medicine:
            return jsonify({
                "success": False,
                "error": "Please enter a medicine name."
            }), 400

        medicine = " ".join(medicine.split())

        # analytics
        update_analytics(medicine)

        # exact match
        if medicine in MED_DB:
            add_to_history(medicine, "database")
            return jsonify({
                "success": True,
                "source": "database",
                "medicine": medicine,
                "data": MED_DB[medicine]
            }), 200

        # partial match
        for key in MED_DB:
            if medicine in key or key in medicine:
                add_to_history(key, "database")
                return jsonify({
                    "success": True,
                    "source": "database",
                    "medicine": key,
                    "data": MED_DB[key],
                    "note": "Closest match found in database."
                }), 200

        # AI lookup
        ai_data, err = groq_medicine_lookup(medicine)

        if err:
            return jsonify({
    "success": True,
    "source": "demo",
    "medicine": medicine,
    "data": {
        "generic_name": "Aspirin",
        "use": "Pain relief, fever reduction and anti-inflammatory",
        "dosage": "Typically 250-1000mg every 4-6 hours",
        "side_effects": [
            "Nausea",
            "Dizziness",
            "Stomach upset"
        ],
        "warnings": [
            "Do not take on empty stomach",
            "Consult doctor before use"
        ],
        "generic_substitutes": [
            {
                "name": "Aspirin Bayer",
                "active_ingredient_match": 100
            },
            {
                "name": "Aspirin Cipla",
                "active_ingredient_match": 100
            }
        ]
    }
}), 200

        add_to_history(medicine, "groq")

        return jsonify({
            "success": True,
            "source": "groq",
            "medicine": medicine,
            "data": ai_data,
            "note": "AI-generated info (educational only)."
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Internal server error.",
            "details": str(e)
        }), 500
def get_medicine_data(medicine_name: str):
    """
    Returns: (data_dict, source, error)
    source => "database" or "groq"
    """
    medicine = (medicine_name or "").strip().lower()
    if not medicine:
        return None, None, "Medicine name missing."

    medicine = " ".join(medicine.split())

    # 1) exact
    if medicine in MED_DB:
        return MED_DB[medicine], "database", None

    # 2) partial
    for key in MED_DB:
        if medicine in key or key in medicine:
            return MED_DB[key], "database", None

    # 3) groq
    ai_data, err = groq_medicine_lookup(medicine)
    if err:
        return None, None, err
    return ai_data, "groq", None
def get_medicine_data(medicine_name: str):
    """
    Returns: (data_dict, source, error)
    source => "database" or "groq"
    """
    medicine = (medicine_name or "").strip().lower()
    if not medicine:
        return None, None, "Medicine name missing."

    medicine = " ".join(medicine.split())

    # 1) exact
    if medicine in MED_DB:
        return MED_DB[medicine], "database", None

    # 2) partial
    for key in MED_DB:
        if medicine in key or key in medicine:
            return MED_DB[key], "database", None

    # 3) groq
    ai_data, err = groq_medicine_lookup(medicine)
    if err:
        return None, None, err
    return ai_data, "groq", None

@app.route("/compare")
def compare_page():
    return render_template("compare.html")

@app.route("/api/compare", methods=["POST"])
def compare_medicines():
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "error": "Invalid request body."
            }), 400

        med_a = (data.get("medicineA") or "").strip()
        med_b = (data.get("medicineB") or "").strip()

        if not med_a or not med_b:
            return jsonify({
                "success": False,
                "error": "Please enter both medicine names."
            }), 400

        a_data, a_source, err_a = get_medicine_data(med_a)
        if err_a:
            return jsonify({
                "success": False,
                "error": f"Medicine A error: {err_a}"
            }), 500

        b_data, b_source, err_b = get_medicine_data(med_b)
        if err_b:
            return jsonify({
                "success": False,
                "error": f"Medicine B error: {err_b}"
            }), 500

        # Groq verdict (comparison)
        verdict = None

        if client:
            system_prompt = """
You are MediScan AI, an educational medicine comparison assistant.

Rules:
- Educational only
- No diagnosis or prescriptions
- Mention consult doctor

Return JSON only:

{
  "summary": "...",
  "safer_for_stomach": "Medicine A / Medicine B / depends",
  "key_differences": ["...", "...", "..."],
  "warning": "..."
}
"""

            user_prompt = f"""
Compare these medicines in simple language:

Medicine A: {med_a}
Data A: {json.dumps(a_data)}

Medicine B: {med_b}
Data B: {json.dumps(b_data)}

Return JSON only.
"""

            try:
                completion = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": system_prompt.strip()},
                        {"role": "user", "content": user_prompt.strip()},
                    ],
                    temperature=0.2,
                    max_tokens=600,
                )

                verdict_text = completion.choices[0].message.content.strip()
                verdict = json.loads(verdict_text)

            except Exception:
                verdict = {
                    "summary": "AI verdict failed. Please try again.",
                    "safer_for_stomach": "depends",
                    "key_differences": [],
                    "warning": "Consult doctor for medical decisions."
                }

        return jsonify({
            "success": True,
            "medicineA": {
                "name": med_a,
                "source": a_source,
                "data": a_data
            },
            "medicineB": {
                "name": med_b,
                "source": b_source,
                "data": b_data
            },
            "verdict": verdict
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Failed to compare medicines.",
            "details": str(e)
        }), 500
@app.route("/interaction")
def interaction_page():
    return render_template("interaction.html")
@app.route("/api/interaction", methods=["POST"])
def medicine_interaction():
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "error": "Invalid request body."
            }), 400

        med_a = (data.get("medicineA") or "").strip()
        med_b = (data.get("medicineB") or "").strip()

        if not med_a or not med_b:
            return jsonify({
                "success": False,
                "error": "Please enter both medicine names."
            }), 400

        if client is None:
            return jsonify({
                "success": False,
                "error": "Groq API key missing. Add GROQ_API_KEY in .env"
            }), 500

        system_prompt = """
You are MediScan AI, an educational medicine interaction checker.

Rules:
- Educational only
- No diagnosis, prescriptions, or emergency instructions.
- If uncertain, say "unknown" or "not enough info".
- Always recommend consulting a doctor/pharmacist.

Return STRICT JSON only:

{
  "risk_level": "low|medium|high|unknown",
  "interaction_summary": "...",
  "what_to_avoid": ["..."],
  "warning_signs": ["..."],
  "final_note": "..."
}
"""

        user_prompt = f"""
Check possible drug interaction between:

Medicine A: {med_a}
Medicine B: {med_b}

Return JSON only.
"""

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            temperature=0.2,
            max_tokens=650,
        )

        text = completion.choices[0].message.content.strip()
        result = json.loads(text)

        return jsonify({
            "success": True,
            "data": result
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Failed to check medicine interaction.",
            "details": str(e)
        }), 500
@app.route("/api/favorites/clear", methods=["POST"])
@login_required
def clear_favorites():
    Favorite.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "Favorites cleared successfully."})

# @app.route("/api/report/pdf", methods=["POST"])
# def report_pdf():

#     data = request.get_json()

#     if not data:
#         return jsonify({
#             "success": False,
#             "error": "Invalid request body."
#         }), 400

#     medicine = (data.get("medicine") or "Unknown").upper()
#     source = (data.get("source") or "Unknown")
#     med = data.get("data") or {}

#     generic = med.get("generic_name", "")
#     use = med.get("use", "")
#     dosage = med.get("dosage", "")
#     side_effects = med.get("side_effects", [])
#     warnings = med.get("warnings", [])
#     generic_substitutes = med.get("generic_substitutes", [])

#     # =========================
#     # PDF START
#     # =========================

#     buffer = BytesIO()

#     doc = SimpleDocTemplate(
#         buffer,
#         pagesize=A4,
#         rightMargin=20,
#         leftMargin=20,
#         topMargin=18,
#         bottomMargin=18
#     )

#     styles = getSampleStyleSheet()
#     elements = []

#     # =========================
#     # STYLES
#     # =========================

#     title_style = ParagraphStyle(
#         'title',
#         fontName='Helvetica-Bold',
#         fontSize=22,
#         leading=26,
#         textColor=colors.white
#     )

#     subtitle_style = ParagraphStyle(
#         'subtitle',
#         fontName='Helvetica',
#         fontSize=11,
#         leading=14,
#         textColor=colors.white
#     )

#     section_style = ParagraphStyle(
#         'section',
#         fontName='Helvetica-Bold',
#         leading=20,
#         # leading=14,
#         textColor=colors.HexColor("#2563eb")
#     )

#     content_style = ParagraphStyle(
#         'content',
#         fontName='Helvetica',
#         fontSize=10,
#         leading=14,
#         textColor=colors.HexColor("#111827")
#     )

#     # =========================
#     # HEADER
#     # =========================

#     header = Table([
#         [
#             Paragraph(
#                 f"""
#                 <font size='30'><b>MediScan AI</b></font><br/>
#                 <font size='15'>AI Medicine Analysis Report</font>
#                 """,
#                 title_style
#             ),

#             Paragraph(
#                 f"""
#                 <font size='12'>Generated</font><br/>
#                 <font size='16'><b>{datetime.now().strftime('%d %b %Y')}</b></font><br/>
#                 <font size='14'>{datetime.now().strftime('%H:%M:%S')}</font>
#                 """,
#                 subtitle_style
#             )
#         ]
#     # ], colWidths=[360, 150])
#     ], colWidths=[365, 170])

#     header.setStyle(TableStyle([
#         ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0057ff")),
#         ('TEXTCOLOR', (0,0), (-1,-1), colors.white),
#         ('LEFTPADDING', (0,0), (-1,-1), 28),
#         ('RIGHTPADDING', (0,0), (-1,-1), 28),
#         ('TOPPADDING', (0,0), (-1,-1), 14),
#         ('BOTTOMPADDING', (0,0), (-1,-1), 14),
#         ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
#     ]))

#     elements.append(header)
#     elements.append(Spacer(1, 10))

#     # =========================
#     # MEDICINE INFO
#     # =========================

#     info = Table([
#         [
#             Paragraph(
#                 f"<b>Medicine Name</b><br/><br/><font size='18'><b>{medicine}</b></font>",
#                 content_style
#             ),

#             Paragraph(
#                 f"<b>Generic Name</b><br/><br/><font size='18'><b>{generic}</b></font>",
#                 content_style
#             )
#         ]
#     ], colWidths=[HALF_WIDTH, HALF_WIDTH])

#     info.setStyle(TableStyle([
#         ('BACKGROUND', (0,0), (-1,-1), colors.white),
#         ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor("#bfdbfe")),
#         ('LEFTPADDING', (0,0), (-1,-1), 24),
#         ('RIGHTPADDING', (0,0), (-1,-1), 24),
#         ('TOPPADDING', (0,0), (-1,-1), 16),
#         ('BOTTOMPADDING', (0,0), (-1,-1), 16),
#         ('TOPPADDING', (0,0), (-1,-1), 10),
#         ('BOTTOMPADDING', (0,0), (-1,-1), 10),
#         ('ALIGN', (0,0), (-1,-1), 'LEFT'),
#     ]))

#     elements.append(
#         Paragraph(
#             """
#             <para align='center'>
#             <font color='#2563eb' size='13'>
#             <b>MEDICINE INFORMATION</b>
#             </font>
#             </para>
#             """,
#             section_style
#         )
#     )

#     elements.append(Spacer(1, 4))
#     elements.append(info)
#     elements.append(Spacer(1, 8))

#     # =========================
#     # USE
#     # =========================

#     use_card = Table([
#         [
#             Paragraph(
#                 f"<font color='#16a34a'><b>USE</b></font><br/><br/>{use}",
#                 content_style
#             )
#         ]
#     ], colWidths=[FULL_WIDTH])

#     use_card.setStyle(TableStyle([
#         ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f0fdf4")),
#         ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#bbf7d0")),
#         ('LEFTPADDING', (0,0), (-1,-1), 22),
#         ('TOPPADDING', (0,0), (-1,-1), 10),
#         ('BOTTOMPADDING', (0,0), (-1,-1), 10),
#     ]))

#     elements.append(use_card)
#     elements.append(Spacer(1, 6))

#     # =========================
#     # DOSAGE
#     # =========================

#     dosage_card = Table([
#         [
#             Paragraph(
#                 f"<font color='#2563eb'><b>DOSAGE (GENERAL)</b></font><br/><br/>{dosage}",
#                 content_style
#             )
#         ]
#     ], colWidths=[FULL_WIDTH])

#     dosage_card.setStyle(TableStyle([
#         ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#eff6ff")),
#         ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#bfdbfe")),
#         ('LEFTPADDING', (0,0), (-1,-1), 22),
#         ('TOPPADDING', (0,0), (-1,-1), 10),
#         ('BOTTOMPADDING', (0,0), (-1,-1), 10),
#     ]))

#     elements.append(dosage_card)
#     elements.append(Spacer(1, 6))

#     # =========================
#     # SIDE EFFECTS + WARNINGS
#     # =========================

#     side_html = "<br/>".join([f"• {x}" for x in side_effects])
#     warn_html = "<br/>".join([f"• {x}" for x in warnings])

#     double_card = Table([
#         [
#             Paragraph(
#                 f"<font color='#ea580c'><b>SIDE EFFECTS</b></font><br/><br/>{side_html}",
#                 content_style
#             ),

#             Paragraph(
#                 f"<font color='#dc2626'><b>WARNINGS</b></font><br/><br/>{warn_html}",
#                 content_style
#             )
#         ]
#     ], colWidths=[HALF_WIDTH, HALF_WIDTH])

#     double_card.setStyle(TableStyle([
#         ('BACKGROUND', (0,0), (0,0), colors.HexColor("#fff7ed")),
#         ('BACKGROUND', (1,0), (1,0), colors.HexColor("#fef2f2")),
#         ('BOX', (0,0), (0,0), 1.2, colors.HexColor("#fdba74")),
#         ('BOX', (1,0), (1,0), 1.2, colors.HexColor("#fca5a5")),
#         ('LEFTPADDING', (0,0), (-1,-1), 20),
#         ('TOPPADDING', (0,0), (-1,-1), 10),
#         ('BOTTOMPADDING', (0,0), (-1,-1), 10),
#     ]))

#     elements.append(double_card)
#     elements.append(Spacer(1, 8))

#     # =========================
#     # SUBSTITUTES
#     # =========================

#     if generic_substitutes:

#         subs_html = ""

#         for s in generic_substitutes:

#             subs_html += f"""
#             <b>{s.get('name')}</b>
#             &nbsp;&nbsp;&nbsp;
#             <font color='#7c3aed'>
#             Match: {s.get('active_ingredient_match')}%
#             </font><br/>
#             """

#         subs_card = Table([
#             [
#                 Paragraph(
#                     f"<font color='#7c3aed'><b>AFFORDABLE GENERIC SUBSTITUTES</b></font><br/><br/>{subs_html}",
#                     content_style
#                 )
#             ]
#         ], colWidths=[FULL_WIDTH])

#         subs_card.setStyle(TableStyle([
#             ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#faf5ff")),
#             ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#d8b4fe")),
#             ('LEFTPADDING', (0,0), (-1,-1), 22),
#             ('TOPPADDING', (0,0), (-1,-1), 10),
#             ('BOTTOMPADDING', (0,0), (-1,-1), 10),
#         ]))

#         elements.append(subs_card)
#         elements.append(Spacer(1, 8))

#     # =========================
#     # FOOTER
#     # =========================

#     footer = Table([
#         [
#             Paragraph(
#                 """
#                 <b>Disclaimer</b><br/>
#                 Educational project only.<br/>
#                 Not medical advice.<br/>
#                 <font color='#2563eb'>
#                 Always consult a doctor.
#                 </font>
#                 """,
#                 content_style
#             ),

#             Paragraph(
#                 """
#                 Your health is important.<br/>
#                 <font color='#2563eb'>
#                 Stay safe, stay healthy.
#                 </font>
#                 """,
#                 content_style
#             )
#         ]
#     ], colWidths=[HALF_WIDTH, HALF_WIDTH])

#     footer.setStyle(TableStyle([
#         ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
#         ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#bfdbfe")),
#         ('LEFTPADDING', (0,0), (-1,-1), 22),
#         ('TOPPADDING', (0,0), (-1,-1), 10),
#         ('BOTTOMPADDING', (0,0), (-1,-1), 10),
#     ]))

#     elements.append(footer)

#     elements.append(Spacer(1, 4))

#     elements.append(
#         Paragraph(
#             "<para align='center'><font color='#64748b'>© 2026 MediScan AI</font></para>",
#             styles['BodyText']
#         )
#     )

#     doc.build(elements)

#     buffer.seek(0)

#     filename = f"mediscan_report_{medicine.lower()}.pdf"

#     return send_file(
#         buffer,
#         as_attachment=True,
#         download_name=filename,
#         mimetype="application/pdf"
#     )

@app.route("/api/report/pdf", methods=["POST"])
def report_pdf():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "error": "Invalid request body."
        }), 400

    medicine = (data.get("medicine") or "Unknown").upper()
    med = data.get("data") or {}

    generic = med.get("generic_name", "")
    use = med.get("use", "")
    dosage = med.get("dosage", "")
    side_effects = med.get("side_effects", [])
    warnings = med.get("warnings", [])
    generic_substitutes = med.get("generic_substitutes", [])

    from io import BytesIO
    from datetime import datetime

    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle
    )

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    # =========================
    # PDF
    # =========================

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=18,
        bottomMargin=18
    )

    styles = getSampleStyleSheet()
    elements = []

    FULL_WIDTH = 536
    HALF_WIDTH = 268

    # =========================
    # STYLES
    # =========================

    title_style = ParagraphStyle(
        'title',
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.white
    )

    subtitle_style = ParagraphStyle(
        'subtitle',
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=colors.white
    )

    section_style = ParagraphStyle(
        'section',
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor("#2563eb")
    )

    content_style = ParagraphStyle(
        'content',
        fontName='Helvetica',
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#111827")
    )

    # =========================
    # HEADER
    # =========================

    header = Table([
        [
            Paragraph(
                f"""
                <font size='30'><b>MediScan AI</b></font><br/>
                <font size='15'>AI Medicine Analysis Report</font>
                """,
                title_style
            ),

            Paragraph(
                f"""
                <font size='12'>Generated</font><br/>
                <font size='16'><b>{datetime.now().strftime('%d %b %Y')}</b></font><br/>
                <font size='14'>{datetime.now().strftime('%H:%M:%S')}</font>
                """,
                subtitle_style
            )
        ]
    ], colWidths=[365, 170])

    header.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0057ff")),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.white),
        ('LEFTPADDING', (0,0), (-1,-1), 28),
        ('RIGHTPADDING', (0,0), (-1,-1), 28),
        ('TOPPADDING', (0,0), (-1,-1), 18),
        ('BOTTOMPADDING', (0,0), (-1,-1), 18),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))

    elements.append(header)
    elements.append(Spacer(1, 6))

    # =========================
    # CENTER TITLE
    # =========================

    title_table = Table([
        [
            Paragraph(
                """
                <para align='center'>
                <font color='#2563eb' size='17'>
                <b>MEDICINE INFORMATION</b>
                </font>
                </para>
                """,
                section_style
            )
        ]
    ], colWidths=[FULL_WIDTH])

    title_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))

    elements.append(title_table)

    # =========================
    # MEDICINE INFO
    # =========================

    info = Table([
        [
            Paragraph(
                f"""
                <b>Medicine Name</b><br/><br/>
                <font size='20'><b>{medicine}</b></font>
                """,
                content_style
            ),

            Paragraph(
                f"""
                <b>Generic Name</b><br/><br/>
                <font size='18'><b>{generic}</b></font>
                """,
                content_style
            )
        ]
    ], colWidths=[HALF_WIDTH, HALF_WIDTH])

    info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor("#bfdbfe")),
        ('LEFTPADDING', (0,0), (-1,-1), 24),
        ('RIGHTPADDING', (0,0), (-1,-1), 24),
        ('TOPPADDING', (0,0), (-1,-1), 16),
        ('BOTTOMPADDING', (0,0), (-1,-1), 16),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
    ]))

    elements.append(info)
    elements.append(Spacer(1, 5))

    # =========================
    # USE
    # =========================

    use_card = Table([
        [
            Paragraph(
                f"""
                <font color='#16a34a'>
                <b>USE</b>
                </font><br/><br/>
                {use}
                """,
                content_style
            )
        ]
    ], colWidths=[FULL_WIDTH])

    use_card.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f0fdf4")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#bbf7d0")),
        ('LEFTPADDING', (0,0), (-1,-1), 22),
        ('RIGHTPADDING', (0,0), (-1,-1), 22),
        ('TOPPADDING', (0,0), (-1,-1), 14),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))

    elements.append(use_card)
    elements.append(Spacer(1, 5))

    # =========================
    # DOSAGE
    # =========================

    dosage_card = Table([
        [
            Paragraph(
                f"""
                <font color='#2563eb'>
                <b>DOSAGE (GENERAL)</b>
                </font><br/><br/>
                {dosage}
                """,
                content_style
            )
        ]
    ], colWidths=[FULL_WIDTH])

    dosage_card.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#eff6ff")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#bfdbfe")),
        ('LEFTPADDING', (0,0), (-1,-1), 22),
        ('RIGHTPADDING', (0,0), (-1,-1), 22),
        ('TOPPADDING', (0,0), (-1,-1), 14),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))

    elements.append(dosage_card)
    elements.append(Spacer(1, 5))

    # =========================
    # SIDE EFFECTS + WARNINGS
    # =========================

    side_html = "<br/>".join([f"• {x}" for x in side_effects])
    warn_html = "<br/>".join([f"• {x}" for x in warnings])

    double_card = Table([
        [
            Paragraph(
                f"""
                <font color='#ea580c'>
                <b>SIDE EFFECTS</b>
                </font><br/><br/>
                {side_html}
                """,
                content_style
            ),

            Paragraph(
                f"""
                <font color='#dc2626'>
                <b>WARNINGS</b>
                </font><br/><br/>
                {warn_html}
                """,
                content_style
            )
        ]
    ], colWidths=[HALF_WIDTH, HALF_WIDTH])

    double_card.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), colors.HexColor("#fff7ed")),
        ('BACKGROUND', (1,0), (1,0), colors.HexColor("#fef2f2")),

        ('BOX', (0,0), (0,0), 1.2, colors.HexColor("#fdba74")),
        ('BOX', (1,0), (1,0), 1.2, colors.HexColor("#fca5a5")),

        ('LEFTPADDING', (0,0), (-1,-1), 20),
        ('RIGHTPADDING', (0,0), (-1,-1), 20),

        ('TOPPADDING', (0,0), (-1,-1), 14),
        ('BOTTOMPADDING', (0,0), (-1,-1), 14),

        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))

    elements.append(double_card)
    elements.append(Spacer(1, 5))

    # =========================
    # GENERIC SUBSTITUTES
    # =========================

    if generic_substitutes:

        subs_html = ""

        for s in generic_substitutes:

            subs_html += f"""
            <b>{s.get('name')}</b>
            &nbsp;&nbsp;&nbsp;
            <font color='#7c3aed'>
            Match: {s.get('active_ingredient_match')}%
            </font><br/><br/>
            """

        subs_card = Table([
            [
                Paragraph(
                    f"""
                    <font color='#7c3aed'>
                    <b>AFFORDABLE GENERIC SUBSTITUTES</b>
                    </font><br/><br/>
                    {subs_html}
                    """,
                    content_style
                )
            ]
        ], colWidths=[FULL_WIDTH])

        subs_card.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#faf5ff")),
            ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#d8b4fe")),
            ('LEFTPADDING', (0,0), (-1,-1), 22),
            ('RIGHTPADDING', (0,0), (-1,-1), 22),
            ('TOPPADDING', (0,0), (-1,-1), 14),
            ('BOTTOMPADDING', (0,0), (-1,-1), 14),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))

        elements.append(subs_card)
        elements.append(Spacer(1, 5))

    # =========================
    # FOOTER
    # =========================

    footer = Table([
        [
            Paragraph(
                """
                <b>Disclaimer</b><br/>
                Educational project only.<br/>
                Not medical advice.<br/>
                <font color='#2563eb'>
                Always consult a doctor.
                </font>
                """,
                content_style
            ),

            Paragraph(
                """
                Your health is important.<br/>
                <font color='#2563eb'>
                Stay safe, stay healthy.
                </font>
                """,
                content_style
            )
        ]
    ], colWidths=[HALF_WIDTH, HALF_WIDTH])

    footer.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#bfdbfe")),
        ('LEFTPADDING', (0,0), (-1,-1), 22),
        ('RIGHTPADDING', (0,0), (-1,-1), 22),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))

    elements.append(footer)

    elements.append(Spacer(1, 4))

    elements.append(
        Paragraph(
            """
            <para align='center'>
            <font color='#64748b'>
            © 2026 MediScan AI
            </font>
            </para>
            """,
            styles['BodyText']
        )
    )

    # =========================
    # BUILD PDF
    # =========================

    doc.build(elements)

    buffer.seek(0)

    filename = f"mediscan_report_{medicine.lower()}.pdf"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )

@app.route("/api/history/clear", methods=["POST"])
@login_required
def clear_history():
    db.session.query(History).filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "History cleared successfully."})
@app.route("/api/analytics/clear", methods=["POST"])
@login_required
def clear_analytics():
    db.session.query(Analytics).filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "Analytics cleared successfully."})
@app.route("/api/scan-medicine", methods=["POST"])
def scan_medicine():
    if client is None:
        return jsonify({"success": False, "error": "Groq API key missing. Add GROQ_API_KEY in .env"})

    data = request.get_json()
    image_b64 = (data.get("image") or "").strip()
    if not image_b64:
        return jsonify({"success": False, "error": "No image provided."})

    # strip data-url prefix if present
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    system_prompt = """
You are MediScan AI OCR. Extract the primary generic active ingredient name from the medicine strip or prescription image.

Rules:
- Return ONLY the main active ingredient / generic medicine name.
- Ignore batch numbers, expiry dates, manufacturer addresses, dosage numbers, and brand names.
- If the image is unreadable or unclear, set extracted_medicine_name to null.

Return STRICT JSON only:
{
  "extracted_medicine_name": "...",
  "confidence": "High|Medium|Low",
  "note": "..."
}
"""

    try:
        completion = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract the medicine name from this image. Return JSON only."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=200,
        )

        ocr_text = completion.choices[0].message.content.strip()
        ocr_json = json.loads(ocr_text)
        extracted = (ocr_json.get("extracted_medicine_name") or "").strip()

        if not extracted:
            return jsonify({"success": False, "error": "Image unclear. Please capture a well-lit photo of the medicine strip text."})

        med_data, source, err = get_medicine_data(extracted)
        if err:
            return jsonify({"success": False, "error": err})

        update_analytics(extracted.lower())
        add_to_history(extracted, "ocr-" + source)

        return jsonify({
            "success": True,
            "source": source,
            "medicine": extracted.lower(),
            "data": med_data,
            "note": f"Scanned via OCR (confidence: {ocr_json.get('confidence', '?')}). AI-generated info (educational only)."
        })

    except (json.JSONDecodeError, KeyError):
        return jsonify({"success": False, "error": "Image unclear. Please capture a well-lit photo of the medicine strip text."})
    except Exception:
        return jsonify({"success": False, "error": "OCR scan failed. Try again."})


@app.route("/assistant")
def assistant_page():
    return render_template("assistant.html")
@app.route("/api/assistant", methods=["POST"])
def assistant_api():
    data = request.get_json() or {}
    query = (data.get("query") or "").strip()[:500]

    if not query:
        return jsonify({"success": False, "error": "Empty query."})

    if client is None:
        return jsonify({"success": False, "error": "Groq API key missing. Add GROQ_API_KEY in .env"})

    system_prompt = """
You are MediScan AI Assistant.

Rules:
- Be helpful and friendly.
- Educational health information only.
- Do NOT diagnose disease.
- Do NOT provide prescriptions or exact dosages for specific people.
- If user asks serious/urgent symptoms, advise to consult doctor/emergency services.
- Keep answers simple and structured with bullet points when useful.
"""

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": query},
            ],
            temperature=0.3,
            max_tokens=700
        )

        answer = completion.choices[0].message.content.strip()
        return jsonify({"success": True, "answer": answer})

    except Exception as e:
        return jsonify({
        "success": False,
        "error": "Groq AI error. Try again.",
        "details": str(e)
    }), 500

@app.route("/download-report", methods=["POST"])
def download_report():
    data = request.get_json() or {}
    symptoms = data.get("symptoms", "")
    extracted_text = data.get("extracted_text", "")
    ai_insights = data.get("ai_insights", "")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=50, leftMargin=50,
        topMargin=50, bottomMargin=50
    )

    styles = getSampleStyleSheet()
    
    # Custom Styles
    header_style = ParagraphStyle(
        name='HeaderStyle',
        parent=styles['Heading1'],
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=14
    )
    
    subhead_style = ParagraphStyle(
        name='SubheadStyle',
        parent=styles['Heading2'],
        textColor=colors.HexColor('#0d9488'),
        spaceAfter=10,
        spaceBefore=14
    )
    
    body_style = ParagraphStyle(
        name='BodyStyle',
        parent=styles['Normal'],
        textColor=colors.HexColor('#374151'),
        fontSize=11,
        leading=15,
        spaceAfter=10
    )
    
    disclaimer_style = ParagraphStyle(
        name='DisclaimerStyle',
        parent=styles['Italic'],
        textColor=colors.HexColor('#6b7280'),
        fontSize=9,
        alignment=1,
        spaceBefore=30
    )

    elements = []

    # Title
    elements.append(Paragraph("MediScan AI Health Report", header_style))
    elements.append(Spacer(1, 4))

    def format_text(text):
        if not text:
            return "N/A"
        return str(text).replace('\n', '<br/>')

    # Symptoms
    elements.append(Paragraph("Patient Symptoms", subhead_style))
    elements.append(Paragraph(format_text(symptoms), body_style))

    # Extracted Text
    elements.append(Paragraph("Extracted Text (Medical Reports)", subhead_style))
    elements.append(Paragraph(format_text(extracted_text), body_style))

    # AI Insights
    elements.append(Paragraph("AI Health Insights", subhead_style))
    elements.append(Paragraph(format_text(ai_insights), body_style))

    # Disclaimer
    elements.append(Spacer(1, 8))
    disclaimer_text = "Disclaimer: This project is for educational and research purposes only and does not replace professional medical advice."
    elements.append(Paragraph(disclaimer_text, disclaimer_style))

    doc.build(elements)
    
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="Medicsan_AI_Health_Report.pdf",
        mimetype="application/pdf"
    )

@app.route("/api/upload-report", methods=["POST"])
@login_required
def upload_report():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected."}), 400

    filename = file.filename.lower()
    
    try:
        if filename.endswith('.pdf'):
            import PyPDF2
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
            
            if not text.strip():
                return jsonify({"success": False, "error": "Could not extract text from PDF. It might be scanned/image-based."}), 400

            system_prompt = """
You are MediScan AI, an educational medical assistant.
Analyze the following lab report/medical document text and provide a simple, easy-to-understand summary.
Mention any abnormal values or key findings.
Do NOT diagnose or provide medical advice. Always recommend consulting a doctor.

Return JSON ONLY:
{
  "summary": "...",
  "key_findings": ["..."],
  "abnormal_values": [{"test": "...", "value": "...", "reference_range": "..."}],
  "note": "..."
}
"""
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": text[:4000]}
                ],
                temperature=0.2,
                max_tokens=800
            )
            result = json.loads(completion.choices[0].message.content.strip())
            return jsonify({"success": True, "analysis": result})

        elif filename.endswith(('.png', '.jpg', '.jpeg')):
            import base64
            image_b64 = base64.b64encode(file.read()).decode('utf-8')
            
            system_prompt = """
You are MediScan AI, an educational medical assistant.
Analyze the following image of a lab report/medical document and provide a simple, easy-to-understand summary.
Mention any abnormal values or key findings.
Do NOT diagnose or provide medical advice. Always recommend consulting a doctor.

Return JSON ONLY:
{
  "summary": "...",
  "key_findings": ["..."],
  "abnormal_values": [{"test": "...", "value": "...", "reference_range": "..."}],
  "note": "..."
}
"""
            completion = client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze this medical report image. Return JSON only."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=800
            )
            result = json.loads(completion.choices[0].message.content.strip())
            return jsonify({"success": True, "analysis": result})
            
        else:
            return jsonify({"success": False, "error": "Unsupported file format. Please upload PDF, PNG, JPG, or JPEG."}), 400

    except json.JSONDecodeError:
         return jsonify({"success": False, "error": "Failed to parse AI response. Try again."}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Error processing file: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
