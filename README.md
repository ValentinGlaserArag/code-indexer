[🇺🇸 English](README.md) | [🇩🇪 Deutsch](README_DE.md)

# Code Indexer Skill for AI Agents

This repository contains a universal AI skill (`code-indexer`) for CLI agents like Claude Code, Codex CLI, OpenCode, and Cursor/Copilot. It grants AI agents "x-ray vision" for Java and Python projects.

Instead of blindly searching large codebases or using `grep` inefficiently, this tool generates a structural index (Packages -> Classes -> Methods + Line Numbers). This enables the AI to save tokens, prevent hallucinations, and read files precisely at the correct line offsets.

## 📋 Prerequisites

*   **Python 3.9+**: Required due to the use of `ast.unparse` (no third-party `pip` libraries are needed).
*   **Eclipse JDT Language Server (`jdtls`)**: Only required if you intend to index **Java** projects. The `jdtls` command must be executable from your system PATH (requires Java JDK 17+).
    *   **macOS**: `brew install jdtls`
    *   **Windows**: `winget install Eclipse.JDTLS` (make sure it's added to PATH)
    *   **Linux**: Download from Eclipse and add to PATH.

## 📦 Installation

Different AI terminals expect skills in different locations. Choose the installation instructions for your tool:

### 1. Codex CLI
Codex CLI expects global skills in the `~/.codex/skills/` directory.
```bash
mkdir -p ~/.codex/skills
git clone https://github.com/ValentinGlaserArag/code-indexer.git ~/.codex/skills/code-indexer
```

### 2. Claude Code / OhMyClaudeCode (OMC)
The OMC ecosystem uses global skills in the `~/.claude/` directory.
```bash
mkdir -p ~/.claude/skills/omc-learned
git clone https://github.com/ValentinGlaserArag/code-indexer.git ~/.claude/skills/omc-learned/code-indexer
```

### 3. OpenCode
OpenCode supports global or project-specific skills.
**Project-specific (Current project only):**
```bash
mkdir -p .opencode/skills
git clone https://github.com/ValentinGlaserArag/code-indexer.git .opencode/skills/code-indexer
```
**Global (For all projects):**
Clone it to `~/.config/opencode/skills/` (Linux/Mac) or your Windows AppData directory depending on your OS.

### 4. GitHub Copilot CLI / Cursor IDE
These tools do not use traditional "skill folders" but rely on system prompts within the project.
1. Clone the repository into a hidden folder in your project (e.g., `.scripts/code-indexer/`).
2. Copy the plain text content of the `SKILL.md` (excluding the top YAML header) and paste it into your `.cursorrules` (Cursor) or `.github/copilot-instructions.md` (Copilot).
3. Adjust the `<path-to-script>` placeholder in the text to point to `.scripts/code-indexer/`.

### 5. GitHub CLI (`gh skill`)
The GitHub CLI (v2.90.0+) has native support for installing agent skills. You can install it globally for a specific agent:
```bash
# For Codex CLI
gh skill install ValentinGlaserArag/code-indexer --agent codex --scope user

# For Claude Code
gh skill install ValentinGlaserArag/code-indexer --agent claude-code --scope user

# For GitHub Copilot
gh skill install ValentinGlaserArag/code-indexer --agent copilot --scope user
```

### 6. Vercel Labs (`npx skills` / skills.sh)
You can install and register this skill using the Vercel Labs `skills.sh` CLI:
```bash
npx skills add ValentinGlaserArag/code-indexer
```

---

## 🛠️ Manual Usage (Command Line)

These scripts are also extremely useful for human developers. Both scripts share the exact same syntax:

```bash
python skills/code-indexer/index_java_methods.py [OPTIONS] <project_root>
python skills/code-indexer/index_python_methods.py [OPTIONS] <project_root>
```

**Required Argument:**
* `<project_root>`: The path to the source code. For multi-module projects, using `.` is recommended to recursively scan everything.

**Optional Filters:**
* `--pkg <Name>`: Filters by Java packages or Python module paths (Wildcards `*` allowed).
* `--class <Name>`: Filters by class or interface (Substring search).
* `--func <Name>`: Searches specifically for methods or free functions.

*(Note: Combining multiple filters acts as a **logical AND** - all conditions must be met).*

**Example:**
```bash
# Find all "update" methods in "Client" classes in the current Java project
python skills/code-indexer/index_java_methods.py --pkg xray.client --class Client --func update .
```

## ⚙️ How it works (Caching)
To ensure blazing fast performance on large projects, the scripts only re-parse modified files. The index is automatically stored in your project root under the `.cache/` folder (e.g., `.cache/list_python_methods_cache.json`). It is highly recommended to add `.cache/` to your `.gitignore`.

## 📚 Detailed Documentation
For a deep dive into the architecture, caching mechanisms, and advanced CLI combinations, see [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md).