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
import uvicorn
from jose import jwt as jose_jwt
from dotenv import load_dotenv
from openai import OpenAI
from httpx import Timeout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from orchestrator.history import HistoryManager

from shared.protocol import (
    Message, MCPRequest, MCPResponse, UIEvent, UIRender, UIUpdate,
    RegisterAgent, RegisterUI, AgentCard, AgentSkill
)
from shared.primitives import (
    Container, Text, Card, Grid, Alert, MetricCard, ProgressBar,
    Collapsible, create_ui_response
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
        self.ui_sessions: Dict[websockets.WebSocketServerProtocol, Dict] = {}
        self.agent_cards: Dict[str, AgentCard] = {}
        self.agent_capabilities: Dict[str, List[Dict]] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}

        # LLM Client
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.llm_model = os.getenv("LLM_MODEL", "meta-llama/Llama-3.2-90B-Vision-Instruct")

        if api_key and base_url:
            self.llm_client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=Timeout(180.0, connect=10.0)  # 180s for large models (DeepSeek, etc.)
            )
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
                token = msg.token
                user_data = None
                
                # Check for token validation (skip if not configured or in debug/dev mode if desired, but we want security)
                if token:
                    user_data = await self.validate_token(token)
                
                if user_data:
                    logger.info(f"UI registered: {user_data.get('preferred_username', 'unknown')}")
                    self.ui_sessions[websocket] = user_data
                    
                    # Notify UI of success (optional, or just send dashboard)
                    await self.send_dashboard(websocket)
                else:
                    logger.warning("UI registration failed: Invalid or missing token")
                    await self.send_ui_render(websocket, [
                        Alert(message="Authentication failed. Please log in again.", variant="error").to_json()
                    ])
                    # We might want to close, but let's let the UI handle the error alert
                    return

            elif isinstance(msg, UIEvent):
                # Ensure authenticated
                if websocket not in self.ui_sessions:
                    await self.send_ui_render(websocket, [
                        Alert(message="Unauthorized. Please refresh.", variant="error").to_json()
                    ])
                    return

                if msg.action == "chat_message":
                    user_message = msg.payload.get("message", "")
                    chat_id = msg.session_id or msg.payload.get("chat_id")
                    
                    # If no chat_id provided, create one
                    if not chat_id:
                        chat_id = self.history.create_chat()
                        # Inform UI about new chat ID
                        await websocket.send(json.dumps({
                            "type": "chat_created",
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

                # Saved components actions
                elif msg.action == "save_component":
                    chat_id = msg.payload.get("chat_id")
                    component_data = msg.payload.get("component_data")
                    component_type = msg.payload.get("component_type")
                    title = msg.payload.get("title")
                    
                    if not chat_id or not component_data:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing required fields for saving component", variant="error").to_json()
                        ])
                        return
                    
                    try:
                        component_id = self.history.save_component(
                            chat_id, component_data, component_type, title
                        )
                        
                        # Send success response
                        await websocket.send(json.dumps({
                            "type": "component_saved",
                            "component": {
                                "id": component_id,
                                "chat_id": chat_id,
                                "component_data": component_data,
                                "component_type": component_type,
                                "title": title or component_type.replace('_', ' ').title(),
                                "created_at": int(time.time() * 1000)
                            }
                        }))
                    except Exception as e:
                        logger.error(f"Failed to save component: {e}")
                        await websocket.send(json.dumps({
                            "type": "component_save_error",
                            "error": str(e)
                        }))

                elif msg.action == "get_saved_components":
                    chat_id = msg.payload.get("chat_id")
                    components = self.history.get_saved_components(chat_id)
                    await websocket.send(json.dumps({
                        "type": "saved_components_list",
                        "components": components
                    }))

                elif msg.action == "delete_saved_component":
                    component_id = msg.payload.get("component_id")
                    if not component_id:
                        await self.send_ui_render(websocket, [
                            Alert(message="Missing component ID", variant="error").to_json()
                        ])
                        return
                    
                    success = self.history.delete_component(component_id)
                    if success:
                        await websocket.send(json.dumps({
                            "type": "component_deleted",
                            "component_id": component_id
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "type": "component_save_error",
                            "error": "Component not found"
                        }))

                elif msg.action == "combine_components":
                    source_id = msg.payload.get("source_id")
                    target_id = msg.payload.get("target_id")
                    
                    if not source_id or not target_id:
                        await websocket.send(json.dumps({
                            "type": "combine_error",
                            "error": "Both source and target component IDs are required"
                        }))
                        return
                    
                    source = self.history.get_component_by_id(source_id)
                    target = self.history.get_component_by_id(target_id)
                    
                    if not source or not target:
                        await websocket.send(json.dumps({
                            "type": "combine_error",
                            "error": "One or both components not found"
                        }))
                        return
                    
                    # Send progress
                    await websocket.send(json.dumps({
                        "type": "combine_status",
                        "status": "combining",
                        "message": f"Combining {source['title']} with {target['title']}..."
                    }))
                    
                    try:
                        result = await self._combine_components_llm(
                            [source, target],
                            mode="combine"
                        )
                        
                        if result.get("error"):
                            await websocket.send(json.dumps({
                                "type": "combine_error",
                                "error": result["error"]
                            }))
                        else:
                            chat_id = source["chat_id"]
                            new_components = self.history.replace_components(
                                [source_id, target_id],
                                result["components"],
                                chat_id
                            )
                            await websocket.send(json.dumps({
                                "type": "components_combined",
                                "removed_ids": [source_id, target_id],
                                "new_components": new_components
                            }))
                    except Exception as e:
                        logger.error(f"Combine failed: {e}", exc_info=True)
                        await websocket.send(json.dumps({
                            "type": "combine_error",
                            "error": f"Failed to combine components: {str(e)}"
                        }))

                elif msg.action == "condense_components":
                    component_ids = msg.payload.get("component_ids", [])
                    
                    if len(component_ids) < 2:
                        await websocket.send(json.dumps({
                            "type": "combine_error",
                            "error": "At least 2 components are required to condense"
                        }))
                        return
                    
                    components = []
                    for cid in component_ids:
                        comp = self.history.get_component_by_id(cid)
                        if comp:
                            components.append(comp)
                    
                    if len(components) < 2:
                        await websocket.send(json.dumps({
                            "type": "combine_error",
                            "error": "Not enough valid components found"
                        }))
                        return
                    
                    await websocket.send(json.dumps({
                        "type": "combine_status",
                        "status": "condensing",
                        "message": f"Condensing {len(components)} components..."
                    }))
                    
                    try:
                        result = await self._combine_components_llm(
                            components,
                            mode="condense"
                        )
                        
                        if result.get("error"):
                            await websocket.send(json.dumps({
                                "type": "combine_error",
                                "error": result["error"]
                            }))
                        else:
                            chat_id = components[0]["chat_id"]
                            new_components = self.history.replace_components(
                                component_ids,
                                result["components"],
                                chat_id
                            )
                            await websocket.send(json.dumps({
                                "type": "components_condensed",
                                "removed_ids": component_ids,
                                "new_components": new_components
                            }))
                    except Exception as e:
                        logger.error(f"Condense failed: {e}", exc_info=True)
                        await websocket.send(json.dumps({
                            "type": "combine_error",
                            "error": f"Failed to condense components: {str(e)}"
                        }))

        except Exception as e:
            logger.error(f"Error handling UI message: {e}")

    # =========================================================================
    # COMPONENT COMBINING (LLM-powered)
    # =========================================================================

    async def _combine_components_llm(self, components: list, mode: str = "combine") -> dict:
        """Use LLM to combine/condense UI components.
        
        Args:
            components: List of component dicts with component_data, title, etc.
            mode: 'combine' for merging 2 components, 'condense' for reducing many.
        
        Returns:
            {"components": [...]} on success, {"error": "..."} on failure.
        """
        if not self.llm_client:
            return {"error": "LLM not configured"}

        # Build the component descriptions for the prompt
        component_descriptions = []
        for i, comp in enumerate(components):
            component_descriptions.append(
                f"Component {i+1} (title: \"{comp['title']}\", type: \"{comp['component_type']}\"):\n"
                f"```json\n{json.dumps(comp['component_data'], indent=2)}\n```"
            )
        
        components_text = "\n\n".join(component_descriptions)

        schema_description = """Available UI primitive types and their JSON structure:
- "text": {type: "text", content: "...", variant: "body|h1|h2|h3|caption|markdown"}
- "card": {type: "card", title: "...", content: [...child components...]}
- "metric": {type: "metric", title: "...", value: "...", subtitle: "...", progress: 0.0-1.0, variant: "default|warning|error|success"}
- "table": {type: "table", title: "...", headers: [...], rows: [[...],...]}
- "grid": {type: "grid", columns: 2, gap: 16, children: [...child components...]}
- "container": {type: "container", children: [...child components...]}
- "list": {type: "list", items: [...], ordered: false, variant: "default|detailed"}
- "alert": {type: "alert", message: "...", title: "...", variant: "info|success|warning|error"}
- "progress": {type: "progress", value: 0.0-1.0, label: "...", show_percentage: true}
- "bar_chart": {type: "bar_chart", title: "...", labels: [...], datasets: [{label: "...", data: [...]}]}
- "line_chart": {type: "line_chart", title: "...", labels: [...], datasets: [{label: "...", data: [...]}]}
- "pie_chart": {type: "pie_chart", title: "...", labels: [...], data: [...], colors: [...]}
- "code": {type: "code", code: "...", language: "..."}
- "divider": {type: "divider"}
- "collapsible": {type: "collapsible", title: "...", content: [...child components...], default_open: false}"""

        if mode == "combine":
            prompt = f"""You are a UI component combiner. You are given 2 UI components and must merge them into a single cohesive component.

{schema_description}

RULES:
1. Analyze whether these components can be meaningfully combined.
2. If they contain RELATED data (e.g., patient data + disease chart, or multiple system metrics), combine them into a unified component using cards, grids, or tables.
3. If they are UNRELATED or incompatible, respond ONLY with: ERROR: <brief reason>
4. Preserve ALL data — do not lose any information from either component.
5. Use grid layouts to arrange related metrics side-by-side.
6. Use cards with descriptive titles to group related content.

COMPONENTS TO COMBINE:

{components_text}

Respond with ONLY valid JSON (no markdown code fences) in this format:
{{
  "components": [
    {{
      "component_data": {{...the merged component tree...}},
      "component_type": "card",
      "title": "Descriptive Title For Merged Component"
    }}
  ]
}}

Or if they cannot be combined:
ERROR: <reason>"""
        else:  # condense
            prompt = f"""You are a UI component condenser. You are given {len(components)} UI components and must combine as many as possible into fewer cohesive components.

{schema_description}

RULES:
1. Group RELATED components together (e.g., all system metrics into one dashboard card, all patient data into one view).
2. Keep UNRELATED components separate — don't force unrelated data together.
3. Preserve ALL data — do not lose any information.
4. Use grid layouts to arrange related metrics side-by-side.
5. Use cards with descriptive titles to group related content.
6. The goal is to REDUCE the total number of components while maintaining clarity.

COMPONENTS TO CONDENSE:

{components_text}

Respond with ONLY valid JSON (no markdown code fences) in this format:
{{
  "components": [
    {{
      "component_data": {{...component tree...}},
      "component_type": "card",
      "title": "Descriptive Title"
    }}
  ]
}}"""

        try:
            # Use _call_llm for built-in retries (important for transient 502s)
            llm_msg = await self._call_llm(
                None,  # no websocket needed for combine
                [
                    {"role": "system", "content": "You are a precise UI component combiner. Output ONLY valid JSON or an ERROR message. No explanations, no markdown fences."},
                    {"role": "user", "content": prompt}
                ],
                tools_desc=None,
                temperature=0.1
            )
            
            if not llm_msg:
                return {"error": "LLM returned no response"}
            
            content = (llm_msg.content or "").strip()
            logger.info(f"LLM combine response ({len(content)} chars): {content[:200]}...")
            
            # Check for ERROR response
            if content.upper().startswith("ERROR"):
                error_msg = content.split(":", 1)[1].strip() if ":" in content else content
                return {"error": error_msg}
            
            # Try to parse JSON
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try to find JSON in the response
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"error": f"Failed to parse LLM response as JSON"}
            
            if "components" not in result or not isinstance(result["components"], list):
                return {"error": "LLM response missing 'components' array"}
            
            # Known valid primitive types from primitives.py
            VALID_TYPES = {
                "container", "text", "button", "card", "table", "list",
                "alert", "progress", "metric", "code", "image", "grid",
                "tabs", "divider", "input", "bar_chart", "line_chart",
                "pie_chart", "plotly_chart", "collapsible"
            }
            
            # Validate each component
            for comp in result["components"]:
                if "component_data" not in comp:
                    return {"error": "LLM response component missing 'component_data'"}
                
                # Validate the component type
                comp_data = comp["component_data"]
                comp_type = comp_data.get("type", "")
                if comp_type and comp_type not in VALID_TYPES:
                    logger.warning(f"LLM produced unknown component type '{comp_type}', wrapping in card")
                    # Wrap unknown types in a card to ensure they render
                    comp["component_data"] = {
                        "type": "card",
                        "title": comp_data.get("title", "Combined Component"),
                        "content": [comp_data] if comp_type else []
                    }
                    comp_type = "card"
                
                # Recursively validate children
                self._validate_component_tree(comp_data, VALID_TYPES)
                
                if "component_type" not in comp:
                    comp["component_type"] = comp_type or "card"
                if "title" not in comp:
                    comp["title"] = comp["component_data"].get("title", "Combined Component")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM combine error: {e}", exc_info=True)
            return {"error": f"LLM error: {str(e)}"}

    def _validate_component_tree(self, node: dict, valid_types: set):
        """Recursively validate component tree, fixing invalid types."""
        if not isinstance(node, dict):
            return
        
        node_type = node.get("type", "")
        if node_type and node_type not in valid_types:
            logger.warning(f"Fixing unknown component type '{node_type}' -> 'container'")
            node["type"] = "container"
        
        # Validate children arrays
        for key in ("children", "content"):
            children = node.get(key, [])
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        self._validate_component_tree(child, valid_types)
        
        # Validate tab items
        tabs = node.get("tabs", [])
        if isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict):
                    for child in tab.get("content", []):
                        if isinstance(child, dict):
                            self._validate_component_tree(child, valid_types)

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
        await self._safe_send(websocket, json.dumps({
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
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    await self.send_ui_render(websocket, [
                        Alert(message="Failed to get a response from the AI model. Please try again.", variant="error").to_json()
                    ])
                    return

                # Check for reasoning content (DeepSeek, o1, etc.)
                reasoning = getattr(llm_msg, 'reasoning_content', None)
                if reasoning:
                    logger.info(f"LLM returned reasoning content ({len(reasoning)} chars)")
                    reasoning_components = [
                        Collapsible(title="Reasoning", content=[
                            Text(content=reasoning, variant="markdown")
                        ]).to_json()
                    ]
                    await self.send_ui_render(websocket, reasoning_components)
                    self.history.add_message(chat_id, "assistant", reasoning_components)

                # Check if LLM wants to call tools
                if llm_msg.tool_calls:
                    logger.info(f"LLM requested {len(llm_msg.tool_calls)} tool(s)")
                    
                    # Notify UI
                    tool_names = [tc.function.name for tc in llm_msg.tool_calls]
                    await self._safe_send(websocket, json.dumps({
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

                    # Collect tool UI components and send as a single collapsible
                    tool_ui_components = []
                    for res in tool_results:
                        if res and res.ui_components and not res.error:
                            tool_ui_components.extend(res.ui_components)

                    if tool_ui_components:
                        tool_label = ', '.join(tn.replace('_', ' ').title() for tn in tool_names)
                        collapsible = Collapsible(
                            title=f"Tool Results — {tool_label}",
                            content=[
                                comp if isinstance(comp, dict) else comp
                                for comp in tool_ui_components
                            ],
                            default_open=False
                        ).to_json()
                        await self.send_ui_render(websocket, [collapsible])
                        if chat_id:
                            self.history.add_message(chat_id, "assistant", [collapsible])

                    # Append tool outputs to LLM conversation history
                    for i, tc in enumerate(llm_msg.tool_calls):
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
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "thinking",
                        "message": "Analyzing results..."
                    }))
                
                else:
                    # No tool calls -> Final Response
                    logger.info("LLM provided final response. conversation complete.")
                    content = llm_msg.content or "I'm not sure how to help with that."
                    
                    # Send response in a Card container
                    response_components = [
                        Card(title="Analysis", content=[
                            Text(content=content, variant="markdown")
                        ]).to_json()
                    ]
                    await self.send_ui_render(websocket, response_components)

                    # Save complete interaction to history
                    self.history.add_message(chat_id, "assistant", response_components)

                    # Signal that processing is complete
                    await self._safe_send(websocket, json.dumps({
                        "type": "chat_status",
                        "status": "done",
                        "message": ""
                    }))
                    return

            # If loop exits without final response
            if turn_count >= MAX_TURNS:
                logger.warning("Max turns reached. Stopping.")
                await self.send_ui_render(websocket, [
                    Alert(message="I stopped after several steps to avoid getting stuck. Please refine your request if more is needed.", variant="warning").to_json()
                ])
                await self._safe_send(websocket, json.dumps({
                    "type": "chat_status",
                    "status": "done",
                    "message": ""
                }))

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"WebSocket closed during chat processing for chat_id {chat_id} — client likely reconnected")
        except Exception as e:
            logger.error(f"LLM routing error: {e}", exc_info=True)
            # Clear the 'thinking' spinner so the UI doesn't hang
            await self._safe_send(websocket, json.dumps({
                "type": "chat_status",
                "status": "done",
                "message": ""
            }))
            # Show a user-friendly error message
            error_text = str(e)
            if "424" in error_text or "Failed Dependency" in error_text or "Repository Not Found" in error_text:
                error_text = f"The LLM server cannot find the configured model '{self.llm_model}'. Please verify the model name in your .env file and that the vLLM server has this model loaded."
            elif "502" in error_text or "Bad Gateway" in error_text:
                error_text = "The AI model returned a 502 Bad Gateway error. It may be overloaded or restarting. Please try again in a moment."
            elif "504" in error_text or "Gateway Time-out" in error_text:
                error_text = "The AI model timed out. It may be overloaded or still warming up. Please try again in a moment."
            elif "timeout" in error_text.lower():
                error_text = "Request timed out waiting for the AI model. Please try again."
            await self.send_ui_render(websocket, [
                Alert(message=error_text, variant="error", title="Error").to_json()
            ])

    async def _call_llm(self, websocket, messages, tools_desc=None, temperature=None):
        """Helper to call LLM with retries and exponential backoff.
        
        Only retries on transient errors (502, 503, 504). Fails fast on
        non-transient errors like 424 (model not found) or 401 (auth).
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self.llm_model,
                    "messages": messages
                }
                if tools_desc:
                    kwargs["tools"] = tools_desc
                    kwargs["tool_choice"] = "auto"
                if temperature is not None:
                    kwargs["temperature"] = temperature
                
                response = await asyncio.to_thread(
                    self.llm_client.chat.completions.create,
                    **kwargs
                )
                return response.choices[0].message
            except Exception as e:
                error_str = str(e)
                is_transient = any(code in error_str for code in ["502", "503", "504", "Bad Gateway", "Service Unavailable", "Connection", "timeout"])
                is_fatal = any(code in error_str for code in ["424", "401", "403", "Repository Not Found", "Invalid username"])
                
                logger.warning(f"LLM Attempt {attempt}/{self.MAX_RETRIES} failed: {e}")
                
                # Don't retry fatal errors — they won't resolve with retries
                if is_fatal:
                    logger.error(f"Fatal LLM error (no retry): {e}")
                    raise e
                
                if attempt == self.MAX_RETRIES:
                    raise e
                
                # Exponential backoff: 1s, 2s, 4s, 8s
                backoff = min(2 ** (attempt - 1), 8)
                if is_transient:
                    logger.info(f"Transient error detected, retrying in {backoff}s...")
                await asyncio.sleep(backoff)
        return None

    # =========================================================================
    # CONSTANTS
    # =========================================================================

    MAX_RETRIES = 5
    RETRY_BACKOFF = [1.0, 2.0, 4.0, 8.0]  # exponential backoff

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

        # Don't render tool results immediately — the caller (handle_chat_message)
        # batches all tool results into a single collapsible section.
        if result and result.error:
            # Errors are still shown immediately so the user knows something went wrong
            err_msg = result.error.get('message', 'Unknown error')
            await self.send_ui_render(websocket, [
                Alert(message=f"Tool '{tool_name}' failed: {err_msg}", variant="error").to_json()
            ])

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
        
        # Process results — don't render here, caller batches into collapsible
        final_results = []
        error_components = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                err_res = MCPResponse(error={"message": str(result)})
                final_results.append(err_res)
                error_components.append(Alert(message=f"Tool error: {str(result)}", variant="error").to_json())
            else:
                final_results.append(result)
                if result and result.error:
                    error_components.append(Alert(message=f"Tool '{tool_names[i]}' failed: {result.error.get('message')}", variant="error").to_json())

        # Only render errors immediately — successful results are batched by caller
        if error_components:
            await self.send_ui_render(websocket, error_components)
            
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

    async def _safe_send(self, websocket, data: str) -> bool:
        """Send data over a websocket, returning False if the connection is closed."""
        try:
            await websocket.send(data)
            return True
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket closed while sending — client likely reconnected")
            return False

    async def send_ui_render(self, websocket, components: List):
        """Send a UIRender message to a UI client."""
        msg = UIRender(components=components)
        await self._safe_send(websocket, msg.to_json())

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
            if websocket in self.ui_sessions:
                del self.ui_sessions[websocket]
            logger.info(f"UI client disconnected (total: {len(self.ui_clients)})")

    async def start(self):
        """Start the orchestrator WebSocket server and auth HTTP server."""
        logger.info(f"Orchestrator starting on port {PORT}")

        # Auto-discover agents (continuous monitor)
        agent_port = int(os.getenv("AGENT_PORT", 8003))
        asyncio.create_task(self._monitor_agents(agent_port))

        # Start BFF auth HTTP server on port 8002
        from orchestrator.auth import app as auth_app
        auth_port = int(os.getenv("AUTH_PORT", 8002))
        config = uvicorn.Config(auth_app, host="0.0.0.0", port=auth_port, log_level="info")
        auth_server = uvicorn.Server(config)
        asyncio.create_task(auth_server.serve())
        logger.info(f"Auth proxy listening on http://0.0.0.0:{auth_port}")

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

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    async def validate_token(self, token: str) -> Optional[Dict]:
        """Validate JWT token against KeyCloak."""
        # 0. Mock Auth Bypass
        if os.getenv("VITE_USE_MOCK_AUTH") == "true" and token == "dev-token":
            logger.info("Mock Auth: Validated dev-token")
            return {
                "sub": "dev-user-id",
                "preferred_username": "DevUser",
                "email": "dev@local",
                "realm_access": {"roles": ["admin", "user"]}
            }

        try:
            authority = os.getenv("VITE_KEYCLOAK_AUTHORITY")
            expected_client = os.getenv("VITE_KEYCLOAK_CLIENT_ID")
            
            if not authority or not expected_client:
                logger.warning("Auth not configured (VITE_KEYCLOAK_AUTHORITY/CLIENT_ID missing)")
                return None

            # Fetch JWKS
            jwks_url = f"{authority}/protocol/openid-connect/certs"
            async with aiohttp.ClientSession() as session:
                async with session.get(jwks_url) as resp:
                    jwks = await resp.json()

            # Verify token — skip strict audience check since Keycloak
            # confidential clients set aud="account", not the client_id.
            # We validate azp (authorized party) instead.
            payload = jose_jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_at_hash": False}
            )

            # Verify authorized party matches our client
            azp = payload.get("azp")
            if azp and azp != expected_client:
                logger.warning(f"Token azp '{azp}' does not match expected client '{expected_client}'")
                return None

            return payload
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None


if __name__ == "__main__":
    orch = Orchestrator()
    asyncio.run(orch.start())
