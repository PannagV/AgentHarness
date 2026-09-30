import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp_manager import MCPManager


class MCPManagerConfigTests(unittest.TestCase):
    def test_loads_stdio_and_external_servers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "servers.yaml"
            config.write_text(
                "servers:\n"
                "  - name: local\n"
                "    transport: stdio\n"
                "    command: python\n"
                "    args: [server.py]\n"
                "  - name: remote\n"
                "    transport: sse\n"
                "    url: https://example.test/sse\n",
                encoding="utf-8",
            )
            manager = MCPManager(root, config)

            servers = manager.load_config()

            self.assertEqual([server.name for server in servers], ["local", "remote"])
            self.assertEqual(servers[0].args, ("server.py",))
            self.assertEqual(servers[1].url, "https://example.test/sse")

    def test_environment_values_are_expanded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "servers.yaml"
            config.write_text(
                "servers:\n"
                "  - name: remote\n"
                "    transport: sse\n"
                "    url: https://example.test/sse\n"
                "    headers:\n"
                "      Authorization: Bearer ${TEST_MCP_TOKEN}\n",
                encoding="utf-8",
            )
            old_value = os.environ.get("TEST_MCP_TOKEN")
            os.environ["TEST_MCP_TOKEN"] = "secret"
            try:
                server = MCPManager(root, config).load_config()[0]
            finally:
                if old_value is None:
                    os.environ.pop("TEST_MCP_TOKEN", None)
                else:
                    os.environ["TEST_MCP_TOKEN"] = old_value

            self.assertEqual(server.headers["Authorization"], "Bearer secret")

    def test_missing_environment_variable_marks_server_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "servers.yaml"
            config.write_text(
                "servers:\n"
                "  - name: remote\n"
                "    transport: sse\n"
                "    url: https://example.test/sse\n"
                "    headers:\n"
                "      Authorization: Bearer ${MISSING_TEST_MCP_TOKEN}\n",
                encoding="utf-8",
            )
            manager = MCPManager(root, config)

            self.assertEqual(manager.load_config(), [])
            self.assertIn("remote", manager.load_errors)

    def test_discovered_tools_are_namespaced_for_responses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = MCPManager(directory)
            tool = SimpleNamespace(
                name="search_web",
                description="Search the web",
                inputSchema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )
            manager.servers["searxng"] = SimpleNamespace(tools=[tool], client=object())
            manager._rebuild_tool_index()

            self.assertEqual(
                manager.responses_tools(),
                [{
                    "type": "function",
                    "name": "mcp__searxng__search_web",
                    "description": "Search the web",
                    "parameters": tool.inputSchema,
                }],
            )


if __name__ == "__main__":
    unittest.main()
