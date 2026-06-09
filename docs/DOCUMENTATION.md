[🇺🇸 English](DOCUMENTATION.md) | [🇩🇪 Deutsch](DOKUMENTATION_DE.md)

# Detailed Documentation: Code-Indexer

This documentation is aimed at developers and system architects who want to understand how the `code-indexer` works under the hood, why it is indispensable for AI agents, and how to utilize it optimally via the command line.

---

## 1. Concept & Philosophy ("X-Ray Vision")

AI Language Models (LLMs) like Claude, GPT-4, or Gemini have limited context windows. When an AI agent needs to analyze a codebase, it often wastes valuable tokens (and thus "thinking capacity") by blindly searching and reading entire files.

**The Solution:** The Code-Indexer separates *finding* from *reading*.
It scans the source code and extracts only the architectural signatures (packages, modules, class names, method signatures, and their line numbers).

### The ROI (Return on Investment) for AI Agents
* **Preventing Hallucinations:** The AI stops inventing method names or parameters when integrating a new feature. The index provides the strict contract (API) of the existing codebase.
* **Massive Token Savings:** An index containing 50 classes consumes significantly fewer tokens than loading 2-3 large Java/Python files into context.
* **Laser-Focus when Reading:** Because the index outputs exact line numbers (e.g., `[L15-L42]`), the AI can use a file-reading tool with an offset to load only those specific 27 lines into context, avoiding parsing a 1000-line file.

---

## 2. Technical Implementation & Caching

The scripts (`skills/code-indexer/index_java_methods.py` and `skills/code-indexer/index_python_methods.py`) use structural parsing (Regex/AST) to understand code. 
**They do not require compilation!** Neither Maven, Gradle, nor an active Python environment (venv) needs to be initialized.

### Intelligent Caching
To avoid delays in large monoliths (projects with >1000 files), the scripts utilize a caching system:
1. During the first run, the project is analyzed comprehensively.
2. The result is saved in `<project_root>/.cache/list_methods_cache.json` (or `list_python_methods_cache.json`).
3. On every subsequent run, the script only checks the modification date (`mtime`) of the files. Only code files that you or the AI just edited are re-parsed. The rest is loaded from the cache in milliseconds.

*(Tip: Add `.cache/` to your `.gitignore`).*

### Execution Requirements & JDTLS Setup
Unlike other deep-analysis tools (which might require SQLite, Node.js toolchains, or compiling local binary bindings like `tree-sitter`), `code-indexer` is built to be extremely lightweight and requires zero installation of third-party python packages.

*   **Python Requirement**: Python 3.9+ is required because the parser relies on `ast.unparse` (added in Python 3.9) to format signatures.
*   **Java Requirement (`jdtls`)**: The Java indexer executes the local Eclipse JDT Language Server (`jdtls`) using standard input/output streams. To use Java indexing:
    1.  Ensure you have **Java JDK 17+** installed.
    2.  Install `jdtls` and add the executable to your system's `PATH`.

---

## 3. CLI Reference (Command Line Arguments)

Both scripts share the exact same syntax and functionality.

### General Syntax
```bash
python skills/code-indexer/index_java_methods.py [OPTIONS] <project_root>
python skills/code-indexer/index_python_methods.py [OPTIONS] <project_root>
```

### Required Argument
* `<project_root>`
  The path to the source code.
  **Best Practice:** Always pass `.` (the current directory). The script will recursively search all subfolders. This is especially important for multi-module projects (e.g., Maven projects with multiple `src/main/java` folders).

### Optional Filters
When reading the index in the terminal, the output for large projects can be overwhelming. Use filters to trim the tree down to the relevant branches. Wildcards (`*`, `?`) are supported.

#### `--pkg <Name>` (Package/Module Filter)
Filters the output by folder structures, Java packages, or Python module paths.
* **Java:** `python skills/code-indexer/index_java_methods.py --pkg de.aragit.xray.auth .`
* **Python:** `python skills/code-indexer/index_python_methods.py --pkg xray.auth .`

#### `--class <Name>` (Class Filter)
Shows only the structure of a specific class or interface. Functions as a substring search (e.g., `Client` finds both `ApiClient` and `DbClient`).
* **Java:** `python skills/code-indexer/index_java_methods.py --class JiraClientImpl .`
* **Python:** `python skills/code-indexer/index_python_methods.py --class JiraServer .`

