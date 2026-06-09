import argparse
import bisect
import fnmatch
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from subprocess import PIPE, Popen


class LspClient:
    def __init__(self, command, cwd):
        self.process = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=cwd)
        self._next_id = 1
        self._pending = {}
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._drain_stderr_loop, daemon=True)
        self._stderr_reader.start()

    def _drain_stderr_loop(self):
        if self.process.stderr is None:
            return
        while True:
            line = self.process.stderr.readline()
            if not line:
                return

    def _read_loop(self):
        while True:
            message = self._read_message()
            if message is None:
                return
            msg_id = message.get("id")
            if msg_id is None:
                continue
            with self._lock:
                entry = self._pending.get(msg_id)
            if entry is None:
                continue
            entry["response"] = message
            entry["event"].set()

    def _read_message(self):
        if self.process.stdout is None:
            return None
        headers = {}
        while True:
            line = self.process.stdout.readline()
            if not line:
                return None
            line = line.decode("utf-8").strip()
            if line == "":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if length == 0:
            return None
        body = self.process.stdout.read(length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def _send(self, payload):
        if self.process.stdin is None:
            return
        data = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8")
        self.process.stdin.write(header + data)
        self.process.stdin.flush()

    def request(self, method, params, timeout=30):
        with self._lock:
            msg_id = self._next_id
            self._next_id += 1
            event = threading.Event()
            self._pending[msg_id] = {"event": event, "response": None}
        try:
            self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
            if not event.wait(timeout=timeout):
                raise TimeoutError(f"Timeout waiting for {method}")
            with self._lock:
                entry = self._pending.get(msg_id)
                response = entry["response"] if entry else None
        finally:
            with self._lock:
                self._pending.pop(msg_id, None)
        if response is None:
            raise RuntimeError(f"No response for {method}")
        if "error" in response:
            raise RuntimeError(response["error"])
        return response.get("result")

    def notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def shutdown(self):
        try:
            self.request("shutdown", {}, timeout=10)
        except Exception:
            pass
        self.notify("exit", {})
        try:
            self.process.terminate()
        except Exception:
            pass


def to_uri(path):
    return Path(path).resolve().as_uri()


def find_java_files(root):
    ignore = {".git", "target", "build", ".idea", ".gradle", ".mvn"}
    result = []

    def _scan(directory):
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in ignore:
                            _scan(entry.path)
                    elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".java"):
                        try:
                            mtime = entry.stat().st_mtime
                            result.append((entry.path, mtime))
                        except OSError:
                            pass
        except PermissionError:
            pass

    _scan(root)
    return result


def read_package_name(text):
    match = re.search(r"package\s+([\w.]+);", text)
    return match.group(1) if match else "default"


def symbol_kind(kind):
    if kind == 5:
        return "C"
    if kind == 11:
        return "I"
    if kind == 10:
        return "E"
    return "U"


def is_method_kind(kind):
    return kind in {6, 9, 12}


def extract_from_document_symbols(symbols):
    result = []

    def method_range_info(symbol):
        method_range = symbol.get("range") or symbol.get("selectionRange") or {}
        start = method_range.get("start", {}).get("line")
        end = method_range.get("end", {}).get("line")
        if start is not None:
            start += 1
        if end is not None:
            end += 1
        return start, end

    def class_display_name(name, start_line):
        if name:
            return name
        if start_line is not None:
            return f"Anonymous@L{start_line}"
        return "Anonymous"

    def visit(symbol, parent_name=None):
        kind = symbol.get("kind")
        if kind not in {5, 10, 11}:
            return
        start_line, _ = method_range_info(symbol)
        class_name = class_display_name(symbol.get("name", ""), start_line)
        if parent_name:
            class_name = f"{parent_name}.{class_name}"
        children = symbol.get("children", [])
        methods = []
        for child in children:
            if is_method_kind(child.get("kind")):
                name = child.get("name", "")
                detail = child.get("detail", "")
                start, end = method_range_info(child)
                methods.append((name, detail, start, end))
        result.append((class_name, kind, methods))
        for child in children:
            if child.get("kind") in {5, 10, 11}:
                visit(child, class_name)

    for sym in symbols:
        if sym.get("kind") in {5, 10, 11}:
            visit(sym)

    return result


