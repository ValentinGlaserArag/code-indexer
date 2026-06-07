[🇺🇸 English](README.md) | [🇩🇪 Deutsch](README_DE.md)

# Code Indexer Skill für KI-Agenten

Dieses Repository enthält einen universellen KI-Skill (`code-indexer`) für CLI-Agenten wie Claude Code, Codex CLI, OpenCode und Cursor/Copilot. Er verleiht der KI einen "Röntgenblick" für Java- und Python-Projekte.

Anstatt blind in großen Codebasen zu suchen oder `grep` zu verwenden, generiert dieses Tool einen strukturellen Index (Packages -> Klassen -> Methoden + Zeilennummern). Die KI kann so Token sparen, Halluzinationen vermeiden und Dateien punktgenau an den richtigen Zeilen lesen.

## 📋 Systemvoraussetzungen

*   **Python 3.9+**: Erforderlich wegen der Verwendung von `ast.unparse` (keine externen `pip`-Bibliotheken notwendig).
*   **Eclipse JDT Language Server (`jdtls`)**: Nur erforderlich, wenn Sie **Java**-Projekte indizieren möchten. Der Befehl `jdtls` muss im PATH des Systems ausführbar sein (erfordert Java JDK 17+).
    *   **macOS**: `brew install jdtls`
    *   **Windows**: `winget install Eclipse.JDTLS` (stellen Sie sicher, dass es zum PATH hinzugefügt wird)
    *   **Linux**: Von Eclipse herunterladen und zum PATH hinzufügen.

## 📦 Installation

Da verschiedene KI-Terminals unterschiedliche Speicherorte für ihre Skills erwarten, wähle einfach die Anleitung für dein Tool:

### 1. Codex CLI
Das Codex CLI erwartet globale Skills im `~/.codex/skills/` Verzeichnis.
```bash
mkdir -p ~/.codex/skills
git clone https://github.com/ValentinGlaserArag/code-indexer.git ~/.codex/skills/code-indexer
```

### 2. Claude Code / OhMyClaudeCode (OMC)
Das OMC-Ökosystem nutzt globale Skills im `~/.claude/` Verzeichnis.
```bash
mkdir -p ~/.claude/skills/omc-learned
git clone https://github.com/ValentinGlaserArag/code-indexer.git ~/.claude/skills/omc-learned/code-indexer
```

### 3. OpenCode
OpenCode unterstützt globale oder projektbezogene Skills.
**Projektbezogen (Nur für das aktuelle Projekt):**
```bash
mkdir -p .opencode/skills
git clone https://github.com/ValentinGlaserArag/code-indexer.git .opencode/skills/code-indexer
```
**Global (Für alle Projekte):**
Je nach Betriebssystem in `~/.config/opencode/skills/` oder im Windows AppData-Verzeichnis ablegen.

### 4. GitHub Copilot CLI / Cursor IDE
Diese Tools nutzen keine klassischen "Skill-Ordner", sondern System-Prompts im Projekt.
1. Klone das Repository in einen versteckten Ordner deines Projekts (z.B. `.scripts/code-indexer/`).
2. Kopiere den reinen Text-Inhalt der `SKILL.md` (ohne den YAML-Header oben) und füge ihn in deine `.cursorrules` (Cursor) oder `.github/copilot-instructions.md` (Copilot) ein.
3. Passe im Text den Pfad `<path-to-script>` auf `.scripts/code-indexer/` an.

### 5. GitHub CLI (`gh skill`)
Das GitHub CLI (v2.90.0+) bietet native Unterstützung für die Installation von Agenten-Skills. Du kannst einen Skill global für einen bestimmten Agenten installieren:
```bash
# Für das Codex CLI
gh skill install ValentinGlaserArag/code-indexer --agent codex --scope user

# Für Claude Code
gh skill install ValentinGlaserArag/code-indexer --agent claude-code --scope user

# Für GitHub Copilot
gh skill install ValentinGlaserArag/code-indexer --agent copilot --scope user
```

### 6. Vercel Labs (`npx skills` / skills.sh)
Installiere den Skill mit dem CLI-Paketmanager von Vercel Labs:
```bash
npx skills add ValentinGlaserArag/code-indexer
```

---

## 🛠️ Manuelle Nutzung (Kommandozeile)

Auch für menschliche Entwickler sind die Skripte extrem nützlich. Beide Skripte teilen sich exakt dieselbe Syntax:

```bash
python skills/code-indexer/index_java_methods.py [OPTIONEN] <project_root>
python skills/code-indexer/index_python_methods.py [OPTIONEN] <project_root>
```

**Pflichtargument:**
* `<project_root>`: Der Pfad zum Quellcode. Für Projekte mit mehreren Modulen empfiehlt sich `.`, um alles rekursiv zu erfassen.

**Optionale Filter:**
* `--pkg <Name>`: Filtert nach Java-Paketen oder Python-Modulpfaden (Wildcards `*` erlaubt).
* `--class <Name>`: Filtert nach einer Klasse oder einem Interface (Teilstring-Suche).
* `--func <Name>`: Sucht gezielt nach Methoden oder freien Funktionen.

*(Hinweis: Werden mehrere Filter kombiniert, wirken sie als **logisches UND** - alle Bedingungen müssen erfüllt sein).*

**Beispiel:**
```bash
# Finde alle "update"-Methoden in "Client"-Klassen im aktuellen Java-Projekt
python skills/code-indexer/index_java_methods.py --pkg xray.client --class Client --func update .
```

## ⚙️ Wie es funktioniert (Caching)
Um bei großen Projekten blitzschnell zu sein, parsen die Skripte nur geänderte Dateien neu. Der Index wird automatisch in deinem Projekt-Root im Ordner `.cache/` (z.B. `.cache/list_python_methods_cache.json`) abgelegt. Es ist empfehlenswert, `.cache/` in deine `.gitignore` aufzunehmen.
## ?? Detaillierte Dokumentation
F�r einen tiefen Einblick in die Architektur, Caching-Mechanismen und erweiterte CLI-Kombinationen, siehe [docs/DOKUMENTATION.md](docs/DOKUMENTATION.md).
