# mcp-compat

**Know before you deploy if you're breaking MCP users.**

`mcp-compat` compares two MCP server schemas (before/after) and classifies every change as BREAKING, WARN, or SAFE. Gate your deploys on it.

```
mcp-compat: schema compatibility report

  2 BREAKING changes, 1 SAFE change

  BREAKING  get_weather  Parameter 'units' type changed: string → integer
  BREAKING  list_items   Required parameter 'limit' removed
  SAFE      create_item  New optional parameter 'tags' added

  Run with --ci to fail CI on breaking changes
```

## Install

```bash
pip install mcp-compat
```

No external dependencies. Python 3.9+.

## Quick start

```bash
# Compare two local schema files
mcp-compat before.json after.json

# Fail CI on breaking changes
mcp-compat before.json after.json --ci

# JSON output for scripting
mcp-compat before.json after.json --json

# Compare remote schemas
mcp-compat https://example.com/schema-v1.json https://example.com/schema-v2.json
```

Input is a JSON array of MCP tool objects (same format as `agent-friend grade`):

```json
[
  {
    "name": "get_weather",
    "description": "Get current weather",
    "inputSchema": {
      "type": "object",
      "properties": {
        "city": {"type": "string", "description": "City name"},
        "units": {"type": "string", "description": "Units", "default": "celsius"}
      },
      "required": ["city"]
    }
  }
]
```

## Change classification

| Change | Severity | Reason |
|--------|----------|--------|
| Tool removed | BREAKING | All callers break immediately |
| Required parameter removed | BREAKING | Callers passing it hit unexpected behavior |
| New required parameter added | BREAKING | Callers that omit it will receive errors |
| Parameter type changed | BREAKING | Callers sending old type get rejected |
| Required parameter made optional | BREAKING | Removes validation guarantee callers relied on |
| Optional parameter made required | BREAKING | Callers that omit it now fail |
| Optional parameter removed | WARN | Callers passing it may get unexpected behavior |
| Tool added | SAFE | Additive, no existing callers affected |
| New optional parameter added | SAFE | Existing callers unaffected |
| Description changed | SAFE | No functional impact |
| Default value changed | SAFE | Callers that relied on old default may see behavior change (consider as WARN in sensitive contexts) |

## CI integration

Add to your GitHub Actions workflow:

```yaml
- name: Check MCP schema compatibility
  run: |
    pip install mcp-compat
    mcp-compat schema-before.json schema-after.json --ci
```

Or capture the schema before a deploy using `mcp-diff` (from the same ecosystem):

```bash
# Save current schema snapshot with mcp-diff
pip install mcp-diff
mcp-diff snapshot my-server.json

# After updating, compare and gate
mcp-compat schema-before.json schema-after.json --ci
```

## JSON output

```bash
mcp-compat before.json after.json --json
```

```json
{
  "breaking_count": 1,
  "warn_count": 0,
  "safe_count": 2,
  "changes": [
    {
      "severity": "BREAKING",
      "tool": "get_weather",
      "message": "Parameter 'units' type changed: string → integer"
    },
    {
      "severity": "SAFE",
      "tool": "get_weather",
      "message": "New optional parameter 'format' added"
    }
  ]
}
```

## Part of the MCP developer lifecycle

```
agent-friend   lint schemas before publishing
mcp-patch      security audit (prompt injection, over-permission)
mcp-pytest     test tool behavior end-to-end
mcp-snoop      debug stdio traffic in real time
mcp-diff       detect schema changes between versions
mcp-compat     classify breaking changes  ← you are here
```

All on PyPI. All open-source. All zero external dependencies.

## License

MIT
