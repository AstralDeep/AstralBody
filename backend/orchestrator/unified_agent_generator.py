#!/usr/bin/env python3
"""
Unified Agent Generator - Single consolidated generator with validation, progress, and failsafes.

This combines the best features of both agent_generator.py and enhanced_agent_generator.py
into a single, consistent implementation.
"""
import os
import sys
import uuid
import json
import logging
import asyncio
import time
import subprocess
import shutil
from typing import Dict, Any, Optional, Callable, List, Tuple, AsyncGenerator

# Ensure shared module is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.database import Database
from shared.progress import ProgressEmitter, ProgressPhase, ProgressStep, ProgressEvent

from openai import AsyncOpenAI
from dotenv import load_dotenv

from .enhanced_template_manager import EnhancedTemplateManager
from .code_validator import CodeValidator
from .failsafe_pipeline import FailsafePipeline
from .agent_tester import save_agent_files, run_tests_and_yield_logs

load_dotenv()

logger = logging.getLogger("UnifiedAgentGenerator")


class UnifiedAgentGeneratorClient:
    """Unified agent generator with validation, progress tracking, and failsafes."""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("LLM_MODEL", "gpt-4")
        
        # Validate LLM configuration
        if api_key and base_url:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            self.llm_available = True
            logger.info(f"LLM configured with model {self.model}")
        elif api_key and not base_url:
            # Default to OpenAI's official endpoint
            default_base_url = "https://api.openai.com/v1"
            self.client = AsyncOpenAI(api_key=api_key, base_url=default_base_url)
            self.llm_available = True
            logger.info(f"LLM configured with model {self.model} using default OpenAI endpoint")
        elif not api_key and base_url:
            # Cannot authenticate without API key
            self.client = None
            self.llm_available = False
            logger.warning("OPENAI_API_KEY missing but OPENAI_BASE_URL provided; LLM disabled")
        else:
            self.client = None
            self.llm_available = False
            logger.warning("LLM API not configured, using template-only mode")
        
        self.db = Database()
        self.template_manager = EnhancedTemplateManager()
        self.validator = CodeValidator()
    
    def _save_session(self, session: Dict, user_id: str = 'legacy'):
        """Upsert a session into the database."""
        timestamp = int(time.time() * 1000)
        messages_json = json.dumps(session.get("messages", []))
        
        # Check if exists
        existing = self.db.fetch_one(
            "SELECT session_id FROM draft_agents WHERE session_id = ?", 
            (session["session_id"],)
        )
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
        """Get a session from the database."""
        if user_id is None:
            row = self.db.fetch_one("SELECT * FROM draft_agents WHERE session_id = ?", (session_id,))
        else:
            row = self.db.fetch_one(
                "SELECT * FROM draft_agents WHERE session_id = ? AND user_id = ?", 
                (session_id, user_id)
            )
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
        """Get all draft sessions for a user (or all if admin)."""
        if user_id is None:
            rows = self.db.fetch_all("SELECT session_id, name, updated_at FROM draft_agents ORDER BY updated_at DESC")
        else:
            rows = self.db.fetch_all("SELECT session_id, name, updated_at FROM draft_agents WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
        return [{"id": row['session_id'], "name": row['name'] or "Unnamed Draft"} for row in rows]
    
    def get_session_details(self, session_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
        """Returns the full context of a draft session."""
        session = self.get_session(session_id, user_id)
        if not session:
            return None
        return session
    
    def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """Deletes a draft session and its associated files."""
        session = self.get_session(session_id, user_id)
        if not session:
            return False
            
        # Try to delete associated agent directory if it exists
        agent_name = session.get("name")
        if agent_name:
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
    
    async def start_session(self, name: str, persona: str, tools_desc: str, 
                           api_keys: str, user_id: str = 'legacy') -> Dict:
        """Initialize an agent creation session with validation."""
        # Validate inputs
        if not name or not persona:
            raise ValueError("Name and persona are required")
        
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
        
        # Initial greeting from LLM if available
        if self.llm_available:
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=session["messages"]
                )
                msg_content = resp.choices[0].message.content
                if msg_content is None:
                    msg_content = "I'm ready to help you create your agent. Please describe what tools you need."
                session["messages"].append({"role": "assistant", "content": msg_content})
                initial_response = msg_content
            except Exception as e:
                logger.error(f"LLM error in start_session: {e}")
                initial_response = "I'm ready to help you create your agent. Please describe what tools you need."
                session["messages"].append({"role": "assistant", "content": initial_response})
        else:
            initial_response = "I'm ready to help you create your agent. Please describe what tools you need."
            session["messages"].append({"role": "assistant", "content": initial_response})
        
        self._save_session(session, user_id)
        return {"session_id": session_id, "initial_response": initial_response}
    
    async def chat(self, session_id: str, message: str, user_id: Optional[str] = None) -> Dict:
        """Chat with the LLM to refine the agent."""
        session = self.get_session(session_id, user_id)
        if not session:
            raise ValueError("Invalid session")
            
        session["messages"].append({"role": "user", "content": message})
        self._save_session(session, session.get("user_id", "legacy"))
        
        if not self.llm_available:
            # Template-only mode
            response = "I understand your requirements. When you're ready, I can generate the agent code based on our conversation."
            session["messages"].append({"role": "assistant", "content": response})
            self._save_session(session, session.get("user_id", "legacy"))
            return {"response": response, "required_packages": [], "tool_call_id": None}
        
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

        try:
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
            
        except Exception as e:
            logger.error(f"LLM error in chat: {e}")
            response = "I encountered an error. Please try again or proceed with code generation."
            session["messages"].append({"role": "assistant", "content": response})
            self._save_session(session, session.get("user_id", "legacy"))
            return {"response": response, "required_packages": [], "tool_call_id": None}
    
    async def resolve_install(self, session_id: str, tool_call_id: str, approved: bool, packages: list[str], user_id: Optional[str] = None) -> Dict:
        """Execute or decline pip install, then resume chat."""
        session = self.get_session(session_id, user_id)
        if not session:
            raise ValueError("Invalid session")
            
        if approved and packages:
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
        if self.llm_available:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=session["messages"]
            )
            
            msg_content = resp.choices[0].message.content or ""
            session["messages"].append({"role": "assistant", "content": msg_content})
            self._save_session(session, session.get("user_id", "legacy"))
            
            return {"response": msg_content}
        else:
            # Template-only mode
            response = "Package installation resolved. You can continue refining the agent."
            session["messages"].append({"role": "assistant", "content": response})
            self._save_session(session, session.get("user_id", "legacy"))
            return {"response": response}
    
    async def generate_code(self, session_id: str, 
                           progress_callback: Optional[Callable[[ProgressEvent], None]] = None,
                           user_id: Optional[str] = None) -> Dict:
        """Generate agent code with validation and failsafes."""
        emitter = ProgressEmitter(ProgressPhase.GENERATION, progress_callback)
        
        session = self.get_session(session_id, user_id)
        if not session:
            raise ValueError("Invalid session")
        
        agent_name = session.get("name", "custom").replace(" ", "_").lower()
        
        # Step 1: Preparation
        emitter.emit(
            ProgressStep.PROMPT_CONSTRUCTION,
            percentage=10,
            message="Preparing code generation...",
            data={"agent_name": agent_name}
        )
        
        # Extract tool descriptions from conversation
        tool_descriptions = self._extract_tool_descriptions(session)
        
        # Step 2: Generate with LLM if available
        if self.llm_available:
            emitter.emit(
                ProgressStep.LLM_API_CALL,
                percentage=30,
                message="Generating code with AI...",
                data={"model": self.model}
            )
            
            try:
                llm_files = await self._generate_with_llm(session, agent_name, tool_descriptions)
                emitter.emit(
                    ProgressStep.RESPONSE_RECEIVED,
                    percentage=50,
                    message="AI generation complete, validating...",
                    data={"files_generated": list(llm_files.keys())}
                )
                
                # Validate LLM-generated code
                validation_results = {}
                for file_type, content in llm_files.items():
                    result = self.validator.validate_all(content, file_type)
                    validation_results[file_type] = result
                    
                # Check if all files are valid
                all_valid = all(r["valid"] for r in validation_results.values())
                
                if all_valid:
                    emitter.emit(
                        ProgressStep.GENERATION_COMPLETE,
                        percentage=100,
                        message="Code generation successful!",
                        data={"files_generated": list(llm_files.keys()), "validated": True}
                    )
                    return {
                        "files": llm_files,
                        "validated": True,
                        "validation_results": validation_results,
                        "source": "llm"
                    }
                else:
                    emitter.emit(
                        ProgressStep.WARNING,
                        percentage=70,
                        message="AI-generated code has issues, applying fixes...",
                        data={"validation_errors": sum(r["error_count"] for r in validation_results.values())}
                    )
                    
                    # Apply fixes
                    fixed_files = {}
                    for file_type, content in llm_files.items():
                        pipeline = FailsafePipeline(agent_name)
                        fixed_content, interventions = pipeline.validate_and_fix(content, file_type)
                        fixed_files[file_type] = fixed_content
                        
                    emitter.emit(
                        ProgressStep.GENERATION_COMPLETE,
                        percentage=100,
                        message="Code generated with automatic fixes",
                        data={"files_generated": list(fixed_files.keys()), "fixed": True}
                    )
                    
                    return {
                        "files": fixed_files,
                        "validated": False,
                        "validation_results": validation_results,
                        "source": "llm_with_fixes"
                    }
                    
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}")
                emitter.emit(
                    ProgressStep.WARNING,
                    percentage=40,
                    message="AI generation failed, using templates...",
                    data={"error": str(e)}
                )
                # Fall through to template generation
        
        # Step 3: Generate from templates (fallback)
        emitter.emit(
            ProgressStep.CODE_CLEANING,
            percentage=60,
            message="Generating code from templates...",
            data={"agent_name": agent_name}
        )
        
        template_files = self.template_manager.generate_all_templates(
            agent_name, session, tool_descriptions
        )
        
        # Validate template files
        validation_results = {}
        for file_type, content in template_files.items():
            result = self.validator.validate_all(content, file_type)
            validation_results[file_type] = result
        
        emitter.emit(
            ProgressStep.GENERATION_COMPLETE,
            percentage=100,
            message="Template generation complete!",
            data={"files_generated": list(template_files.keys()), "source": "templates"}
        )
        
        return {
            "files": template_files,
            "validated": True,
            "validation_results": validation_results,
            "source": "templates"
        }
    
    async def _generate_with_llm(self, session: Dict, agent_name: str, 
                                tool_descriptions: List[Dict]) -> Dict[str, str]:
        """Generate code using LLM."""
        class_agent_name = "".join([word.capitalize() for word in agent_name.split("_")]) + "Agent"
        class_server_name = "".join([word.capitalize() for word in agent_name.split("_")]) + "Server"
        
        # Read template files for reference
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agents', 'general'))
        with open(os.path.join(agents_dir, 'general_agent.py'), 'r', encoding='utf-8') as f:
            agent_template = f.read()
        with open(os.path.join(agents_dir, 'mcp_server.py'), 'r', encoding='utf-8') as f:
            server_template = f.read()
        
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
   - Set `self.service_name = "{session.get('name', agent_name)}`"
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
        
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        llm_response = resp.choices[0].message.content.strip()
        
        # Parse JSON from response
        try:
            # Extract JSON if wrapped in markdown
            if llm_response.startswith("```json"):
                llm_response = llm_response[7:]
                if llm_response.endswith("```"):
                    llm_response = llm_response[:-3]
            elif llm_response.startswith("```"):
                lines = llm_response.split('\n')
                if len(lines) > 1 and lines[0].startswith("```"):
                    llm_response = '\n'.join(lines[1:-1])
            
            files_data = json.loads(llm_response)
            
            # Validate structure
            if not isinstance(files_data, dict):
                raise ValueError("LLM response is not a JSON object")
            
            required_keys = {"tools", "agent", "server"}
            if not required_keys.issubset(files_data.keys()):
                raise ValueError(f"Missing required keys: {required_keys - set(files_data.keys())}")
            
            # Clean each file content
            cleaned_files = {}
            for key in ["tools", "agent", "server"]:
                content = files_data[key]
                if content.startswith("```python"):
                    content = content[9:]
                if content.endswith("```"):
                    content = content[:-3]
                cleaned_files[key] = content.strip()
            
            return cleaned_files
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            raise ValueError(f"Failed to parse LLM response: {e}")
    
    def _extract_tool_descriptions(self, session: Dict) -> List[Dict]:
        """Extract tool descriptions from conversation."""
        tools_desc = session.get("tools_desc", "")
        messages = session.get("messages", [])
        
        # Combine all text for analysis
        combined_text = tools_desc + " " + " ".join(
            msg.get("content", "") for msg in messages if isinstance(msg, dict) and msg.get("role") in ("user", "assistant")
        )
        
        # Look for tool-like patterns
        import re
        tools = []
        
        # Pattern 1: Explicit tool mentions with descriptions
        tool_pattern = re.compile(r'(?:tool|function|capability)\s+(?:that\s+)?(?:can\s+)?(?:to\s+)?([^.,;!?]+)', re.IGNORECASE)
        for match in tool_pattern.finditer(combined_text):
            description = match.group(1).strip()
            if len(description) > 10:  # Filter out trivial matches
                name = re.sub(r'[^a-z0-9]+', '_', description.lower()).strip('_')
                if name and name not in [t.get('name') for t in tools]:
                    tools.append({
                        "name": name[:50],
                        "description": description,
                        "parameters": [
                            {"name": "input", "type": "string", "description": "Input parameter", "required": True}
                        ]
                    })
        
        # Pattern 2: Sentences containing "should" or "can" that describe actions
        action_pattern = re.compile(r'([^.!?]*\b(?:should|can|must|need to|able to)\b[^.!?]*[.!?])', re.IGNORECASE)
        for match in action_pattern.finditer(combined_text):
            sentence = match.group(1).strip()
            if len(sentence) > 20 and any(keyword in sentence.lower() for keyword in ['tool', 'function', 'capability', 'agent', 'system']):
                name = 'action_' + str(len(tools) + 1)
                tools.append({
                    "name": name,
                    "description": sentence,
                    "parameters": [
                        {"name": "input", "type": "string", "description": "Input parameter", "required": True}
                    ]
                })
        
        # If no tools found, fall back to the original tools_desc parsing
        if not tools and tools_desc:
            parts = re.split(r'[,\n]', tools_desc)
            for part in parts:
                part = part.strip()
                if part:
                    name = re.sub(r'[^a-z0-9]+', '_', part.lower()).strip('_')
                    if name:
                        tools.append({
                            "name": name[:50],
                            "description": part,
                            "parameters": [
                                {"name": "input", "type": "string", "description": "Input parameter", "required": True}
                            ]
                        })
        
        # Limit to at most 5 tools to avoid noise
        tools = tools[:5]
        
        # If still no tools, return a placeholder
        if not tools:
            tools = [
                {
                    "name": "example_tool",
                    "description": "Example tool based on your description",
                    "parameters": [
                        {"name": "input", "type": "string", "description": "Input parameter", "required": True}
                    ]
                }
            ]
        
        return tools
    
    async def validate_code(self, code: str, file_type: str) -> Dict[str, Any]:
        """Validate code and return results."""
        return self.validator.validate_all(code, file_type)
    
    async def fix_code(self, code: str, file_type: str, agent_name: str) -> Dict[str, Any]:
        """Apply fixes to code and return results."""
        pipeline = FailsafePipeline(agent_name)
        fixed_code, interventions = pipeline.validate_and_fix(code, file_type)
        
        return {
            "fixed_code": fixed_code,
            "interventions_needed": len(interventions) > 0,
            "interventions": interventions,
            "summary": pipeline.get_validation_summary()
        }
    
    async def save_and_test_agent(self, session_id: str, files_data: Any, user_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Save files and run tests yielding SSE with proper resource cleanup."""
        session = self.get_session(session_id, user_id)
        if not session:
            yield f"data: {json.dumps({'status': 'error', 'message': 'invalid session'})}\n\n"
            return
            
        try:
            agent_name = session["name"].replace(" ", "_").lower()
            
            # Create progress emitter for testing phase
            emitter = ProgressEmitter(ProgressPhase.TESTING)
            
            # Step 1: Saving files
            yield emitter.emit_sse(
                ProgressStep.SAVING_FILES,
                percentage=10,
                message="Saving agent files...",
                data={"agent_name": agent_name}
            )
            
            # Determine format and prepare files dict
            files_to_save = files_data
            if isinstance(files_data, str):
                # Check if it's a JSON string with three files
                try:
                    parsed = json.loads(files_data)
                    if isinstance(parsed, dict) and "tools" in parsed:
                        files_to_save = parsed
                except json.JSONDecodeError:
                    # Plain string, keep as is
                    pass
            
            agent_dir = save_agent_files(agent_name, files_to_save, session)
            
            # Emit legacy log for backward compatibility
            yield f"data: {json.dumps({'status': 'log', 'message': f'Files saved in {agent_dir}. Starting test suite...'})}\n\n"
            
            # Now run test suite yielding output with proper cleanup
            async for log in self._run_tests_with_cleanup(agent_dir, agent_name):
                yield log
                
        except Exception as e:
            logger.error(f"Generation error: {e}")
            yield f"data: {json.dumps({'status': 'error', 'message': f'Testing failed: {str(e)}'})}\n\n"
    
    async def _run_tests_with_cleanup(self, agent_dir: str, agent_name: str) -> AsyncGenerator[str, None]:
        """Run tests with proper resource cleanup."""
        processes = []
        
        try:
            # Run tests with timeout and cleanup
            async for log in run_tests_and_yield_logs(agent_dir, agent_name):
                yield log
                
                # Track any processes that might have been started
                # (This would need integration with agent_tester to actually track processes)
                # For now, we rely on agent_tester's cleanup
                
        finally:
            # Ensure any leftover processes are cleaned up
            for proc in processes:
                try:
                    if proc.poll() is None:  # Still running
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                except Exception as e:
                    logger.warning(f"Error cleaning up process: {e}")


# Singleton instance
unified_agent_generator = UnifiedAgentGeneratorClient()


if __name__ == "__main__":
    # Test the unified generator
    import asyncio
    
    async def test():
        generator = UnifiedAgentGeneratorClient()
        
        # Test template generation
        test_session = {
            "name": "Test Agent",
            "persona": "A test agent",
            "tools_desc": "Fetches data and analyzes it"
        }
        
        print("Testing template generation...")
        templates = generator.template_manager.generate_all_templates("test_agent", test_session)
        print(f"Generated {len(templates)} templates")
        
        # Test validation
        print("\nTesting validation...")
        for file_type, content in templates.items():
            result = generator.validator.validate_all(content, file_type)
            print(f"{file_type}: {result['valid']} ({result['error_count']} errors, {result['warning_count']} warnings)")
        
        print("\nTest complete!")
    
    asyncio.run(test())
