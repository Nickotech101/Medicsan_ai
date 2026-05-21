// ============================
// MediScan AI - app.js (FULL)
// ============================

const btn = document.getElementById("checkBtn");
const clearBtn = document.getElementById("clearBtn");
const input = document.getElementById("medicineInput");

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
const aiSummary = document.getElementById("aiSummary");

const historyList = document.getElementById("historyList");
const favoritesList = document.getElementById("favoritesList");

const datalist = document.getElementById("medicineList");

const copyBtn = document.getElementById("copyBtn");
const favBtn = document.getElementById("favBtn");
const pdfBtn = document.getElementById("pdfBtn");
const shareBtn = document.getElementById("shareBtn");

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
  } else {
    hideLoader();
    btn.disabled = false;
    clearBtn.disabled = false;
    if (clearHistoryBtn) clearHistoryBtn.disabled = false;
    if (copyBtn) copyBtn.disabled = false;
    if (favBtn) favBtn.disabled = false;
    if (pdfBtn) pdfBtn.disabled = false;
    if (shareBtn) shareBtn.disabled = false;
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
  return `
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
- ${(med.warnings || []).join("\n- ")}

Disclaimer: Educational only. Consult a doctor.
`.trim();
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
    const res = await fetch("/api/history");
    const data = await res.json();
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
    const res = await fetch("/api/favorites");
    const data = await res.json();
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

    aiSummary.textContent =
      `Use: ${med.use} ` +
      `Side effects: ${(med.side_effects || []).slice(0, 2).join(", ")}. ` +
      `Warnings: consult a doctor if unsure.`;

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
});

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
// Initial Loads
// ============================
loadHistory();
loadFavorites();
loadSuggestions();
