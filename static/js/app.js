// ============================
// MediScan AI - app.js (FULL)
// ============================
async function safeApiFetch(url, options = {}) {
  const response = await fetch(url, options);

  const contentType = response.headers.get("content-type") || "";

  if (!contentType.includes("application/json")) {
    throw new Error(`Expected JSON but got ${contentType}`);
  }

  return await response.json();
}
const btn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const input = document.getElementById("medicineInput");
const micBtn = document.getElementById("micBtn");

const statusText = document.getElementById("status");
const loader = document.getElementById("loader");
const clearFavoritesBtn = document.getElementById("clearFavoritesBtn");


const resultBox = document.getElementById("result");
const medTitle = document.getElementById("medTitle");
const note = document.getElementById("note");
const sourceBadge = document.getElementById("sourceBadge");

const useEl = document.getElementById("use");
const dosageEl = document.getElementById("dosage");
const sideEffectsEl = document.getElementById("sideEffects");
const warningsEl = document.getElementById("warnings");
const foodInteractionsEl = document.getElementById("foodInteractions");
const lifestyleInteractionsEl = document.getElementById("lifestyleInteractions");
const pediatricCautionEl = document.getElementById("pediatricCaution");
const geriatricCautionEl = document.getElementById("geriatricCaution");
const aiSummary = document.getElementById("aiSummary");

const historyList = document.getElementById("historyList");
const favoritesList = document.getElementById("favoritesList");

const datalist = document.getElementById("medicineList");

const copyBtn = document.getElementById("copyBtn");
const favBtn = document.getElementById("favBtn");
const pdfBtn = document.getElementById("pdfBtn");
const shareBtn = document.getElementById("shareBtn");
const substitutesBox = document.getElementById("substitutesBox");
const substitutesList = document.getElementById("substitutesList");

const scanBtn = document.getElementById("scanBtn");
const scanFileInput = document.getElementById("scanFileInput");
const scanCanvas = document.getElementById("scanCanvas");
const scanPreview = document.getElementById("scanPreview");
const scanThumb = document.getElementById("scanThumb");
const scanConfirmBtn = document.getElementById("scanConfirmBtn");
const scanClearBtn = document.getElementById("scanClearBtn");
const exportPdfBtn = document.getElementById("exportPdfBtn");

// Clear history button exists in HTML
const clearHistoryBtn = document.getElementById("clearHistoryBtn");

let lastResult = null;

// ============================
// Helpers
// ============================
function setStatus(msg, ok = true) {
  statusText.textContent = msg;
  statusText.style.color = ok ? "#9fffa8" : "#ff9f9f";
}

function showLoader() {
  loader.classList.remove("hidden");
}

function hideLoader() {
  loader.classList.add("hidden");
}

function setLoading(isLoading) {
  if (isLoading) {
    showLoader();
    btn.disabled = true;
    clearBtn.disabled = true;
    if (clearHistoryBtn) clearHistoryBtn.disabled = true;
    if (copyBtn) copyBtn.disabled = true;
    if (favBtn) favBtn.disabled = true;
    if (pdfBtn) pdfBtn.disabled = true;
    if (shareBtn) shareBtn.disabled = true;
    if (scanBtn) scanBtn.disabled = true;
    if (scanConfirmBtn) scanConfirmBtn.disabled = true;
    if (exportPdfBtn) exportPdfBtn.disabled = true;
  } else {
    hideLoader();
    btn.disabled = false;
    clearBtn.disabled = false;
    if (clearHistoryBtn) clearHistoryBtn.disabled = false;
    if (copyBtn) copyBtn.disabled = false;
    if (favBtn) favBtn.disabled = false;
    if (pdfBtn) pdfBtn.disabled = false;
    if (shareBtn) shareBtn.disabled = false;
    if (scanBtn) scanBtn.disabled = false;
    if (scanConfirmBtn) scanConfirmBtn.disabled = false;
    if (exportPdfBtn) exportPdfBtn.disabled = false;
  }
}

