import os
import sys
import uuid
import json
import logging
import asyncio
import time
from typing import Dict, Any, Optional, Callable

# Ensure shared module is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.database import Database
from shared.progress import ProgressEmitter, ProgressPhase, ProgressStep, ProgressEvent

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("AgentGenerator")

class AgentGeneratorClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("LLM_MODEL")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.db = Database()

    def _save_session(self, session: Dict, user_id: str = 'legacy'):
        """Upsert a session into the database."""
        timestamp = int(time.time() * 1000)
        messages_json = json.dumps(session.get("messages", []))
        
        # Check if exists
        existing = self.db.fetch_one("SELECT session_id FROM draft_agents WHERE session_id = ?", (session["session_id"],))
        if existing:
            self.db.execute(
                """UPDATE draft_agents SET
                   name = ?, persona = ?, model = ?, api_keys = ?, tools_desc = ?, messages = ?, updated_at = ?, user_id = ?
                   WHERE session_id = ?""",
                (session.get("name"), session.get("persona"), session.get("model"), session.get("api_keys"),
                 session.get("tools_desc"), messages_json, timestamp, user_id, session["session_id"])
            )
        else:
            self.db.execute(
                """INSERT INTO draft_agents
                   (session_id, user_id, name, persona, model, api_keys, tools_desc, messages, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session["session_id"], user_id, session.get("name"), session.get("persona"), session.get("model"),
                 session.get("api_keys"), session.get("tools_desc"), messages_json, timestamp, timestamp)
            )

    def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
        if user_id is None:
            row = self.db.fetch_one("SELECT * FROM draft_agents WHERE session_id = ?", (session_id,))
        else:
            row = self.db.fetch_one("SELECT * FROM draft_agents WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        if not row:
            return None
        
        try:
            messages = json.loads(row['messages'])
        except (json.JSONDecodeError, TypeError):
            messages = []
            
        return {
            "session_id": row['session_id'],
            "user_id": row['user_id'],
            "name": row['name'],
            "persona": row['persona'],
            "model": row['model'],
            "api_keys": row['api_keys'],
            "tools_desc": row['tools_desc'],
            "messages": messages
        }

    def get_all_sessions(self, user_id: Optional[str] = None) -> list:
        if user_id is None:
            rows = self.db.fetch_all("SELECT session_id, name, updated_at FROM draft_agents ORDER BY updated_at DESC")
        else:
            rows = self.db.fetch_all("SELECT session_id, name, updated_at FROM draft_agents WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
        return [{"id": row['session_id'], "name": row['name'] or "Unnamed Draft"} for row in rows]

    def get_session_details(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
        """Returns the full context of a draft session."""
        session = self.get_session(session_id, user_id)
        if not session: return None
        return session

    def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """Deletes a draft session and its associated files."""
        session = self.get_session(session_id, user_id)
        if not session:
            return False
            
        # Try to delete associated agent directory if it exists
        agent_name = session.get("name")
        if agent_name:
            import shutil
            agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agents', agent_name))
            if os.path.exists(agent_dir) and os.path.isdir(agent_dir):
                try:
                    shutil.rmtree(agent_dir)
                    logger.info(f"Deleted agent directory: {agent_dir}")
                except Exception as e:
                    logger.error(f"Failed to delete agent directory {agent_dir}: {e}")
                    
        # Delete from DB
        if user_id is None:
            self.db.execute("DELETE FROM draft_agents WHERE session_id = ?", (session_id,))
        else:
            self.db.execute("DELETE FROM draft_agents WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        return True

    async def start_session(self, name: str, persona: str, tools_desc: str, api_keys: str, user_id: str = 'legacy') -> Dict:
        """Initialize an agent creation session."""
        session_id = str(uuid.uuid4())
        
        system_prompt = f"""You are the AstralBody Agent Creator System.
Your job is to help the user refine and define a new AI Agent for the system.

Requested Name: {name}
Persona: {persona}
Tools Needed: {tools_desc}
API Keys Needed: {api_keys}

We need to figure out the exact python tool functions (MCP_TOOLS) this agent will need.
Greet the user and list out the tools you think are necessary based on their description. Ask for their approval or if they want to add anything else."""

        session = {
            "session_id": session_id,
            "user_id": user_id,
            "name": name,
            "persona": persona,
            "model": self.model,
            "api_keys": api_keys,
            "tools_desc": tools_desc,
            "messages": [
                {"role": "system", "content": system_prompt}
            ]
        }
        
        # Initial greeting from LLM
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=session["messages"]
        )
        msg_content = resp.choices[0].message.content
        session["messages"].append({"role": "assistant", "content": msg_content})
        
        self._save_session(session, user_id)
        return {"session_id": session_id, "initial_response": msg_content}

    async def chat(self, session_id: str, message: str, user_id: Optional[str] = None) -> Dict:
        """Chat with the LLM to refine the agent."""
        session = self.get_session(session_id, user_id)
        if not session:
            raise ValueError("Invalid session")
            
        session["messages"].append({"role": "user", "content": message})
        self._save_session(session, session.get("user_id", "legacy"))
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "request_package_install",
                    "description": "Request installation of pip packages needed for the agent.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "packages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of python packages to pip install (e.g. ['requests', 'beautifulsoup4'])"
                            }
                        },
                        "required": ["packages"]
                    }
                }
            }
        ]

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=session["messages"],
            tools=tools
        )
        msg = resp.choices[0].message
        
        assistant_msg: Dict[str, Any] = {"role": "assistant"}
        if msg.content:
            assistant_msg["content"] = msg.content
        else:
            assistant_msg["content"] = ""
            
        required_packages = []
        tool_call_id = None
        
        if getattr(msg, "tool_calls", None):
            tool_calls_dump = []
            for t in msg.tool_calls:
                tool_calls_dump.append({
                    "id": t.id,
                    "type": "function",
                    "function": {
                        "name": t.function.name,
                        "arguments": t.function.arguments
                    }
                })
                if t.function.name == "request_package_install":
                    try:
                        args = json.loads(t.function.arguments)
                        required_packages.extend(args.get("packages", []))
                        tool_call_id = t.id
                    except json.JSONDecodeError:
                        pass
            assistant_msg["tool_calls"] = tool_calls_dump

        session["messages"].append(assistant_msg)
        self._save_session(session, session.get("user_id", "legacy"))
        
        return {
            "response": msg.content or "",
            "required_packages": required_packages,
            "tool_call_id": tool_call_id
        }

    async def resolve_install(self, session_id: str, tool_call_id: str, approved: bool, packages: list[str], user_id: Optional[str] = None) -> Dict:
        """Execute or decline pip install, then resume chat."""
        session = self.get_session(session_id, user_id)
        if not session:
            raise ValueError("Invalid session")
            
        if approved and packages:
            import subprocess
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            if os.name == 'nt':
                pip_exe = os.path.join(root_dir, '.venv', 'Scripts', 'pip.exe')
            else:
                pip_exe = os.path.join(root_dir, '.venv', 'bin', 'pip')
            
            if not os.path.exists(pip_exe):
                pip_exe = "pip"
                
            try:
                subprocess.run([pip_exe, "install"] + packages, check=True, capture_output=True, text=True)
                tool_result = f"Successfully installed: {', '.join(packages)}"
            except subprocess.CalledProcessError as e:
                tool_result = f"Failed to install packages. Error: {e.stderr}"
        else:
            tool_result = "User declined the package installation."
            
        session["messages"].append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": tool_result
        })
        self._save_session(session, session.get("user_id", "legacy"))
        
        # Ask LLM to respond to tool result
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=session["messages"]
        )
        
        msg_content = resp.choices[0].message.content or ""
        session["messages"].append({"role": "assistant", "content": msg_content})
        self._save_session(session, session.get("user_id", "legacy"))
        
        return {"response": msg_content}
        
    async def generate_code(self, session_id: str, progress_callback: Optional[Callable[[ProgressEvent], None]] = None, user_id: Optional[str] = None) -> Dict:
        """Call LLM to generate the three python files and return them as a dict."""
        # Create progress emitter
        emitter = ProgressEmitter(ProgressPhase.GENERATION, progress_callback)
        
        session = self.get_session(session_id, user_id)
        if not session:
            raise ValueError("Invalid session")
        
        agent_name = session.get("name", "custom").replace(" ", "_").lower()
        class_agent_name = "".join([word.capitalize() for word in agent_name.split("_")]) + "Agent"
        class_server_name = "".join([word.capitalize() for word in agent_name.split("_")]) + "Server"
        
        # Step 1: Prompt construction
        emitter.emit(
            ProgressStep.PROMPT_CONSTRUCTION,
            percentage=10,
            message="Constructing generation prompt...",
            data={"agent_name": agent_name}
        )
        
        # Read template files for reference
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agents', 'general'))
        with open(os.path.join(agents_dir, 'general_agent.py'), 'r', encoding='utf-8') as f:
            agent_template = f.read()
        with open(os.path.join(agents_dir, 'mcp_server.py'), 'r', encoding='utf-8') as f:
            server_template = f.read()
        
        # The prompt requires the LLM to output all three files
        gen_prompt = f"""Based on our discussion, generate THREE Python files for the agent:

1. {agent_name}_tools.py - Tool functions and TOOL_REGISTRY
2. {agent_name}_agent.py - Agent class inheriting from GeneralAgent pattern
3. {agent_name}_server.py - MCP server class

REQUIREMENTS:

1. {agent_name}_tools.py:
   - Import from `shared.primitives`. The ONLY allowed imports are: `Text`, `Button`, `Card`, `Table`, `List_`, `Alert`, `ProgressBar`, `MetricCard`, `CodeBlock`, `Image`, `Grid`, `Tabs`, `Divider`, `Input`, `BarChart`, `LineChart`, `PieChart`, `PlotlyChart`, `Collapsible`, `Container`.
   - Define tool functions with clear input types and return type `Dict[str, Any]` matching the dict `{{"_ui_components": [...], "_data": {{}}}}`.
   - Each function's `_ui_components` list must use the valid components listed above.
   - Define the `TOOL_REGISTRY` dict at the bottom, registering each function with its schema description.
   - Embody best coding practices, handle exceptions.

2. {agent_name}_agent.py:
   - Use the reference template provided below.
   - Class name must be `{class_agent_name}`
   - Set `self.agent_id = "{agent_name}-1"`
   - Set `self.service_name = "{session.get('name', agent_name)}"`
   - Import `{class_server_name}` from `{agent_name}_server` instead of `from agents.general.mcp_server import MCPServer`
   - Include WebSocket handling for orchestrator communication
   - Provide A2A agent card endpoint at `/.well-known/agent-card.json`

3. {agent_name}_server.py:
   - Use the reference template provided below.
   - Class name must be `{class_server_name}`
   - Must handle MCP requests (tools/list, tools/call)
   - Import `TOOL_REGISTRY` from `{agent_name}_tools` instead of `from agents.general.mcp_tools import TOOL_REGISTRY`
   - Include error handling and retry logic

--- REFERENCE: general_agent.py ---
{agent_template}

--- REFERENCE: mcp_server.py ---
{server_template}

Provide all three files in this exact JSON format:
{{
  "tools": "content of {agent_name}_tools.py",
  "agent": "content of {agent_name}_agent.py",
  "server": "content of {agent_name}_server.py"
}}

IMPORTANT: Each file content must be a valid Python script. Do NOT include markdown code fences in the JSON values."""

        messages = list(session["messages"])
        messages.append({"role": "user", "content": gen_prompt})
        
        # Step 2: LLM API call
        emitter.emit(
            ProgressStep.LLM_API_CALL,
            percentage=30,
            message="Calling LLM API...",
            data={"model": self.model, "prompt_length": len(gen_prompt)},
            force=True
        )
        
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        llm_response = resp.choices[0].message.content.strip()
        
        # Step 3: Response received
        emitter.emit(
            ProgressStep.RESPONSE_RECEIVED,
            percentage=40,
            message="LLM response received, parsing...",
            data={"response_length": len(llm_response)}
        )
        
        # Try to parse JSON from LLM response
        try:
            # Step 4: JSON parsing
            emitter.emit(
                ProgressStep.JSON_PARSING,
                percentage=50,
                message="Parsing JSON from LLM response..."
            )
            
            # Extract JSON if wrapped in markdown
            if llm_response.startswith("```json"):
                llm_response = llm_response[7:]
                if llm_response.endswith("```"):
                    llm_response = llm_response[:-3]
            elif llm_response.startswith("```"):
                # Generic code block
                lines = llm_response.split('\n')
                if len(lines) > 1 and lines[0].startswith("```"):
                    llm_response = '\n'.join(lines[1:-1])
            
            files_data = json.loads(llm_response)
            
            # Step 5: Structure validation
            emitter.emit(
                ProgressStep.STRUCTURE_VALIDATION,
                percentage=60,
                message="Validating file structure...",
                data={"keys_found": list(files_data.keys())}
            )
            
            # Validate structure
            if not isinstance(files_data, dict):
                raise ValueError("LLM response is not a JSON object")
            
            required_keys = {"tools", "agent", "server"}
            if not required_keys.issubset(files_data.keys()):
                # Fallback: LLM might have returned just tools code
                logger.warning("LLM didn't return three files, falling back to single file mode")
                tools_code = files_data.get("tools") or files_data.get("code") or llm_response
                
                emitter.emit(
                    ProgressStep.WARNING,
                    percentage=70,
                    message="LLM returned incomplete response, using fallback mode",
                    data={"warning": "incomplete_response", "keys_found": list(files_data.keys())}
                )
                
                # Generate agent and server from templates
                from orchestrator.agent_tester import save_agent_files
                # We'll create a temporary session dict to use template generation
                # For now, return just tools and let frontend handle templates
                result = {
                    "files": {
                        "tools": tools_code.strip(),
                        "agent": "",  # Will be filled from template
                        "server": ""   # Will be filled from template
                    },
                    "fallback": True
                }
                
                # Step 7: Generation complete (with fallback)
                emitter.emit(
                    ProgressStep.GENERATION_COMPLETE,
                    percentage=100,
                    message="Code generation complete (fallback mode)",
                    data={"files_generated": ["tools"], "fallback": True}
                )
                
                return result
            
            # Step 6: Code cleaning
            emitter.emit(
                ProgressStep.CODE_CLEANING,
                percentage=70,
                message="Cleaning code files...",
                data={"files_to_clean": list(files_data.keys())}
            )
            
            # Clean each file content
            cleaned_files = {}
            for key in ["tools", "agent", "server"]:
                content = files_data[key]
                if content.startswith("```python"):
                    content = content[9:]
                if content.endswith("```"):
                    content = content[:-3]
                cleaned_files[key] = content.strip()
            
            # Step 7: Generation complete
            emitter.emit(
                ProgressStep.GENERATION_COMPLETE,
                percentage=100,
                message="Code generation complete!",
                data={"files_generated": list(cleaned_files.keys()), "fallback": False}
            )
            
            return {"files": cleaned_files}
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            
            # Emit error progress
            emitter.emit_error(
                message=f"Failed to parse LLM response: {e}",
                error=e,
                data={"fallback": True}
            )
            
            # Fallback to original single-file mode
            mcp_tools_code = llm_response
            if mcp_tools_code.startswith("```python"):
                mcp_tools_code = mcp_tools_code[9:]
            if mcp_tools_code.endswith("```"):
                mcp_tools_code = mcp_tools_code[:-3]
            mcp_tools_code = mcp_tools_code.strip()
            
            return {
                "code": mcp_tools_code,  # Backward compatibility
                "files": {
                    "tools": mcp_tools_code,
                    "agent": "",
                    "server": ""
                },
                "fallback": True
            }

    async def save_and_test_agent(self, session_id: str, mcp_tools_code: str, user_id: Optional[str] = None) -> str:
        """Save files and run tests yielding SSE.
        
        Accepts either:
        - Old format: string with tools.py code
        - New format: dict with keys 'tools', 'agent', 'server'
        """
        from orchestrator.agent_tester import run_tests_and_yield_logs, save_agent_files
        
        session = self.get_session(session_id, user_id)
        if not session:
            yield f"data: {json.dumps({'status': 'error', 'message': 'invalid session'})}\n\n"
            return
            
        try:
            agent_name = session["name"].replace(" ", "_").lower()
            
            # Create progress emitter for testing phase
            from shared.progress import ProgressEmitter, ProgressPhase, ProgressStep, ProgressEvent
            emitter = ProgressEmitter(ProgressPhase.TESTING)
            
            # Step 1: Saving files
            yield emitter.emit_sse(
                ProgressStep.SAVING_FILES,
                percentage=10,
                message="Saving agent files...",
                data={"agent_name": agent_name}
            )
            
            # Determine format and prepare files dict
            files_to_save = mcp_tools_code
            if isinstance(mcp_tools_code, str):
                # Check if it's a JSON string with three files
                try:
                    parsed = json.loads(mcp_tools_code)
                    if isinstance(parsed, dict) and "tools" in parsed:
                        files_to_save = parsed
                except json.JSONDecodeError:
                    # Plain string, keep as is
                    pass
            
            agent_dir = save_agent_files(agent_name, files_to_save, session)
            
            # Emit legacy log for backward compatibility
            yield f"data: {json.dumps({'status': 'log', 'message': f'Files saved in {agent_dir}. Starting test suite...'})}\n\n"
            
            # Now run test suite yielding output
            async for log in run_tests_and_yield_logs(agent_dir, agent_name):
                yield log
                
        except Exception as e:
            logger.error(f"Generation error: {e}")
            yield f"data: {json.dumps({'status': 'error', 'message': f'Testing failed: {str(e)}'})}\n\n"

# Singleton
agent_generator = AgentGeneratorClient()
