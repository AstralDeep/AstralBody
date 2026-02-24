#!/usr/bin/env python3
"""Test the SSE endpoint for agent generation."""
import asyncio
import aiohttp
import json
import sys

async def test_sse_endpoint():
    """Test the generate-with-progress SSE endpoint."""
    # We need a valid session_id from an existing session
    # First, let's create a session
    async with aiohttp.ClientSession() as session:
        # Create a test session
        start_data = {
            "name": "TestAgent",
            "persona": "A test agent",
            "toolsDescription": "Fetches data",
            "apiKeys": ""
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer dev-token"  # Using mock auth
        }
        
        try:
            # Start a session
            print("Creating test session...")
            async with session.post(
                "http://localhost:8001/api/agent-creator/start",
                json=start_data,
                headers=headers
            ) as resp:
                if resp.status != 200:
                    print(f"Failed to create session: {resp.status}")
                    text = await resp.text()
                    print(f"Response: {text}")
                    return False
                
                result = await resp.json()
                session_id = result.get("session_id")
                print(f"Created session: {session_id}")
                
                # Now test the SSE endpoint
                print(f"\nTesting SSE endpoint for session {session_id}...")
                sse_url = f"http://localhost:8001/api/agent-creator/generate-with-progress?session_id={session_id}&token=dev-token"
                
                async with session.get(sse_url, headers=headers) as sse_resp:
                    if sse_resp.status != 200:
                        print(f"SSE endpoint failed: {sse_resp.status}")
                        return False
                    
                    print(f"SSE connection established (status: {sse_resp.status})")
                    print("Waiting for events... (timeout: 30 seconds)")
                    
                    # Read SSE stream
                    buffer = ""
                    timeout = 30
                    start_time = asyncio.get_event_loop().time()
                    
                    async for chunk in sse_resp.content:
                        if chunk:
                            buffer += chunk.decode('utf-8')
                            
                            # Parse SSE events
                            while "\n\n" in buffer:
                                event, buffer = buffer.split("\n\n", 1)
                                
                                # Skip empty lines and comments
                                if not event or event.startswith(':'):
                                    continue
                                    
                                # Parse data line
                                for line in event.split('\n'):
                                    if line.startswith('data: '):
                                        data = line[6:]
                                        try:
                                            parsed = json.loads(data)
                                            print(f"\nReceived event: {json.dumps(parsed, indent=2)}")
                                            
                                            # Check for completion
                                            if parsed.get("type") == "complete":
                                                print("\nGeneration completed successfully!")
                                                return True
                                            elif parsed.get("type") == "progress":
                                                print(f"Progress: {parsed.get('percentage')}% - {parsed.get('message')}")
                                            
                                        except json.JSONDecodeError:
                                            print(f"Raw data: {data}")
                        
                        # Check timeout
                        if asyncio.get_event_loop().time() - start_time > timeout:
                            print("\nTimeout waiting for completion")
                            return False
                    
                    print("\nSSE stream ended")
                    return False
                    
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        success = asyncio.run(test_sse_endpoint())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted")
        sys.exit(1)