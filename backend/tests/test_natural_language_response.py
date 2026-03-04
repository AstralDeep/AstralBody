
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os
import sys

# Mock dependencies that might be missing in the test environment
sys.modules['aiohttp'] = MagicMock()
mock_websockets = MagicMock()
mock_websockets.exceptions = MagicMock()
mock_websockets.exceptions.ConnectionClosed = type('ConnectionClosed', (Exception,), {})
sys.modules['websockets'] = mock_websockets
sys.modules['websockets.exceptions'] = mock_websockets.exceptions
sys.modules['openai'] = MagicMock()
sys.modules['dotenv'] = MagicMock()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.protocol import MCPResponse, AgentCard, AgentSkill

class TestNaturalLanguageResponse(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["OPENAI_BASE_URL"] = "http://fake.api"
        os.environ["LLM_MODEL"] = "test-model"

        # Now we can safely import orchestrator
        from orchestrator.orchestrator import Orchestrator
        self.orchestrator = Orchestrator()
        self.orchestrator.llm_client = MagicMock()

    async def test_multi_turn_convo(self):
        # Setup
        ws = AsyncMock()
        chat_id = self.orchestrator.history.create_chat()

        # Mock Agent
        agent_id = "agent-1"
        self.orchestrator.agents[agent_id] = AsyncMock()
        self.orchestrator.agent_cards[agent_id] = AgentCard(
            name="Test", description="Test", agent_id=agent_id,
            skills=[AgentSkill(name="search_patients", description="d", id="search_patients")]
        )
        self.orchestrator.agent_capabilities[agent_id] = [{"name": "search_patients"}]

        # Allow all tool permissions for this test
        self.orchestrator.tool_permissions.is_tool_allowed = MagicMock(return_value=True)

        # Mock LLM Responses via _call_llm (avoids asyncio.to_thread + StopIteration issues)
        # Turn 1: Call Tool
        msg1 = MagicMock(spec=[])
        msg1.tool_calls = [MagicMock()]
        msg1.tool_calls[0].function.name = "search_patients"
        msg1.tool_calls[0].function.arguments = '{}'
        msg1.tool_calls[0].id = "call_123"
        msg1.content = None
        msg1.reasoning_content = None

        # Turn 2: Natural Language Response
        msg2 = MagicMock(spec=[])
        msg2.tool_calls = None
        msg2.content = "I found 5 patients."
        msg2.reasoning_content = None

        # Mock _call_llm directly to avoid asyncio.to_thread issues
        call_llm_results = [msg1, msg2]
        call_llm_index = 0
        async def mock_call_llm(ws, messages, tools):
            nonlocal call_llm_index
            if call_llm_index < len(call_llm_results):
                result = call_llm_results[call_llm_index]
                call_llm_index += 1
                return result
            return None
        self.orchestrator._call_llm = mock_call_llm

        # Also mock summarize_chat_title to avoid LLM call for title
        self.orchestrator.summarize_chat_title = AsyncMock()

        # Mock Tool Execution
        async def mock_execute(ws, agent_id, tool_name, args, max_retries=None):
            return MCPResponse(
                request_id="call_123",
                result={"_data": {"count": 5}},
                ui_components=[{"type": "card", "title": "Results"}]
            )
        self.orchestrator._execute_with_retry = mock_execute

        # Execute
        await self.orchestrator.handle_chat_message(ws, "Find patients", chat_id)

        # Verify
        # 1. _call_llm was called twice (tool call + final response)
        assert call_llm_index == 2

        # 2. Check UI sent final text via send_text
        sent_messages = [call.args[0] for call in ws.send_text.call_args_list]
        found_message = any("I found 5 patients" in msg for msg in sent_messages)
        assert found_message, f"Expected 'I found 5 patients' not found in: {sent_messages}"

if __name__ == "__main__":
    unittest.main()
