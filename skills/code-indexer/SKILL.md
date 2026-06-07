---
name: code-indexer
description: Fast structural codebase explorer for Java and Python.
triggers: [java, python, method, function, index, architecture, class]
allowed-tools: [bash, run_command, execute_command, shell]
---
# code-indexer

**Purpose:** Explore codebase structure (classes, methods, functions, line numbers) BEFORE reading files.

**Script Locations:** 
The scripts `index_java_methods.py` and `index_python_methods.py` are located in the same directory as this SKILL.md file. 
Common absolute paths depending on your CLI: 
- Codex CLI: `~/.codex/skills/code-indexer/`
- Claude Code / OMC: `~/.claude/skills/omc-learned/code-indexer/`
- OpenCode: `~/.config/opencode/skills/code-indexer/` or project-local `.opencode/skills/code-indexer/`

**Rules:**
1. NEVER guess class/method locations or use grep blindly in Java/Python.
2. ALWAYS run the appropriate indexer via your `bash` or terminal tool first. Resolve the script path and run: 
   `python <path-to-script>/index_<lang>_methods.py [--pkg PKG] [--class CLASS] [--func FUNC] <target-dir>`
3. For multi-module projects or to scan everything, use `.` as the `<target-dir>`.
4. Use exact `offset`/`limit` with the `Read` tool based on the line numbers `[Lxx-Lyy]` in the output.

**Examples:**
`bash(command="python ~/.codex/skills/code-indexer/index_java_methods.py --class JiraClientImpl .")`
`bash(command="python .opencode/skills/code-indexer/index_python_methods.py --func test_simple .")`