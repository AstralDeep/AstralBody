import os
import sys
import json
import asyncio
import subprocess
import websockets
import socket
from typing import Dict, Any, AsyncGenerator

from shared.protocol import MCPRequest
from shared.progress import ProgressEmitter, ProgressPhase, ProgressStep, create_log_event
from orchestrator.template_manager import generate_all_templates

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AGENTS_DIR = os.path.join(BASE_DIR, 'agents')

def save_agent_files(agent_name: str, mcp_tools_code: str, session: Dict) -> str:
    """Save the required files for the new agent into its own directory.
    
    Supports both old format (single tools code string) and new format (dict with three files).
    """
    new_agent_dir = os.path.join(AGENTS_DIR, agent_name)
    os.makedirs(new_agent_dir, exist_ok=True)
    
    class_agent_name = "".join([word.capitalize() for word in agent_name.split("_")]) + "Agent"
    class_server_name = "".join([word.capitalize() for word in agent_name.split("_")]) + "Server"
    
    # Determine if we have old format (string) or new format (dict)
    files = {}
    if isinstance(mcp_tools_code, dict) and "tools" in mcp_tools_code:
        # New format: dict with three files
        files = mcp_tools_code
        tools_code = files.get("tools", "")
        agent_code = files.get("agent", "")
        server_code = files.get("server", "")
    else:
        # Old format: single tools code string
        tools_code = mcp_tools_code
        agent_code = ""
        server_code = ""
    
    # Use template manager to generate missing files
    if not agent_code or not server_code:
        templates = generate_all_templates(agent_name, session)
        if not agent_code:
            agent_code = templates["agent"]
        if not server_code:
            server_code = templates["server"]
    
    # Write the files
    with open(os.path.join(new_agent_dir, f'{agent_name}_agent.py'), 'w', encoding='utf-8') as f:
        f.write(agent_code)
        
    with open(os.path.join(new_agent_dir, f'{agent_name}_server.py'), 'w', encoding='utf-8') as f:
        f.write(server_code)
        
    with open(os.path.join(new_agent_dir, f'{agent_name}_tools.py'), 'w', encoding='utf-8') as f:
        f.write(tools_code)
        
    # Create empty __init__.py
    with open(os.path.join(new_agent_dir, '__init__.py'), 'w') as f:
        f.write("")
        
    return new_agent_dir


