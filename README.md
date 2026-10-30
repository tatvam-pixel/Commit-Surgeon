# Commit Surgeon

> **AI-powered offline Git commit management tool**

Commit Surgeon analyzes tangled Git working trees, identifies logically related changes, suggests meaningful commit messages, obtains human approval, crafts atomic Git commits, and generates structured Pull Request descriptions—**100% offline** using local open-source models.

---

## 1. Problem Being Solved

Developers often accumulate messy working trees containing multiple unrelated changes:
- Simultaneous bug fixes and feature enhancements
- Incidental refactoring mixed with functional logic
- Formatting tweaks and dependency updates scattered across files

Manually staging changes with `git add -p` is time-consuming, tedious, and error-prone. This leads to monolithic "dump commits" (e.g., `fix stuff`, `wip`, or 50-file single commits) that destroy git bisect capabilities, complicate code reviews, and clutter repository history.

**Commit Surgeon** acts as a surgical assistant: it dissects your diffs into logical, atomic units and stages them cleanly with semantic commit messages, keeping you in complete control through an interactive approval gate.

---

## 2. Current Implementation Status

| Feature / Component | Status | Description |
| :--- | :---: | :--- |
| **Project Foundation & Structure** | **Implemented** | Modular package hierarchy with PEP 8 standards |
| **Configuration Management** | **Implemented** | Pydantic-based settings with `.env` support |
| **Environment Verification** | **Implemented** | Auto-detection for Python, Git, Ollama, and local models |
| **Initial Rich CLI** | **Implemented** | Read-only diagnostic CLI displaying system readiness |
| **Comprehensive Test Suite** | **Implemented** | Pytest unit test coverage with external service mocking |
| *Diff Parsing & Hunk Extraction* | *Planned (Step 2)* | Extraction of working tree diffs and hunk boundaries |
| *Semantic Hunk Clustering* | *Planned (Step 3)* | Local LLM grouping of related changes into commit plans |
| *Commit Message Generation* | *Planned (Step 3)* | Conventional Commits generated via `qwen3.5:4b` |
| *Interactive Human Approval* | *Planned (Step 4)* | Terminal review, edit, and confirmation interface |
| *Atomic Commit Execution* | *Planned (Step 5)* | Safe Git staging and commit creation without data loss |
| *Pull Request Generation* | *Planned (Step 6)* | Consolidated PR summary and markdown documentation |

---

## 3. Technology Stack

- **Language:** Python 3.10+ (tested on Python 3.13)
- **VCS:** Git CLI
- **Local Inference Engine:** [Ollama](https://ollama.com/) (offline, zero external API calls)
- **Local Language Model:** `qwen3.5:4b` (4B parameters, optimized for code reasoning and low memory footprint)
- **Data Validation & Schemas:** [Pydantic v2](https://docs.pydantic.dev/)
- **Terminal UI & Formatting:** [Rich](https://github.com/Textualize/rich)
- **Configuration & Environment:** [python-dotenv](https://github.com/theskumar/python-dotenv)
- **Testing Framework:** [Pytest](https://pytest.org/)

---

## 4. Project Directory Structure

```text
commit-surgeon/
│
├── main.py                 # Application entry point and diagnostic CLI
├── requirements.txt        # Pinned project dependencies
├── .gitignore              # Git ignore rules for Python, virtualenv, and temp files
├── README.md               # Documentation and setup guide
├── .env.example            # Sample configuration settings
│
├── config/                 # Application configuration
│   ├── __init__.py
│   └── settings.py         # Pydantic Settings class loading from environment
│
├── git_engine/             # Git repository inspection and staging (future steps)
│   └── __init__.py
│
├── ai_engine/              # Ollama client and prompt templates (future steps)
│   └── __init__.py
│
├── approval/               # Interactive human approval flow (future steps)
│   └── __init__.py
│
├── utils/                  # Helper utilities and environment verification
│   ├── __init__.py
│   └── environment.py      # Python, Git, Ollama, and Model detection
│
├── output/                 # Directory for generated reports and PR artifacts
│   └── .gitkeep
│
└── tests/                  # Automated Pytest suite
    ├── __init__.py
    ├── test_cli.py         # CLI startup and output formatting tests
    ├── test_config.py      # Configuration and default values tests
    └── test_environment.py # Environment detection and mock service tests
```

---

## 5. Getting Started

### Prerequisites

- **Python:** Version 3.10 or newer (tested with Python 3.13)
- **Git:** Installed and available in your system `PATH`
- **Ollama:** Installed locally (see instructions below)

### Step 1: Clone or Navigate to the Repository

```bash
cd commit-surgeon
```

### Step 2: Create and Activate the Virtual Environment

Create a dedicated virtual environment named `.venv`:

```bash
python -m venv .venv
```

Activate the environment based on your platform:

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
.\.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

### Step 3: Install Dependencies

With the virtual environment active, install the project dependencies:

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment (Optional)

Copy the sample environment file to `.env`:

```bash
cp .env.example .env     # Linux / macOS
copy .env.example .env   # Windows
```

You can customize variables such as `OLLAMA_API_URL` or `DEFAULT_MODEL` if you are using non-default ports or custom hosts.

---

## 6. Ollama Setup & Model Download

Commit Surgeon is **strictly offline-first** and uses Ollama for local inference. It does not send code to cloud services or third-party APIs.

### 1. Install Ollama

- **Windows / macOS:** Download the installer from [https://ollama.com/download](https://ollama.com/download).
- **Linux:** Run the official installer script:
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ```

### 2. Start the Ollama Service

Make sure the Ollama daemon is running in the background:

```bash
ollama serve
```

*(On Windows and macOS, opening the Ollama desktop application automatically runs the daemon.)*

### 3. Download the Local Model

Commit Surgeon is designed to use **`qwen3.5:4b`**, a 4-billion-parameter open-source model. It provides excellent code understanding, diff comprehension, and commit structuring capabilities while running fast on standard consumer laptops (CPU or GPU).

Download the model manually:

```bash
ollama pull qwen3.5:4b
```

> **Note:** Commit Surgeon will never automatically download models in the background without explicit user action to protect your bandwidth and disk storage.

---

## 7. Running the Application

Run the diagnostic CLI:

```bash
python main.py
```

### Expected Output:

When services and models are fully configured:
```text
COMMIT SURGEON
AI-powered offline Git commit management

Version: 0.1.0

Environment Status:
- Python: Installed
- Git: Installed
- Ollama: Running
- Local Model: Available

Project Status: Environment Check Complete (Ready)
```

When Ollama is not running:
```text
COMMIT SURGEON
AI-powered offline Git commit management

Version: 0.1.0

Environment Status:
- Python: Installed
- Git: Installed
- Ollama: Not Running
- Local Model: Unknown

Project Status: Environment Check Complete (Setup Required)
```

If Ollama is stopped or the model has not yet been pulled, the CLI will clearly report the status and provide exact copy-paste commands (`ollama serve`, `ollama pull qwen3.5:4b`) to resolve it.

---

## 8. Running the Tests

Execute the automated test suite with Pytest:

```bash
pytest -v
```

All external dependencies (network calls, Ollama API, git commands) are mocked in the test suite so tests run quickly and reliably without requiring an active Ollama instance or internet access.