def extract_from_symbol_information(symbols):
    grouped = {}
    for sym in symbols:
        if not is_method_kind(sym.get("kind")):
            continue
        container = sym.get("containerName") or ""
        loc_range = (sym.get("location") or {}).get("range", {})
        start = loc_range.get("start", {}).get("line")
        end = loc_range.get("end", {}).get("line")
        if start is not None:
            start += 1
        if end is not None:
            end += 1
        grouped.setdefault(container, []).append((sym.get("name", ""), "", start, end))
    result = []
    for container, methods in grouped.items():
        result.append((container, 5, methods))
    return result


def format_method(name, detail, start_line, end_line):
    if detail:
        signature = f"{name}{detail}" if detail.startswith("(") else f"{name} {detail}"
    else:
        signature = name
    if start_line and end_line:
        return f"{signature}  [L{start_line}-L{end_line}]"
    if start_line:
        return f"{signature}  [L{start_line}]"
    return signature


def strip_comments_and_strings(text):
    result = []
    i = 0
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_char = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                result.append(ch)
            else:
                result.append(" ")
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                result.append(" ")
                result.append(" ")
                i += 2
            else:
                result.append(" " if ch != "\n" else "\n")
                i += 1
            continue
        if in_string:
            if ch == "\\" and nxt:
                result.append(" ")
                result.append(" ")
                i += 2
                continue
            if ch == '"':
                in_string = False
            result.append(" " if ch != "\n" else "\n")
            i += 1
            continue
        if in_char:
            if ch == "\\" and nxt:
                result.append(" ")
                result.append(" ")
                i += 2
                continue
            if ch == "'":
                in_char = False
            result.append(" ")
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            result.append(" ")
            result.append(" ")
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            result.append(" ")
            result.append(" ")
            i += 2
            continue
        if ch == '"':
            in_string = True
            result.append(" ")
            i += 1
            continue
        if ch == "'":
            in_char = True
            result.append(" ")
            i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def build_line_starts(text):
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def line_from_index(line_starts, index):
    return bisect.bisect_right(line_starts, index) - 1


