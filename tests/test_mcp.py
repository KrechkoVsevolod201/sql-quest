import unittest

from mcp_server import respond


class McpTests(unittest.TestCase):
    def test_initialize_and_tool_discovery(self):
        initialized = respond({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "sql-quest")
        tools = respond({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertIn("run_sql", [tool["name"] for tool in tools])

    def test_notifications_do_not_send_responses(self):
        self.assertIsNone(respond({"jsonrpc": "2.0", "method": "notifications/initialized"}))


if __name__ == "__main__":
    unittest.main()