function renderList(listEl, items) {
  listEl.innerHTML = "";
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    listEl.appendChild(li);
  });
}

function buildCopyText(medName, med, src) {
  let txt = `
MediScan AI Report
-----------------------
Medicine: ${medName}
Source: ${src}

Generic Name: ${med.generic_name}

Use:
${med.use}

Dosage (general):
${med.dosage}

Side Effects:
- ${(med.side_effects || []).join("\n- ")}

Warnings:
- ${(med.warnings || []).join("\n- ")}`;

  const subs = med.generic_substitutes || [];
  if (subs.length > 0) {
    txt += `\n\nAffordable Generic Substitutes:\n`;
    subs.forEach(s => { txt += `- ${s.name} (Match: ${s.active_ingredient_match}%)\n`; });
  }

  txt += `\n\nDisclaimer: Educational only. Consult a doctor.`;
  return txt.trim();
}

// ============================
// API loads
// ============================
async function loadSuggestions() {
  try {
    const res = await fetch("/api/suggestions");
    const data = await res.json();
    if (!data.success) return;

    datalist.innerHTML = "";
    (data.suggestions || []).forEach((s) => {
      const option = document.createElement("option");
      option.value = s;
      datalist.appendChild(option);
    });
  } catch (e) {
    // ignore
  }
}

async function loadHistory() {
  try {
    const data = await safeApiFetch("/api/history/clear", {
  method: "POST"
});
    if (!data.success) return;

    const items = data.history || [];
    historyList.innerHTML = "";

    if (items.length === 0) {
      historyList.textContent = "No searches yet.";
      return;
    }

    items.forEach((h) => {
      const div = document.createElement("div");
      div.className = "history-item";
      div.textContent = h.query;

      div.addEventListener("click", () => {
        input.value = h.query;
        fetchMedicine();
      });

      historyList.appendChild(div);
    });
  } catch (e) {
    historyList.textContent = "History load failed.";
  }
}

async function loadFavorites() {
  try {
    const data = await safeApiFetch("/api/favorites");
    if (!data.success) return;

    const favs = data.favorites || [];
    favoritesList.innerHTML = "";

    if (favs.length === 0) {
      favoritesList.textContent = "No favorites yet.";
      return;
    }

    favs.forEach((f) => {
      const div = document.createElement("div");
      div.className = "history-item";
      div.textContent = f.medicine;

      div.addEventListener("click", () => {
        input.value = f.medicine;
        fetchMedicine();
      });

      favoritesList.appendChild(div);
    });
  } catch (e) {
    favoritesList.textContent = "Favorites load failed.";
  }
}

