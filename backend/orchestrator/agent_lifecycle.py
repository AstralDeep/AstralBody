"""
Agent Lifecycle Manager for AstralBody.

Manages the full lifecycle of user-created agents:
  pending → generating → generated → testing → analyzing →
  approved/pending_review/rejected → live

Handles code generation, security analysis, file I/O,
subprocess management, and approval flow.
"""
import ast
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from typing import Dict, Any, Optional, List, Callable, Awaitable

from orchestrator.agent_generator import AgentCodeGenerator
from orchestrator.agent_validator import AgentSpecValidator
from orchestrator.code_security import CodeSecurityAnalyzer, Severity

logger = logging.getLogger("AgentLifecycle")

# Statuses
PENDING = "pending"
GENERATING = "generating"
GENERATED = "generated"
TESTING = "testing"
ANALYZING = "analyzing"
APPROVED = "approved"
PENDING_REVIEW = "pending_review"
REJECTED = "rejected"
VALIDATING = "validating"
LIVE = "live"
ERROR = "error"


class AgentLifecycleManager:
    """Manages draft agent creation, testing, approval, and promotion to live."""

    def __init__(self, db, orchestrator=None):
        """
        Args:
            db: Database instance with draft_agents CRUD methods
            orchestrator: Orchestrator instance (for LLM client reuse and WS broadcasts)
        """
        self.db = db
        self.orchestrator = orchestrator
        self.generator = AgentCodeGenerator(
            llm_client=getattr(orchestrator, 'llm_client', None),
            llm_model=getattr(orchestrator, 'llm_model', None),
        )
        self.security = CodeSecurityAnalyzer()
        self.validator = AgentSpecValidator()
        self._draft_processes: Dict[str, subprocess.Popen] = {}  # draft_id -> process
        self._agents_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'agents')
        )

    # ─── Progress Callback ───────────────────────────────────────────

    async def _send_progress(self, websocket, draft_id: str, step: str,
                              message: str, status: str, detail: Dict = None):
        """Send progress update to the UI client."""
        if websocket:
            try:
                payload = {
                    "type": "agent_creation_progress",
                    "draft_id": draft_id,
                    "step": step,
                    "message": message,
                    "status": status,
                }
                if detail:
                    payload["detail"] = detail
                await websocket.send_text(json.dumps(payload))
            except Exception as e:
                logger.warning(f"Failed to send progress: {e}")

    def _append_log(self, draft_id: str, message: str):
        """Append a message to the draft's generation_log."""
        draft = self.db.get_draft_agent(draft_id)
        if not draft:
            return
        log = json.loads(draft.get("generation_log") or "[]")
        log.append({"message": message, "timestamp": int(time.time() * 1000)})
        self.db.update_draft_agent(draft_id, generation_log=json.dumps(log))

    def _extract_required_credentials(self, tools_code: str) -> list:
        """Extract REQUIRED_CREDENTIALS from generated mcp_tools.py using AST (no exec)."""
        try:
            tree = ast.parse(tools_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "REQUIRED_CREDENTIALS":
                            return ast.literal_eval(node.value)
        except Exception as e:
            logger.warning(f"Failed to extract REQUIRED_CREDENTIALS: {e}")
        return []

    # ─── Spec Validation ─────────────────────────────────────────────

    async def _validate_and_fix(self, draft_id: str, slug: str,
                                 tools_code: str, agent_name: str,
                                 description: str, websocket=None,
                                 max_retries: int = 2) -> tuple:
        """Run spec validation with auto-fix retry loop.

        Returns (final_code, validation_report).
        """
        for attempt in range(max_retries + 1):
            await self._send_progress(
                websocket, draft_id, "validating",
                f"Validating tool outputs against spec"
                f"{f' (attempt {attempt + 1})' if attempt > 0 else ''}...",
                VALIDATING,
            )

            report = self.validator.validate(tools_code, slug, self._agents_dir)
            self._append_log(
                draft_id,
                f"Spec validation {'passed' if report.passed else 'failed'}: "
                f"{report.tools_passed}/{report.tools_tested} tools passed"
            )

            if report.passed:
                return tools_code, report

            if attempt < max_retries:
                # Build fix prompt from validation errors
                error_lines = []
                for f in report.findings:
                    if f.severity == "error":
                        prefix = f"[{f.tool_name}] " if f.tool_name else ""
                        error_lines.append(f"- {prefix}{f.message}")

                fix_prompt = (
                    "The generated tools FAILED spec validation with these errors:\n"
                    + "\n".join(error_lines)
                    + "\n\nFix ALL these issues. Ensure every tool returns "
                    "{'_ui_components': [c.to_json() for c in components], '_data': {...}} "
                    "using the shared.primitives classes."
                )

                await self._send_progress(
                    websocket, draft_id, "auto_fixing",
                    f"Auto-fixing validation errors (attempt {attempt + 1}/{max_retries})...",
                    VALIDATING,
                )
                self._append_log(draft_id, f"Auto-fix attempt {attempt + 1}: {fix_prompt[:200]}")

                try:
                    tools_code = await self.generator.refine_tools_file(
                        current_code=tools_code,
                        user_message=fix_prompt,
                        agent_name=agent_name,
                        description=description,
                    )

                    # Syntax check the fix
                    try:
                        compile(tools_code, f"{slug}/mcp_tools.py", "exec")
                    except SyntaxError as e:
                        self._append_log(draft_id, f"Auto-fix produced syntax error: {e}")
                        continue  # Try again

                    # Write the fixed code
                    tools_file = os.path.join(self._agents_dir, slug, "mcp_tools.py")
                    with open(tools_file, "w", encoding="utf-8") as fh:
                        fh.write(tools_code)

                except Exception as e:
                    self._append_log(draft_id, f"Auto-fix failed: {e}")
                    break

        return tools_code, report

    def _remove_draft_marker(self, slug: str):
        """Remove the .draft marker file when an agent is promoted to live."""
        marker = os.path.join(self._agents_dir, slug, ".draft")
        if os.path.exists(marker):
            os.remove(marker)
            logger.info(f"Removed .draft marker for {slug}")

    # ─── Slug Sanitization ───────────────────────────────────────────

    def _sanitize_slug(self, name: str) -> str:
        """Convert agent name to a safe directory slug. Alphanumeric + underscores only."""
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower().strip())
        slug = slug.strip('_')
        if not slug:
            slug = 'custom_agent'
        # Prevent path traversal
        slug = slug.replace('..', '').replace('/', '').replace('\\', '')
        return slug

    def _ensure_unique_slug(self, slug: str) -> str:
        """Ensure slug doesn't conflict with existing agent directories."""
        base_slug = slug
        counter = 1
        while os.path.exists(os.path.join(self._agents_dir, slug)):
            slug = f"{base_slug}_{counter}"
            counter += 1
        return slug

    # ─── Create Draft ────────────────────────────────────────────────

    async def create_draft(self, user_id: str, agent_name: str, description: str,
                            tools_spec: List[Dict] = None, skill_tags: List[str] = None,
                            packages: List[str] = None) -> Dict[str, Any]:
        """Create a new draft agent record."""
        # Validate
        if not agent_name or len(agent_name.strip()) < 2:
            raise ValueError("Agent name must be at least 2 characters")
        if not description or len(description.strip()) < 10:
            raise ValueError("Description must be at least 10 characters")
        if len(agent_name) > 100:
            raise ValueError("Agent name must be under 100 characters")

        slug = self._sanitize_slug(agent_name)
        slug = self._ensure_unique_slug(slug)
        draft_id = str(uuid.uuid4())

        self.db.create_draft_agent(
            draft_id=draft_id,
            user_id=user_id,
            agent_name=agent_name.strip(),
            agent_slug=slug,
            description=description.strip(),
            tools_spec=json.dumps(tools_spec) if tools_spec else None,
            skill_tags=json.dumps(skill_tags) if skill_tags else None,
            packages=json.dumps(packages) if packages else None,
        )

        logger.info(f"Created draft agent '{agent_name}' (id={draft_id}, slug={slug}) for user {user_id}")
        return self.db.get_draft_agent(draft_id)

    # ─── Generate Code ───────────────────────────────────────────────

    async def generate_code(self, draft_id: str, websocket=None) -> Dict[str, Any]:
        """Generate the 3 agent files for a draft."""
        draft = self.db.get_draft_agent(draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")

        slug = draft["agent_slug"]
        agent_name = draft["agent_name"]
        description = draft["description"]
        tools_spec = json.loads(draft["tools_spec"]) if draft.get("tools_spec") else []
        skill_tags = json.loads(draft["skill_tags"]) if draft.get("skill_tags") else []
        packages = json.loads(draft["packages"]) if draft.get("packages") else []

        # Update status
        self.db.update_draft_agent(draft_id, status=GENERATING)
        self._append_log(draft_id, "Starting code generation...")

        try:
            # Step 1: Generate template files (no LLM needed)
            await self._send_progress(websocket, draft_id, "generating_template",
                                       "Generating agent template files...", GENERATING)
            self._append_log(draft_id, "Generating template files...")

            template_files = self.generator.generate_template_files(
                agent_name=agent_name,
                description=description,
                slug=slug,
                skill_tags=skill_tags,
            )

            # Step 2: Generate tools via LLM
            await self._send_progress(websocket, draft_id, "generating_tools",
                                       "Generating tool implementations with AI...", GENERATING)
            self._append_log(draft_id, "Generating tool implementations...")

            tools_code = await self.generator.generate_tools_file(
                agent_name=agent_name,
                description=description,
                tools_spec=tools_spec,
                packages=packages,
            )

            all_files = {**template_files, "mcp_tools.py": tools_code}

            # Step 2.5: Syntax validation on ALL generated files
            await self._send_progress(websocket, draft_id, "syntax_check",
                                       "Validating Python syntax...", GENERATING)
            self._append_log(draft_id, "Validating syntax of generated files...")

            for fname, code in all_files.items():
                try:
                    compile(code, f"{slug}/{fname}", "exec")
                except SyntaxError as e:
                    error_msg = f"Syntax error in {fname} (line {e.lineno}): {e.msg}"
                    logger.error(f"Generated code has syntax error: {error_msg}")
                    self.db.update_draft_agent(
                        draft_id, status=ERROR,
                        error_message=error_msg,
                    )
                    await self._send_progress(websocket, draft_id, "syntax_error",
                                               error_msg, ERROR)
                    self._append_log(draft_id, f"SYNTAX ERROR: {error_msg}")
                    return self.db.get_draft_agent(draft_id)

            # Step 3: Security analysis
            await self._send_progress(websocket, draft_id, "security_scan",
                                       "Running security analysis...", GENERATING)
            self._append_log(draft_id, "Running security analysis on generated code...")

            report = self.security.analyze(tools_code, filename=f"{slug}/mcp_tools.py")

            if not report.passed and report.max_severity == Severity.CRITICAL:
                self.db.update_draft_agent(
                    draft_id,
                    status=ERROR,
                    security_report=json.dumps(report.to_dict()),
                    error_message="Security analysis found critical issues in generated code.",
                )
                await self._send_progress(websocket, draft_id, "security_failed",
                                           "Security analysis found critical issues. Code was not written.",
                                           ERROR, detail=report.to_dict())
                self._append_log(draft_id, f"Security analysis FAILED: {report.recommendation}")
                return self.db.get_draft_agent(draft_id)

            # Step 4: Write files to disk
            await self._send_progress(websocket, draft_id, "writing_files",
                                       "Writing agent files...", GENERATING)
            self._append_log(draft_id, "Writing agent files to disk...")

            agent_dir = os.path.join(self._agents_dir, slug)
            os.makedirs(agent_dir, exist_ok=True)

            # Write draft marker — start.py skips directories with .draft
            with open(os.path.join(agent_dir, ".draft"), "w", encoding="utf-8") as f:
                f.write(draft_id)

            # Write __init__.py
            init_content = f'"""Auto-generated agent: {agent_name}"""\n'
            with open(os.path.join(agent_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write(init_content)

            for filename, content in all_files.items():
                filepath = os.path.join(agent_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

            # Step 5: Spec validation (with auto-fix retry)
            tools_code, validation_report = await self._validate_and_fix(
                draft_id=draft_id, slug=slug, tools_code=tools_code,
                agent_name=agent_name, description=description,
                websocket=websocket,
            )

            # Step 5.5: Extract required credentials declared by LLM
            required_creds = self._extract_required_credentials(tools_code)
            if required_creds:
                self._append_log(draft_id, f"Detected {len(required_creds)} required credential(s)")
                await self._send_progress(
                    websocket, draft_id, "credentials_detected",
                    f"This agent requires {len(required_creds)} credential(s). You'll need to provide them before testing.",
                    GENERATING,
                    detail={"required_credentials": required_creds},
                )

            # Step 6: Update status
            update_kwargs = {
                "status": GENERATED,
                "security_report": json.dumps(report.to_dict()) if report.findings else None,
                "validation_report": json.dumps(validation_report.to_dict()),
                "required_credentials": json.dumps(required_creds) if required_creds else None,
            }
            if not validation_report.passed:
                update_kwargs["error_message"] = (
                    f"Spec validation failed: {validation_report.tools_passed}/"
                    f"{validation_report.tools_tested} tools passed. "
                    "You can still test manually or refine the agent."
                )

            self.db.update_draft_agent(draft_id, **update_kwargs)

            status_msg = (
                "Agent files generated and validated successfully!"
                if validation_report.passed
                else f"Agent generated but validation found issues "
                     f"({validation_report.tools_passed}/{validation_report.tools_tested} tools passed). "
                     "Review the validation report or refine the agent."
            )
            await self._send_progress(websocket, draft_id, "complete",
                                       status_msg, GENERATED,
                                       detail={
                                           "security": report.to_dict() if report.findings else None,
                                           "validation": validation_report.to_dict(),
                                       })
            self._append_log(draft_id, "Code generation complete!")

            return self.db.get_draft_agent(draft_id)

        except Exception as e:
            logger.error(f"Code generation failed for draft {draft_id}: {e}")
            self.db.update_draft_agent(draft_id, status=ERROR, error_message=str(e))
            await self._send_progress(websocket, draft_id, "error",
                                       f"Code generation failed: {e}", ERROR)
            self._append_log(draft_id, f"ERROR: {e}")
            return self.db.get_draft_agent(draft_id)

    # ─── Start Draft Agent for Testing ───────────────────────────────

    def _find_next_port(self) -> int:
        """Find the next available port for a draft agent."""
        start_port = int(os.environ.get("AGENT_PORT", 8003))
        max_agents = int(os.environ.get("MAX_AGENTS", 10))

        # Collect ports in use by connected agents
        used_ports = set()
        if self.orchestrator:
            for agent_id, url in getattr(self.orchestrator, 'agent_urls', {}).items():
                try:
                    port = int(url.split(':')[-1])
                    used_ports.add(port)
                except (ValueError, IndexError):
                    pass

        # Also check ports used by other draft agents
        for draft_id, proc in self._draft_processes.items():
            if proc.poll() is None:  # still running
                draft = self.db.get_draft_agent(draft_id)
                if draft and draft.get("port"):
                    used_ports.add(draft["port"])

        # Find first available port, starting after the static agents range
        # Static agents use start_port to start_port + max_agents
        # Draft agents start after that
        search_start = start_port + max_agents
        for port in range(search_start, search_start + 50):
            if port not in used_ports:
                return port

        raise RuntimeError("No available ports for draft agent")

    async def start_draft_agent(self, draft_id: str, websocket=None) -> Dict[str, Any]:
        """Start a draft agent subprocess for testing."""
        draft = self.db.get_draft_agent(draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")

        if draft["status"] not in (GENERATED, TESTING, APPROVED, LIVE):
            raise ValueError(f"Cannot start agent in status '{draft['status']}'. Generate code first.")

        slug = draft["agent_slug"]
        agent_dir = os.path.join(self._agents_dir, slug)
        agent_script = os.path.join(agent_dir, f"{slug}_agent.py")

        if not os.path.exists(agent_script):
            raise FileNotFoundError(f"Agent script not found: {agent_script}")

        # Stop existing process if any
        await self.stop_draft_agent(draft_id)

        port = self._find_next_port()
        python_exe = sys.executable

        await self._send_progress(websocket, draft_id, "starting_agent",
                                   f"Starting agent on port {port}...", TESTING)
        self._append_log(draft_id, f"Starting agent on port {port}...")

        proc = subprocess.Popen(
            [python_exe, agent_script, "--port", str(port)],
            cwd=agent_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._draft_processes[draft_id] = proc

        self.db.update_draft_agent(draft_id, status=TESTING, port=port)

        # Wait for agent to start up, then actively discover it with the orchestrator
        agent_id = f"{slug.replace('_', '-')}-1"
        agent_url = f"http://localhost:{port}"
        discovered = False

        if self.orchestrator:
            # Retry discovery a few times — the subprocess needs time to bind the port
            for attempt in range(6):
                await asyncio.sleep(2)
                # Check if process is still alive
                if proc.poll() is not None:
                    stderr_out = proc.stderr.read().decode() if proc.stderr else ""
                    error_msg = f"Agent process exited with code {proc.returncode}"
                    if stderr_out:
                        error_msg += f": {stderr_out[:500]}"
                    logger.error(error_msg)
                    self.db.update_draft_agent(draft_id, status=ERROR, error_message=error_msg)
                    await self._send_progress(websocket, draft_id, "error", error_msg, ERROR)
                    self._append_log(draft_id, f"ERROR: {error_msg}")
                    return self.db.get_draft_agent(draft_id)

                try:
                    await self.orchestrator.discover_agent(agent_url)
                    if agent_id in self.orchestrator.agents:
                        discovered = True
                        logger.info(f"Draft agent {agent_id} discovered on port {port}")
                        break
                except Exception as e:
                    logger.debug(f"Discovery attempt {attempt+1} for draft agent on port {port}: {e}")
        else:
            await asyncio.sleep(2)

        # Set ownership to creator (private by default)
        user = self.db.get_user(draft["user_id"])
        owner_email = user.get("email", draft["user_id"]) if user else draft["user_id"]
        self.db.set_agent_ownership(agent_id, owner_email=owner_email, is_public=False)

        # Draft agents: all scopes ENABLED so the user can test tools.
        # Scopes get disabled when the agent is approved/moved to live.
        if self.orchestrator:
            self.orchestrator.tool_permissions.set_agent_scopes(
                draft["user_id"], agent_id,
                {"tools:read": True, "tools:write": True, "tools:search": True, "tools:system": True}
            )

        if discovered:
            await self._send_progress(websocket, draft_id, "agent_started",
                                       f"Agent running on port {port} and registered with orchestrator.",
                                       TESTING)
            self._append_log(draft_id, f"Agent started and discovered on port {port}")
        else:
            await self._send_progress(websocket, draft_id, "agent_started",
                                       f"Agent running on port {port} but not yet discovered. It may take a moment.",
                                       TESTING)
            self._append_log(draft_id, f"Agent started on port {port} (discovery pending)")

        return self.db.get_draft_agent(draft_id)

    async def stop_draft_agent(self, draft_id: str) -> None:
        """Stop a running draft agent subprocess and unregister from orchestrator."""
        # Unregister from orchestrator so re-discovery works after refinement
        draft = self.db.get_draft_agent(draft_id)
        if draft and self.orchestrator:
            slug = draft["agent_slug"]
            agent_id = f"{slug.replace('_', '-')}-1"
            port = draft.get("port")
            # Remove from orchestrator's registries
            self.orchestrator.agents.pop(agent_id, None)
            if port:
                agent_url = f"http://localhost:{port}"
                # Clean up agent_urls
                urls_to_remove = [k for k, v in self.orchestrator.agent_urls.items() if v == agent_url]
                for k in urls_to_remove:
                    del self.orchestrator.agent_urls[k]

        proc = self._draft_processes.get(draft_id)
        if proc and proc.poll() is None:
            if os.name == 'nt':
                try:
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
                    )
                except Exception:
                    proc.terminate()
                # Wait for process to fully exit so file handles are released
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()

            del self._draft_processes[draft_id]
            logger.info(f"Stopped draft agent process for {draft_id}")

    # ─── Refine Agent ────────────────────────────────────────────────

    async def refine_agent(self, draft_id: str, user_message: str,
                            websocket=None) -> Dict[str, Any]:
        """Refine an agent's tools based on user feedback."""
        draft = self.db.get_draft_agent(draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")

        slug = draft["agent_slug"]
        tools_file = os.path.join(self._agents_dir, slug, "mcp_tools.py")

        if not os.path.exists(tools_file):
            raise FileNotFoundError("Agent tools file not found. Generate code first.")

        # Stop running agent
        await self.stop_draft_agent(draft_id)

        self.db.update_draft_agent(draft_id, status=GENERATING)
        await self._send_progress(websocket, draft_id, "refining",
                                   "Refining agent based on your feedback...", GENERATING)

        # Update refinement history
        history = json.loads(draft.get("refinement_history") or "[]")
        history.append({
            "role": "user",
            "content": user_message,
            "timestamp": int(time.time() * 1000),
        })

        try:
            # Read current code
            with open(tools_file, "r", encoding="utf-8") as f:
                current_code = f.read()

            # Refine via LLM
            await self._send_progress(websocket, draft_id, "generating_tools",
                                       "Generating updated tool implementations...", GENERATING)

            new_code = await self.generator.refine_tools_file(
                current_code=current_code,
                user_message=user_message,
                agent_name=draft["agent_name"],
                description=draft["description"],
            )

            # Syntax validation
            try:
                compile(new_code, f"{slug}/mcp_tools.py", "exec")
            except SyntaxError as e:
                error_msg = f"Refined code has syntax error (line {e.lineno}): {e.msg}"
                self.db.update_draft_agent(
                    draft_id, status=ERROR, error_message=error_msg,
                    refinement_history=json.dumps(history),
                )
                await self._send_progress(websocket, draft_id, "syntax_error",
                                           error_msg, ERROR)
                return self.db.get_draft_agent(draft_id)

            # Security analysis
            await self._send_progress(websocket, draft_id, "security_scan",
                                       "Running security analysis on updated code...", GENERATING)

            report = self.security.analyze(new_code, filename=f"{slug}/mcp_tools.py")

            if not report.passed and report.max_severity == Severity.CRITICAL:
                self.db.update_draft_agent(
                    draft_id,
                    status=ERROR,
                    security_report=json.dumps(report.to_dict()),
                    error_message="Refinement produced code with critical security issues.",
                    refinement_history=json.dumps(history),
                )
                await self._send_progress(websocket, draft_id, "security_failed",
                                           "Security analysis found critical issues in updated code.",
                                           ERROR, detail=report.to_dict())
                return self.db.get_draft_agent(draft_id)

            # Write updated code
            with open(tools_file, "w", encoding="utf-8") as f:
                f.write(new_code)

            # Spec validation on refined code
            validation_report = self.validator.validate(new_code, slug, self._agents_dir)
            self._append_log(
                draft_id,
                f"Post-refinement validation: "
                f"{validation_report.tools_passed}/{validation_report.tools_tested} tools passed"
            )

            history.append({
                "role": "system",
                "content": (
                    "Code updated successfully."
                    if validation_report.passed
                    else f"Code updated but validation found issues: "
                         f"{validation_report.tools_passed}/{validation_report.tools_tested} tools passed."
                ),
                "timestamp": int(time.time() * 1000),
            })

            # Re-extract credentials from refined code
            required_creds = self._extract_required_credentials(new_code)

            self.db.update_draft_agent(
                draft_id,
                status=GENERATED,
                security_report=json.dumps(report.to_dict()) if report.findings else None,
                validation_report=json.dumps(validation_report.to_dict()),
                refinement_history=json.dumps(history),
                required_credentials=json.dumps(required_creds) if required_creds else None,
            )

            status_msg = (
                "Agent updated and validated! You can test it again."
                if validation_report.passed
                else f"Agent updated but validation found issues "
                     f"({validation_report.tools_passed}/{validation_report.tools_tested} tools passed). "
                     "Review findings or refine further."
            )
            await self._send_progress(websocket, draft_id, "refinement_complete",
                                       status_msg, GENERATED,
                                       detail={
                                           "security": report.to_dict() if report.findings else None,
                                           "validation": validation_report.to_dict(),
                                       })
            self._append_log(draft_id, f"Refinement complete: {user_message[:100]}")

            return self.db.get_draft_agent(draft_id)

        except Exception as e:
            logger.error(f"Refinement failed for draft {draft_id}: {e}")
            self.db.update_draft_agent(draft_id, status=ERROR, error_message=str(e),
                                        refinement_history=json.dumps(history))
            await self._send_progress(websocket, draft_id, "error",
                                       f"Refinement failed: {e}", ERROR)
            return self.db.get_draft_agent(draft_id)

    # ─── Auto-Fix Tool Errors ────────────────────────────────────────

    def _get_draft_by_agent_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Look up a draft agent record by its runtime agent_id (e.g. 'etf-agent-1')."""
        # agent_id format is "{slug_with_hyphens}-1", reverse to get slug
        if not agent_id.endswith("-1"):
            return None
        slug = agent_id[:-2].replace('-', '_')  # "etf-agent" -> "etf_agent"
        draft = self.db.get_draft_agent_by_slug(slug)
        if draft and draft["status"] in (TESTING, GENERATED, LIVE):
            return draft
        return None

    async def auto_fix_tool_error(self, agent_id: str, tool_name: str,
                                   error_message: str, websocket=None) -> bool:
        """Automatically attempt to fix a tool error by refining the generated code.

        Returns True if a fix was attempted, False if this agent isn't a draft.
        """
        draft = self._get_draft_by_agent_id(agent_id)
        if not draft:
            return False

        draft_id = draft["id"]
        slug = draft["agent_slug"]
        tools_file = os.path.join(self._agents_dir, slug, "mcp_tools.py")

        if not os.path.exists(tools_file):
            return False

        logger.info(f"Auto-fix triggered for draft {draft_id}: tool '{tool_name}' error: {error_message}")

        # Build a targeted refinement message from the error
        fix_message = (
            f"The tool '{tool_name}' is failing with this error:\n"
            f"  {error_message}\n\n"
            f"Please fix the implementation of '{tool_name}' so it handles this correctly. "
            f"Common issues include: missing parameters, wrong parameter types, "
            f"missing imports, incorrect API usage, or unhandled edge cases. "
            f"Fix ONLY the issue — do not change other tools."
        )

        await self._send_progress(websocket, draft_id, "auto_fix",
                                   f"Auto-fixing tool '{tool_name}': {error_message[:100]}...",
                                   GENERATING)
        self._append_log(draft_id, f"Auto-fix triggered for '{tool_name}': {error_message[:200]}")

        try:
            # Stop the running agent
            await self.stop_draft_agent(draft_id)

            # Read current code
            with open(tools_file, "r", encoding="utf-8") as f:
                current_code = f.read()

            # Refine via LLM
            new_code = await self.generator.refine_tools_file(
                current_code=current_code,
                user_message=fix_message,
                agent_name=draft["agent_name"],
                description=draft["description"],
            )

            # Syntax validation
            try:
                compile(new_code, f"{slug}/mcp_tools.py", "exec")
            except SyntaxError as e:
                logger.error(f"Auto-fix produced syntax error: {e}")
                await self._send_progress(websocket, draft_id, "auto_fix_failed",
                                           f"Auto-fix produced invalid code (syntax error). Manual refinement needed.",
                                           TESTING)
                # Restart original agent
                await self.start_draft_agent(draft_id, websocket)
                return True

            # Security analysis
            report = self.security.analyze(new_code, filename=f"{slug}/mcp_tools.py")
            if not report.passed and report.max_severity == Severity.CRITICAL:
                logger.error("Auto-fix produced code with critical security issues")
                await self._send_progress(websocket, draft_id, "auto_fix_failed",
                                           "Auto-fix produced code with security issues. Manual refinement needed.",
                                           TESTING)
                await self.start_draft_agent(draft_id, websocket)
                return True

            # Write fixed code
            with open(tools_file, "w", encoding="utf-8") as f:
                f.write(new_code)

            # Update refinement history
            history = json.loads(draft.get("refinement_history") or "[]")
            history.append({
                "role": "system",
                "content": f"Auto-fix applied for tool '{tool_name}': {error_message[:200]}",
                "timestamp": int(time.time() * 1000),
            })
            self.db.update_draft_agent(draft_id, refinement_history=json.dumps(history))

            # Restart agent with fixed code
            await self.start_draft_agent(draft_id, websocket)

            await self._send_progress(websocket, draft_id, "auto_fix_complete",
                                       f"Auto-fix applied for tool '{tool_name}'. Agent restarted.",
                                       TESTING)
            self._append_log(draft_id, f"Auto-fix complete for '{tool_name}'")
            return True

        except Exception as e:
            logger.error(f"Auto-fix failed for draft {draft_id}: {e}")
            await self._send_progress(websocket, draft_id, "auto_fix_failed",
                                       f"Auto-fix failed: {e}", TESTING)
            # Try to restart the original agent
            try:
                await self.start_draft_agent(draft_id, websocket)
            except Exception:
                pass
            return True

    # ─── Approve Agent ───────────────────────────────────────────────

    async def approve_agent(self, draft_id: str, websocket=None) -> Dict[str, Any]:
        """Run comprehensive analysis and approve/reject the agent."""
        draft = self.db.get_draft_agent(draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")

        slug = draft["agent_slug"]
        tools_file = os.path.join(self._agents_dir, slug, "mcp_tools.py")

        if not os.path.exists(tools_file):
            raise FileNotFoundError("Agent files not found. Generate code first.")

        self.db.update_draft_agent(draft_id, status=ANALYZING)
        await self._send_progress(websocket, draft_id, "analyzing",
                                   "Running comprehensive security analysis...", ANALYZING)
        self._append_log(draft_id, "Starting approval analysis...")

        try:
            # Step 1: Full code security analysis
            await self._send_progress(websocket, draft_id, "code_analysis",
                                       "Analyzing generated code...", ANALYZING)

            with open(tools_file, "r", encoding="utf-8") as f:
                tools_code = f.read()

            report = self.security.analyze(tools_code, filename=f"{slug}/mcp_tools.py")

            # Step 2: Verify code is syntactically valid and imports work
            await self._send_progress(websocket, draft_id, "syntax_check",
                                       "Verifying code syntax...", ANALYZING)

            try:
                compile(tools_code, f"{slug}/mcp_tools.py", "exec")
            except SyntaxError as e:
                self.db.update_draft_agent(
                    draft_id, status=REJECTED,
                    security_report=json.dumps(report.to_dict()),
                    error_message=f"Syntax error in generated code: {e}",
                )
                await self._send_progress(websocket, draft_id, "rejected",
                                           f"Code has syntax errors: {e}", REJECTED)
                return self.db.get_draft_agent(draft_id)

            # Step 3: Spec validation
            await self._send_progress(websocket, draft_id, "spec_validation",
                                       "Validating tools against spec...", ANALYZING)

            validation_report = self.validator.validate(tools_code, slug, self._agents_dir)
            self.db.update_draft_agent(
                draft_id,
                validation_report=json.dumps(validation_report.to_dict()),
            )

            if not validation_report.passed:
                self.db.update_draft_agent(
                    draft_id, status=PENDING_REVIEW,
                    security_report=json.dumps(report.to_dict()),
                    error_message=(
                        f"Spec validation failed: {validation_report.tools_passed}/"
                        f"{validation_report.tools_tested} tools passed. "
                        "Requires review before going live."
                    ),
                )
                await self._send_progress(websocket, draft_id, "pending_review",
                                           "Agent has validation issues — requires review.",
                                           PENDING_REVIEW, detail={
                                               "security": report.to_dict(),
                                               "validation": validation_report.to_dict(),
                                           })
                self._append_log(draft_id, "Sent to review: spec validation failed")
                return self.db.get_draft_agent(draft_id)

            # Step 4: Decision based on security findings
            if report.max_severity == Severity.CRITICAL:
                self.db.update_draft_agent(
                    draft_id, status=REJECTED,
                    security_report=json.dumps(report.to_dict()),
                    error_message="Critical security issues detected. Agent rejected.",
                )
                await self._send_progress(websocket, draft_id, "rejected",
                                           "Agent rejected: critical security issues found.",
                                           REJECTED, detail=report.to_dict())
                self._append_log(draft_id, "REJECTED: Critical security issues")
                return self.db.get_draft_agent(draft_id)

            elif report.max_severity == Severity.HIGH:
                self.db.update_draft_agent(
                    draft_id, status=PENDING_REVIEW,
                    security_report=json.dumps(report.to_dict()),
                )
                await self._send_progress(websocket, draft_id, "pending_review",
                                           "Agent requires admin review before going live.",
                                           PENDING_REVIEW, detail=report.to_dict())
                self._append_log(draft_id, "Sent to admin review queue (high-severity findings)")
                return self.db.get_draft_agent(draft_id)

            else:
                # Clean or medium/low only → auto-approve
                self.db.update_draft_agent(
                    draft_id, status=LIVE,
                    security_report=json.dumps(report.to_dict()) if report.findings else None,
                )
                self._remove_draft_marker(slug)
                # Live agents: all scopes DISABLED — user must explicitly enable
                agent_id = f"{slug.replace('_', '-')}-1"
                if self.orchestrator:
                    self.orchestrator.tool_permissions.set_agent_scopes(
                        draft["user_id"], agent_id,
                        {"tools:read": False, "tools:write": False, "tools:search": False, "tools:system": False}
                    )
                await self._send_progress(websocket, draft_id, "approved",
                                           "Agent approved and is now live!", LIVE,
                                           detail=report.to_dict() if report.findings else None)
                self._append_log(draft_id, "APPROVED: Agent is now live")

                # Ensure agent is running
                if draft_id not in self._draft_processes or \
                   self._draft_processes[draft_id].poll() is not None:
                    await self.start_draft_agent(draft_id, websocket)

                return self.db.get_draft_agent(draft_id)

        except Exception as e:
            logger.error(f"Approval analysis failed for draft {draft_id}: {e}")
            self.db.update_draft_agent(draft_id, status=ERROR, error_message=str(e))
            await self._send_progress(websocket, draft_id, "error",
                                       f"Approval analysis failed: {e}", ERROR)
            return self.db.get_draft_agent(draft_id)

    # ─── Admin Review ────────────────────────────────────────────────

    async def admin_review(self, draft_id: str, decision: str, admin_user_id: str,
                            notes: str = None, websocket=None) -> Dict[str, Any]:
        """Admin approves or rejects a draft agent pending review."""
        draft = self.db.get_draft_agent(draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")
        if draft["status"] != PENDING_REVIEW:
            raise ValueError(f"Draft is not pending review (status: {draft['status']})")

        if decision == "approve":
            self.db.update_draft_agent(
                draft_id, status=LIVE,
                reviewed_by=admin_user_id,
                review_notes=notes or "Approved by admin",
            )
            self._remove_draft_marker(draft["agent_slug"])
            # Live agents: all scopes DISABLED — user must explicitly enable
            agent_id = f"{draft['agent_slug'].replace('_', '-')}-1"
            if self.orchestrator:
                self.orchestrator.tool_permissions.set_agent_scopes(
                    draft["user_id"], agent_id,
                    {"tools:read": False, "tools:write": False, "tools:search": False, "tools:system": False}
                )
            self._append_log(draft_id, f"Admin approved by {admin_user_id}")

            # Start agent if not running
            if draft_id not in self._draft_processes or \
               self._draft_processes[draft_id].poll() is not None:
                await self.start_draft_agent(draft_id, websocket)

            return self.db.get_draft_agent(draft_id)

        elif decision == "reject":
            self.db.update_draft_agent(
                draft_id, status=REJECTED,
                reviewed_by=admin_user_id,
                review_notes=notes or "Rejected by admin",
            )
            await self.stop_draft_agent(draft_id)
            self._append_log(draft_id, f"Admin rejected by {admin_user_id}: {notes or 'No reason given'}")
            return self.db.get_draft_agent(draft_id)

        else:
            raise ValueError(f"Invalid decision: {decision}. Must be 'approve' or 'reject'.")

    # ─── Delete Draft ────────────────────────────────────────────────

    async def delete_draft(self, draft_id: str) -> bool:
        """Delete a draft agent — stops process, removes files, deletes DB record."""
        draft = self.db.get_draft_agent(draft_id)
        if not draft:
            return False

        # Stop process and wait for it to fully terminate
        await self.stop_draft_agent(draft_id)
        # Give the OS time to release file handles (Windows is slow to release)
        await asyncio.sleep(0.5)

        # Remove files — retry on Windows where handles may linger
        slug = draft["agent_slug"]
        agent_dir = os.path.join(self._agents_dir, slug)
        if os.path.exists(agent_dir):
            for attempt in range(3):
                try:
                    shutil.rmtree(agent_dir)
                    logger.info(f"Removed agent directory: {agent_dir}")
                    break
                except (PermissionError, OSError) as e:
                    if attempt < 2:
                        logger.debug(f"rmtree attempt {attempt + 1} failed for {agent_dir}: {e}, retrying...")
                        await asyncio.sleep(1)
                    else:
                        logger.warning(f"Could not fully remove {agent_dir}: {e}")
                        # Force-remove individual files then try the directory
                        for root, dirs, files in os.walk(agent_dir, topdown=False):
                            for name in files:
                                try:
                                    os.remove(os.path.join(root, name))
                                except OSError:
                                    pass
                            for name in dirs:
                                try:
                                    os.rmdir(os.path.join(root, name))
                                except OSError:
                                    pass
                        try:
                            os.rmdir(agent_dir)
                        except OSError:
                            logger.warning(f"Directory still locked: {agent_dir}")

        # Delete DB record
        self.db.delete_draft_agent(draft_id)
        logger.info(f"Deleted draft agent {draft_id} ({draft['agent_name']})")
        return True
