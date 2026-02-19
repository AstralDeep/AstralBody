import asyncio
import json
import websockets
import sys

# Define the complex query
QUERY = "search all the patients, graph their age, then do an arxiv search about the main disease in this patient population, then give me the system stats (cpu, memory, storage, all of it)"
URI = "ws://localhost:8001"

# Helper to print to both stdout and file
log_file = open("verification_log.txt", "w", encoding="utf-8")

def log(msg):
    print(msg)
    log_file.write(msg + "\n")
    log_file.flush()

async def test_flow():
    log(f"Connecting to {URI}...")
    try:
        async with websockets.connect(URI) as websocket:
            log("Connected.")
            
            # 1. Register/Handshake (Simulate UI)
            # Orchestrator expects a RegisterUI message or just handles messages.
            # looking at orchestrator.py, it handles UIEvent immediately.
            # But let's send a register just in case, or just start chatting.
            # Orchestrator handles `RegisterUI`.
            
            register_msg = {
                "type": "register_ui",
                "capabilities": ["text", "images"],
                "session_id": "test_script_1"
            }
            await websocket.send(json.dumps(register_msg))
            log("Sent RegisterUI.")

            # Wait for system config/dashboard
            while True:
                resp_raw = await websocket.recv()
                try:
                    resp = json.loads(resp_raw)
                except json.JSONDecodeError:
                    log(f"Received non-JSON: {resp_raw}")
                    continue
                log(f"Received: {resp.get('type')}")
                if resp.get("type") == "system_config":
                    log("System ready.")
                    break

            # 2. Send Chat Message
            chat_msg = {
                "type": "ui_event",
                "action": "chat_message",
                "payload": {
                    "message": QUERY
                }
            }
            log(f"Sending Query: {QUERY}")
            await websocket.send(json.dumps(chat_msg))

            # 3. Listen for responses
            # We expect:
            # - chat_status (thinking)
            # - chat_status (executing)
            # - ui_render (with tool outputs) multiple times?
            # - ui_render (final analysis)
            
            log("Listening for responses (Ctrl+C to stop)...")
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > 120:
                    log("Timeout waiting for full flow.")
                    break
                    
                resp_raw = await websocket.recv()
                try:
                    resp = json.loads(resp_raw)
                except json.JSONDecodeError:
                    log(f"Received non-JSON: {resp_raw}")
                    continue

                msg_type = resp.get("type")
                
                if msg_type == "chat_status":
                    status = resp.get("status")
                    message = resp.get("message")
                    log(f"STATUS: {status} - {message}")
                    
                elif msg_type == "ui_render":
                    components = resp.get("components", [])
                    log(f"RENDER: {len(components)} components")
                    for c in components:
                        title = c.get("title", "No Title")
                        c_type = c.get("type", "unknown")
                        log(f"  - [{c_type}] {title}")
                        
                        # Detailed check for specific expected components
                        if c_type == "card" and "Patient Search Results" in title:
                            log("    -> FOUND: Patient Search Results")
                        if c_type == "card" and "Patient Ages" in title:
                            log("    -> FOUND: Graph/Chart")
                        if c_type == "card" and "Wikipedia" in title:
                            log("    -> FOUND: Wikipedia Results")
                        
                        # New UI check
                        if c_type == "card" and "ArXiv Research" in title:
                             log("    -> FOUND: Arxiv Research Card (New UI)")
                             # Check for metrics
                             content_str = str(c)
                             if "MetricCard" in content_str and "Total Papers" in content_str:
                                 log("    -> FOUND: Arxiv Metrics (Total Papers)")

                        if "System Status" in title:
                            log("    -> FOUND: System Status")

                        if title == "Analysis":
                            log("\n--- FINAL ANALYSIS RECEIVED ---")
                            content = c.get("content", [])
                            for item in content:
                                if item.get("type") == "text":
                                    log(f"Analysis Content: {item.get('content')[:500]}...")
                            return

                elif msg_type == "error":
                    log(f"ERROR: {resp.get('message')}")

    except Exception as e:
        log(f"Connection error: {e}")
    finally:
        log_file.close()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(test_flow())
    except KeyboardInterrupt:
        print("Stopped.")
