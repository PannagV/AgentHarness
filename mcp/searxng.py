"""
    SearXNG MCP Server

    Usage:
        HTTP Server: python server.py --transport sse --host <host-ip> --port 8001
        MCP Stdio: python server.py --transport stdio


"""

import os

import httpx
from fastmcp import FastMCP


# Initialize the MCP server
mcp = FastMCP("Searxng-Core")

# ── Configuration ──────────────────────────────────────────────
SEARXNG_BASE_URL = os.environ.get("SEARXNG_BASE_URL", "http://127.0.0.1:8080")



# ── Tools ──────────────────────────────────────────────────────

@mcp.tool()
async def search_web(
    query: str,
    categories: str = "general",
    page: int = 1,
    max_results: int = 10,
) -> str:
    """Search the web using the local SearXNG instance.

    Args:
        query: The search query string.
        categories: Comma-separated categories to search in (e.g. "general", "images", "news", "videos", "it", "science").
        page: Page number for paginated results (default: 1).
        max_results: Maximum number of results to return (default: 10, max: 20).
    """
    max_results = min(max_results, 20)


    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "pageno": page,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{SEARXNG_BASE_URL}/search", params=params)
            resp.raise_for_status()
        except httpx.ConnectError:
            msg = (
                "ERROR: Could not connect to SearXNG at "
                f"{SEARXNG_BASE_URL}. "
                "Make sure the Docker container is running (docker compose up -d)."
            )
            return msg
        except httpx.HTTPStatusError as e:
            return f"ERROR: SearXNG returned HTTP {e.response.status_code}."
        except httpx.TimeoutException:
            return "ERROR: SearXNG search timed out."

        data = resp.json()
    results = data.get("results", [])

    if not results:
        return f"No results found for: {query}"

    # Format results into a readable text block
    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results[:max_results], 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        snippet = r.get("content", "No description available.")
        engine = r.get("engine", "unknown")
        lines.append(
            f"[{i}] {title}\n"
            f"    URL: {url}\n"
            f"    Source: {engine}\n"
            f"    {snippet}\n"
        )

    # Append query metadata
    total = len(data.get("results", []))
    lines.append(f"--- Showing {min(max_results, total)} of {total} results (page {page}) ---")

    return "\n".join(lines)

"""
@mcp.tool()
def calculate_threat_score(cve_score: float, exploitability: float) -> str:
   Calculates a custom risk score based on CVSS and exploit status.
    log.request("calculate_threat_score", {
        "cve_score": cve_score,
        "exploitability": exploitability,
    })

    risk = cve_score * exploitability
    if risk > 7.0:
        result = f"CRITICAL: Risk Score {risk:.2f}. Immediate patching required."
    else:
        result = f"MODERATE: Risk Score {risk:.2f}. Monitor for PoC."

    log.response("calculate_threat_score", result)
    return result
"""



# ── Prompts ────────────────────────────────────────────────────
"""
@mcp.prompt()
def audit_report_template(vuln_name: str) -> str:
    Generates a structured prompt for a vulnerability report.
    return f"Analyze the following vulnerability: {vuln_name}. Provide a summary and a PoC check list."
"""

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Searxng-Core MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transport mode: 'stdio' (default) for local clients, 'sse' for network access",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (SSE mode, default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Port to listen on (SSE mode, default: 8001)")
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run()
