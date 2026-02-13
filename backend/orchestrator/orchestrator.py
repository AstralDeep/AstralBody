"""
Orchestrator — Central hub for the multi-agent system.

Responsibilities:
1. WebSocket server for UI clients (/ws) and agent connections
2. A2A agent discovery via agent cards
3. LLM-powered tool routing (chat message → tool selection)
4. Parallel MCP tool execution across agents
5. Dynamic UI assembly (combines tool outputs into cohesive layouts)
"""
import asyncio
import json
import time
import os
import sys
import logging
from typing import Dict, List, Optional, Any
from dataclasses import asdict

import websockets
import aiohttp
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestrator.history import HistoryManager

from shared.protocol import (
    Message, MCPRequest, MCPResponse, UIEvent, UIRender, UIUpdate,
    RegisterAgent, RegisterUI, AgentCard, AgentSkill
)
from shared.primitives import (
    Container, Text, Card, Grid, Alert, MetricCard, ProgressBar,
    create_ui_response
)

load_dotenv(override=True)

PORT = int(os.getenv("ORCHESTRATOR_PORT", 8001))

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('Orchestrator')


class Orchestrator:
    def __init__(self):
        self.agents: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.ui_clients: List[websockets.WebSocketServerProtocol] = []
        self.agent_cards: Dict[str, AgentCard] = {}
        self.agent_capabilities: Dict[str, List[Dict]] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}

        # LLM Client
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.llm_model = os.getenv("LLM_MODEL", "meta-llama/Llama-3.2-90B-Vision-Instruct")

        if api_key and base_url:
            self.llm_client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info(f"LLM configured: {base_url} model={self.llm_model}")
        else:
            self.llm_client = None
            logger.warning("No LLM configured — tool routing disabled")

        # History Manager
        self.history = HistoryManager()

    # =========================================================================
    # AGENT MANAGEMENT
    # =========================================================================

    async def register_agent(self, websocket, msg: RegisterAgent):
        """Register a specialist agent and store its capabilities."""
        card = msg.agent_card
        if not card:
            logger.warning("RegisterAgent with no card")
            return

        self.agents[card.agent_id] = websocket
        self.agent_cards[card.agent_id] = card

        # Extract capabilities for routing
        caps = []
        for skill in card.skills:
            caps.append({
                "name": skill.id,
                "description": skill.description,
                "input_schema": skill.input_schema
            })
        self.agent_capabilities[card.agent_id] = caps

        logger.info(f"Agent registered: {card.agent_id} ({card.name}) with {len(caps)} tools")

        # Notify all UI clients
        for ui in self.ui_clients:
            try:
                await ui.send(json.dumps({
                    "type": "agent_registered",
                    "agent_id": card.agent_id,
                    "name": card.name,
                    "tools": [c["name"] for c in caps]
                }))
            except Exception:
                pass

    async def discover_agent(self, base_url: str):
        """Discover an agent by fetching its A2A agent card and connecting via WebSocket."""
        try:
            # Fetch agent card
            card_url = f"{base_url}/.well-known/agent-card.json"
            async with aiohttp.ClientSession() as session:
                async with session.get(card_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to fetch agent card from {card_url}: {resp.status}")
                        return
                    card_data = await resp.json()

            card = AgentCard.from_dict(card_data)
            agent_id = card.agent_id

            if agent_id in self.agents:
                logger.info(f"Agent {agent_id} already connected")
                return

            # Connect via WebSocket
            ws_url = f"ws://{base_url.replace('http://', '').replace('https://', '')}/agent"
            ws = await websockets.connect(ws_url)

            # Listen for RegisterAgent message
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            parsed = Message.from_json(raw)
            if isinstance(parsed, RegisterAgent):
                await self.register_agent(ws, parsed)

            # Start listening loop
            asyncio.create_task(self._agent_listen_loop(ws, agent_id))

            logger.info(f"Connected to agent: {agent_id} at {base_url}")

        except Exception as e:
            logger.error(f"Failed to discover agent at {base_url}: {e}")

    async def _agent_listen_loop(self, ws, agent_id: str):
        """Listen for messages from a connected agent."""
        try:
            async for message in ws:
                await self.handle_agent_message(ws, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Agent {agent_id} disconnected")
        finally:
            if agent_id in self.agents:
                del self.agents[agent_id]
            if agent_id in self.agent_cards:
                del self.agent_cards[agent_id]
                logger.info(f"Agent {agent_id} deregistered")

    # =========================================================================
    # MESSAGE HANDLING
    # =========================================================================

    async def handle_agent_message(self, websocket, message: str):
        """Handle message from an agent."""
        try:
            msg = Message.from_json(message)

            if isinstance(msg, RegisterAgent):
                await self.register_agent(websocket, msg)

            elif isinstance(msg, MCPResponse):
                req_id = msg.request_id
                if req_id in self.pending_requests:
                    self.pending_requests[req_id].set_result(msg)
                else:
                    logger.warning(f"Received response for unknown request: {req_id}")

        except Exception as e:
            logger.error(f"Error handling agent message: {e}")

    async def handle_ui_message(self, websocket, message: str):
        """Handle message from a UI client."""
        try:
            msg = Message.from_json(message)

            if isinstance(msg, RegisterUI):
                logger.info(f"UI registered")
                await self.send_dashboard(websocket)

            elif isinstance(msg, UIEvent):
                if msg.action == "chat_message":
                    user_message = msg.payload.get("message", "")
                    chat_id = msg.session_id or msg.payload.get("chat_id")
                    
                    # If no chat_id provided, create one
                    if not chat_id:
                        chat_id = self.history.create_chat()
                        # Inform UI about new chat ID
                        await websocket.send(json.dumps({
                            "type": "ui_event",
                            "action": "chat_created",
                            "payload": {"chat_id": chat_id}
                        }))

                    await self.handle_chat_message(websocket, user_message, chat_id)

                elif msg.action == "get_dashboard":
                    await self.send_dashboard(websocket)

                elif msg.action == "discover_agents":
                    await self.send_agent_list(websocket)

                elif msg.action == "get_history":
                    chats = self.history.get_recent_chats()
                    await websocket.send(json.dumps({
                        "type": "history_list",
                        "chats": chats
                    }))

                elif msg.action == "load_chat":
                    chat_id = msg.payload.get("chat_id")
                    chat = self.history.get_chat(chat_id)
                    if chat:
                        await websocket.send(json.dumps({
                            "type": "chat_loaded",
                            "chat": chat
                        }))
                    else:
                        await self.send_ui_render(websocket, [
                            Alert(message="Chat not found", variant="error").to_json()
                        ])

                elif msg.action == "new_chat":
                    chat_id = self.history.create_chat()
                    await websocket.send(json.dumps({
                        "type": "chat_created",
                        "payload": {"chat_id": chat_id}
                    }))

        except Exception as e:
            logger.error(f"Error handling UI message: {e}")

    # =========================================================================
    # LLM-POWERED TOOL ROUTING
    # =========================================================================

    async def handle_chat_message(self, websocket, message: str, chat_id: str):
        """Process a chat message: LLM determines which tools to call (Multi-Turn Re-Act Loop)."""
        logger.info(f"Processing chat message: '{message}' for chat_id {chat_id}")
        if not message:
            logger.warning("Empty message received")
            return

        if not self.llm_client:
            await self.send_ui_render(websocket, [
                Alert(message="LLM not configured. Set OPENAI_API_KEY and OPENAI_BASE_URL.", variant="error").to_json()
            ])
            return

        # Send loading state to UI
        await websocket.send(json.dumps({
            "type": "chat_status",
            "status": "thinking",
            "message": "Analyzing request and planning actions..."
        }))
        
        # Save User Message to History
        self.history.add_message(chat_id, "user", message)

        # Async title summarization for new chats
        chat_data = self.history.get_chat(chat_id)
        if chat_data and len(chat_data.get("messages", [])) == 1:
            asyncio.create_task(self.summarize_chat_title(chat_id, message))

        # Build tool definitions from registered agents
        logger.info(f"Building tool definitions from {len(self.agent_cards)} agents...")
        tools_desc = []
        tool_to_agent = {}  # Map tool name → agent_id

        for agent_id, card in self.agent_cards.items():
            if agent_id not in self.agents:
                continue

            for skill in card.skills:
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": skill.id,
                        "description": skill.description,
                        "parameters": skill.input_schema or {"type": "object", "properties": {}}
                    }
                }
                tools_desc.append(tool_def)
                tool_to_agent[skill.id] = agent_id

        if not tools_desc:
            await self.send_ui_render(websocket, [
                Alert(message="No agents connected. Please wait for agents to register.", variant="warning").to_json()
            ])
            return

        try:
            # ------------------------------------------------------------------
            # SYSTEM PROMPT
            # ------------------------------------------------------------------
            system_prompt = """You are an AI orchestrator. Your goal is to simplify complex tasks for the user by intelligently using available tools.

AVAILABLE TOOLS: sent in the `tools` parameter.

PROCESS (Re-Act Loop):
1. **Analyze**: Break down the user's request into logical steps.
2. **Plan & Execute**: 
   - If you need data, call the appropriate tool.
   - You can call multiple tools in parallel if they are independent.
   - If a step depends on previous output (e.g., "search patients" -> "graph their age"), wait for the first tool's result before calling the next.
3. **Observe**: You will receive the tool's output in the next turn.
4. **Iterate**: 
   - IF the task is not complete or you need more data (e.g., now you have the patients, need to graph them), call the next tool.
   - IF you have all necessary information, provide a final answer.

CRITICAL RULES:
- **VERIFY**: Check if tool outputs actually contain the data you expect before stating it exists. If a search returns 0 results, do NOT try to graph them.
- **FINAL RESPONSE**: When you have finished all actions, provide a natural language summary of what you did and what was found.
- **VISUALIZATIONS**: If the user asks for a graph, YOU MUST call the graphing tool. Do not just describe the data.
"""

            # ------------------------------------------------------------------
            # MULTI-TURN LOOP
            # ------------------------------------------------------------------
            messages = [
                {"role": "system", "content": system_prompt},
                # For context, we could add recent history here, but let's keep it focused on the current task
                {"role": "user", "content": message}
            ]

            MAX_TURNS = 5
            turn_count = 0

            while turn_count < MAX_TURNS:
                turn_count += 1
                logger.info(f"--- Turn {turn_count}/{MAX_TURNS} ---")

                # Call LLM
                llm_msg = await self._call_llm(websocket, messages, tools_desc)
                if not llm_msg:
                    logger.error("LLM returned None, stopping loop.")
                    break

                # Check if LLM wants to call tools
                if llm_msg.tool_calls:
                    logger.info(f"LLM requested {len(llm_msg.tool_calls)} tool(s)")
                    
                    # Notify UI
                    tool_names = [tc.function.name for tc in llm_msg.tool_calls]
                    await websocket.send(json.dumps({
                        "type": "chat_status",
                        "status": "executing",
                        "message": f"Running: {', '.join(tool_names)}..."
                    }))

                    # Add assistant's message (with tool calls) to history
                    messages.append(llm_msg)

                    # Execute tools
                    tool_results = []
                    if len(llm_msg.tool_calls) == 1:
                        tc = llm_msg.tool_calls[0]
                        res = await self.execute_single_tool(websocket, tc, tool_to_agent, chat_id)
                        if res: tool_results.append(res)
                    else:
                        res_list = await self.execute_parallel_tools(websocket, llm_msg.tool_calls, tool_to_agent, chat_id)
                        tool_results.extend(res_list)

                    # Append tool outputs to history
                    # We MUST ensure the tool_call_id matches what OpenAI sent
                    for i, tc in enumerate(llm_msg.tool_calls):
                        # Find corresponding result (preserves order)
                        res = tool_results[i] if i < len(tool_results) else None
                        
                        content_str = "No output"
                        if res:
                            if res.error:
                                content_str = f"Error: {res.error.get('message')}"
                            elif res.result:
                                if isinstance(res.result, dict) and "_data" in res.result:
                                    content_str = json.dumps(res.result["_data"])
                                else:
                                    content_str = json.dumps(res.result)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": content_str
                        })

                    # Loop continues to next turn to let LLM analyze results
                
                else:
                    # No tool calls -> Final Response
                    logger.info("LLM provided final response. conversation complete.")
                    content = llm_msg.content or "I'm not sure how to help with that."
                    
                    # Send text response to UI
                    await self.send_ui_render(websocket, [
                        Card(title="Analysis", content=[
                            Text(content=content, variant="markdown")
                        ]).to_json()
                    ])

                    # Save complete interaction to history
                    self.history.add_message(chat_id, "assistant", [
                        Card(title="Analysis", content=[
                            Text(content=content, variant="markdown")
                        ]).to_json()
                    ])
                    return

            # If loop exits without final response
            if turn_count >= MAX_TURNS:
                logger.warning("Max turns reached. Stopping.")
                await self.send_ui_render(websocket, [
                    Alert(message="I stopped after several steps to avoid getting stuck. Please refine your request if more is needed.", variant="warning").to_json()
                ])

        except Exception as e:
            logger.error(f"LLM routing error: {e}", exc_info=True)
            await self.send_ui_render(websocket, [
                Alert(message=str(e), variant="error", title="Error").to_json()
            ])

    async def _call_llm(self, websocket, messages, tools_desc=None):
        """Helper to call LLM with retries."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self.llm_model,
                    "messages": messages
                }
                if tools_desc:
                    kwargs["tools"] = tools_desc
                    kwargs["tool_choice"] = "auto"
                
                response = await asyncio.to_thread(
                    self.llm_client.chat.completions.create,
                    **kwargs
                )
                return response.choices[0].message
            except Exception as e:
                logger.warning(f"LLM Attempt {attempt} failed: {e}")
                if attempt == self.MAX_RETRIES:
                    raise e
                await asyncio.sleep(1)
        return None

    # =========================================================================
    # CONSTANTS
    # =========================================================================

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1.0, 2.0]  # seconds between retries (attempt 1→2, 2→3)

    async def execute_single_tool(self, websocket, tool_call, tool_to_agent: Dict, chat_id: str = None) -> Optional[MCPResponse]:
        """Execute a single tool call and render its UI components. Returns the Result object."""
        tool_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
        except json.JSONDecodeError:
            args = {}

        agent_id = tool_to_agent.get(tool_name)
        if not agent_id or agent_id not in self.agents:
            err_msg = f"No agent available for tool '{tool_name}'"
            await self.send_ui_render(websocket, [
                Alert(message=err_msg, variant="error").to_json()
            ])
            return MCPResponse(error={"message": err_msg})

        result = await self._execute_with_retry(websocket, agent_id, tool_name, args)

        if result and result.ui_components and not result.error:
            if chat_id:
                self.history.add_message(chat_id, "assistant", result.ui_components)
            await self.send_ui_render(websocket, result.ui_components)
        elif result and result.error:
            # We render the error, but we also return it so the LLM knows it failed
            err_msg = result.error.get('message', 'Unknown error')
            await self.send_ui_render(websocket, [
                Alert(message=f"Tool '{tool_name}' failed: {err_msg}", variant="error").to_json()
            ])
        else:
             # Fallback for generic results
             pass

        return result

    async def execute_parallel_tools(self, websocket, tool_calls, tool_to_agent: Dict, chat_id: str = None) -> List[Optional[MCPResponse]]:
        """Execute multiple tool calls in parallel. Returns list of Results."""
        tasks = []
        tool_names = []

        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}

            agent_id = tool_to_agent.get(tool_name)
            if agent_id and agent_id in self.agents:
                tasks.append(self._execute_with_retry(websocket, agent_id, tool_name, args))
                tool_names.append(tool_name)
            else:
                 # Create a dummy task that returns an error result
                 async def _dummy_error():
                     return MCPResponse(error={"message": f"No agent for {tool_name}"})
                 tasks.append(_dummy_error())
                 tool_names.append(tool_name)

        if not tasks:
            return []

        # Execute all tools concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and render
        final_results = []
        all_components = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # System error during execution
                err_res = MCPResponse(error={"message": str(result)})
                final_results.append(err_res)
                all_components.append(Alert(message=f"Tool error: {str(result)}", variant="error").to_json())
            else:
                final_results.append(result)
                if result:
                    if result.ui_components:
                        all_components.extend(result.ui_components)
                    if result.error:
                        all_components.append(Alert(message=f"Tool '{tool_names[i]}' failed: {result.error.get('message')}", variant="error").to_json())

        if all_components:
            if chat_id:
                self.history.add_message(chat_id, "assistant", all_components)
            await self.send_ui_render(websocket, all_components)
            
        return final_results

    async def _execute_with_retry(
        self, websocket, agent_id: str, tool_name: str, args: Dict,
        max_retries: int = None
    ) -> Optional[MCPResponse]:
        """Execute a tool call with up to max_retries attempts.

        On retryable errors, sends status updates to the UI and waits
        with exponential backoff before trying again.
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        last_result = None

        for attempt in range(1, max_retries + 1):
            result = await self.execute_tool_and_wait(agent_id, tool_name, args)
            last_result = result

            # Success: no error at all
            if result and not result.error:
                if attempt > 1:
                    logger.info(f"Tool '{tool_name}' succeeded on attempt {attempt}/{max_retries}")
                return result

            # Check if error is retryable
            is_retryable = True
            error_msg = "Unknown error"
            if result and result.error:
                is_retryable = result.error.get("retryable", True)
                error_msg = result.error.get("message", "Unknown error")

            if not is_retryable:
                logger.info(f"Tool '{tool_name}' failed with non-retryable error: {error_msg}")
                return result

            # Retryable error — try again if attempts remain
            if attempt < max_retries:
                backoff = self.RETRY_BACKOFF[attempt - 1] if attempt - 1 < len(self.RETRY_BACKOFF) else 2.0
                logger.warning(
                    f"Tool '{tool_name}' failed (attempt {attempt}/{max_retries}): {error_msg}. "
                    f"Retrying in {backoff}s..."
                )
                # Notify UI about the retry
                try:
                    await websocket.send(json.dumps({
                        "type": "chat_status",
                        "status": "retrying",
                        "message": f"Tool '{tool_name.replace('_', ' ').title()}' failed. "
                                   f"Retrying... (attempt {attempt + 1}/{max_retries})"
                    }))
                except Exception:
                    pass  # Don't let status notification failure break retry logic

                await asyncio.sleep(backoff)
            else:
                logger.error(
                    f"Tool '{tool_name}' failed after {max_retries} attempts: {error_msg}"
                )

        return last_result

    async def execute_tool_and_wait(self, agent_id: str, tool_name: str, args: Dict, timeout: float = 30.0) -> Optional[MCPResponse]:
        """Send an MCP tool call to an agent and wait for the response."""
        request_id = f"req_{tool_name}_{int(time.time() * 1000)}"

        request = MCPRequest(
            request_id=request_id,
            method="tools/call",
            params={"name": tool_name, "arguments": args}
        )

        # Create a future for the response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future

        try:
            agent_ws = self.agents[agent_id]
            await agent_ws.send(request.to_json())
            logger.info(f"Sent tool call: {tool_name} → {agent_id}")

            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            logger.error(f"Tool call timed out: {tool_name}")
            return MCPResponse(request_id=request_id,
                               error={"message": "Tool call timed out", "retryable": True})
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return MCPResponse(request_id=request_id,
                               error={"message": str(e), "retryable": True})
        finally:
            self.pending_requests.pop(request_id, None)

    # =========================================================================
    # UI HELPERS
    # =========================================================================

    async def send_ui_render(self, websocket, components: List):
        """Send a UIRender message to a UI client."""
        msg = UIRender(components=components)
        await websocket.send(msg.to_json())

    async def send_dashboard(self, websocket):
        """Send the initial dashboard view."""
        agent_list = []
        for agent_id, card in self.agent_cards.items():
            agent_list.append({
                "id": card.agent_id,
                "name": card.name,
                "tools": [s.id for s in card.skills],
                "status": "connected"
            })

        await websocket.send(json.dumps({
            "type": "system_config",
            "config": {
                "agents": agent_list,
                "total_tools": sum(len(c) for c in self.agent_capabilities.values())
            }
        }))

    async def send_agent_list(self, websocket):
        """Send list of connected agents."""
        agents = []
        for agent_id, card in self.agent_cards.items():
            agents.append({
                "id": card.agent_id,
                "name": card.name,
                "description": card.description,
                "tools": [{"name": s.id, "description": s.description} for s in card.skills],
                "status": "connected"
            })

        await websocket.send(json.dumps({
            "type": "agent_list",
            "agents": agents
        }))

    # =========================================================================
    # SERVER
    # =========================================================================

    async def handle_ui_connection(self, websocket, path=None):
        """Handle a UI client WebSocket connection."""
        self.ui_clients.append(websocket)
        logger.info(f"UI client connected (total: {len(self.ui_clients)})")

        try:
            async for message in websocket:
                await self.handle_ui_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.ui_clients.remove(websocket)
            logger.info(f"UI client disconnected (total: {len(self.ui_clients)})")

    async def start(self):
        """Start the orchestrator WebSocket server."""
        logger.info(f"Orchestrator starting on port {PORT}")

        # Auto-discover agents (continuous monitor)
        agent_port = int(os.getenv("AGENT_PORT", 8003))
        asyncio.create_task(self._monitor_agents(agent_port))

        async with websockets.serve(self.handle_ui_connection, "0.0.0.0", PORT):
            logger.info(f"Orchestrator listening on ws://0.0.0.0:{PORT}")
            await asyncio.Future()  # Run forever

    async def _monitor_agents(self, agent_port: int):
        """Continuously monitor and discover agents."""
        agent_url = f"http://localhost:{agent_port}"
        logger.info(f"Starting agent monitor for {agent_url}...")

        while True:
            try:
                # This will connect if not already connected
                await self.discover_agent(agent_url)
            except Exception as e:
                # Log only on state change or verbose debug? For now, keep it quiet
                # discover_agent already logs errors
                pass
            
            await asyncio.sleep(5)  # Check every 5 seconds

    async def summarize_chat_title(self, chat_id: str, message: str):
        """Generate a concise title for the chat using LLM."""
        if not self.llm_client:
            return

        try:
            response = await asyncio.to_thread(
                self.llm_client.chat.completions.create,
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "Summarize the following user request into a concise 3-5 word title. Return ONLY the title, no quotes or other text."},
                    {"role": "user", "content": message}
                ],
                max_tokens=20
            )
            title = response.choices[0].message.content.strip().strip('"')
            
            # Update history and notify UI
            self.history.update_chat_title(chat_id, title)
            
            # Broadcast update to all connected UIs
            if self.ui_clients:
                history_list = self.history.get_recent_chats()
                msg = json.dumps({
                    "type": "history_list",
                    "chats": history_list
                })
                # Create tasks for sending to avoid blocking
                await asyncio.gather(
                    *[client.send(msg) for client in self.ui_clients],
                    return_exceptions=True
                )
                
        except Exception as e:
            logger.error(f"Failed to summarize chat title: {e}")


if __name__ == "__main__":
    orch = Orchestrator()
    asyncio.run(orch.start())
