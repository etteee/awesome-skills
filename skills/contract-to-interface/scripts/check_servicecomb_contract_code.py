#!/usr/bin/env python3
"""Reject handwritten ServiceComb interfaces and their reachable DTOs.

The checker has no third-party runtime dependencies. It deliberately uses a
conservative Java source parser: it understands declarations, annotations,
method signatures, fields, records, imports, and balanced Java delimiters, but
does not attempt full symbol attribution. Ambiguous symbols are not guessed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_CONFIG = (
    Path(__file__).resolve().parent.parent
    / "references"
    / "servicecomb-contract-policy.json"
)
IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
QUALIFIED_IDENTIFIER = rf"{IDENTIFIER}(?:\.{IDENTIFIER})*"
JAVA_MODIFIERS = {
    "public",
    "protected",
    "private",
    "static",
    "final",
    "abstract",
    "default",
    "synchronized",
    "native",
    "strictfp",
    "transient",
    "volatile",
    "sealed",
    "non-sealed",
}
NON_TYPE_TOKENS = JAVA_MODIFIERS | {
    "extends",
    "super",
    "throws",
    "void",
    "byte",
    "short",
    "int",
    "long",
    "float",
    "double",
    "boolean",
    "char",
    "var",
    "class",
    "interface",
    "record",
    "enum",
}
CONTROL_WORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "synchronized",
    "new",
    "return",
    "throw",
    "assert",
}


@dataclass
class SourceFile:
    path: str
    text: str
    comments_removed: str
    structure_mask: str
    package: str
    imports: dict[str, str]
    wildcard_imports: list[str]
    declarations: list["TypeDecl"] = field(default_factory=list)


@dataclass
class TypeDecl:
    source: SourceFile
    kind: str
    name: str
    fqcn: str
    start: int
    open_brace: int
    end: int
    context_start: int
    header: str
    body: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.source.path, self.start)

    @property
    def context(self) -> str:
        return self.source.comments_removed[self.context_start : self.end]

    @property
    def line(self) -> int:
        return line_number(self.source.text, self.start)


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str


class PolicyError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detect handwritten ServiceComb contracts and DTOs in Java sources."
        )
    )
    parser.add_argument(
        "--repo-root", type=Path, default=Path.cwd(), help="Git repository root."
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="Policy JSON file."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="Check the Git index.")
    mode.add_argument("--all", action="store_true", help="Check all tracked Java files.")
    mode.add_argument(
        "--files", nargs="+", metavar="FILE", help="Check selected working-tree files."
    )
    mode.add_argument(
        "--base", help="Check Java files changed from this Git revision to --head."
    )
    parser.add_argument("--head", default="HEAD", help="Head revision for --base mode.")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="Output format."
    )
    return parser.parse_args()


def run_git(repo: Path, args: Sequence[str], *, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PolicyError(f"git {' '.join(args)} failed: {detail}")
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="replace")


def zero_paths(raw: str | bytes) -> list[str]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="surrogateescape")
    return [path for path in raw.split("\0") if path]


def normalize_path(repo: Path, raw_path: str | Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(repo.resolve())
        except ValueError as error:
            raise PolicyError(f"path is outside repository: {raw_path}") from error
    return path.as_posix().lstrip("./")


def is_java(path: str) -> bool:
    return path.endswith(".java")


def git_paths(repo: Path, args: Sequence[str]) -> list[str]:
    return [path for path in zero_paths(run_git(repo, args, binary=True)) if is_java(path)]


def select_sources(
    args: argparse.Namespace,
) -> tuple[list[str], list[str], str | None]:
    repo = args.repo_root.resolve()
    if args.staged:
        candidates = git_paths(
            repo,
            ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        )
        universe = git_paths(repo, ["ls-files", "-z", "--", "*.java"])
        return sorted(set(candidates)), sorted(set(universe)), ":"
    if args.base:
        candidates = git_paths(
            repo,
            ["diff", "--name-only", "--diff-filter=ACMR", "-z", args.base, args.head],
        )
        universe = git_paths(
            repo, ["ls-tree", "-r", "--name-only", "-z", args.head, "--", "*.java"]
        )
        return sorted(set(candidates)), sorted(set(universe)), args.head
    if args.files:
        candidates = [normalize_path(repo, path) for path in args.files if is_java(str(path))]
        try:
            universe = git_paths(repo, ["ls-files", "-z", "--", "*.java"])
        except PolicyError:
            universe = []
        return sorted(set(candidates)), sorted(set(universe + candidates)), None

    universe = git_paths(repo, ["ls-files", "-z", "--", "*.java"])
    return sorted(set(universe)), sorted(set(universe)), None


def read_source(repo: Path, path: str, revision: str | None) -> str:
    if revision == ":":
        return str(run_git(repo, ["show", f":{path}"]))
    if revision:
        return str(run_git(repo, ["show", f"{revision}:{path}"]))
    try:
        return (repo / path).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise PolicyError(f"Java source is not UTF-8: {path}") from error


def mask_java(text: str, *, mask_literals: bool) -> str:
    output = list(text)
    state = "code"
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if char == "/" and next_char == "/":
                output[index] = output[index + 1] = " "
                state = "line-comment"
                index += 2
                continue
            if char == "/" and next_char == "*":
                output[index] = output[index + 1] = " "
                state = "block-comment"
                index += 2
                continue
            if char in {'"', "'"}:
                quote = char
                state = "literal"
                if mask_literals:
                    output[index] = " "
                index += 1
                continue
        elif state == "line-comment":
            if char == "\n":
                state = "code"
            else:
                output[index] = " "
            index += 1
            continue
        elif state == "block-comment":
            if char == "*" and next_char == "/":
                output[index] = output[index + 1] = " "
                state = "code"
                index += 2
                continue
            if char != "\n":
                output[index] = " "
            index += 1
            continue
        elif state == "literal":
            if mask_literals and char != "\n":
                output[index] = " "
            if char == "\\":
                if index + 1 < len(text):
                    if mask_literals and text[index + 1] != "\n":
                        output[index + 1] = " "
                    index += 2
                    continue
            elif char == quote:
                state = "code"
            index += 1
            continue
        index += 1
    return "".join(output)


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def matching_delimiter(text: str, start: int, opening: str, closing: str) -> int:
    if start >= len(text) or text[start] != opening:
        return -1
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return -1


def resolve_imported_name(source: SourceFile, raw_name: str, allowed: set[str]) -> str | None:
    if "." in raw_name:
        return raw_name if raw_name in allowed else None
    imported = source.imports.get(raw_name)
    if imported in allowed:
        return imported
    wildcard_matches = [
        f"{package}.{raw_name}"
        for package in source.wildcard_imports
        if f"{package}.{raw_name}" in allowed
    ]
    return wildcard_matches[0] if len(wildcard_matches) == 1 else None


def annotation_occurrences(
    source: SourceFile,
    configured_types: Iterable[str],
    *,
    start: int = 0,
    end: int | None = None,
) -> list[tuple[str, int, str]]:
    allowed = set(configured_types)
    end = len(source.comments_removed) if end is None else end
    structural = source.structure_mask[start:end]
    original = source.comments_removed[start:end]
    occurrences: list[tuple[str, int, str]] = []
    for match in re.finditer(rf"@({QUALIFIED_IDENTIFIER})\b", structural):
        raw_name = match.group(1)
        resolved = resolve_imported_name(source, raw_name, allowed)
        if not resolved:
            continue
        cursor = match.end()
        while cursor < len(structural) and structural[cursor].isspace():
            cursor += 1
        arguments = ""
        if cursor < len(structural) and structural[cursor] == "(":
            closing = matching_delimiter(structural, cursor, "(", ")")
            if closing >= 0:
                arguments = original[cursor + 1 : closing]
        occurrences.append((resolved.rsplit(".", 1)[-1], start + match.start(), arguments))
    return occurrences


def remove_annotations(text: str) -> str:
    structural = mask_java(text, mask_literals=True)
    output = list(text)
    cursor = 0
    pattern = re.compile(rf"@{QUALIFIED_IDENTIFIER}")
    while True:
        match = pattern.search(structural, cursor)
        if not match:
            break
        end = match.end()
        while end < len(structural) and structural[end].isspace():
            end += 1
        if end < len(structural) and structural[end] == "(":
            closing = matching_delimiter(structural, end, "(", ")")
            if closing >= 0:
                end = closing + 1
        for index in range(match.start(), end):
            if output[index] != "\n":
                output[index] = " "
        cursor = max(end, match.end())
    return "".join(output)


def context_start(text: str, declaration_start: int) -> int:
    last_semicolon = text.rfind(";", 0, declaration_start)
    last_brace = text.rfind("}", 0, declaration_start)
    return max(last_semicolon, last_brace) + 1


def parse_source(path: str, text: str) -> SourceFile:
    comments_removed = mask_java(text, mask_literals=False)
    structure_mask = mask_java(text, mask_literals=True)
    package_match = re.search(rf"\bpackage\s+({QUALIFIED_IDENTIFIER})\s*;", comments_removed)
    package = package_match.group(1) if package_match else ""
    imports: dict[str, str] = {}
    wildcard_imports: list[str] = []
    for match in re.finditer(rf"\bimport\s+(?:static\s+)?({QUALIFIED_IDENTIFIER})(\.\*)?\s*;", comments_removed):
        qualified = match.group(1)
        if match.group(2):
            wildcard_imports.append(qualified)
        else:
            imports[qualified.rsplit(".", 1)[-1]] = qualified

    source = SourceFile(
        path,
        text,
        comments_removed,
        structure_mask,
        package,
        imports,
        wildcard_imports,
    )
    declaration_pattern = re.compile(rf"(?<!@)\b(class|interface|record|enum)\s+({IDENTIFIER})\b")
    for match in declaration_pattern.finditer(structure_mask):
        open_brace = structure_mask.find("{", match.end())
        if open_brace < 0:
            continue
        semicolon = structure_mask.find(";", match.end(), open_brace)
        if semicolon >= 0:
            continue
        close_brace = matching_delimiter(structure_mask, open_brace, "{", "}")
        if close_brace < 0:
            continue
        name = match.group(2)
        fqcn = f"{package}.{name}" if package else name
        start = match.start()
        source.declarations.append(
            TypeDecl(
                source=source,
                kind=match.group(1),
                name=name,
                fqcn=fqcn,
                start=start,
                open_brace=open_brace,
                end=close_brace + 1,
                context_start=context_start(comments_removed, start),
                header=comments_removed[start:open_brace],
                body=comments_removed[open_brace + 1 : close_brace],
            )
        )
    return source


class TypeIndex:
    def __init__(self, sources: Iterable[SourceFile]) -> None:
        self.by_fqcn: dict[str, TypeDecl] = {}
        self.by_simple: dict[str, list[TypeDecl]] = {}
        for source in sources:
            for declaration in source.declarations:
                self.by_fqcn.setdefault(declaration.fqcn, declaration)
                self.by_simple.setdefault(declaration.name, []).append(declaration)

    def resolve(self, source: SourceFile, raw_name: str) -> TypeDecl | None:
        name = raw_name.replace("$", ".")
        if name in self.by_fqcn:
            return self.by_fqcn[name]
        simple = name.rsplit(".", 1)[-1]
        imported = source.imports.get(simple)
        if imported and imported in self.by_fqcn:
            return self.by_fqcn[imported]
        same_package = f"{source.package}.{simple}" if source.package else simple
        if same_package in self.by_fqcn:
            return self.by_fqcn[same_package]
        candidates = self.by_simple.get(simple, [])
        return candidates[0] if len(candidates) == 1 else None


def split_top_level(text: str, delimiter: str = ",") -> list[str]:
    pieces: list[str] = []
    start = 0
    depths = {"<": 0, "(": 0, "[": 0}
    closing = {">": "<", ")": "(", "]": "["}
    for index, char in enumerate(text):
        if char in depths:
            depths[char] += 1
        elif char in closing:
            opening = closing[char]
            depths[opening] = max(0, depths[opening] - 1)
        elif char == delimiter and all(depth == 0 for depth in depths.values()):
            pieces.append(text[start:index])
            start = index + 1
    pieces.append(text[start:])
    return pieces


def strip_leading_modifiers(text: str) -> str:
    tokens = text.strip().split()
    while tokens and tokens[0] in JAVA_MODIFIERS:
        tokens.pop(0)
    if tokens and tokens[0].startswith("<"):
        generic_depth = 0
        while tokens:
            token = tokens.pop(0)
            generic_depth += token.count("<") - token.count(">")
            if generic_depth <= 0:
                break
    return " ".join(tokens)


def method_type_expressions(declaration: TypeDecl) -> list[str]:
    body = remove_annotations(declaration.body)
    structural = mask_java(body, mask_literals=True)
    expressions: list[str] = []
    depth = 0
    segment_start = 0
    index = 0
    while index < len(structural):
        char = structural[index]
        if char == "{" and depth == 0:
            depth = 1
            index += 1
            continue
        if char == "{" and depth > 0:
            depth += 1
            index += 1
            continue
        if char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                segment_start = index + 1
            index += 1
            continue
        if depth == 0 and char == ";":
            segment_start = index + 1
            index += 1
            continue
        if depth != 0 or char != "(":
            index += 1
            continue

        close = matching_delimiter(structural, index, "(", ")")
        if close < 0:
            break
        cursor = index - 1
        while cursor >= segment_start and structural[cursor].isspace():
            cursor -= 1
        name_end = cursor + 1
        while cursor >= segment_start and re.match(r"[A-Za-z0-9_$]", structural[cursor]):
            cursor -= 1
        method_name = structural[cursor + 1 : name_end]
        prefix = body[segment_start : cursor + 1].strip()
        suffix = structural[close + 1 :]
        suffix_match = re.match(r"\s*(?:throws\s+[^;{]+)?\s*([;{])", suffix)
        if (
            not method_name
            or method_name in CONTROL_WORDS
            or method_name == declaration.name
            or not suffix_match
            or "=" in prefix
        ):
            index = close + 1
            continue

        return_expression = strip_leading_modifiers(prefix)
        if return_expression:
            expressions.append(return_expression)
        parameters = body[index + 1 : close]
        for parameter in split_top_level(parameters):
            parameter = strip_leading_modifiers(parameter.replace("...", "[]"))
            parameter_match = re.match(r"(.+?)\s+" + IDENTIFIER + r"\s*$", parameter, re.DOTALL)
            if parameter_match:
                expressions.append(parameter_match.group(1).strip())
        index = close + 1
    return expressions


def field_type_expressions(declaration: TypeDecl) -> list[str]:
    body = remove_annotations(declaration.body)
    structural = mask_java(body, mask_literals=True)
    expressions: list[str] = []
    depth = 0
    segment_start = 0
    for index, char in enumerate(structural):
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                segment_start = index + 1
        elif char == ";" and depth == 0:
            statement = body[segment_start:index].strip()
            segment_start = index + 1
            if not statement or "(" in statement:
                continue
            declaration_part = statement.split("=", 1)[0].strip()
            declaration_part = strip_leading_modifiers(declaration_part)
            field_match = re.match(r"(.+?)\s+" + IDENTIFIER + r"(?:\s*\[\])?\s*$", declaration_part, re.DOTALL)
            if field_match:
                expressions.append(field_match.group(1).strip())

    if declaration.kind == "record":
        header_mask = mask_java(declaration.header, mask_literals=True)
        open_paren = header_mask.find("(")
        if open_paren >= 0:
            close_paren = matching_delimiter(header_mask, open_paren, "(", ")")
            if close_paren >= 0:
                components = remove_annotations(declaration.header[open_paren + 1 : close_paren])
                for component in split_top_level(components):
                    component_match = re.match(r"(.+?)\s+" + IDENTIFIER + r"\s*$", component.strip(), re.DOTALL)
                    if component_match:
                        expressions.append(component_match.group(1).strip())
    return expressions


def dto_related_type_expressions(declaration: TypeDecl) -> list[str]:
    expressions = field_type_expressions(declaration)
    body = remove_annotations(declaration.body)
    accessor_pattern = re.compile(
        rf"\b(?:public|protected)\s+"
        rf"(?P<return>[A-Za-z_$][A-Za-z0-9_$.<>, ?\[\]]*)\s+"
        rf"(?P<name>(?:get|is|set){IDENTIFIER})\s*"
        rf"\((?P<parameters>[^()]*)\)",
        re.DOTALL,
    )
    for match in accessor_pattern.finditer(body):
        return_type = match.group("return").strip()
        if return_type != "void":
            expressions.append(return_type)
        for parameter in split_top_level(match.group("parameters")):
            parameter = strip_leading_modifiers(parameter.replace("...", "[]"))
            parameter_match = re.match(
                r"(.+?)\s+" + IDENTIFIER + r"\s*$", parameter, re.DOTALL
            )
            if parameter_match:
                expressions.append(parameter_match.group(1).strip())

    superclass = re.search(
        rf"\bextends\s+({QUALIFIED_IDENTIFIER}(?:\s*<[^>]+>)?)",
        declaration.header,
    )
    if superclass:
        expressions.append(superclass.group(1))
    return expressions


def type_tokens(expression: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(QUALIFIED_IDENTIFIER, expression):
        token = match.group(0)
        simple = token.rsplit(".", 1)[-1]
        if token in NON_TYPE_TOKENS or simple in NON_TYPE_TOKENS:
            continue
        if not simple or not (simple[0].isupper() or simple[0] in "_$"):
            continue
        tokens.append(token)
    return tokens


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def type_allowed(declaration: TypeDecl, policy: dict[str, Any]) -> bool:
    return path_matches(declaration.fqcn, policy.get("allowed_type_globs", []))


def schema_interface_name(arguments: str) -> str | None:
    match = re.search(rf"\bschemaInterface\s*=\s*({QUALIFIED_IDENTIFIER})\s*\.class\b", arguments)
    return match.group(1) if match else None


def rpc_reference_names(
    source: SourceFile, policy: dict[str, Any]
) -> list[tuple[int, str]]:
    text = source.comments_removed
    results: list[tuple[int, str]] = []
    for _, offset, arguments in annotation_occurrences(
        source, policy["rpc_reference_annotations"]
    ):
        annotation_end = offset + len("@RpcReference")
        if arguments:
            open_paren = source.structure_mask.find("(", annotation_end)
            close_paren = matching_delimiter(
                source.structure_mask, open_paren, "(", ")"
            )
            annotation_end = close_paren + 1 if close_paren >= 0 else annotation_end
        tail = text[annotation_end : annotation_end + 500]
        annotation_free_tail = remove_annotations(tail)
        field_match = re.search(
            rf"(?:public|protected|private)?\s*(?:final\s+)?({QUALIFIED_IDENTIFIER})\s+{IDENTIFIER}\s*;",
            annotation_free_tail,
        )
        if field_match:
            results.append((offset, field_match.group(1)))
            continue
        method_match = re.search(
            rf"(?:public|protected|private)?\s*(?:void|{QUALIFIED_IDENTIFIER})\s+{IDENTIFIER}\s*\(\s*({QUALIFIED_IDENTIFIER})\s+{IDENTIFIER}",
            annotation_free_tail,
        )
        if method_match:
            results.append((offset, method_match.group(1)))

    invoker_allowed = set(policy["rpc_invoker_types"])
    if resolve_imported_name(source, "Invoker", invoker_allowed):
        for match in re.finditer(
            rf"\bInvoker\s*\.\s*createProxy\s*\([^;]*?,\s*({QUALIFIED_IDENTIFIER})\s*\.class\s*\)",
            text,
            re.DOTALL,
        ):
            results.append((match.start(), match.group(1)))
    return results


def rest_consumer_roots(source: SourceFile, schemes: Iterable[str]) -> tuple[int | None, set[str]]:
    first_offset: int | None = None
    for scheme in schemes:
        offset = source.comments_removed.find(scheme)
        if offset >= 0 and (first_offset is None or offset < first_offset):
            first_offset = offset
    if first_offset is None:
        return None, set()
    names = {
        match.group(1)
        for match in re.finditer(rf"\bnew\s+({QUALIFIED_IDENTIFIER})\s*\(", source.comments_removed)
    }
    names.update(
        match.group(1)
        for match in re.finditer(rf"\b({QUALIFIED_IDENTIFIER})\s*\.class\b", source.comments_removed)
    )
    return first_offset if first_offset is not None else 0, names


def load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PolicyError(f"policy file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise PolicyError(f"invalid policy JSON: {error}") from error
    required_arrays = (
        "generated_path_globs",
        "allowed_path_globs",
        "allowed_type_globs",
        "reserved_contract_type_globs",
        "generated_markers",
        "provider_schema_annotations",
        "mapping_annotations",
        "swagger_annotations",
        "rpc_reference_annotations",
        "rpc_invoker_types",
        "service_url_schemes",
    )
    for key in required_arrays:
        if not isinstance(policy.get(key), list):
            raise PolicyError(f"policy field must be an array: {key}")
    return policy


def load_sources(
    repo: Path, universe: Iterable[str], revision: str | None
) -> dict[str, SourceFile]:
    sources: dict[str, SourceFile] = {}
    for path in universe:
        try:
            text = read_source(repo, path, revision)
        except PolicyError as error:
            if revision is None and not (repo / path).exists():
                continue
            raise error
        sources[path] = parse_source(path, text)
    return sources


def collect_contract_roots(
    sources: dict[str, SourceFile], index: TypeIndex, policy: dict[str, Any]
) -> tuple[dict[tuple[str, int], TypeDecl], dict[str, set[str]], dict[str, set[str]]]:
    schema_refs: dict[str, set[str]] = {}
    rpc_refs: dict[str, set[str]] = {}
    for source in sources.values():
        for _, _, arguments in annotation_occurrences(
            source, policy["provider_schema_annotations"]
        ):
            referenced = schema_interface_name(arguments)
            if referenced:
                schema_refs.setdefault(source.path, set()).add(referenced)
        for _, referenced in rpc_reference_names(source, policy):
            rpc_refs.setdefault(source.path, set()).add(referenced)

    referenced_keys: set[tuple[str, int]] = set()
    for source_path, names in (*schema_refs.items(), *rpc_refs.items()):
        source = sources[source_path]
        for name in names:
            declaration = index.resolve(source, name)
            if declaration:
                referenced_keys.add(declaration.key)
    roots: dict[tuple[str, int], TypeDecl] = {}
    for source in sources.values():
        for declaration in source.declarations:
            schema_calls = annotation_occurrences(
                source,
                policy["provider_schema_annotations"],
                start=declaration.context_start,
                end=declaration.end,
            )
            direct_schema = any(
                not schema_interface_name(arguments)
                for _, _, arguments in schema_calls
            )
            referenced_interface = (
                declaration.kind == "interface" and declaration.key in referenced_keys
            )
            if direct_schema or referenced_interface:
                roots[declaration.key] = declaration
    return roots, schema_refs, rpc_refs


def reachable_dtos(
    sources: dict[str, SourceFile],
    index: TypeIndex,
    roots: dict[tuple[str, int], TypeDecl],
    policy: dict[str, Any],
) -> dict[tuple[str, int], TypeDecl]:
    queue: list[tuple[SourceFile, str]] = []
    for declaration in roots.values():
        for expression in method_type_expressions(declaration):
            queue.extend((declaration.source, token) for token in type_tokens(expression))
        for _, _, arguments in annotation_occurrences(
            declaration.source,
            policy["swagger_annotations"],
            start=declaration.context_start,
            end=declaration.end,
        ):
            for match in re.finditer(rf"\b(?:response|implementation)\s*=\s*({QUALIFIED_IDENTIFIER})\s*\.class", arguments):
                queue.append((declaration.source, match.group(1)))

    for source in sources.values():
        _, names = rest_consumer_roots(source, policy["service_url_schemes"])
        queue.extend((source, name) for name in names)

    dtos: dict[tuple[str, int], TypeDecl] = {}
    visited = set(roots)
    while queue:
        source, name = queue.pop(0)
        declaration = index.resolve(source, name)
        if not declaration or declaration.key in visited or type_allowed(declaration, policy):
            continue
        visited.add(declaration.key)
        dtos[declaration.key] = declaration
        for expression in dto_related_type_expressions(declaration):
            queue.extend((declaration.source, token) for token in type_tokens(expression))
    return dtos


def first_annotation_line(
    source: SourceFile, configured_types: Iterable[str]
) -> tuple[int, list[str]] | None:
    found = [
        (name, offset)
        for name, offset, _ in annotation_occurrences(source, configured_types)
    ]
    if not found:
        return None
    return line_number(source.text, found[0][1]), [name for name, _ in found]


def inspect(
    sources: dict[str, SourceFile], candidates: set[str], policy: dict[str, Any]
) -> list[Violation]:
    index = TypeIndex(sources.values())
    roots, _, _ = collect_contract_roots(sources, index, policy)
    dtos = reachable_dtos(sources, index, roots, policy)
    violations: set[Violation] = set()

    for path in sorted(candidates):
        source = sources.get(path)
        if not source or path_matches(path, policy["allowed_path_globs"]):
            continue

        if path_matches(path, policy["generated_path_globs"]) or any(
            marker in source.comments_removed for marker in policy["generated_markers"]
        ):
            violations.add(
                Violation(path, 1, "SCB000", "generated Java source must not be committed")
            )

        for declaration in source.declarations:
            if path_matches(
                declaration.fqcn, policy["reserved_contract_type_globs"]
            ):
                violations.add(
                    Violation(
                        path,
                        declaration.line,
                        "SCB001",
                        f"tracked type {declaration.fqcn} occupies a package reserved for generated contract code",
                    )
                )

        for annotation, offset, arguments in annotation_occurrences(
            source, policy["provider_schema_annotations"]
        ):
                referenced = schema_interface_name(arguments)
                if not referenced:
                    violations.add(
                        Violation(
                            path,
                            line_number(source.text, offset),
                            "SCB101",
                            f"@{annotation} publishes a handwritten contract; use generated schemaInterface code",
                        )
                    )
                    continue
                declaration = index.resolve(source, referenced)
                if declaration and not type_allowed(declaration, policy):
                    violations.add(
                        Violation(
                            path,
                            line_number(source.text, offset),
                            "SCB102",
                            f"schemaInterface {referenced} resolves to tracked handwritten source {declaration.source.path}",
                        )
                    )

        root_declarations = [
            declaration for key, declaration in roots.items() if key[0] == path
        ]
        if root_declarations:
            mapping_info = first_annotation_line(source, policy["mapping_annotations"])
            if mapping_info:
                line, names = mapping_info
                violations.add(
                    Violation(
                        path,
                        line,
                        "SCB110",
                        "handwritten ServiceComb mapping annotations define contract surface: "
                        + ", ".join(f"@{name}" for name in names),
                    )
                )
            swagger_info = first_annotation_line(source, policy["swagger_annotations"])
            if swagger_info:
                line, names = swagger_info
                violations.add(
                    Violation(
                        path,
                        line,
                        "SCB111",
                        "handwritten Swagger/OpenAPI annotations define contract metadata: "
                        + ", ".join(f"@{name}" for name in names),
                    )
                )
            for declaration in root_declarations:
                if declaration.kind == "interface" and not type_allowed(declaration, policy):
                    violations.add(
                        Violation(
                            path,
                            declaration.line,
                            "SCB120",
                            f"handwritten contract interface {declaration.fqcn} must be generated from the authoritative contract",
                        )
                    )

        rest_offset, _ = rest_consumer_roots(source, policy["service_url_schemes"])
        if rest_offset is not None:
            violations.add(
                Violation(
                    path,
                    line_number(source.text, rest_offset),
                    "SCB130",
                    "direct ServiceComb RestOperations client code must be generated from the contract",
                )
            )

        for offset, referenced in rpc_reference_names(source, policy):
            declaration = index.resolve(source, referenced)
            if declaration and declaration.kind == "interface" and not type_allowed(declaration, policy):
                violations.add(
                    Violation(
                        path,
                        line_number(source.text, offset),
                        "SCB131",
                        f"RPC consumer references tracked handwritten interface {declaration.fqcn}",
                    )
                )

        for declaration in source.declarations:
            if declaration.key in dtos and not type_allowed(declaration, policy):
                violations.add(
                    Violation(
                        path,
                        declaration.line,
                        "SCB200",
                        f"handwritten DTO {declaration.fqcn} is reachable from a ServiceComb contract signature",
                    )
                )
    return sorted(violations)


def render(violations: list[Violation], output_format: str) -> None:
    if output_format == "json":
        print(
            json.dumps(
                [
                    {
                        "path": violation.path,
                        "line": violation.line,
                        "rule": violation.rule,
                        "message": violation.message,
                    }
                    for violation in violations
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if not violations:
        print("ServiceComb contract policy passed.")
        return
    for violation in violations:
        print(
            f"{violation.path}:{violation.line}: {violation.rule} {violation.message}"
        )
    print(f"Blocked: {len(violations)} contract policy violation(s).", file=sys.stderr)


def main() -> int:
    args = parse_args()
    try:
        repo = args.repo_root.resolve()
        policy = load_policy(args.config.resolve())
        candidates, universe, revision = select_sources(args)
        if not candidates:
            render([], args.format)
            return 0
        sources = load_sources(repo, universe, revision)
        violations = inspect(sources, set(candidates), policy)
        render(violations, args.format)
        return 1 if violations else 0
    except PolicyError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
