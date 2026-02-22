import requests
import asyncio
import websockets
import json
import uuid
import os

async def test_workflow():
    chat_id = str(uuid.uuid4())
    print(f"Generated chat_id: {chat_id}")
    
    # 1. Upload a file
    file_content = b"header1,header2\nval1,val2"
    files = {"file": ("test_data.csv", file_content)}
    data = {"session_id": chat_id}
    
    print("Uploading file to port 8002 (BFF)...")
    res = requests.post("http://localhost:8002/api/upload", files=files, data=data)
    print("Upload status:", res.status_code)
    print("Upload response:", res.json())
    
    # 2. Check if file is saved correctly without UUID renaming
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    file_path = os.path.join(backend_dir, "tmp", chat_id, "test_data.csv")
    print(f"Checking if file exists at {file_path}: {os.path.exists(file_path)}")
    
    # 3. Simulate frontend sending a message with this chat_id to the orchestrator (ws://localhost:8001)
    # The orchestrator should create the chat because it doesn't exist yet
    print("Sending message to Orchestrator...")
    async with websockets.connect("ws://localhost:8001") as ws:
        # We don't necessarily need to register_ui to test chat message
        msg = {
            "type": "ui_event",
            "action": "chat_message",
            "session_id": chat_id,
            "payload": {
                "message": "Hello, I uploaded test_data.csv",
                "chat_id": chat_id
            }
        }
        await ws.send(json.dumps(msg))
        
        # We expect a chat_created message or something similar
        # plus the response from the LLM
        for _ in range(5):
            try:
                recv_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                recv_data = json.loads(recv_msg)
                print(f"WS Received type: {recv_data.get('type')}")
                if recv_data.get('type') == 'chat_created':
                    print("Received chat_created successfully!")
                    print(recv_data)
                elif recv_data.get('type') == 'chat_status':
                    print(f"Status: {recv_data.get('status')} - {recv_data.get('message')}")
            except Exception as e:
                print("WS loop error or timeout:", e)
                break

if __name__ == "__main__":
    asyncio.run(test_workflow())