// ============================
// Main function
// ============================
async function fetchMedicine() {
  const medicine = input.value.trim();
  resultBox.classList.add("hidden");

  if (!medicine) {
    setStatus("❌ Please enter a medicine name.", false);
    return;
  }

  setLoading(true);
  setStatus("⏳ Generating medicine info...");

  try {
    const res = await fetch("/api/medicine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ medicine }),
    });

    const data = await res.json();

    if (!data.success) {
      setStatus("❌ " + data.error, false);
      setLoading(false);
      return;
    }

    lastResult = data;

    const med = data.data;
    const sourceTag = data.source === "groq" ? "🤖 Groq AI" : "📦 Database";

    medTitle.textContent = `💊 ${data.medicine.toUpperCase()} (${med.generic_name})`;
    sourceBadge.textContent = sourceTag;
    note.textContent = data.note ? "✅ " + data.note : "";

    useEl.textContent = med.use;
    dosageEl.textContent = med.dosage;

    renderList(sideEffectsEl, med.side_effects);
    renderList(warningsEl, med.warnings);
    renderList(foodInteractionsEl, med.food_interactions || []);
    renderList(lifestyleInteractionsEl, med.lifestyle_interactions || []);

    if (pediatricCautionEl) {
      pediatricCautionEl.textContent = med.pediatric_caution || "No specific cautions documented.";
    }
    if (geriatricCautionEl) {
      geriatricCautionEl.textContent = med.geriatric_caution || "No specific cautions documented.";
    }

    aiSummary.textContent =
      `Use: ${med.use} ` +
      `Side effects: ${(med.side_effects || []).slice(0, 2).join(", ")}. ` +
      `Warnings: consult a doctor if unsure.`;

    // Generic Substitutes
    const subs = med.generic_substitutes || [];
    substitutesList.innerHTML = "";
    if (subs.length > 0) {
      subs.forEach(s => {
        const chip = document.createElement("div");
        chip.className = "sub-chip";
        chip.innerHTML = `<span>${s.name}</span><span class="match-badge">${s.active_ingredient_match}% match</span>`;
        substitutesList.appendChild(chip);
      });
      substitutesBox.classList.remove("hidden");
    } else {
      substitutesBox.classList.add("hidden");
    }

    // ✅ COPY
    copyBtn.onclick = async () => {
      try {
        const txt = buildCopyText(data.medicine, med, sourceTag);
        await navigator.clipboard.writeText(txt);
        setStatus("✅ Copied report to clipboard!");
      } catch {
        setStatus("❌ Copy failed. Browser denied permission.", false);
      }
    };

    // ✅ FAVORITES
    favBtn.onclick = async () => {
      try {
        setLoading(true);
        setStatus("⏳ Updating favorites...");

        const r = await fetch("/api/favorites/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            medicine: data.medicine,
            generic_name: med.generic_name,
          }),
        });

        const out = await r.json();

        if (out.success) {
          setStatus(out.favorited ? "⭐ Added to favorites!" : "❌ Removed from favorites!");
          loadFavorites();
          loadSuggestions();
        } else {
          setStatus("❌ Favorite action failed.", false);
        }

        setLoading(false);
      } catch (e) {
        setStatus("❌ Error updating favorites.", false);
        setLoading(false);
      }
    };

    // ✅ PDF DOWNLOAD
    pdfBtn.onclick = async () => {
      try {
        setLoading(true);
        setStatus("⏳ Creating PDF report...");

        const pdfRes = await fetch("/api/report/pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(lastResult),
        });

        const blob = await pdfRes.blob();
        const url = window.URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = `mediscan_report_${data.medicine}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();

        window.URL.revokeObjectURL(url);

        setStatus("✅ PDF downloaded!");
        setLoading(false);
      } catch (e) {
        setStatus("❌ PDF download failed.", false);
        setLoading(false);
      }
    };

    // ✅ SHARE (WhatsApp)
    shareBtn.onclick = async () => {
      try {
        const txt = buildCopyText(data.medicine, med, sourceTag);
        await navigator.clipboard.writeText(txt);
        setStatus("✅ Report copied! Opening WhatsApp...");

        const whatsapp = `https://wa.me/?text=${encodeURIComponent(txt)}`;
        window.open(whatsapp, "_blank");
      } catch {
        setStatus("❌ Share failed. Clipboard blocked by browser.", false);
      }
    };

    resultBox.classList.remove("hidden");
    setStatus("✅ Done! See results below.");

    // refresh lists
    loadHistory();
    loadFavorites();
    loadSuggestions();

    setLoading(false);
  } catch (err) {
    console.error(err);
    setStatus("❌ Server error. Try again.", false);
    setLoading(false);
  }
}

// ============================
// Events
// ============================

if (clearFavoritesBtn) {
  clearFavoritesBtn.addEventListener("click", async () => {
    try {
      setLoading(true);
      setStatus("⏳ Clearing favorites...");

      const res = await fetch("/api/favorites/clear", { method: "POST" });
      const data = await res.json();

      if (data.success) {
        setStatus("✅ Favorites cleared!");
        loadFavorites();
        loadSuggestions();
      } else {
        setStatus("❌ Failed to clear favorites.", false);
      }

      setLoading(false);
    } catch (err) {
      setStatus("❌ Server error clearing favorites.", false);
      setLoading(false);
    }
  });
}

btn.addEventListener("click", fetchMedicine);

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") fetchMedicine();
});