def find_matching_brace(text, start_index):
    depth = 0
    for i in range(start_index, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_method_segment(segment, class_simple_name):
    segment = segment.strip()
    if not segment:
        return None
    if re.search(r"\b(class|interface|enum)\b", segment):
        return None
    first_word = segment.split(None, 1)[0]
    if first_word in {"if", "for", "while", "switch", "catch", "try", "do", "synchronized"}:
        return None
    method_match = re.search(
        r"([A-Za-z_][\w<>\[\],\s]*)\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)\s*(?:throws\s+[^\{]+)?$",
        segment,
        re.DOTALL,
    )
    if not method_match:
        return None
    raw_return = " ".join(method_match.group(1).split())
    name = method_match.group(2)
    params = " ".join(method_match.group(3).split())
    modifiers = {
        "public",
        "protected",
        "private",
        "static",
        "final",
        "abstract",
        "synchronized",
        "native",
        "strictfp",
        "default",
    }
    return_tokens = [token for token in raw_return.split() if token not in modifiers]
    return_type = " ".join(return_tokens)
    if name == class_simple_name and not return_type:
        detail = f"({params})" if params else "()"
        return name, detail
    if not return_type:
        return None
    detail = f"({params})" if params else "()"
    detail = f"{detail}  : {return_type}"
    return name, detail


def extract_parsed_class_entries(text):
    clean = strip_comments_and_strings(text)
    line_starts = build_line_starts(text)
    class_pattern = re.compile(r"\b(class|interface|enum)\s+([A-Za-z_][\w]*)\b")
    anon_pattern = re.compile(r"\bnew\s+[^;\{]+?\)\s*\{", re.DOTALL)
    blocks = []

    for match in class_pattern.finditer(clean):
        brace_start = clean.find("{", match.end())
        if brace_start == -1:
            continue
        brace_end = find_matching_brace(clean, brace_start)
        if brace_end == -1:
            continue
        blocks.append(
            {
                "name": match.group(2),
                "brace_start": brace_start,
                "brace_end": brace_end,
                "start_line": line_from_index(line_starts, brace_start) + 1,
                "end_line": line_from_index(line_starts, brace_end) + 1,
            }
        )

    for match in anon_pattern.finditer(clean):
        brace_start = match.end() - 1
        brace_end = find_matching_brace(clean, brace_start)
        if brace_end == -1:
            continue
        start_line = line_from_index(line_starts, brace_start) + 1
        blocks.append(
            {
                "name": f"Anonymous@L{start_line}",
                "brace_start": brace_start,
                "brace_end": brace_end,
                "start_line": start_line,
                "end_line": line_from_index(line_starts, brace_end) + 1,
            }
        )

    for block in blocks:
        parent = None
        for candidate in blocks:
            if candidate is block:
                continue
            if (
                candidate["brace_start"] < block["brace_start"]
                and candidate["brace_end"] > block["brace_end"]
            ):
                if parent is None or (
                    candidate["brace_end"] - candidate["brace_start"]
                    < parent["brace_end"] - parent["brace_start"]
                ):
                    parent = candidate
        block["parent"] = parent

    for block in blocks:
        if block["parent"]:
            block["full_name"] = f"{block['parent']['full_name']}.{block['name']}"
        else:
            block["full_name"] = block["name"]

    for block in blocks:
        methods = []
        start = block["brace_start"] + 1
        end = block["brace_end"]
        depth = 0
        segment_start = start
        i = start
        class_simple = block["name"]
        while i < end:
            ch = clean[i]
            if ch == "{":
                if depth == 0:
                    segment = clean[segment_start:i]
                    parsed = parse_method_segment(segment, class_simple)
                    if parsed:
                        name, detail = parsed
                        method_end = find_matching_brace(clean, i)
                        if method_end == -1 or method_end > end:
                            method_end = i
                        start_line = line_from_index(line_starts, segment_start) + 1
                        end_line = line_from_index(line_starts, method_end) + 1
                        methods.append((name, detail, start_line, end_line))
                    segment_start = i + 1
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    segment_start = i + 1
            elif ch == ";" and depth == 0:
                segment_start = i + 1
            i += 1
        block["methods"] = methods

    entries = []
    for block in blocks:
        entries.append((block["full_name"], 5, block["methods"]))
    return entries


def merge_parsed_entries(entries, parsed_entries):
    by_name = {name: (kind, methods) for name, kind, methods in entries}
    for name, kind, methods in parsed_entries:
        if name in by_name:
            existing_kind, existing_methods = by_name[name]
            if not existing_methods and methods:
                by_name[name] = (existing_kind, methods)
        else:
            by_name[name] = (kind, methods)
    merged = [(name, kind, methods) for name, (kind, methods) in by_name.items()]
    return merged


def normalize_entries(entries):
    normalized = []
    for item in entries:
        if len(item) == 4:
            class_name, kind, methods, file_stem = item
        elif len(item) == 3:
            class_name, kind, methods = item
            file_stem = None
        else:
            continue
        updated = []
        for method in methods:
            if len(method) == 4:
                name, detail, start_line, end_line = method
            elif len(method) == 2:
                name, detail = method
                start_line = None
                end_line = None
            else:
                continue
            updated.append((name, detail, start_line, end_line))
        normalized.append((class_name, kind, updated, file_stem))
    return normalized


def entries_have_line_info(entries):
    for _, _, methods, file_stem in entries:
        if not file_stem:
            return False
        for _, _, start_line, end_line in methods:
            if start_line is not None or end_line is not None:
                return True
    return False


CACHE_FILE = ".cache/list_methods_cache.json"
CACHE_VERSION = 2


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def matches_wildcard(value, pattern):
    if not pattern:
        return True
    return fnmatch.fnmatchcase(value, pattern)


def main():
    parser = argparse.ArgumentParser(
        description="Index Java classes and methods grouped by package."
    )
    parser.add_argument("project_root", help="Root directory to scan for .java files")
    parser.add_argument(
        "--pkg",
        help="Filter packages with wildcard (*, ?) on package name",
    )
    parser.add_argument(
        "--class",
        dest="class_filter",
        help="Filter classes with wildcard (*, ?) on class name",
    )
    parser.add_argument(
        "--func",
        dest="func_filter",
        help="Filter methods with wildcard (*, ?) on method name",
    )

    args = parser.parse_args()

    root = os.path.abspath(args.project_root)
    files = find_java_files(root)
    by_package = {}
    cache = load_cache()
    new_cache = {}
    client = None

    for path, mtime in files:
        cached_entry = cache.get(path)
        if (
            cached_entry
            and cached_entry.get("mtime") == mtime
            and cached_entry.get("version") == CACHE_VERSION
        ):
            package = cached_entry["package"]
            entries = normalize_entries(cached_entry["entries"])
            if entries_have_line_info(entries):
                by_package.setdefault(package, []).extend(entries)
                new_cache[path] = {
                    "mtime": mtime,
                    "package": package,
                    "entries": entries,
                    "version": CACHE_VERSION,
                }
                continue

        if client is None:
            client = LspClient(["jdtls"], cwd=root)
            init_params = {
                "processId": os.getpid(),
                "rootUri": to_uri(root),
                "capabilities": {
                    "textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}}
                },
                "workspaceFolders": [{"uri": to_uri(root), "name": os.path.basename(root)}],
            }
            client.request("initialize", init_params, timeout=60)
            client.notify("initialized", {})

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        uri = to_uri(path)
        opened = False
        try:
            client.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "java",
                        "version": 1,
                        "text": text,
                    }
                },
            )
            opened = True
            for _ in range(3):
                try:
                    symbols = client.request(
                        "textDocument/documentSymbol",
                        {"textDocument": {"uri": uri}},
                        timeout=30,
                    )
                    if symbols is not None:
                        break
                except TimeoutError:
                    time.sleep(0.3)
            else:
                continue

            package = read_package_name(text)
            if symbols and isinstance(symbols, list) and "kind" in symbols[0]:
                entries = extract_from_document_symbols(symbols)
            else:
                entries = extract_from_symbol_information(symbols or [])

            parsed_entries = extract_parsed_class_entries(text)
            entries = merge_parsed_entries(entries, parsed_entries)

            if entries:
                entries = [(name, kind, methods, Path(path).stem) for name, kind, methods in entries]
                by_package.setdefault(package, []).extend(entries)
            new_cache[path] = {
                "mtime": mtime,
                "package": package,
                "entries": entries,
                "version": CACHE_VERSION,
            }
        finally:
            if opened:
                try:
                    client.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
                except Exception:
                    pass

    total_matches = 0
    for package in sorted(by_package.keys()):
        if not matches_wildcard(package, args.pkg):
            continue

        classes = sorted(by_package[package], key=lambda x: x[0])
        filtered_classes = []
        for class_name, kind, methods, file_stem in classes:
            if args.class_filter and not matches_wildcard(class_name, args.class_filter):
                continue

            filtered_methods = methods
            if args.func_filter:
                filtered_methods = [
                    method
                    for method in methods
                    if method[0] and matches_wildcard(method[0], args.func_filter)
                ]

            if args.func_filter and not filtered_methods:
                continue

            filtered_classes.append((class_name, kind, filtered_methods, file_stem))

        if not filtered_classes:
            continue

        print(f"PACKAGE {package}")
        for class_name, kind, methods, file_stem in filtered_classes:
            kind_icon = symbol_kind(kind)
            print(f"  {kind_icon} {class_name}")
            indent = "    "
            for name, detail, start_line, end_line in methods:
                if not name:
                    continue
                print(f"{indent}- {format_method(name, detail, start_line, end_line)}")
                total_matches += 1
        print("")

    if total_matches == 0:
        print("No matches found.")

    if client:
        client.shutdown()
    save_cache(new_cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
