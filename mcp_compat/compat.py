"""Core comparison logic for MCP schema compatibility analysis."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    BREAKING = "BREAKING"
    WARN = "WARN"
    SAFE = "SAFE"


@dataclass
class Change:
    severity: Severity
    tool: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "severity": self.severity.value,
            "tool": self.tool,
            "message": self.message,
        }


@dataclass
class CompatReport:
    changes: List[Change] = field(default_factory=list)

    @property
    def breaking(self) -> List[Change]:
        return [c for c in self.changes if c.severity == Severity.BREAKING]

    @property
    def warnings(self) -> List[Change]:
        return [c for c in self.changes if c.severity == Severity.WARN]

    @property
    def safe(self) -> List[Change]:
        return [c for c in self.changes if c.severity == Severity.SAFE]

    def has_breaking(self) -> bool:
        return bool(self.breaking)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "breaking_count": len(self.breaking),
            "warn_count": len(self.warnings),
            "safe_count": len(self.safe),
            "changes": [c.to_dict() for c in self.changes],
        }


def _get_required(schema: Dict[str, Any]) -> set:
    """Return the set of required parameter names from a tool's inputSchema."""
    input_schema = schema.get("inputSchema", {})
    return set(input_schema.get("required", []))


def _get_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Return the properties dict from a tool's inputSchema."""
    input_schema = schema.get("inputSchema", {})
    return input_schema.get("properties", {})


def _param_type(prop: Dict[str, Any]) -> Optional[str]:
    """Extract the type from a property definition."""
    return prop.get("type")


def compare_schemas(
    before: List[Dict[str, Any]],
    after: List[Dict[str, Any]],
) -> CompatReport:
    """Compare two MCP tool schema lists and classify changes."""
    report = CompatReport()

    before_by_name: Dict[str, Dict[str, Any]] = {t["name"]: t for t in before}
    after_by_name: Dict[str, Dict[str, Any]] = {t["name"]: t for t in after}

    before_names = set(before_by_name)
    after_names = set(after_by_name)

    # Tools removed
    for name in sorted(before_names - after_names):
        report.changes.append(Change(Severity.BREAKING, name, "Tool removed"))

    # Tools added
    for name in sorted(after_names - before_names):
        report.changes.append(Change(Severity.SAFE, name, "New tool added"))

    # Tools present in both — compare parameters
    for name in sorted(before_names & after_names):
        before_tool = before_by_name[name]
        after_tool = after_by_name[name]

        before_required = _get_required(before_tool)
        after_required = _get_required(after_tool)
        before_props = _get_properties(before_tool)
        after_props = _get_properties(after_tool)

        before_param_names = set(before_props)
        after_param_names = set(after_props)

        # Required parameter removed
        for param in sorted(before_required - after_param_names):
            report.changes.append(
                Change(
                    Severity.BREAKING,
                    name,
                    f"Required parameter '{param}' removed",
                )
            )

        # Required parameter renamed is captured as remove + add below

        # New required parameter added (breaks callers that omit it)
        for param in sorted(after_required - before_param_names):
            report.changes.append(
                Change(
                    Severity.BREAKING,
                    name,
                    f"New required parameter '{param}' added",
                )
            )

        # New optional parameter added
        for param in sorted((after_param_names - before_param_names) - after_required):
            report.changes.append(
                Change(
                    Severity.SAFE,
                    name,
                    f"New optional parameter '{param}' added",
                )
            )

        # Optional parameter removed (WARN)
        for param in sorted((before_param_names - after_param_names) - before_required):
            report.changes.append(
                Change(
                    Severity.WARN,
                    name,
                    f"Optional parameter '{param}' removed",
                )
            )

        # Inspect parameters present in both
        for param in sorted(before_param_names & after_param_names):
            before_prop = before_props[param]
            after_prop = after_props[param]

            # Type changed
            before_type = _param_type(before_prop)
            after_type = _param_type(after_prop)
            if before_type != after_type:
                report.changes.append(
                    Change(
                        Severity.BREAKING,
                        name,
                        f"Parameter '{param}' type changed: {before_type} → {after_type}",
                    )
                )

            # Required → optional (BREAKING: removes server-side validation callers relied on)
            was_required = param in before_required
            now_required = param in after_required
            if was_required and not now_required:
                report.changes.append(
                    Change(
                        Severity.BREAKING,
                        name,
                        f"Required parameter '{param}' made optional (removes validation guarantee)",
                    )
                )

            # Optional → required (BREAKING: callers that omit it will now fail)
            if not was_required and now_required:
                report.changes.append(
                    Change(
                        Severity.BREAKING,
                        name,
                        f"Optional parameter '{param}' made required",
                    )
                )

            # Default value changed (SAFE)
            before_default = before_prop.get("default")
            after_default = after_prop.get("default")
            if before_default != after_default and "default" in before_prop:
                report.changes.append(
                    Change(
                        Severity.SAFE,
                        name,
                        f"Parameter '{param}' default changed: {before_default!r} → {after_default!r}",
                    )
                )

            # Description changed (SAFE)
            before_desc = before_prop.get("description", "")
            after_desc = after_prop.get("description", "")
            if before_desc != after_desc:
                report.changes.append(
                    Change(
                        Severity.SAFE,
                        name,
                        f"Parameter '{param}' description changed",
                    )
                )

        # Tool description changed (SAFE)
        before_desc = before_tool.get("description", "")
        after_desc = after_tool.get("description", "")
        if before_desc != after_desc:
            report.changes.append(
                Change(
                    Severity.SAFE,
                    name,
                    "Tool description changed",
                )
            )

    return report


def load_schema(source: str) -> List[Dict[str, Any]]:
    """Load an MCP schema from a file path or URL."""
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    else:
        with open(source, "r", encoding="utf-8") as f:
            data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            f"Schema must be a JSON array of tool objects, got {type(data).__name__}"
        )
    return data


def load_schema_from_stdin() -> List[Dict[str, Any]]:
    """Load an MCP schema from stdin."""
    import sys
    data = json.load(sys.stdin)
    if not isinstance(data, list):
        raise ValueError(
            f"Schema must be a JSON array of tool objects, got {type(data).__name__}"
        )
    return data
