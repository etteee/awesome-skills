#!/usr/bin/env python3
"""Validate contract-to-interface integration configuration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


STATIC_PLACEHOLDER = re.compile(r"<[A-Z][A-Z0-9_.-]*>")
RUNTIME_VARIABLE = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
ALLOWED_RUNTIME_VARIABLES = {
    "repo_root",
    "service_dir",
    "service_id",
    "interface_id",
    "contract_version",
    "contract_file",
    "output_directory",
}
REQUIRED_PATHS = (
    ("mcp", "tool"),
    ("mcp", "arguments_template"),
    ("mcp", "response_mode"),
    ("mcp", "contract_selector"),
    ("contract", "format"),
    ("contract", "local_path_template"),
    ("generation", "working_directory_template"),
    ("generation", "command_template"),
    ("generation", "output_directory_template"),
    ("build", "working_directory_template"),
    ("build", "command_template"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate integration-config.json and find unresolved placeholders."
    )
    parser.add_argument("config", type=Path, help="Path to integration-config.json")
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Validate template structure while allowing unresolved static placeholders.",
    )
    return parser.parse_args()


def get_path(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for segment in path:
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def walk(value: Any, location: str = "$") -> list[tuple[str, str]]:
    strings: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            strings.append((f"{location}.<key>", str(key)))
            strings.extend(walk(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            strings.extend(walk(child, f"{location}[{index}]"))
    elif isinstance(value, str):
        strings.append((location, value))
    return strings


def main() -> int:
    args = parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: configuration not found: {args.config}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"ERROR: invalid JSON: {error}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for path in REQUIRED_PATHS:
        value = get_path(config, path)
        dotted = ".".join(path)
        if value is None or value == "" or value == {}:
            errors.append(f"missing required value: {dotted}")

    strings = walk(config)
    unresolved: list[tuple[str, str]] = []
    unknown_runtime: list[tuple[str, str]] = []
    for location, value in strings:
        for placeholder in STATIC_PLACEHOLDER.findall(value):
            unresolved.append((location, placeholder))
        for runtime_name in RUNTIME_VARIABLE.findall(value):
            if runtime_name not in ALLOWED_RUNTIME_VARIABLES:
                unknown_runtime.append((location, runtime_name))

    response_mode = get_path(config, ("mcp", "response_mode"))
    if not STATIC_PLACEHOLDER.search(str(response_mode)) and response_mode not in {
        "inline",
        "url",
        "path",
    }:
        errors.append("mcp.response_mode must be inline, url, or path")

    generation_command = get_path(config, ("generation", "command_template"))
    if isinstance(generation_command, str) and not STATIC_PLACEHOLDER.search(
        generation_command
    ):
        for required_variable in ("contract_file", "output_directory"):
            if f"{{{{{required_variable}}}}}" not in generation_command:
                errors.append(
                    "generation.command_template must contain "
                    f"{{{{{required_variable}}}}}"
                )

    for location, runtime_name in unknown_runtime:
        errors.append(f"unknown runtime variable at {location}: {{{{{runtime_name}}}}}")

    if unresolved and not args.allow_placeholders:
        for location, placeholder in unresolved:
            errors.append(f"unresolved placeholder at {location}: {placeholder}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if unresolved:
        unique = sorted({placeholder for _, placeholder in unresolved})
        print(
            "Template structure valid; unresolved placeholders allowed: "
            + ", ".join(unique)
        )
    else:
        print("Integration configuration valid; no static placeholders remain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
