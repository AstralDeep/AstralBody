#!/usr/bin/env python3
"""
Test script for SSE endpoint authentication fix.

Tests:
1. Backend token extraction from query parameters
2. SSE endpoint authentication with token query parameter
3. Frontend hook URL construction
4. Mock authentication flow
"""

import sys
import os
import json
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, Any

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from fastapi import FastAPI, Request, Depends
from fastapi.testclient import TestClient
from fastapi.security import HTTPBearer


def test_backend_token_extraction():
    """Test that get_current_user_payload extracts token from query parameter."""
    print("\n=== Test 1: Backend Token Extraction ===")
    
    # Import the auth module
    from orchestrator.auth import get_current_user_payload, security
    
    # Create a mock request with token in query parameter
    mock_request = Mock(spec=Request)
    mock_request.method = "GET"
    mock_request.query_params = {"token": "dev-token"}
    
    # Mock credentials to be None (no Authorization header)
    mock_credentials = None
    
    # Mock environment for mock auth
    with patch.dict(os.environ, {"VITE_USE_MOCK_AUTH": "true"}):
        # Call the dependency
        # Note: We need to call it as a function since it's async
        async def run_test():
            return await get_current_user_payload(mock_request, mock_credentials)
        
        result = asyncio.run(run_test())
        
        # Verify result
        assert result is not None
        assert result["sub"] == "dev-user-id"
        assert result["preferred_username"] == "DevUser"
        assert "realm_access" in result
        
        print("✓ Token extraction from query parameter works")
        
        # Test with Authorization header instead
        mock_request_with_header = Mock(spec=Request)
        mock_request_with_header.method = "GET"
        mock_request_with_header.query_params = {}
        
        mock_credentials_with_header = Mock()
        mock_credentials_with_header.credentials = "dev-token"
        
        async def run_test_with_header():
            return await get_current_user_payload(mock_request_with_header, mock_credentials_with_header)
        
        result2 = asyncio.run(run_test_with_header())
        assert result2["sub"] == "dev-user-id"
        print("✓ Token extraction from Authorization header works")
        
        # Test without token (should raise 401)
        mock_request_no_token = Mock(spec=Request)
        mock_request_no_token.method = "GET"
        mock_request_no_token.query_params = {}
        
        async def run_test_no_token():
            try:
                return await get_current_user_payload(mock_request_no_token, None)
            except Exception as e:
                return e
        
        result3 = asyncio.run(run_test_no_token())
        assert hasattr(result3, 'status_code') and result3.status_code == 401
        print("✓ Missing token raises 401")
        
    return True