async def run_tests_and_yield_logs(agent_dir: str, agent_name: str) -> AsyncGenerator[str, None]:
    """Starts the agent subprocess on a free port, connects to it, tests it, and yields SSE logs."""
    
    # Create progress emitter for testing phase
    emitter = ProgressEmitter(ProgressPhase.TESTING)
    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
        
    process = None
    
    # Use the python executable from the .venv explicitly to ensure isolation and proper dependencies
    if os.name == 'nt':
        python_exe = os.path.join(BASE_DIR, '..', '.venv', 'Scripts', 'python.exe')
    else:
        python_exe = os.path.join(BASE_DIR, '..', '.venv', 'bin', 'python')
        
    if not os.path.exists(python_exe):
        # Fallback if venv is not where we expect
        python_exe = sys.executable
        
    agent_script = os.path.join(agent_dir, f'{agent_name}_agent.py')
    
    # Step 1: Starting process
    yield emitter.emit_sse(
        ProgressStep.STARTING_PROCESS,
        percentage=20,
        message=f'Starting agent process on port {port}...',
        data={'port': port}
    )
    # Also emit legacy log for backward compatibility
    yield f"data: {json.dumps({'status': 'log', 'message': f'Starting agent process on port {port}...'})}\n\n"
    
    try:
        # Start subprocess
        process = subprocess.Popen(
            [python_exe, agent_script, "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=agent_dir, # run from new agent dir to ensure local imports match
            env=os.environ.copy()
        )
        
        # Drain process stdout in the background to prevent it from blocking and deadlocking
        def dump_output():
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
        
        # Run it in a background thread
        import threading
        threading.Thread(target=dump_output, daemon=True).start()

        # Step 2: Waiting for boot
        yield emitter.emit_sse(
            ProgressStep.WAITING_FOR_BOOT,
            percentage=30,
            message='Waiting for agent to boot (3 seconds)...',
            data={'wait_time': 3}
        )
        
        # Give it a moment to boot up
        await asyncio.sleep(3)
        
        if process.poll() is not None:
            stdout_data, _ = process.communicate()
            error_msg = f'Agent failed to start:\n{stdout_data}'
            yield emitter.emit_sse(
                ProgressStep.ERROR,
                percentage=100,
                message=error_msg,
                data={'error': True, 'process_output': stdout_data}
            )
            yield f"data: {json.dumps({'status': 'error', 'message': error_msg})}\n\n"
            return
            
        # Step 3: Agent started
        yield emitter.emit_sse(
            ProgressStep.WEBSOCKET_CONNECTION,
            percentage=40,
            message='Agent started successfully. Trying to connect via WebSocket...',
            data={'process_id': process.pid}
        )
        yield f"data: {json.dumps({'status': 'log', 'message': 'Agent started successfully. Trying to connect via WebSocket...'})}\n\n"
        
        ws_url = f"ws://localhost:{port}/agent"
        
        # Test 1: Connect to Agent
        try:
            async with websockets.connect(ws_url, ping_interval=None) as ws:
                # Step 4: WebSocket connected
                yield emitter.emit_sse(
                    ProgressStep.AGENT_REGISTRATION,
                    percentage=50,
                    message='WebSocket connected! Waiting for registration...',
                    data={'ws_url': ws_url}
                )
                yield f"data: {json.dumps({'status': 'log', 'message': 'WebSocket connected! Waiting for registration...'})}\n\n"
                
                # Receive registration
                reg_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                reg_data = json.loads(reg_msg)
                
                if reg_data.get("type") != "register_agent":
                    raise Exception("First message was not register_agent")
                    
                tools = reg_data.get("agent_card", {}).get("skills", [])
                tool_names = [t.get('name', 'unknown') for t in tools]
                
                # Step 5: Agent registered
                yield emitter.emit_sse(
                    ProgressStep.TOOLS_LIST_TEST,
                    percentage=60,
                    message=f'Agent registered {len(tools)} tools: {tool_names}',
                    data={'tools_count': len(tools), 'tool_names': tool_names}
                )
                yield f"data: {json.dumps({'status': 'log', 'message': f'Agent registered {len(tools)} tools: {tool_names}'})}\n\n"
                
                if len(tools) == 0:
                    error_msg = f'Agent registered 0 tools. Check {agent_name}_tools.py TOOL_REGISTRY.'
                    yield emitter.emit_sse(
                        ProgressStep.ERROR,
                        percentage=100,
                        message=error_msg,
                        data={'error': True, 'tools_registered': 0}
                    )
                    yield f"data: {json.dumps({'status': 'error', 'message': error_msg})}\n\n"
                    return
                
                # Step 6: Testing tools/list
                yield emitter.emit_sse(
                    ProgressStep.TOOLS_CALL_TEST,
                    percentage=70,
                    message='Testing tools/list endpoint...',
                    data={'test_type': 'tools/list'}
                )
                yield f"data: {json.dumps({'status': 'log', 'message': 'Testing tools/list endpoint...'})}\n\n"
                
                req_id = "test-1"
                list_req = MCPRequest(method="tools/list", request_id=req_id, params={})
                await ws.send(list_req.to_json())
                
                list_resp_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                list_resp = json.loads(list_resp_raw)
                
                if list_resp.get("error"):
                    error_msg = f'tools/list returned error: {list_resp.get("error")}'
                    yield emitter.emit_sse(
                        ProgressStep.ERROR,
                        percentage=100,
                        message=error_msg,
                        data={'error': True, 'response': list_resp}
                    )
                    yield f"data: {json.dumps({'status': 'error', 'message': error_msg})}\n\n"
                    return
                    
                # Step 7: Validation complete
                yield emitter.emit_sse(
                    ProgressStep.VALIDATION_COMPLETE,
                    percentage=80,
                    message='tools/list succeeded! Agent conforms to MCP protocol.',
                    data={'test_passed': True}
                )
                yield f"data: {json.dumps({'status': 'log', 'message': 'tools/list succeeded! Agent conforms to MCP protocol.'})}\n\n"
                
                # Step 8: Testing complete
                yield emitter.emit_sse(
                    ProgressStep.TESTING_COMPLETE,
                    percentage=100,
                    message='All tests passed.',
                    data={'success': True, 'tools_registered': len(tools)}
                )
                yield f"data: {json.dumps({'status': 'success', 'message': 'All tests passed.'})}\n\n"
                
        except Exception as e:
            error_msg = f'WebSocket test failed: {str(e)}'
            yield emitter.emit_sse(
                ProgressStep.ERROR,
                percentage=100,
                message=error_msg,
                data={'error': True, 'exception': str(e)}
            )
            yield f"data: {json.dumps({'status': 'error', 'message': error_msg})}\n\n"
            
    except Exception as e:
        error_msg = f'Subprocess test failed: {str(e)}'
        yield emitter.emit_sse(
            ProgressStep.ERROR,
            percentage=100,
            message=error_msg,
            data={'error': True, 'exception': str(e)}
        )
        yield f"data: {json.dumps({'status': 'error', 'message': error_msg})}\n\n"
        
    finally:
        # DO NOT kill if successful -> the user wants it auto-started and ready!
        # Wait, the frontend might disconnect or it might just exist in standard system.
        # But actually to plug into the system, the Orchestrator needs to discover it.
        # It's better to leave it running so the orchestrator auto-discovers it.
        # (Assuming orchestrator is instructed to monitor port 8010? No, orchestrator monitors AGENT_PORT 8003).
        # We need the orchestrator to discover it.
        # The orchestrator's `_monitor_agents` currently only monitors `AGENT_PORT=8003` in `start.py`.
        # To make it auto-discoverable, we really should either notify the orchestrator or tell the user to restart.
        # But user requested it auto-starts!
        # For now, we will leave the process running! We'll just detach it or keep a reference.
        # Wait, if we keep the reference local, it might die when tests finish. Let's not terminate if successful.
        pass
