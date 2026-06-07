import argparse
import ast
import fnmatch
import json
import os
from pathlib import Path


CACHE_FILE = ".cache/list_python_methods_cache.json"
CACHE_VERSION = 1


def find_python_files(root):
    ignore = {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
        "target",
    }
    result = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignore]
        for name in files:
            if name.endswith(".py"):
                result.append(os.path.join(current, name))
    return result


def module_and_package_from_path(root, path):
    rel = os.path.relpath(path, root)
    rel_posix = rel.replace("\\", "/")
    no_ext = rel_posix[:-3] if rel_posix.endswith(".py") else rel_posix
    parts = [p for p in no_ext.split("/") if p and p != "."]

    if not parts:
        return "default", "default"

    if parts[-1] == "__init__":
        module_parts = parts[:-1]
    else:
        module_parts = parts

    module_name = ".".join(module_parts) if module_parts else "default"
    package_name = ".".join(module_parts[:-1]) if len(module_parts) > 1 else "default"
    return module_name, package_name


def symbol_kind(kind):
    if kind == "class":
        return "C"
    if kind == "module":
        return "M"
    return "U"


def format_method(name, detail, start_line, end_line):
    signature = f"{name}{detail}" if detail else name
    if start_line and end_line:
        return f"{signature}  [L{start_line}-L{end_line}]"
    if start_line:
        return f"{signature}  [L{start_line}]"
    return signature


def annotation_to_text(node):
    if node is None:
        return None
    text = ast.unparse(node)
    return text if text else None


def arg_to_text(arg):
    if arg is None:
        return ""
    name = arg.arg
    anno = annotation_to_text(arg.annotation)
    if anno:
        return f"{name}: {anno}"
    return name


def build_signature(node):
    args = node.args
    params = []

    posonly = list(getattr(args, "posonlyargs", []))
    regular = list(args.args)
    defaults = list(args.defaults)

    positional = posonly + regular
    default_start = len(positional) - len(defaults)

    for i, arg in enumerate(positional):
        text = arg_to_text(arg)
        if i >= default_start and default_start >= 0:
            default_node = defaults[i - default_start]
            text += f"={ast.unparse(default_node)}"
        params.append(text)

    if posonly:
        params.insert(len(posonly), "/")

    if args.vararg is not None:
        params.append(f"*{arg_to_text(args.vararg)}")
    elif args.kwonlyargs:
        params.append("*")

    for kwarg, kwdefault in zip(args.kwonlyargs, args.kw_defaults):
        text = arg_to_text(kwarg)
        if kwdefault is not None:
            text += f"={ast.unparse(kwdefault)}"
        params.append(text)

    if args.kwarg is not None:
        params.append(f"**{arg_to_text(args.kwarg)}")

    detail = "(" + ", ".join(params) + ")"
    ret = annotation_to_text(getattr(node, "returns", None))
    if ret:
        detail += f"  : {ret}"
    return detail


def extract_entries_from_ast(text, module_name):
    tree = ast.parse(text)
    entries = []

    module_functions = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.class_stack = []

        def _class_name(self, name):
            if not self.class_stack:
                return name
            return f"{self.class_stack[-1]}.{name}"

        def _method_tuple(self, node):
            name = node.name
            detail = build_signature(node)
            start_line = getattr(node, "lineno", None)
            end_line = getattr(node, "end_lineno", None)
            return (name, detail, start_line, end_line)

        def visit_ClassDef(self, node):
            full_name = self._class_name(node.name)
            methods = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(self._method_tuple(child))

            entries.append((full_name, "class", methods, Path(module_name).stem))

            self.class_stack.append(full_name)
            for child in node.body:
                if isinstance(child, ast.ClassDef):
                    self.visit(child)
            self.class_stack.pop()

        def visit_FunctionDef(self, node):
            if not self.class_stack:
                module_functions.append(self._method_tuple(node))

        def visit_AsyncFunctionDef(self, node):
            if not self.class_stack:
                module_functions.append(self._method_tuple(node))

    Visitor().visit(tree)

    if module_functions:
        module_entry_name = module_name if module_name != "default" else "<root-module>"
        entries.append((module_entry_name, "module", module_functions, Path(module_name).stem))

    return entries


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
        description="Index Python classes and functions grouped by package/module."
    )
    parser.add_argument("project_root", help="Root directory to scan for .py files")
    parser.add_argument(
        "--pkg",
        help="Filter packages with wildcard (*, ?) on package name",
    )
    parser.add_argument(
        "--class",
        dest="class_filter",
        help="Filter classes/modules with wildcard (*, ?) on class/module name",
    )
    parser.add_argument(
        "--func",
        dest="func_filter",
        help="Filter functions/methods with wildcard (*, ?) on function name",
    )

    args = parser.parse_args()

    root = os.path.abspath(args.project_root)
    files = find_python_files(root)
    by_package = {}
    cache = load_cache()
    new_cache = {}

    for path in files:
        mtime = os.path.getmtime(path)
        cached_entry = cache.get(path)
        if (
            cached_entry
            and cached_entry.get("mtime") == mtime
            and cached_entry.get("version") == CACHE_VERSION
        ):
            package = cached_entry.get("package", "default")
            entries = cached_entry.get("entries", [])
            by_package.setdefault(package, []).extend(entries)
            new_cache[path] = cached_entry
            continue

        module_name, package = module_and_package_from_path(root, path)

        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

        try:
            entries = extract_entries_from_ast(text, module_name)
        except SyntaxError:
            entries = []

        if entries:
            by_package.setdefault(package, []).extend(entries)

        new_cache[path] = {
            "mtime": mtime,
            "package": package,
            "entries": entries,
            "version": CACHE_VERSION,
        }

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
        for class_name, kind, methods, _ in filtered_classes:
            print(f"  {symbol_kind(kind)} {class_name}")
            for name, detail, start_line, end_line in methods:
                if not name:
                    continue
                print(f"    - {format_method(name, detail, start_line, end_line)}")
                total_matches += 1
        print("")

    if total_matches == 0:
        print("No matches found.")

    save_cache(new_cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