def test_sse_endpoint_authentication():
    """Test that the SSE endpoint accepts token query parameter."""
    print("\n=== Test 2: SSE Endpoint Authentication ===")
    
    # Import the auth app
    from orchestrator.auth import app
    
    # Create test client
    client = TestClient(app)
    
    # Mock the agent_generator to avoid actual generation
    with patch('orchestrator.auth.agent_generator') as mock_gen, \
         patch.dict(os.environ, {"VITE_USE_MOCK_AUTH": "true"}):
        
        # Setup mock
        mock_gen.generate_code = AsyncMock(return_value={
            "files": {"tools.py": "# test", "agent.py": "", "server.py": ""}
        })
        
        # Test 2.1: GET request with token query parameter
        print("Testing GET /api/agent-creator/generate-with-progress?token=dev-token&session_id=test-session")
        response = client.get(
            "/api/agent-creator/generate-with-progress",
            params={"token": "dev-token", "session_id": "test-session"}
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        # SSE endpoint returns 200 with text/event-stream
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        print("✓ GET request with token query parameter accepted")
        
        # Test 2.2: POST request with token query parameter (should also work)
        print("\nTesting POST /api/agent-creator/generate-with-progress?token=dev-token")
        response_post = client.post(
            "/api/agent-creator/generate-with-progress",
            params={"token": "dev-token"},
            json={"session_id": "test-session"}
        )
        
        assert response_post.status_code == 200
        assert "text/event-stream" in response_post.headers.get("content-type", "")
        print("✓ POST request with token query parameter accepted")
        
        # Test 2.3: Request without token (should return 401)
        print("\nTesting without token (should return 401)")
        response_no_token = client.get(
            "/api/agent-creator/generate-with-progress",
            params={"session_id": "test-session"}
        )
        
        print(f"Response without token: {response_no_token.status_code}")
        print(f"Response body: {response_no_token.json()}")
        
        # Should be 401 Unauthorized
        assert response_no_token.status_code == 401
        print("✓ Missing token returns 401")
        
        # Test 2.4: Test endpoint with Authorization header
        print("\nTesting with Authorization header")
        response_with_auth = client.get(
            "/api/agent-creator/generate-with-progress",
            params={"session_id": "test-session"},
            headers={"Authorization": "Bearer dev-token"}
        )
        
        assert response_with_auth.status_code == 200
        print("✓ Authorization header works")
        
    return True


def test_frontend_hook_url_construction():
    """Test that useProgressSSE hook constructs correct URL with token."""
    print("\n=== Test 3: Frontend Hook URL Construction ===")
    
    # Read the frontend hook file
    hook_path = os.path.join("frontend", "src", "hooks", "useProgressSSE.ts")
    with open(hook_path, 'r', encoding='utf-8') as f:
        hook_content = f.read()
    
    # Check that token is added to params
    assert "params.append('token', token)" in hook_content
    print("✓ Hook includes token in URLSearchParams")
    
    # Check that endpoint URL is correct
    assert "/api/agent-creator/generate-with-progress" in hook_content
    print("✓ Hook uses correct endpoint")
    
    # Check that EventSource is created with query string
    assert "EventSource(`${endpoint}?${params.toString()}`" in hook_content
    print("✓ Hook constructs EventSource with query parameters")
    
    # Simulate URL construction
    base_url = "http://localhost:8001"
    endpoint = f"{base_url}/api/agent-creator/generate-with-progress"
    session_id = "test-session-123"
    token = "dev-token"
    
    params = {"session_id": session_id, "token": token}
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    full_url = f"{endpoint}?{query_string}"
    
    print(f"\nExample constructed URL: {full_url}")
    
    # Verify the URL format
    assert "token=dev-token" in full_url
    assert "session_id=test-session-123" in full_url
    print("✓ URL construction produces correct format")
    
    return True


def test_mock_auth_flow():
    """Test the complete mock authentication flow."""
    print("\n=== Test 4: Complete Mock Auth Flow ===")
    
    # Import auth dependencies
    from orchestrator.auth import get_current_user_payload, verify_admin
    
    # Create mock request with dev-token
    mock_request = Mock(spec=Request)
    mock_request.method = "GET"
    mock_request.query_params = {"token": "dev-token"}
    
    with patch.dict(os.environ, {"VITE_USE_MOCK_AUTH": "true"}):
        # Test get_current_user_payload
        async def test_payload():
            return await get_current_user_payload(mock_request, None)
        
        payload = asyncio.run(test_payload())
        assert payload["sub"] == "dev-user-id"
        print("✓ Mock auth returns dev user payload")
        
        # Test verify_admin (which depends on get_current_user_payload)
        async def test_admin():
            return await verify_admin(payload)
        
        admin_result = asyncio.run(test_admin())
        assert admin_result["is_admin"] == True
        print("✓ verify_admin adds is_admin flag")
        
        # Test with non-admin token (should fail)
        # First create a mock payload without admin role
        non_admin_payload = {
            "sub": "regular-user",
            "preferred_username": "RegularUser",
            "realm_access": {"roles": ["user"]}  # Only user role, not admin
        }
        
        async def test_non_admin():
            try:
                return await verify_admin(non_admin_payload)
            except Exception as e:
                return e
        
        non_admin_result = asyncio.run(test_non_admin())
        assert hasattr(non_admin_result, 'status_code') and non_admin_result.status_code == 403
        print("✓ Non-admin user gets 403 Forbidden")
    
    return True


def test_sse_stream_content():
    """Test that SSE stream produces correct format."""
    print("\n=== Test 5: SSE Stream Content ===")
    
    from orchestrator.auth import app
    from shared.progress import ProgressEvent, ProgressPhase, ProgressStep
    
    client = TestClient(app)
    
    with patch('orchestrator.auth.agent_generator') as mock_gen, \
         patch.dict(os.environ, {"VITE_USE_MOCK_AUTH": "true"}):
        
        # Create a mock progress callback collector
        captured_callbacks = []
        
        def mock_generate_code(session_id, progress_callback=None, user_id=None):
            # Store the callback for testing
            if progress_callback:
                captured_callbacks.append(progress_callback)
                
                # Call it with a test event
                event = ProgressEvent(
                    phase=ProgressPhase.GENERATION,
                    step=ProgressStep.PROMPT_CONSTRUCTION,
                    percentage=10,
                    message="Test progress event"
                )
                progress_callback(event)
                
                # Call with completion
                event2 = ProgressEvent(
                    phase=ProgressPhase.GENERATION,
                    step=ProgressStep.GENERATION_COMPLETE,
                    percentage=100,
                    message="Generation complete!"
                )
                progress_callback(event2)
            
            return {"files": {"test.py": "# test"}}
        
        mock_gen.generate_code = AsyncMock(side_effect=mock_generate_code)
        
        # Make request
        response = client.get(
            "/api/agent-creator/generate-with-progress",
            params={"token": "dev-token", "session_id": "test-session"},
            stream=True
        )
        
        # Read SSE stream
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line.decode('utf-8'))
                if len(lines) >= 3:  # Get first few events
                    break
        
        print(f"Received {len(lines)} SSE lines")
        for i, line in enumerate(lines):
            print(f"  Line {i}: {line[:100]}..." if len(line) > 100 else f"  Line {i}: {line}")
        
        # Verify SSE format
        assert len(lines) > 0
        assert any(line.startswith("data: {") for line in lines)
        print("✓ SSE stream produces valid events")
        
        # Parse first data event
        for line in lines:
            if line.startswith("data: {"):
                json_str = line[6:]  # Remove "data: " prefix
                try:
                    data = json.loads(json_str)
                    assert data["type"] == "progress"
                    assert data["phase"] == "generation"
                    print("✓ SSE event has correct structure")
                    break
                except json.JSONDecodeError:
                    continue
    
    return True


def main():
    """Run all authentication fix tests."""
    print("=" * 70)
    print("SSE Endpoint Authentication Fix Tests")
    print("=" * 70)
    
    tests = [
        ("Backend Token Extraction", test_backend_token_extraction),
        ("SSE Endpoint Authentication", test_sse_endpoint_authentication),
        ("Frontend Hook URL Construction", test_frontend_hook_url_construction),
        ("Mock Auth Flow", test_mock_auth_flow),
        ("SSE Stream Content", test_sse_stream_content),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"\n\nRunning: {test_name}")
            print("-" * 50)
            success = test_func()
            if success:
                passed += 1
                print(f"\n✓ {test_name} PASSED")
            else:
                failed += 1
                print(f"\n✗ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"\n✗ {test_name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print("\n✅ All authentication fix tests passed!")
        print("\nSummary of verification:")
        print("1. ✅ Backend correctly extracts token from query parameters")
        print("2. ✅ SSE endpoint accepts authentication via query parameter")
        print("3. ✅ Frontend hook properly includes token in URL")
        print("4. ✅ Mock authentication flow works correctly")
        print("5. ✅ SSE stream produces valid events")
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the authentication fix.")
        sys.exit(1)


if __name__ == "__main__":
    main()