clearBtn.addEventListener("click", () => {
  input.value = "";
  resultBox.classList.add("hidden");
  setStatus("✅ Cleared");
    setTimeout(() => {
    setStatus(""); // ← dismiss the message after 2.5s
  }, 1500);
  substitutesBox.classList.add("hidden");
  setStatus("✅ Cleared.");
});

if (exportPdfBtn) {
  exportPdfBtn.addEventListener("click", async () => {
    try {
      const symptomsInput = document.getElementById("symptoms-input");
      const extractedTextBox = document.getElementById("extracted-text-box");
      const insightTextContainer = document.getElementById("insight-text-container");
      
      const symptoms = symptomsInput ? (symptomsInput.value || symptomsInput.innerText) : "";
      const extracted_text = extractedTextBox ? (extractedTextBox.value || extractedTextBox.innerText) : "";
      const ai_insights = insightTextContainer ? (insightTextContainer.value || insightTextContainer.innerText) : "";
      
      if (!symptoms && !extracted_text && !ai_insights) {
        alert("No data available to export. Please ensure the inputs are filled.");
        return;
      }

      setLoading(true);
      setStatus("⏳ Generating AI Insights PDF...");

      const pdfRes = await fetch("/download-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symptoms: symptoms,
          extracted_text: extracted_text,
          ai_insights: ai_insights
        })
      });

      if (!pdfRes.ok) {
        throw new Error("Failed to generate PDF");
      }

      const blob = await pdfRes.blob();
      const url = window.URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = url;
      a.download = "Medicsan_AI_Health_Report.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();

      window.URL.revokeObjectURL(url);

      setStatus("✅ AI Insights PDF downloaded!");
      setLoading(false);
    } catch (e) {
      alert("Error exporting PDF: " + e.message);
      setStatus("❌ AI Insights PDF download failed.", false);
      setLoading(false);
    }
  });
}


// ✅ Clear History (NO alert/confirm)
if (clearHistoryBtn) {
  clearHistoryBtn.addEventListener("click", async () => {
    try {
      setLoading(true);
      setStatus("⏳ Clearing history...");

      const res = await fetch("/api/history/clear", { method: "POST" });
      const data = await res.json();

      if (data.success) {
        setStatus("✅ History cleared!");
        loadHistory();
        loadSuggestions();
      } else {
        setStatus("❌ Failed to clear history.", false);
      }

      setLoading(false);
    } catch (err) {
      setStatus("❌ Server error clearing history.", false);
      setLoading(false);
    }
  });
}

// ============================
// OCR Scan
// ============================
let scanBase64 = null;

scanBtn.addEventListener("click", () => scanFileInput.click());

