import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orchestrator.orchestrator import Orchestrator
from shared.protocol import Message, UIEvent

class TestContextPersistence(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Patch HistoryManager to avoid DB dependency
        with patch('orchestrator.orchestrator.HistoryManager') as mock_history:
            self.orchestrator = Orchestrator()
            self.orchestrator.history = mock_history()
            # Patch llm_client
            self.orchestrator.llm_client = MagicMock()

    async def test_history_included_in_llm_request(self):
        # Mock history
        chat_id = "test-chat-id"
        mock_messages = [
            {"role": "user", "content": "I like bananas"},
            {"role": "assistant", "content": [{"type": "text", "content": "Bananas are great!"}]},
            {"role": "user", "content": "How much do they cost?"} # The message being added in handle_chat_message
        ]
        self.orchestrator.history.get_chat.return_value = {
            "id": chat_id,
            "messages": mock_messages
        }
        
        # Mock websocket
        mock_ws = MagicMock()
        mock_ws.send = AsyncMock()

        # Mock LLM response
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "They cost about $0.50 each."
        mock_completion.choices[0].message.tool_calls = None
        mock_completion.choices[0].message.reasoning_content = None
        self.orchestrator.llm_client.chat.completions.create.return_value = mock_completion

        # Mock agents
        mock_card = MagicMock()
        mock_card.agent_id = "medical-agent"
        mock_card.skills = [MagicMock(id="analyze_csv_file", description="Analyze CSV", input_schema={})]
        self.orchestrator.agent_cards = {"medical-agent": mock_card}
        self.orchestrator.agents = {"medical-agent": MagicMock()}

        # Call handle_chat_message
        await self.orchestrator.handle_chat_message(mock_ws, "How much do they cost?", chat_id)

        # Verify history was included in the call to LLM
        # We need to capture the keyword arguments of the call
        kwargs = self.orchestrator.llm_client.chat.completions.create.call_args.kwargs
        sent_messages = kwargs['messages']
        
        # Expectations:
        # 1. System prompt
        # 2. Previous user message
        # 3. Previous assistant message (stringified UI)
        # 4. Current user message
        
        self.assertEqual(len(sent_messages), 4)
        self.assertEqual(sent_messages[1]['content'], "I like bananas")
        self.assertIn("Bananas are great!", sent_messages[2]['content'])
        self.assertEqual(sent_messages[3]['content'], "How much do they cost?")
        print("Test Passed: History correctly included in LLM request.")

if __name__ == "__main__":
    unittest.main()