#### `--func <Name>` (Method/Function Filter)
Searches across files for specific methods or functions. Perfect for finding all classes that implement a specific interface method.
* **Java:** `python skills/code-indexer/index_java_methods.py --func getById .`
* **Python:** `python skills/code-indexer/index_python_methods.py --func test_* .`

---

## 4. Examples for Combined Searches

The true power of the terminal lies in combining filters. **Note:** When combining multiple filters (`--pkg`, `--class`, `--func`), they act as a **logical AND**. The script will only return results that match *all* provided conditions simultaneously.

**Scenario 1: Java Refactoring**
Find all methods containing "update" in their name, located in classes named "Client", but strictly within the "xray.client" package:
```bash
python skills/code-indexer/index_java_methods.py --pkg xray.client --class Client --func update .
```

**Scenario 2: Reviewing Python Tests**
Find all setup functions within modules that contain the word "test":
```bash
python skills/code-indexer/index_python_methods.py --pkg *test* --func setup* .
```

---

## 5. Supported Queries & Capabilities

To provide a better understanding of the `code_indexer` capabilities, here is a list of common queries and an evaluation of whether the tool can directly answer them. The indexer strictly focuses on **Java** and **Python**.

### ✅ Fully Supported (Directly answerable)
These queries can be easily answered using the built-in name and structure filters:

* **"Show me all classes that contain 'user' in their name"**
* **"What methods does the User class have?"**
* **"List all Java packages and Python modules with their classes"**
* **"Find Java and Python classes and their methods"**
* **"Find all Python magic methods (operator overloads) in the Matrix class"**
* **"List all Java packages / Python modules and their contained classes"**

### ⚠️ Partially Supported (Limited or workaround needed)
The tool reaches its functional limits here due to a lack of semantic understanding or complex type graphs:

* **"Find functions related to database operations"**
  *(No semantic understanding. You can only search for keywords within the method name, e.g., `--func db`.)*
* **"Show me functions that handle authentication"**
  *(Same reason as above. Only string-based search for e.g. `--func auth` is possible.)*
* **"Show me Java interfaces and their implementations"**
  *(Interfaces and classes are indexed, but the tool does not automatically link classes to the interfaces they implement. The inheritance graph is missing.)*
* **"Show me Java generic methods with their type bounds"**
  *(Method signatures are extracted, but complex `<T>` generics and type-bounds are not specifically parsed for filtering.)*

### ❌ Not Supported (Cannot be answered)
These queries are impossible to answer because they require modifying code (the tool is read-only) or analyzing the body of a method (the tool only reads the API "shell"):

* **"Find Java and Python lambda expressions used within methods"**
  *(The indexer only parses class and method signatures. The inner code/body of a method is ignored, hence no inline lambdas are found.)*
* **"Add logging to all database connection functions"**
  *(Read-only tool, cannot write or modify code.)*
* **"Refactor the User class to use dependency injection"**
  *(Read-only tool, cannot refactor code.)*
* **"Convert these Python functions to async/await pattern"**
  *(Read-only tool, cannot convert code.)*
* **"Add error handling to authentication methods"**
  *(Read-only tool, cannot write code.)*
* **"Optimize this function for better performance"**
  *(Read-only tool, does not perform performance analysis or optimization.)*

---

## 6. Role in the AI-Assisted Software Development Life Cycle (AI-SDLC)

The limitations of the `code_indexer` regarding partially or unsupported queries are mostly *by-design*. The tool is built to be a purely static **navigation and discovery tool** (the "map") for the AI. It forms a perfect symbiosis with the cognitive capabilities of an LLM:

* **Discovery Phase (Missing Semantics/Type Graphs):** Since the indexer lacks semantic understanding, the AI must work iteratively (e.g., filtering for `persistence` packages when looking for database operations). Missing type inheritance graphs are compensated by the AI querying specific interface method names.
* **Debugging & Deep-Dives (No Body/Lambdas):** The indexer deliberately provides the AI with only the API shell and the *exact line numbers*. This protects the context window. To understand lambdas or fix bugs, the AI subsequently uses file-reading tools to load exactly that line range.
* **Implementation & Refactoring (Read-Only):** The indexer acts as the "eyes" of the AI. It intentionally does not modify code. The AI acts as the "hands" using its own write tools to refactor or write code at the coordinates identified by the indexer.
* **Performance Optimization:** Profiling is dynamic, whereas the indexer is static. The AI merely uses the indexer to quickly locate functions in the codebase after an external performance analysis.