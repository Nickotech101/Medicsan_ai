@app.route("/api/suggestions", methods=["GET"])
def suggestions():

    query = request.args.get("q", "").strip().lower()

    history = load_json(HISTORY_PATH, [])
    favs = load_json(FAV_PATH, [])

    hist_names = [h["query"] for h in history if "query" in h]
    fav_names = [f.get("medicine", "") for f in favs if f.get("medicine")]

    suggestions = []

    for medicine in POPULAR_MEDICINES:
        if medicine.lower().startswith(query):
            suggestions.append(medicine)

    for medicine in medicine_cache:
        if medicine.lower().startswith(query):
            suggestions.append(medicine)

    for x in (fav_names + hist_names + list(MED_DB.keys())):
        if x and x.lower().startswith(query):
            suggestions.append(x)

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

    suggestions = list(dict.fromkeys(suggestions))

    return jsonify({
        "suggestions": suggestions[:10]
    })


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

        update_analytics(medicine)

        if medicine in MED_DB:
            add_to_history(medicine, "database")
            med_data = dict(MED_DB[medicine])

            med_data.setdefault(
                "food_interactions",
                ["No specific food interactions documented."]
            )

            med_data.setdefault(
                "lifestyle_interactions",
                ["No specific lifestyle restrictions documented."]
            )

            med_data.setdefault(
                "pediatric_caution",
                "Consult a pediatrician for safe dosing."
            )

            med_data.setdefault(
                "geriatric_caution",
                "Consult a doctor if unsure."
            )

            return jsonify({
                "success": True,
                "source": "database",
                "medicine": medicine,
                "data": med_data
            }), 200

        for key in MED_DB:
            if medicine in key or key in medicine:

                add_to_history(key, "database")

                med_data = dict(MED_DB[key])

                return jsonify({
                    "success": True,
                    "source": "database",
                    "medicine": key,
                    "data": med_data,
                    "note": "Closest match found in database."
                }), 200

        ai_data, err = groq_medicine_lookup(medicine)

        if err:
            return jsonify({
                "success": False,
                "error": err
            }), 500

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

        verdict = None

        c = get_client()

        if c:
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
                completion = c.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": system_prompt.strip()},
                        {"role": "user", "content": user_prompt.strip()},
                    ],
                    temperature=0.2,
                    max_tokens=600,
                )

                verdict = json.loads(
                    completion.choices[0].message.content.strip()
                )

            except Exception:
                verdict = {
                    "summary": "AI verdict failed.",
                    "safer_for_stomach": "depends",
                    "key_differences": [],
                    "warning": "Consult doctor."
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

        c = get_client()

        if c is None:
            return jsonify({
                "success": False,
                "error": "Groq API key missing."
            }), 500

        system_prompt = """
You are MediScan AI, an educational medicine interaction checker.
Return STRICT JSON only.
"""

        user_prompt = f"""
Check interaction between:

Medicine A: {med_a}
Medicine B: {med_b}
"""

        completion = c.chat.completions.create(
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


@app.route("/symptom")
def symptom_page():
    return render_template("symptom.html")


@app.route("/api/symptom-check", methods=["POST"])
def symptom_check():

    data = request.get_json()

    symptoms = (data.get("symptoms") or "").strip()

    if not symptoms:
        return jsonify({
            "success": False,
            "error": "Please describe your symptoms."
        })

    c = get_client()

    if c is None:
        return jsonify({
            "success": False,
            "error": "Groq API key missing."
        })

    system_prompt = """
You are MediScan AI, an educational symptom analysis assistant.

Return STRICT JSON only:

{
  "possible_conditions": [],
  "suggested_medicines": [],
  "home_remedies": [],
  "warning": ""
}
"""

    user_prompt = f"""
Patient symptoms: {symptoms}

Return JSON only.
"""

    try:
        completion = c.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            temperature=0.4,
            max_tokens=900,
        )

        text = completion.choices[0].message.content.strip()

        result = json.loads(text)

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception:
        return jsonify({
            "success": False,
            "error": "AI error. Please try again."
        })