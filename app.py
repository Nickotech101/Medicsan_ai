from flask import Flask, render_template, request, jsonify, send_file
import json
import os
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
from io import BytesIO
import threading

file_lock = threading.Lock()

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__)

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
    if not query:
        return

    history = load_json(HISTORY_PATH, [])
    history = [h for h in history if h.get("query", "").lower() != query.lower()]

    history.insert(0, {
        "query": query,
        "source": source,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    save_json(HISTORY_PATH, history[:10])


def update_analytics(query: str):
    query = query.strip().lower()
    if not query:
        return
    analytics = load_json(ANALYTICS_PATH, {})
    analytics[query] = analytics.get(query, 0) + 1
    save_json(ANALYTICS_PATH, analytics)


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

Return STRICT JSON only in this schema:

{
  "generic_name": "...",
  "use": "...",
  "dosage": "...",
  "side_effects": ["..."],
  "warnings": ["..."],
  "food_interactions": ["..."],
  "lifestyle_interactions": ["..."]
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
        required = ["generic_name", "use", "dosage", "side_effects", "warnings", "food_interactions", "lifestyle_interactions"]
        for k in required:
            if k not in data:
                return None, "Groq response missing fields."
        return data, None
    except Exception:
        return None, "Groq returned invalid JSON. Try again."


# ================= ROUTES =================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@app.route("/api/suggestions", methods=["GET"])
def suggestions():
    history = load_json(HISTORY_PATH, [])
    favs = load_json(FAV_PATH, [])
    hist_names = [h["query"] for h in history if "query" in h]
    fav_names = [f.get("medicine", "") for f in favs if f.get("medicine")]

    db_names = list(MED_DB.keys())

    combined = []
    for x in (fav_names + hist_names + db_names):
        if x and x.lower() not in [c.lower() for c in combined]:
            combined.append(x)

    return jsonify({"success": True, "suggestions": combined[:40]})


@app.route("/api/history", methods=["GET"])
def history_api():
    history = load_json(HISTORY_PATH, [])
    return jsonify({"success": True, "history": history})


@app.route("/api/favorites", methods=["GET"])
def favorites_api():
    favs = load_json(FAV_PATH, [])
    return jsonify({"success": True, "favorites": favs})


@app.route("/api/favorites/toggle", methods=["POST"])
def favorites_toggle():
    data = request.get_json()
    medicine = (data.get("medicine") or "").strip().lower()
    generic_name = (data.get("generic_name") or "").strip()

    if not medicine:
        return jsonify({"success": False, "error": "Medicine missing."})

    favs = load_json(FAV_PATH, [])

    existing = next((f for f in favs if f.get("medicine", "").lower() == medicine), None)
    if existing:
        favs = [f for f in favs if f.get("medicine", "").lower() != medicine]
        save_json(FAV_PATH, favs)
        return jsonify({"success": True, "favorited": False})

    favs.insert(0, {
        "medicine": medicine,
        "generic_name": generic_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    favs = favs[:20]
    save_json(FAV_PATH, favs)
    return jsonify({"success": True, "favorited": True})


@app.route("/api/analytics", methods=["GET"])
def analytics_api():
    analytics = load_json(ANALYTICS_PATH, {})
    # Top 10
    top = sorted(analytics.items(), key=lambda x: x[1], reverse=True)[:10]
    return jsonify({"success": True, "top": top, "all": analytics})


@app.route("/api/medicine", methods=["POST"])
def medicine_info():
    data = request.get_json() or {}
    medicine = (data.get("medicine") or "").strip().lower()[:200]

    if not medicine:
        return jsonify({"success": False, "error": "Please enter a medicine name."})

    medicine = " ".join(medicine.split())

    # analytics
    update_analytics(medicine)

    # 1) exact match
    if medicine in MED_DB:
        add_to_history(medicine, "database")
        med_data = dict(MED_DB[medicine])
        med_data.setdefault("food_interactions", ["No specific food interactions documented. Consult a pharmacist if unsure."])
        med_data.setdefault("lifestyle_interactions", ["No specific lifestyle restrictions documented."])
        return jsonify({"success": True, "source": "database", "medicine": medicine, "data": med_data})

    # 2) partial match
    for key in MED_DB:
        if medicine in key or key in medicine:
            add_to_history(key, "database")
            med_data = dict(MED_DB[key])
            med_data.setdefault("food_interactions", ["No specific food interactions documented. Consult a pharmacist if unsure."])
            med_data.setdefault("lifestyle_interactions", ["No specific lifestyle restrictions documented."])
            return jsonify({
                "success": True,
                "source": "database",
                "medicine": key,
                "data": med_data,
                "note": "Closest match found in database."
            })

    # 3) Groq
    ai_data, err = groq_medicine_lookup(medicine)
    if err:
        return jsonify({"success": False, "error": err})

    add_to_history(medicine, "groq")
    return jsonify({
        "success": True,
        "source": "groq",
        "medicine": medicine,
        "data": ai_data,
        "note": "AI-generated info (educational only)."
    })
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
    data = request.get_json()

    med_a = (data.get("medicineA") or "").strip()
    med_b = (data.get("medicineB") or "").strip()

    if not med_a or not med_b:
        return jsonify({"success": False, "error": "Please enter both medicine names."})

    a_data, a_source, err_a = get_medicine_data(med_a)
    if err_a:
        return jsonify({"success": False, "error": f"Medicine A error: {err_a}"})

    b_data, b_source, err_b = get_medicine_data(med_b)
    if err_b:
        return jsonify({"success": False, "error": f"Medicine B error: {err_b}"})

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
        "medicineA": {"name": med_a, "source": a_source, "data": a_data},
        "medicineB": {"name": med_b, "source": b_source, "data": b_data},
        "verdict": verdict
    })
@app.route("/interaction")
def interaction_page():
    return render_template("interaction.html")
@app.route("/api/interaction", methods=["POST"])
def medicine_interaction():
    data = request.get_json()

    med_a = (data.get("medicineA") or "").strip()
    med_b = (data.get("medicineB") or "").strip()

    if not med_a or not med_b:
        return jsonify({"success": False, "error": "Please enter both medicine names."})

    if client is None:
        return jsonify({"success": False, "error": "Groq API key missing. Add GROQ_API_KEY in .env"})

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

    try:
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

        return jsonify({"success": True, "data": result})

    except Exception:
        return jsonify({
            "success": True,
            "data": {
                "risk_level": "unknown",
                "interaction_summary": "AI could not confidently evaluate this interaction. Try again.",
                "what_to_avoid": [],
                "warning_signs": [],
                "final_note": "Educational only. Consult a doctor/pharmacist."
            }
        })
@app.route("/api/favorites/clear", methods=["POST"])
def clear_favorites():
    save_json(FAV_PATH, [])
    return jsonify({"success": True, "message": "Favorites cleared successfully."})


@app.route("/api/report/pdf", methods=["POST"])
def report_pdf():
    """
    Creates a PDF report for current medicine response.
    """
    data = request.get_json()
    medicine = (data.get("medicine") or "Unknown").upper()
    source = (data.get("source") or "Unknown")
    med = data.get("data") or {}

    generic = med.get("generic_name", "")
    use = med.get("use", "")
    dosage = med.get("dosage", "")
    side_effects = med.get("side_effects", [])
    warnings = med.get("warnings", [])

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, "MediScan AI - Medicine Report")

    y -= 30
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    y -= 25
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, f"Medicine: {medicine}")

    y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Generic Name: {generic}")
    y -= 18
    c.drawString(50, y, f"Source: {source}")

    def draw_block(title, content):
        nonlocal y
        y -= 28
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, title)
        y -= 16
        c.setFont("Helvetica", 11)

        # wrap text
        for line in str(content).split("\n"):
            words = line.split(" ")
            current = ""
            for w in words:
                if len(current + " " + w) > 85:
                    c.drawString(55, y, current.strip())
                    y -= 14
                    current = w
                else:
                    current += " " + w
            if current.strip():
                c.drawString(55, y, current.strip())
                y -= 14

    draw_block("Use", use)
    draw_block("Dosage (General)", dosage)

    draw_block("Side Effects", "- " + "\n- ".join(side_effects) if side_effects else "Not available")
    draw_block("Warnings", "- " + "\n- ".join(warnings) if warnings else "Not available")

    y -= 25
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(50, y, "Disclaimer: Educational project only. Not medical advice. Always consult a doctor.")

    c.showPage()
    c.save()

    buffer.seek(0)

    filename = f"mediscan_report_{medicine.lower()}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")

@app.route("/api/history/clear", methods=["POST"])
def clear_history():
    # Clear history
    save_json(HISTORY_PATH, [])
    return jsonify({"success": True, "message": "History cleared successfully."})
@app.route("/api/analytics/clear", methods=["POST"])
def clear_analytics():
    save_json(ANALYTICS_PATH, {})
    return jsonify({"success": True, "message": "Analytics cleared successfully."})
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
        return jsonify({"success": False, "error": "Groq AI error. Try again."})

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
    elements.append(Spacer(1, 12))

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
    elements.append(Spacer(1, 20))
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

if __name__ == "__main__":
    app.run(debug=True)
