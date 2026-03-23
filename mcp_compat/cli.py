"""CLI entry point for mcp-compat."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from .compat import (
    Change,
    CompatReport,
    Severity,
    compare_schemas,
    load_schema,
    load_schema_from_stdin,
)


def _format_report(report: CompatReport) -> str:
    """Format a CompatReport for human-readable output."""
    lines = ["mcp-compat: schema compatibility report", ""]

    if not report.changes:
        lines.append("  No changes detected.")
        return "\n".join(lines)

    breaking = report.breaking
    warnings = report.warnings
    safe = report.safe

    summary_parts = []
    if breaking:
        n = len(breaking)
        summary_parts.append(f"{n} BREAKING {'change' if n == 1 else 'changes'}")
    if warnings:
        n = len(warnings)
        summary_parts.append(f"{n} WARN {'change' if n == 1 else 'changes'}")
    if safe:
        n = len(safe)
        summary_parts.append(f"{n} SAFE {'change' if n == 1 else 'changes'}")

    lines.append(f"  {', '.join(summary_parts)}")
    lines.append("")

    # Compute column widths for alignment
    all_changes = report.changes
    max_tool_len = max((len(c.tool) for c in all_changes), default=10)
    max_sev_len = max((len(c.severity.value) for c in all_changes), default=8)

    for change in all_changes:
        sev = change.severity.value.ljust(max_sev_len)
        tool = change.tool.ljust(max_tool_len)
        lines.append(f"  {sev}  {tool}  {change.message}")

    lines.append("")
    if breaking:
        lines.append("  Run with --ci to fail CI on breaking changes")
    return "\n".join(lines)


def main(argv: List[str] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-compat",
        description="Classify breaking vs non-breaking changes in MCP server schemas.",
    )
    parser.add_argument(
        "before",
        nargs="?",
        help="Before schema: file path or URL (omit to read stdin)",
    )
    parser.add_argument(
        "after",
        nargs="?",
        help="After schema: file path or URL",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Exit with code 1 if breaking changes are found",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )

    args = parser.parse_args(argv)

    # Validate argument combinations
    if args.before and not args.after:
        parser.error("Both BEFORE and AFTER are required when providing positional arguments.")

    try:
        if args.before and args.after:
            before = load_schema(args.before)
            after = load_schema(args.after)
        else:
            # stdin mode not meaningful without two sources; require both
            parser.error("Two schema sources (BEFORE and AFTER) are required.")
    except (OSError, ValueError) as exc:
        print(f"mcp-compat: error loading schema: {exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"mcp-compat: unexpected error: {exc}", file=sys.stderr)
        sys.exit(2)

    report = compare_schemas(before, after)

    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(_format_report(report))

    if args.ci and report.has_breaking():
        sys.exit(1)


if __name__ == "__main__":
    main()
