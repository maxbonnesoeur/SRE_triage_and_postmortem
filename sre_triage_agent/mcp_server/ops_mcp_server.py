"""Enterprise Ops MCP Server (stdio transport).

Exposes alerts, structured logs, golden-signal metrics, deployment history,
and SRE runbooks over the Model Context Protocol (MCP) so ADK agents (via
`McpToolset`) or any external MCP-compatible client can query operational state
through a standardized interface.

Run directly:
    python3 -m sre_triage_agent.mcp_server.ops_mcp_server
"""

from __future__ import annotations

from typing import Any

try:
    from mcp.server.mcpserver import MCPServer as _MCPServer
except ImportError:  # pragma: no cover - compatibility with mcp<2
    from mcp.server.fastmcp import FastMCP as _MCPServer  # type: ignore[attr-defined,no-redef]

from sre_triage_agent.tools.telemetry_tools import (
    get_recent_deployments,
    get_service_metrics,
    list_active_alerts,
    query_service_logs,
    search_runbooks,
)

mcp = _MCPServer(
    name="enterprise-ops-mcp",
    instructions=(
        "Enterprise observability and release-management MCP server providing "
        "read-only access to firing alerts, logs, metrics, deployments, and runbooks."
    ),
)


@mcp.tool()
def mcp_list_active_alerts(service_name: str = "") -> dict[str, Any]:
    """List currently firing enterprise alerts, optionally filtered by service."""
    return list_active_alerts(service_name=service_name)


@mcp.tool()
def mcp_query_service_logs(
    service_name: str,
    level: str = "",
    keyword: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Query bounded application logs for a microservice."""
    return query_service_logs(
        service_name=service_name,
        level=level,
        keyword=keyword,
        limit=limit,
    )


@mcp.tool()
def mcp_get_service_metrics(service_name: str) -> dict[str, Any]:
    """Retrieve golden-signal service metrics compared to SLO baselines."""
    return get_service_metrics(service_name=service_name)


@mcp.tool()
def mcp_get_recent_deployments(service_name: str, limit: int = 5) -> dict[str, Any]:
    """Fetch recent production deployments and commit summaries for a service."""
    return get_recent_deployments(service_name=service_name, limit=limit)


@mcp.tool()
def mcp_search_runbooks(service_name: str = "", symptom_query: str = "") -> dict[str, Any]:
    """Search SRE runbooks by service name and symptom keywords."""
    return search_runbooks(service_name=service_name, symptom_query=symptom_query)


def main() -> None:
    """Start the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
