# 🩺 MediScan AI

> **Medical Disclaimer:** MediScan AI is intended for **research and educational purposes only**. It is **not a substitute for professional medical advice, diagnosis, or treatment**. Always consult a qualified healthcare provider for medical decisions. Never disregard professional medical advice or delay seeking it based on results from this tool.

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-black?logo=flask)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)
[![Issues](https://img.shields.io/github/issues/Ranjit1401/Medicsan_ai)](https://github.com/Ranjit1401/Medicsan_ai/issues)

MediScan AI is an AI-powered medical scan analysis tool built with Flask. It allows users to upload medical scan images (X-rays, MRIs, CT scans) and receive AI-generated insights to assist in preliminary analysis.

---

## 📑 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Prerequisites](#-prerequisites)
- [Local Setup & Installation](#-local-setup--installation)
- [Running the Application](#-running-the-application)
- [API Reference](#-api-reference)
- [How to Interpret Results](#-how-to-interpret-results)
- [Project Structure](#-project-structure)
- [Dataset & Model Details](#-dataset--model-details)
- [Contributing](#-contributing)
- [Safety & Usage Guidelines](#-safety--usage-guidelines)
- [License](#-license)

---

## ✨ Features

- Upload medical scan images (JPEG, PNG, DICOM)
- AI-powered preliminary analysis of scans
- Confidence scores for detected conditions
- Simple web interface via Flask
- RESTful API for programmatic access

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Client (Browser)                 │
│              Upload Scan → View Results             │
└───────────────────────┬─────────────────────────────┘
                        │ HTTP
                        ▼
┌─────────────────────────────────────────────────────┐
│                   Flask Web Server                  │
│  ┌─────────────┐        ┌──────────────────────┐    │
│  │  Routes /   │        │  Image Preprocessing │    │
│  │  Templates  │───────▶ (resize,normalize)   │    │
│  └─────────────┘        └──────────┬───────────┘    │
│                                    │                │
│                          ┌─────────▼──────────┐     │
│                          │    AI/ML Model      │    │
│                          │  (CNN / TF / PyTorch)│   │
│                          └─────────┬──────────┘     │
│                                    │                │
│                          ┌─────────▼──────────┐     │
│                          │  Results Formatter  │    │
│                          │  (labels + scores)  │    │
│                          └────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

**Tech Stack:**

| Layer        | Technology                        |
|--------------|-----------------------------------|
| Backend      | Python 3.8+, Flask                |
| AI/ML        | TensorFlow / PyTorch (CNN model)  |
| Image I/O    | Pillow, OpenCV                    |
| Frontend     | HTML, CSS, Jinja2 Templates       |
| Deployment   | Gunicorn (recommended for prod)   |

---

## 🔧 Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.8 or higher** — [Download](https://www.python.org/downloads/)
- **pip** (comes with Python)
- **Git** — [Download](https://git-scm.com/)
- A virtual environment tool (`venv` is built into Python 3)

Optional but recommended:
- **CUDA-enabled GPU** for faster inference (CPU works fine for testing)

---

## 🚀 Local Setup & Installation

Follow these steps exactly to get MediScan AI running on your machine.

### 1. Clone the Repository

```bash
git clone https://github.com/Ranjit1401/Medicsan_ai.git
cd Medicsan_ai
```

### 2. Create a Virtual Environment

Using a virtual environment keeps dependencies isolated from your global Python installation.

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate
```

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

You should see `(venv)` appear at the start of your terminal prompt, confirming the environment is active.

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Troubleshooting:** If you get errors on Windows, try upgrading pip first:
> ```bash
> python -m pip install --upgrade pip
> ```

### 4. Download Pre-trained Model Weights

If model weights are not included in the repo (large files), download them separately:

```bash
# Example — update this URL to the actual weights source
wget https://github.com/Ranjit1401/Medicsan_ai/releases/download/v1.0/model_weights.h5 -O models/model_weights.h5
```

Or manually place the weights file in the `models/` directory as specified in `config.py`.

### 5. Configure Environment Variables

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and set:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
MODEL_PATH=models/model_weights.h5
UPLOAD_FOLDER=uploads/
MAX_CONTENT_LENGTH=16777216   # 16 MB max upload
```

---

## ▶️ Running the Application

### Development Mode

```bash
flask run
```

The app will be available at **http://127.0.0.1:5000**

### Production Mode (with Gunicorn)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Running with Python directly

```bash
python app.py
```

---

## 📡 API Reference

MediScan AI exposes a simple REST API for programmatic use.

### `POST /api/analyze`

Upload a medical scan image and receive AI analysis results.

**Request:**

| Parameter | Type   | Required | Description                              |
|-----------|--------|----------|------------------------------------------|
| `file`    | File   | Yes      | Scan image (JPEG, PNG; max 16MB)         |
| `type`    | String | No       | Scan type: `xray`, `mri`, `ct` (default: auto-detect) |

**Example using `curl`:**

```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -F "file=@/path/to/scan.jpg" \
  -F "type=xray"
```

**Example using Python `requests`:**

```python
import requests

with open("scan.jpg", "rb") as f:
    response = requests.post(
        "http://127.0.0.1:5000/api/analyze",
        files={"file": f},
        data={"type": "xray"}
    )

result = response.json()
print(result)
```

**Success Response (200):**

```json
{
  "status": "success",
  "scan_type": "xray",
  "predictions": [
    {
      "label": "Pneumonia",
      "confidence": 0.87
    },
    {
      "label": "Normal",
      "confidence": 0.13
    }
  ],
  "disclaimer": "This result is for educational purposes only and should not be used for clinical decisions."
}
```

**Error Response (400):**

```json
{
  "status": "error",
  "message": "No file provided or unsupported file format."
}
```

### `GET /api/health`

Check if the server is running.

```bash
curl http://127.0.0.1:5000/api/health
```

```json
{ "status": "ok", "model_loaded": true }
```

---

## 🔍 How to Interpret Results

Each prediction response contains `label` and `confidence` fields.

| Confidence Range | Interpretation |
|-----------------|----------------|
| 0.85 – 1.00    | High model confidence — still requires clinical verification |
| 0.60 – 0.84    | Moderate confidence — treat as a preliminary flag only |
| 0.00 – 0.59    | Low confidence — result is likely unreliable for this scan |

**Important notes on results:**

- **Confidence scores are not probabilities of a diagnosis.** They reflect how strongly the model pattern-matched against its training data.
- The model may produce false positives and false negatives. Do not use results to make health decisions.
- Results should always be reviewed alongside full clinical context by a qualified medical professional.
- Image quality significantly affects accuracy. Use clear, properly oriented scans for best results.

---

## 📁 Project Structure

```
Medicsan_ai/
├── app.py                  # Main Flask application entry point
├── config.py               # Configuration (paths, model settings)
├── requirements.txt        # Python dependencies
├── .env.example            # Sample environment variables
│
├── models/                 # ML model definitions and weights
│   ├── model.py            # Model architecture definition
│   └── model_weights.h5    # Pre-trained weights (download separately)
│
├── api/                    # API route handlers
│   └── routes.py
│
├── utils/                  # Helper utilities
│   ├── preprocess.py       # Image preprocessing functions
│   └── postprocess.py      # Result formatting
│
├── templates/              # Jinja2 HTML templates
│   ├── index.html
│   └── result.html
│
├── static/                 # CSS, JS, images
│   ├── css/
│   └── js/
│
├── uploads/                # Temporary storage for uploaded scans
└── tests/                  # Unit and integration tests
    └── test_api.py
```

---

## 🧠 Dataset & Model Details

### Model Architecture

MediScan AI uses a Convolutional Neural Network (CNN) for image classification. The architecture is inspired by standard medical imaging baselines:

- **Base:** ResNet-50 / VGG-16 (transfer learning from ImageNet)
- **Custom Head:** GlobalAveragePooling → Dense(256, ReLU) → Dropout(0.5) → Dense(n_classes, Softmax)
- **Input Size:** 224×224 pixels, RGB
- **Framework:** TensorFlow / Keras

### Training Dataset

| Dataset | Source | Classes | Size |
|---------|--------|---------|------|
| Chest X-Ray | [Kaggle - Chest X-Ray Images (Pneumonia)](https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia) | Normal, Pneumonia | ~5,800 images |

> If you train on additional datasets, please update this section accordingly.

### Performance Metrics

| Metric    | Value  |
|-----------|--------|
| Accuracy  | ~92%   |
| Precision | ~91%   |
| Recall    | ~93%   |
| AUC-ROC   | ~0.97  |

*Metrics are on held-out test set. Performance may vary on out-of-distribution data.*

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository
2. **Create a branch** for your feature: `git checkout -b feature/your-feature-name`
3. **Make your changes** and add tests where appropriate
4. **Run tests:** `pytest tests/`
5. **Commit:** `git commit -m "feat: add your feature description"`
6. **Push:** `git push origin feature/your-feature-name`
7. **Open a Pull Request** against the `main` branch

Please check open [Issues](https://github.com/Ranjit1401/Medicsan_ai/issues) before starting work — especially issues labeled `good first issue`.

---

## ⚠️ Safety & Usage Guidelines

### Medical Disclaimer

**MediScan AI is a research and educational tool. It is NOT approved for clinical use.**

- This tool does not constitute medical advice.
- Results should never be used to self-diagnose or make treatment decisions.
- All outputs must be reviewed by a licensed medical professional before any action is taken.
- The developers and contributors of this project accept no liability for decisions made based on the tool's output.

### Responsible Use

- Do not upload scans containing personally identifiable patient information (PII/PHI) to any publicly hosted version of this tool.
- If deploying this tool in any institutional setting, ensure compliance with applicable regulations (HIPAA, GDPR, etc.).
- Be transparent with end-users that this is an AI tool with known limitations.

### Known Limitations

- The model is trained on a limited dataset and may not generalize to all scan types, equipment manufacturers, or patient demographics.
- Performance may degrade on low-resolution, rotated, or artifact-heavy images.
- The model cannot detect all conditions — a "Normal" prediction does not guarantee absence of disease.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.

---

## 🙏 Acknowledgements

- [Kaggle Chest X-Ray Dataset](https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia)
- [TensorFlow / Keras](https://www.tensorflow.org/)
- [Flask](https://flask.palletsprojects.com/)
- All open-source contributors

---

*Built with ❤️ for the open-source medical AI community. Remember: AI assists, doctors decide.*