scanFileInput.addEventListener("change", () => {
  const file = scanFileInput.files[0];
  if (!file) return;

  const ALLOWED = ["image/jpeg", "image/png", "image/webp"];
  if (!ALLOWED.includes(file.type)) {
    setStatus("❌ Only JPEG, PNG, or WebP images are supported.", false);
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    setStatus("❌ Image too large. Please use an image under 5MB.", false);
    return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      const MAX = 800;
      let w = img.width, h = img.height;
      if (w > MAX) { h = Math.round(h * MAX / w); w = MAX; }
      scanCanvas.width = w;
      scanCanvas.height = h;
      scanCanvas.getContext("2d").drawImage(img, 0, 0, w, h);
      scanBase64 = scanCanvas.toDataURL("image/jpeg", 0.85);
      scanThumb.src = scanBase64;
      scanPreview.classList.remove("hidden");
      setStatus("🖼️ Image ready. Click 'Identify Medicine' to scan.");
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
  scanFileInput.value = "";
});

scanClearBtn.addEventListener("click", () => {
  scanBase64 = null;
  scanPreview.classList.add("hidden");
  scanThumb.src = "";
  setStatus("✅ Scan cleared.");
});

scanConfirmBtn.addEventListener("click", async () => {
  if (!scanBase64) return;

  setLoading(true);
  setStatus("⏳ Scanning medicine strip...");
  resultBox.classList.add("hidden");

  try {
    const res = await fetch("/api/scan-medicine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: scanBase64 }),
    });

    const data = await res.json();

    if (!data.success) {
      setStatus("❌ " + data.error, false);
      setLoading(false);
      return;
    }

    // feed into existing renderer by populating input and reusing render logic
    input.value = data.medicine;
    scanPreview.classList.add("hidden");
    scanBase64 = null;

    lastResult = data;
    const med = data.data;
    const sourceTag = "📷 OCR Scan";

    medTitle.textContent = `💊 ${data.medicine.toUpperCase()} (${med.generic_name})`;
    sourceBadge.textContent = sourceTag;
    note.textContent = data.note ? "✅ " + data.note : "";

    useEl.textContent = med.use;
    dosageEl.textContent = med.dosage;
    renderList(sideEffectsEl, med.side_effects);
    renderList(warningsEl, med.warnings);

    aiSummary.textContent =
      `Use: ${med.use} ` +
      `Side effects: ${(med.side_effects || []).slice(0, 2).join(", ")}. ` +
      `Warnings: consult a doctor if unsure.`;

    const subs = med.generic_substitutes || [];
    substitutesList.innerHTML = "";
    if (subs.length > 0) {
      subs.forEach(s => {
        const chip = document.createElement("div");
        chip.className = "sub-chip";
        chip.innerHTML = `<span>${s.name}</span><span class="match-badge">${s.active_ingredient_match}% match</span>`;
        substitutesList.appendChild(chip);
      });
      substitutesBox.classList.remove("hidden");
    } else {
      substitutesBox.classList.add("hidden");
    }

    copyBtn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(buildCopyText(data.medicine, med, sourceTag));
        setStatus("✅ Copied report to clipboard!");
      } catch { setStatus("❌ Copy failed.", false); }
    };

    pdfBtn.onclick = async () => {
      try {
        setLoading(true);
        setStatus("⏳ Creating PDF report...");
        const pdfRes = await fetch("/api/report/pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(lastResult),
        });
        const blob = await pdfRes.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `mediscan_report_${data.medicine}.pdf`;
        document.body.appendChild(a); a.click(); a.remove();
        window.URL.revokeObjectURL(url);
        setStatus("✅ PDF downloaded!");
        setLoading(false);
      } catch { setStatus("❌ PDF download failed.", false); setLoading(false); }
    };

    shareBtn.onclick = async () => {
      try {
        const txt = buildCopyText(data.medicine, med, sourceTag);
        await navigator.clipboard.writeText(txt);
        setStatus("✅ Report copied! Opening WhatsApp...");
        window.open(`https://wa.me/?text=${encodeURIComponent(txt)}`, "_blank");
      } catch { setStatus("❌ Share failed.", false); }
    };

    resultBox.classList.remove("hidden");
    setStatus("✅ Medicine identified! See results below.");
    loadHistory(); loadFavorites(); loadSuggestions();
    setLoading(false);
  } catch (err) {
    console.error(err);
    setStatus("❌ Server error. Try again.", false);
    setLoading(false);
  }
});
// Voice Search (Speech-to-Text)
// ============================
if (micBtn) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    micBtn.addEventListener('click', () => {
      recognition.start();
    });

    recognition.onstart = function() {
      micBtn.classList.add("listening");
      setStatus("🎙️ Listening... Please speak a medicine name.");
    };

    recognition.onresult = function(event) {
      const transcript = event.results[0][0].transcript;
      input.value = transcript.replace(/\.$/, '').trim();
      setStatus("✅ Speech recognized. Searching...");
      fetchMedicine();
    };

    recognition.onerror = function(event) {
      micBtn.classList.remove("listening");
      setStatus("❌ Microphone error: " + event.error, false);
    };

    recognition.onend = function() {
      micBtn.classList.remove("listening");
    };
  } else {
    micBtn.addEventListener('click', () => {
      setStatus("❌ Speech Recognition API not supported in this browser.", false);
    });
  }
}

// ============================
// Initial Loads
// ============================
loadHistory();
loadFavorites();
loadSuggestions();
