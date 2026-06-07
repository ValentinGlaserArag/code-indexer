[🇺🇸 English](DOCUMENTATION.md) | [🇩🇪 Deutsch](DOKUMENTATION_DE.md)

# Ausführliche Dokumentation: Code-Indexer

Diese Dokumentation richtet sich an Entwickler und Systemarchitekten, die verstehen wollen, wie der `code-indexer` im Detail funktioniert, warum er für KI-Agenten unverzichtbar ist und wie man ihn über die Kommandozeile optimal nutzt.

---

## 1. Konzept & Philosophie (Der "Röntgenblick")

KI-Sprachmodelle (LLMs) wie Claude, GPT-4 oder Gemini haben begrenzte Kontextfenster. Wenn ein KI-Agent eine Codebasis analysieren soll, verliert er oft wertvolle Token (und damit "Denkkapazität") beim bloßen Suchen und Lesen ganzer Dateien.

**Die Lösung:** Der Code-Indexer trennt das *Finden* vom *Lesen*.
Er scannt den Quellcode und extrahiert lediglich die architektonischen Signaturen (Pakete, Module, Klassennamen, Methodensignaturen und deren Zeilennummern). 

### Der ROI (Return on Investment) für KI-Agenten
* **Vermeidung von Halluzinationen:** Die KI erfindet keine Methodennamen oder Parameter mehr, wenn sie ein neues Feature integrieren soll. Der Index liefert ihr den strikten Vertrag (API) der bestehenden Codebasis.
* **Massive Token-Ersparnis:** Ein Index über 50 Klassen verbraucht weniger Token als das vollständige Einlesen von 2-3 großen Java/Python-Dateien.
* **Laser-Fokus beim Lesen:** Da der Index exakte Zeilennummern ausgibt (z.B. `[L15-L42]`), kann die KI gezielt nur diese 27 Zeilen mit einem Dateilese-Tool in ihren Kontext laden, anstatt eine 1000-Zeilen-Datei parsen zu müssen.

---

## 2. Technische Funktionsweise & Caching

Die Skripte (`skills/code-indexer/index_java_methods.py` und `skills/code-indexer/index_python_methods.py`) nutzen strukturelles Parsen (Regex/AST), um Code zu verstehen. 
**Sie erfordern keine Kompilierung!** Weder Maven, Gradle noch ein aktives Python-Environment (venv) müssen gestartet werden.

### Intelligentes Caching
Um bei großen Monolithen (Projekte mit >1000 Dateien) Verzögerungen zu vermeiden, nutzen die Skripte ein Caching-System:
1. Beim ersten Lauf wird das Projekt analysiert.
2. Das Ergebnis wird in `<project_root>/.cache/list_methods_cache.json` (bzw. `list_python_methods_cache.json`) gespeichert.
3. Bei jedem weiteren Lauf wird nur noch das Änderungsdatum (`mtime`) der Dateien geprüft. Nur Code-Dateien, die du oder die KI gerade bearbeitet haben, werden neu geparst. Der Rest wird in Millisekunden aus dem Cache geladen.

*(Tipp: Füge `.cache/` zu deiner `.gitignore` hinzu).*

### Voraussetzungen für die Ausführung & JDTLS-Einrichtung
Im Gegensatz zu anderen Deep-Analysis-Tools (die beispielsweise SQLite, Node.js-Toolchains oder das Kompilieren lokaler Binär-Bindings wie `tree-sitter` erfordern), ist `code-indexer` extrem leichtgewichtig und erfordert keinerlei Installation von externen Python-Bibliotheken (Pip-Packages).

*   **Python-Voraussetzung**: Python 3.9+ wird benötigt, da der Parser die in Python 3.9 eingeführte Funktion `ast.unparse` nutzt, um die Signaturen sauber zu formatieren.
*   **Java-Voraussetzung (`jdtls`)**: Der Java-Indexer kommuniziert direkt über Standard-Input/Output-Streams mit einer lokalen Instanz des Eclipse JDT Language Server (`jdtls`). Zur Indizierung von Java:
    1.  Stellen Sie sicher, dass **Java JDK 17+** auf Ihrem System installiert ist.
    2.  Installieren Sie `jdtls` und fügen Sie die ausführbare Datei zum `PATH` Ihres Systems hinzu.

---

## 3. CLI Referenz (Kommandozeilen-Argumente)

Beide Skripte teilen sich exakt dieselbe Syntax und Funktionalität.

### Allgemeine Syntax
```bash
python skills/code-indexer/index_java_methods.py [OPTIONEN] <project_root>
python skills/code-indexer/index_python_methods.py [OPTIONEN] <project_root>
```

### Pflichtargument
* `<project_root>`
  Der Pfad zum Quellcode. 
  **Best Practice:** Übergib immer `.` (das aktuelle Verzeichnis). Das Skript durchsucht rekursiv alle Unterordner. Das ist besonders wichtig bei Multi-Modul-Projekten (z.B. Maven-Projekte mit mehreren `src/main/java`-Ordnern).

### Optionale Filter
Wenn man den Index im Terminal liest, kann die Ausgabe bei großen Projekten überwältigend sein. Nutzen Sie die Filter, um den Baum auf die relevanten Äste zu stutzen. Wildcards (`*`, `?`) werden unterstützt.

#### `--pkg <Name>` (Package/Modul-Filter)
Filtert die Ausgabe nach Ordner-Strukturen, Java-Paketen oder Python-Modulpfaden.
* **Java:** `python skills/code-indexer/index_java_methods.py --pkg de.aragit.xray.auth .`
* **Python:** `python skills/code-indexer/index_python_methods.py --pkg xray.auth .`

#### `--class <Name>` (Klassen-Filter)
Zeigt nur die Struktur einer bestimmten Klasse oder eines Interfaces an. Funktioniert als Teilstring-Suche (z.B. findet `Client` sowohl `ApiClient` als auch `DbClient`).
* **Java:** `python skills/code-indexer/index_java_methods.py --class JiraClientImpl .`
* **Python:** `python skills/code-indexer/index_python_methods.py --class JiraServer .`

#### `--func <Name>` (Methoden-/Funktions-Filter)
Sucht dateiübergreifend nach Methoden oder Funktionen. Perfekt, um z.B. herauszufinden, welche Klassen ein bestimmtes Interface implementieren.
* **Java:** `python skills/code-indexer/index_java_methods.py --func getById .`
* **Python:** `python skills/code-indexer/index_python_methods.py --func test_* .`

---

## 4. Beispiele für kombinierte Suchen

Die wahre Stärke im Terminal liegt in der Kombination der Filter. **Hinweis:** Wenn du mehrere Filter gleichzeitig verwendest (`--pkg`, `--class`, `--func`), wirken diese als **logisches UND**. Das Skript zeigt nur Treffer an, die *alle* Bedingungen gleichzeitig erfüllen.

**Szenario 1: Java-Refactoring**
Finde alle Methoden, die "update" im Namen tragen, in allen Klassen, die "Client" heißen, aber nur innerhalb des Pakets "xray.client":
```bash
python skills/code-indexer/index_java_methods.py --pkg xray.client --class Client --func update .
```

**Szenario 2: Python-Tests überprüfen**
Finde alle Setup-Funktionen in den Modulen, die das Wort "test" beinhalten:
```bash
python skills/code-indexer/index_python_methods.py --pkg *test* --func setup* .
```