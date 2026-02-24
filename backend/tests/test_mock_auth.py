#!/usr/bin/env python3
"""
Test script for mock authentication fix.
Verifies that validate_token function in orchestrator.py works correctly with mock authentication.
"""
import os
import sys
import asyncio
import json
import base64
import logging

# Suppress logging from Orchestrator
logging.getLogger('Orchestrator').setLevel(logging.WARNING)
logging.getLogger('uvicorn').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from orchestrator.orchestrator import Orchestrator

# JWT token from frontend MockAuthContext.tsx
MOCK_JWT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiYWRtaW4iLCJ1c2VyIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYXN0cmFsLWZyb250ZW5kIjp7InJvbGVzIjpbImFkbWluIiwidXNlciJdfX0sInN1YiI6ImRldi11c2VyLWlkIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiRGV2VXNlciJ9."
    "fake-signature-ignore"
)

def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload for verification."""
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid JWT token")
    payload_b64 = parts[1]
    # Add padding
    payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
    payload_json = base64.b64decode(payload_b64).decode('utf-8')
    return json.loads(payload_json)

async def test_mock_auth_with_jwt():
    """Test validate_token with the JWT token from MockAuthContext."""
    print("\n=== Test 1: JWT token with mock auth enabled ===")
    os.environ["VITE_USE_MOCK_AUTH"] = "true"
    orch = Orchestrator()
    
    payload = await orch.validate_token(MOCK_JWT_TOKEN)
    assert payload is not None, "Token validation failed"
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    
    # Verify expected fields
    assert payload.get("sub") == "dev-user-id", f"Expected sub='dev-user-id', got {payload.get('sub')}"
    assert payload.get("preferred_username") == "DevUser", f"Expected preferred_username='DevUser', got {payload.get('preferred_username')}"
    
    # Verify roles
    realm_access = payload.get("realm_access", {})
    roles = realm_access.get("roles", [])
    assert "admin" in roles, f"'admin' role missing in {roles}"
    assert "user" in roles, f"'user' role missing in {roles}"
    
    # Verify resource_access
    resource_access = payload.get("resource_access", {})
    astral_frontend = resource_access.get("astral-frontend", {})
    client_roles = astral_frontend.get("roles", [])
    assert "admin" in client_roles, f"'admin' missing in client roles {client_roles}"
    assert "user" in client_roles, f"'user' missing in client roles {client_roles}"
    
    print("  [PASS] JWT token validated successfully with correct roles")
    return True

async def test_mock_auth_with_dev_token():
    """Test validate_token with the legacy 'dev-token' string."""
    print("\n=== Test 2: 'dev-token' string with mock auth enabled ===")
    os.environ["VITE_USE_MOCK_AUTH"] = "true"
    orch = Orchestrator()
    
    payload = await orch.validate_token("dev-token")
    assert payload is not None, "dev-token validation failed"
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    
    assert payload.get("sub") == "dev-user-id"
    assert payload.get("preferred_username") == "DevUser"
    assert payload.get("email") == "dev@local"
    
    realm_access = payload.get("realm_access", {})
    roles = realm_access.get("roles", [])
    assert "admin" in roles
    assert "user" in roles
    
    print("  [PASS] dev-token validated successfully")
    return True

async def test_mock_auth_with_invalid_token():
    """Test that invalid token returns None (or default mock user?)."""
    print("\n=== Test 3: Invalid token with mock auth enabled ===")
    os.environ["VITE_USE_MOCK_AUTH"] = "true"
    orch = Orchestrator()
    
    # Some random string that's not a JWT
    payload = await orch.validate_token("random-invalid-token")
    # According to the code, if decoding fails, it returns default mock user
    assert payload is not None, "Invalid token should still return default mock user"
    assert payload.get("sub") == "dev-user-id"
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    print("  [PASS] Invalid token falls back to default mock user")
    return True

async def test_mock_auth_disabled():
    """Test that when VITE_USE_MOCK_AUTH is false, token validation fails (no Keycloak config)."""
    print("\n=== Test 4: Mock auth disabled (real auth) ===")
    # Ensure env var is not set or false
    os.environ["VITE_USE_MOCK_AUTH"] = "false"
    # Remove any Keycloak config to simulate missing config
    if "VITE_KEYCLOAK_AUTHORITY" in os.environ:
        del os.environ["VITE_KEYCLOAK_AUTHORITY"]
    if "VITE_KEYCLOAK_CLIENT_ID" in os.environ:
        del os.environ["VITE_KEYCLOAK_CLIENT_ID"]
    
    orch = Orchestrator()
    
    # With mock auth disabled and no Keycloak config, validate_token should return None
    payload = await orch.validate_token(MOCK_JWT_TOKEN)
    if payload is None:
        print("  [PASS] Real auth correctly returns None (no Keycloak config)")
        return True
    else:
        # In a real environment with proper Keycloak config, it would attempt to validate.
        # Since we don't have that, we can't test further.
        print(f"  Note: payload returned (maybe mock auth still active?): {payload}")
        return False

async def test_role_extraction():
    """Verify that roles are correctly extracted from the payload."""
    print("\n=== Test 5: Role extraction ===")
    os.environ["VITE_USE_MOCK_AUTH"] = "true"
    orch = Orchestrator()
    
    # Use JWT token
    payload = await orch.validate_token(MOCK_JWT_TOKEN)
    assert payload is not None
    
    # The _get_user_id method uses sub field
    user_id = orch._get_user_id(None)  # websocket not needed for this test
    # Since we didn't register a websocket session, it returns 'legacy'
    # That's fine; we just want to ensure the payload is stored.
    
    # Check that roles are present for authorization
    realm_roles = payload.get("realm_access", {}).get("roles", [])
    resource_roles = payload.get("resource_access", {}).get("astral-frontend", {}).get("roles", [])
    all_roles = set(realm_roles + resource_roles)
    print(f"  Extracted roles: {all_roles}")
    assert "admin" in all_roles
    assert "user" in all_roles
    print("  [PASS] Role extraction successful")
    return True

async def main():
    """Run all tests."""
    print("Starting mock authentication tests...")
    
    # Save original environment
    original_env = {k: os.environ.get(k) for k in ["VITE_USE_MOCK_AUTH", "VITE_KEYCLOAK_AUTHORITY", "VITE_KEYCLOAK_CLIENT_ID"]}
    
    try:
        # Ensure we start with mock auth enabled for most tests
        os.environ["VITE_USE_MOCK_AUTH"] = "true"
        
        results = []
        results.append(await test_mock_auth_with_jwt())
        results.append(await test_mock_auth_with_dev_token())
        results.append(await test_mock_auth_with_invalid_token())
        results.append(await test_role_extraction())
        results.append(await test_mock_auth_disabled())
        
        if all(results):
            print("\n[SUCCESS] All tests passed!")
            return 0
        else:
            print("\n[FAILURE] Some tests failed.")
            return 1
    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
