"""
Keycloak Token Exchange Verification Script
Tests the RFC 8693 token exchange setup end-to-end.
"""
import os
import sys
import json
import asyncio
import base64
import aiohttp

# Load .env from project root (two levels up from tests/)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v

AUTHORITY = os.getenv("VITE_KEYCLOAK_AUTHORITY", "")
CLIENT_ID = os.getenv("VITE_KEYCLOAK_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
AGENT_SERVICE_CLIENT_ID = os.getenv("AGENT_SERVICE_CLIENT_ID", "astral-agent-service")
AGENT_SERVICE_CLIENT_SECRET = os.getenv("AGENT_SERVICE_CLIENT_SECRET", "")

TOKEN_URL = f"{AUTHORITY}/protocol/openid-connect/token"


def decode_jwt(token):
    parts = token.split(".")
    payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64))


async def step1_get_service_token():
    """Get a token via the agent-service client (which has service accounts enabled)."""
    print("=" * 60)
    print("STEP 1: Obtain token via astral-agent-service (service account)")
    print("=" * 60)
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "client_credentials",
            "client_id": AGENT_SERVICE_CLIENT_ID,
            "client_secret": AGENT_SERVICE_CLIENT_SECRET,
        }
        async with session.post(TOKEN_URL, data=data) as resp:
            body = await resp.json()
            if resp.status != 200:
                print(f"  FAIL ({resp.status}): {body.get('error')}: {body.get('error_description')}")
                return None
            token = body["access_token"]
            payload = decode_jwt(token)
            print(f"  OK: Got access token (expires_in={body.get('expires_in')}s)")
            print(f"  sub: {payload.get('sub')}")
            print(f"  azp: {payload.get('azp')}")
            return token


async def step1b_get_frontend_token():
    """Try to get a token via astral-frontend using client credentials."""
    print()
    print("=" * 60)
    print("STEP 1b: Try astral-frontend client credentials")
    print("=" * 60)
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        async with session.post(TOKEN_URL, data=data) as resp:
            body = await resp.json()
            if resp.status != 200:
                print(f"  INFO: astral-frontend does not have service accounts ({body.get('error')})")
                print(f"  This is expected — it's a frontend OIDC client.")
                print(f"  To test with a real user token, log into the app and copy your access_token.")
                return None
            token = body["access_token"]
            payload = decode_jwt(token)
            print(f"  OK: Got access token")
            print(f"  sub: {payload.get('sub')}")
            return token


async def step2_exchange_token_with(subject_token, from_client_id, from_client_secret):
    """Exchange a token for a delegation token (RFC 8693). 
    The 'audience' is the OTHER client (the one we're delegating to).
    """
    # Determine audience: if exchanging FROM frontend → TO agent-service, and vice versa
    audience = AGENT_SERVICE_CLIENT_ID if from_client_id == CLIENT_ID else CLIENT_ID
    
    print()
    print("=" * 60)
    print("STEP 2: RFC 8693 Token Exchange")
    print("=" * 60)
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": from_client_id,
            "client_secret": from_client_secret,
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "audience": audience,
        }
        print(f"  POST {TOKEN_URL}")
        print(f"  from: {from_client_id}")
        print(f"  audience: {audience}")
        async with session.post(TOKEN_URL, data=data) as resp:
            body = await resp.json()
            if resp.status != 200:
                print(f"\n  FAIL ({resp.status}): {body.get('error')}")
                print(f"  Description: {body.get('error_description')}")
                return None, None
            payload = decode_jwt(body["access_token"])
            print(f"\n  OK: Token exchange succeeded!")
            print(f"  token_type: {body.get('token_type')}")
            print(f"  expires_in: {body.get('expires_in')}s")
            print(f"  issued_token_type: {body.get('issued_token_type')}")
            print(f"\n  Delegation token claims:")
            print(f"    sub: {payload.get('sub')}")
            print(f"    azp: {payload.get('azp')}")
            print(f"    aud: {payload.get('aud')}")
            print(f"    act: {payload.get('act')}")
            print(f"    scope: {payload.get('scope')}")
            return body["access_token"], payload


async def step3_verify_agent_client():
    print()
    print("=" * 60)
    print("STEP 3: Verify agent-service client")
    print("=" * 60)
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "client_credentials",
            "client_id": AGENT_SERVICE_CLIENT_ID,
            "client_secret": AGENT_SERVICE_CLIENT_SECRET,
        }
        async with session.post(TOKEN_URL, data=data) as resp:
            body = await resp.json()
            if resp.status != 200:
                print(f"  FAIL ({resp.status}): {body.get('error')}: {body.get('error_description')}")
                return False
            print(f"  OK: agent-service client authenticated (expires_in={body.get('expires_in')}s)")
            return True


async def main():
    print(f"\nKeycloak Token Exchange Verification")
    print(f"Authority: {AUTHORITY}")
    print(f"Frontend client: {CLIENT_ID}")
    print(f"Agent service: {AGENT_SERVICE_CLIENT_ID}")
    print()

    # Step 1: Get a service account token from agent-service
    service_token = await step1_get_service_token()
    if not service_token:
        print("\nABORT: Cannot get agent-service token")
        return

    # Step 1b: Check if frontend has service accounts (informational)
    frontend_token = await step1b_get_frontend_token()

    # Step 2: Exchange the service token to test the token exchange flow
    # Use whichever token we got
    exchange_token = frontend_token or service_token
    exchange_client_id = CLIENT_ID if frontend_token else AGENT_SERVICE_CLIENT_ID
    exchange_client_secret = CLIENT_SECRET if frontend_token else AGENT_SERVICE_CLIENT_SECRET

    deleg_token, payload = await step2_exchange_token_with(
        exchange_token, exchange_client_id, exchange_client_secret
    )

    # Step 3: Verify agent-service directly
    agent_ok = await step3_verify_agent_client()

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    checks = [
        ("Agent-service client authenticated", service_token is not None),
        ("Token exchange succeeded", deleg_token is not None),
        ("sub claim present", payload.get("sub") is not None if payload else False),
        ("Agent-service client valid", agent_ok),
    ]
    if payload and deleg_token:
        aud = payload.get("aud", "")
        aud_check = AGENT_SERVICE_CLIENT_ID in str(aud) if frontend_token else CLIENT_ID in str(aud)
        checks.append(("aud claim correct", aud_check))

    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {label}")
    print(f"\n{'ALL CHECKS PASSED' if all(ok for _, ok in checks) else 'SOME CHECKS FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())
