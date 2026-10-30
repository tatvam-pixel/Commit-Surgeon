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
| **Project Foundation & Structure** | **Implemented (Step 1)** | Modular package hierarchy with PEP 8 standards |
| **Configuration Management** | **Implemented (Step 1)** | Pydantic-based settings with `.env` support |
| **Environment Verification** | **Implemented (Step 1)** | Auto-detection for Python, Git, Ollama, and local models |
| **Initial Rich CLI** | **Implemented (Step 1)** | Read-only diagnostic CLI displaying system readiness |
| **Diff Parsing & Hunk Extraction** | **Implemented (Step 2)** | Staged, unstaged, and untracked diff extraction with hunk attribution |
| **Repository Changes Analyzer** | **Implemented (Step 2)** | CLI `analyze` command and structured change statistics |
| **Semantic Hunk Clustering** | **Implemented (Step 3)** | Local LLM grouping of related changes into commit plans |
| **Commit Message Generation** | **Implemented (Step 3)** | Conventional Commits generated via `qwen3.5:4b` with validation |
| **AI Change Grouping CLI** | **Implemented (Step 3)** | CLI `group` command with self-repairing JSON parser and validator |
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
├── main.py                 # Application entry point and CLI commands (check, analyze, group)
├── requirements.txt        # Minimum version dependency specifications
├── .gitignore              # Git ignore rules for Python, virtualenv, and temp files
├── README.md               # Documentation and setup guide
├── WALKTHROUGH.md          # Technical walkthrough and architectural guide
├── .env.example            # Sample configuration settings
│
├── config/                 # Application configuration
│   ├── __init__.py
│   └── settings.py         # Pydantic Settings class loading from environment
│
├── git_engine/             # Git repository inspection and diff extraction
│   ├── __init__.py
│   ├── analyzer.py         # RepositoryChanges aggregation and diff analyzer
│   ├── diff.py             # Staged, unstaged, and synthetic untracked diff extraction
│   ├── exceptions.py       # Git engine exception hierarchy
│   ├── models.py           # DiffHunk, FileChange, RepositoryChanges models
│   ├── parser.py           # Unified diff parser and hunk header extraction
│   ├── repository.py       # Git command execution and repository metadata
│   └── status.py           # Git status parsing and change classification
│
├── ai_engine/              # Local LLM integration and semantic grouping
│   ├── __init__.py
│   ├── analyzer.py         # AIChangeAnalyzer with self-healing JSON repair
│   ├── context.py          # PreparedChangeContext and sensitive file filtering
│   ├── exceptions.py       # AI engine exception hierarchy
│   ├── grouper.py          # ChangeGrouper high-level workflow coordinator
│   ├── models.py           # Pydantic models for grouping results and proposed commits
│   ├── ollama_client.py    # Local Ollama REST client
│   ├── prompts.py          # Strict system and grouping prompts
│   └── validator.py        # GroupValidator enforcing grouping invariants
│
├── approval/               # Interactive human approval flow (Step 4)
│   └── __init__.py
│
├── utils/                  # Helper utilities and environment verification
│   ├── __init__.py
│   └── environment.py      # Python, Git, Ollama, model, and endpoint checks
│
└── tests/                  # Automated Pytest suite
    ├── __init__.py
    ├── conftest.py         # Shared fixtures and temporary Git repositories
    ├── test_ai_analyzer.py
    ├── test_ai_models.py
    ├── test_change_grouper.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_conflict_and_attribution.py
    ├── test_environment.py
    ├── test_git_diff.py
    ├── test_git_parser.py
    ├── test_git_repository.py
    ├── test_git_status.py
    ├── test_group_validator.py
    ├── test_hunk_id_and_endpoint.py
    ├── test_hunk_separation.py
    ├── test_ollama_client.py
    └── test_security_fixes.py
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

### 1. Environment Diagnostic Check

Run the diagnostic CLI:

```bash
python main.py
```

### 2. Git Change Analysis

Analyze changes in the current repository or a specified path:

```bash
python main.py analyze [optional_path]
```

This inspects the repository, partitions staged and unstaged hunks, and outputs a detailed statistical summary.

### 3. AI Change Grouping

Analyze and group related changes into atomic proposed commits using the local `qwen3.5:4b` model:

```bash
python main.py group [optional_path]
```

This prepares sanitized context (excluding sensitive files like `.env`), executes structured local inference, validates group cohesion and completeness, and displays proposed commit groups with titles and justifications.

---

## 8. Running the Tests

Execute the automated test suite with Pytest:

```bash
pytest -v
```

All external dependencies (network calls, Ollama API, git commands) are mocked in the test suite so tests run quickly and reliably without requiring an active Ollama instance or internet access.
