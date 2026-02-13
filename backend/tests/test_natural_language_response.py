
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os
import sys

# Mock dependencies that might be missing in the test environment
sys.modules['aiohttp'] = MagicMock()
sys.modules['websockets'] = MagicMock()
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
        chat_id = "test-chat"
        self.orchestrator.history.create_chat()
        
        # Mock Agent
        agent_id = "agent-1"
        self.orchestrator.agents[agent_id] = AsyncMock()
        self.orchestrator.agent_cards[agent_id] = AgentCard(
            name="Test", description="Test", agent_id=agent_id,
            skills=[AgentSkill(name="search_patients", description="d", id="search_patients")]
        )
        self.orchestrator.agent_capabilities[agent_id] = [{"name": "search_patients"}]
        
        # Mock LLM Responses
        # Turn 1: Call Tool
        msg1 = MagicMock()
        msg1.tool_calls = [MagicMock()]
        msg1.tool_calls[0].function.name = "search_patients"
        msg1.tool_calls[0].function.arguments = '{}'
        msg1.tool_calls[0].id = "call_123"
        msg1.content = None

        # Turn 2: Natural Language Response
        msg2 = MagicMock()
        msg2.tool_calls = None
        msg2.content = "I found 5 patients."
        
        # Configure the mock to return these in sequence
        self.orchestrator.llm_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=msg1)]), # Response 1
            MagicMock(choices=[MagicMock(message=msg2)])  # Response 2
        ]
        
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
        # 1. Check calls to LLM
        assert self.orchestrator.llm_client.chat.completions.create.call_count == 2
        
        # 2. Check Second LLM Call included tool output
        call_args_2 = self.orchestrator.llm_client.chat.completions.create.call_args_list[1]
        messages_2 = call_args_2.kwargs['messages']
        
        # Messages should be: System, User, Assistant(ToolCall), Tool(Result)
        assert len(messages_2) >= 4
        assert messages_2[-1]["role"] == "tool"
        assert '{"count": 5}' in messages_2[-1]["content"]
        assert messages_2[-1]["tool_call_id"] == "call_123"
        
        # 3. Check UI sent final text
        # ws.send is called multiple times (status updates, tool output, final text)
        # Verify one of them contains "I found 5 patients"
        sent_messages = [call.args[0] for call in ws.send.call_args_list]
        print("DEBUG: Sent messages:", sent_messages)
        found_message = any("I found 5 patients" in msg for msg in sent_messages)
        assert found_message, f"Expected message not found in: {sent_messages}"

if __name__ == "__main__":
    unittest.main()
