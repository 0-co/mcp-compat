"""Tests for mcp_compat core comparison logic and CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

import pytest

# Add parent dir to path so we can import without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_compat.compat import Change, CompatReport, Severity, compare_schemas
from mcp_compat.cli import _format_report, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tool(
    name: str,
    description: str = "A tool.",
    properties: Dict[str, Any] = None,
    required: List[str] = None,
) -> Dict[str, Any]:
    props = properties or {}
    req = required or []
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": props,
            "required": req,
        },
    }


def str_param(description: str = "A string param.", default=None) -> Dict[str, Any]:
    prop: Dict[str, Any] = {"type": "string", "description": description}
    if default is not None:
        prop["default"] = default
    return prop


def int_param(description: str = "An integer param.") -> Dict[str, Any]:
    return {"type": "integer", "description": description}


# ---------------------------------------------------------------------------
# 1. No changes
# ---------------------------------------------------------------------------

class TestNoChanges:
    def test_identical_schemas_produce_no_changes(self):
        tool = make_tool("search", properties={"q": str_param()}, required=["q"])
        report = compare_schemas([tool], [tool])
        assert report.changes == []
        assert not report.has_breaking()


# ---------------------------------------------------------------------------
# 2. Tool-level changes
# ---------------------------------------------------------------------------

class TestToolLevelChanges:
    def test_tool_removed_is_breaking(self):
        before = [make_tool("get_weather")]
        after: list = []
        report = compare_schemas(before, after)
        assert len(report.breaking) == 1
        assert report.breaking[0].tool == "get_weather"
        assert "removed" in report.breaking[0].message.lower()

    def test_tool_added_is_safe(self):
        before: list = []
        after = [make_tool("get_weather")]
        report = compare_schemas(before, after)
        assert len(report.safe) == 1
        assert report.safe[0].tool == "get_weather"
        assert not report.has_breaking()

    def test_tool_description_changed_is_safe(self):
        before = [make_tool("search", description="Old description.")]
        after = [make_tool("search", description="New description.")]
        report = compare_schemas(before, after)
        assert not report.has_breaking()
        safe_msgs = [c.message for c in report.safe]
        assert any("description" in m.lower() for m in safe_msgs)


# ---------------------------------------------------------------------------
# 3. Required parameter changes
# ---------------------------------------------------------------------------

class TestRequiredParamChanges:
    def test_required_param_removed_is_breaking(self):
        before = [make_tool("list", properties={"limit": int_param()}, required=["limit"])]
        after = [make_tool("list", properties={}, required=[])]
        report = compare_schemas(before, after)
        assert report.has_breaking()
        assert any("limit" in c.message for c in report.breaking)

    def test_new_required_param_added_is_breaking(self):
        before = [make_tool("create", properties={}, required=[])]
        after = [make_tool("create", properties={"name": str_param()}, required=["name"])]
        report = compare_schemas(before, after)
        assert report.has_breaking()
        assert any("name" in c.message for c in report.breaking)

    def test_required_param_made_optional_is_breaking(self):
        # Required → optional removes the validation guarantee callers depend on
        before = [make_tool("send", properties={"msg": str_param()}, required=["msg"])]
        after = [make_tool("send", properties={"msg": str_param()}, required=[])]
        report = compare_schemas(before, after)
        assert report.has_breaking()
        assert any("msg" in c.message for c in report.breaking)

    def test_optional_param_made_required_is_breaking(self):
        before = [make_tool("query", properties={"filter": str_param()}, required=[])]
        after = [make_tool("query", properties={"filter": str_param()}, required=["filter"])]
        report = compare_schemas(before, after)
        assert report.has_breaking()
        assert any("filter" in c.message for c in report.breaking)


# ---------------------------------------------------------------------------
# 4. Parameter type changes
# ---------------------------------------------------------------------------

class TestParamTypeChanges:
    def test_param_type_changed_is_breaking(self):
        before = [make_tool(
            "get",
            properties={"id": str_param()},
            required=["id"],
        )]
        after = [make_tool(
            "get",
            properties={"id": int_param()},
            required=["id"],
        )]
        report = compare_schemas(before, after)
        assert report.has_breaking()
        assert any("type changed" in c.message for c in report.breaking)
        assert any("string" in c.message and "integer" in c.message for c in report.breaking)


# ---------------------------------------------------------------------------
# 5. Safe optional-param changes
# ---------------------------------------------------------------------------

class TestOptionalParamChanges:
    def test_new_optional_param_is_safe(self):
        before = [make_tool("search", properties={"q": str_param()}, required=["q"])]
        after = [make_tool(
            "search",
            properties={"q": str_param(), "limit": int_param()},
            required=["q"],
        )]
        report = compare_schemas(before, after)
        assert not report.has_breaking()
        assert any("limit" in c.message for c in report.safe)

    def test_optional_param_removed_is_warn(self):
        before = [make_tool(
            "search",
            properties={"q": str_param(), "limit": int_param()},
            required=["q"],
        )]
        after = [make_tool("search", properties={"q": str_param()}, required=["q"])]
        report = compare_schemas(before, after)
        assert not report.has_breaking()
        assert any("limit" in c.message for c in report.warnings)

    def test_param_default_changed_is_safe(self):
        before = [make_tool(
            "fetch",
            properties={"fmt": str_param(default="json")},
            required=[],
        )]
        after = [make_tool(
            "fetch",
            properties={"fmt": str_param(default="xml")},
            required=[],
        )]
        report = compare_schemas(before, after)
        assert not report.has_breaking()
        assert any("default" in c.message for c in report.safe)


# ---------------------------------------------------------------------------
# 6. Mixed change scenario
# ---------------------------------------------------------------------------

class TestMixedChanges:
    def test_mixed_breaking_and_safe(self):
        before = [
            make_tool(
                "get_weather",
                properties={
                    "city": str_param(),
                    "units": str_param(default="celsius"),
                },
                required=["city"],
            ),
            make_tool("old_tool"),
        ]
        after = [
            make_tool(
                "get_weather",
                properties={
                    "city": str_param(),
                    "units": {"type": "integer", "description": "Units as int"},
                },
                required=["city"],
            ),
            make_tool("new_tool"),
        ]
        report = compare_schemas(before, after)
        assert report.has_breaking()
        # old_tool removed (BREAKING), units type changed (BREAKING)
        breaking_msgs = [c.message for c in report.breaking]
        assert any("removed" in m for m in breaking_msgs)
        assert any("type changed" in m for m in breaking_msgs)
        # new_tool added (SAFE)
        assert any(c.tool == "new_tool" for c in report.safe)


# ---------------------------------------------------------------------------
# 7. Report to_dict
# ---------------------------------------------------------------------------

class TestReportDict:
    def test_to_dict_structure(self):
        before = [make_tool("t", properties={"p": str_param()}, required=["p"])]
        after: list = []
        report = compare_schemas(before, after)
        d = report.to_dict()
        assert "breaking_count" in d
        assert "warn_count" in d
        assert "safe_count" in d
        assert "changes" in d
        assert d["breaking_count"] == 1
        assert isinstance(d["changes"], list)


# ---------------------------------------------------------------------------
# 8. CLI tests (using main() with captured output)
# ---------------------------------------------------------------------------

class TestCLI:
    def _run(self, before_data, after_data, extra_args=None):
        """Write schemas to temp files and run CLI, returning (stdout, exit_code)."""
        import io
        from unittest.mock import patch

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as bf:
            json.dump(before_data, bf)
            bf_path = bf.name

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as af:
            json.dump(after_data, af)
            af_path = af.name

        argv = [bf_path, af_path] + (extra_args or [])
        captured = io.StringIO()
        exit_code = 0
        try:
            with patch("sys.stdout", captured):
                main(argv)
        except SystemExit as e:
            exit_code = int(e.code) if e.code is not None else 0
        finally:
            os.unlink(bf_path)
            os.unlink(af_path)

        return captured.getvalue(), exit_code

    def test_ci_flag_exits_1_on_breaking(self):
        before = [make_tool("t")]
        after: list = []
        _, code = self._run(before, after, ["--ci"])
        assert code == 1

    def test_ci_flag_exits_0_on_no_breaking(self):
        tool = make_tool("t")
        _, code = self._run([tool], [tool], ["--ci"])
        assert code == 0

    def test_json_output_is_valid_json(self):
        before = [make_tool("t")]
        after: list = []
        out, _ = self._run(before, after, ["--json"])
        data = json.loads(out)
        assert "breaking_count" in data
        assert data["breaking_count"] == 1

    def test_no_changes_output(self):
        tool = make_tool("t")
        out, _ = self._run([tool], [tool])
        assert "No changes detected" in out

    def test_human_output_contains_breaking(self):
        before = [make_tool("search")]
        after: list = []
        out, _ = self._run(before, after)
        assert "BREAKING" in out
        assert "search" in out

    def test_safe_only_exits_0_no_ci(self):
        before: list = []
        after = [make_tool("new_tool")]
        _, code = self._run(before, after)
        assert code == 0

    def test_safe_only_exits_0_with_ci(self):
        before: list = []
        after = [make_tool("new_tool")]
        _, code = self._run(before, after, ["--ci"])
        assert code == 0
