# Medicsan AI

AI-powered healthcare assistant for comparing medicines and summarizing medical reports.
For research and educational use only — not medical advice.

---

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup (Windows / Linux / macOS)](#setup-windows--linux--macos)
  - [Windows (PowerShell)](#windows-powershell)
  - [Windows (cmd)](#windows-cmd)
  - [Linux / macOS (bash)](#linux--macos-bash)
- [Run locally](#run-locally)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Features

- AI-based health insights
- Medical report analysis
- User-friendly interface
- Flask backend
- Responsive UI
- Auto Generated PDF Reports

## Tech Stack

- Python
- Flask
- HTML/CSS
- JavaScript
- AI/ML

## Prerequisites

- Python 3.12+
- Git
- A virtual environment is recommended

## Setup (Windows / Linux / macOS)

Clone the repository:

```powershell
git clone https://github.com/Ranjit1401/Medicsan_ai.git
cd Medicsan_ai
```

### Windows (PowerShell)

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Windows (cmd)

```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

### Linux / macOS (bash)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run locally

Start the application with:

```powershell
python app.py
```

Open in your browser:

```text
http://127.0.0.1:5000
```

## Project structure

## Project structure

```text
Medicsan_ai/
├── .github/
├── data/
├── static/
├── templates/
├── tests/
├── venv/
├── .gitignore
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── app.py
├── init_db.py
├── package-lock.json
├── pyproject.toml
├── pytest.ini
└── requirements.txt
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines.

## License

MIT — see `LICENSE` for details.

## Contact

Project maintainer: [@Ranjit1401](https://github.com/Ranjit1401)