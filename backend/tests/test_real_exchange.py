"""Quick test: exchange a real user token for a delegation token."""
import os, sys, json, base64, asyncio, aiohttp

# Load .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v

AUTHORITY = os.getenv("VITE_KEYCLOAK_AUTHORITY")
CLIENT_ID = os.getenv("VITE_KEYCLOAK_CLIENT_ID")
CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET")
AGENT_CLIENT = os.getenv("AGENT_SERVICE_CLIENT_ID", "astral-agent-service")
TOKEN_URL = f"{AUTHORITY}/protocol/openid-connect/token"

USER_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJMejZjMWNoaUxLa3ItQjhscFVKMEdLZjk3ZTk3U0dQcWVZOEZHYVM0S3RzIn0.eyJleHAiOjE3NzI0NzgzODcsImlhdCI6MTc3MjQ3ODA4NywiYXV0aF90aW1lIjoxNzcyNDc4MDg2LCJqdGkiOiJvZnJ0YWM6NzVjMDUxODItYTIyZC00ZjFkLTkxZTQtNmVlMmJiNzBhZDZhIiwiaXNzIjoiaHR0cHM6Ly9pYW0uYWkudWt5LmVkdS9yZWFsbXMvQXN0cmFsIiwiYXVkIjpbInJlYWxtLW1hbmFnZW1lbnQiLCJhY2NvdW50Il0sInN1YiI6IjU4ZTBkNGZmLWYwMDYtNGZiZS1hYTEzLTEwOWM2ZDUxYzk5ZCIsInR5cCI6IkJlYXJlciIsImF6cCI6ImFzdHJhbC1mcm9udGVuZCIsInNpZCI6IjQxMDdkNjUyLTlmNDAtNDhkNS1hMGIyLWM2NGFkYWIyN2E5NiIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiKiJdLCJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiZGVmYXVsdC1yb2xlcy1hc3RyYWwiLCJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsicmVhbG0tbWFuYWdlbWVudCI6eyJyb2xlcyI6WyJ2aWV3LXJlYWxtIiwidmlldy1pZGVudGl0eS1wcm92aWRlcnMiLCJtYW5hZ2UtaWRlbnRpdHktcHJvdmlkZXJzIiwiaW1wZXJzb25hdGlvbiIsInJlYWxtLWFkbWluIiwiY3JlYXRlLWNsaWVudCIsIm1hbmFnZS11c2VycyIsInF1ZXJ5LXJlYWxtcyIsInZpZXctYXV0aG9yaXphdGlvbiIsInF1ZXJ5LWNsaWVudHMiLCJxdWVyeS11c2VycyIsIm1hbmFnZS1ldmVudHMiLCJtYW5hZ2UtcmVhbG0iLCJ2aWV3LWV2ZW50cyIsInZpZXctdXNlcnMiLCJ2aWV3LWNsaWVudHMiLCJtYW5hZ2UtYXV0aG9yaXphdGlvbiIsIm1hbmFnZS1jbGllbnRzIiwicXVlcnktZ3JvdXBzIl19LCJhc3RyYWwtZnJvbnRlbmQiOnsicm9sZXMiOlsiYWRtaW4iLCJ1c2VyIl19LCJhY2NvdW50Ijp7InJvbGVzIjpbIm1hbmFnZS1hY2NvdW50IiwibWFuYWdlLWFjY291bnQtbGlua3MiLCJ2aWV3LXByb2ZpbGUiXX19LCJzY29wZSI6Im9wZW5pZCBvZmZsaW5lX2FjY2VzcyBlbWFpbCBwcm9maWxlIiwiZW1haWxfdmVyaWZpZWQiOnRydWUsIm5hbWUiOiJTYW0gQXJtc3Ryb25nIiwicHJlZmVycmVkX3VzZXJuYW1lIjoib2lkYy5zYW0uYXJtc3Ryb25nQHVreS5lZHUiLCJnaXZlbl9uYW1lIjoiU2FtIiwiZmFtaWx5X25hbWUiOiJBcm1zdHJvbmciLCJlbWFpbCI6InNhbS5hcm1zdHJvbmdAdWt5LmVkdSJ9.NxnhT012amIdLiThn6X_rwo7Q8K0lKxJUZWSSKVZzVVwIVrtC9ezy0gensYePYWS9Ad5o1aqjWxYau_RFgtj5yt6u2bmuH_NPnk_UH6_Qm6uhOMuJ8vDZivPTOQxkFM3o7ijY2PA4t4Qjln2q14bfZ6C5wRQoEdJSv_s5Jl1XBenfNk_dSqYyynhUM8TfyoiDzW280AUmUEDyn0h6YrBz5vayUX5Xd0cp6MPcbOLBQfswVZxLyUAlHPODeDWy6lgP7i0uCvxlyJCWs8pv8IJOkgSp_z65h3nIMIiiFjhaN-IDKUGtoMrNPV3pRzYWWc6eG424W7_if4w6FLAXNSISg"

def decode(tok):
    p = tok.split(".")[1]
    p += "=" * ((4 - len(p) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(p))

async def main():
    print("User token claims:")
    user_payload = decode(USER_TOKEN)
    print(f"  sub: {user_payload['sub']}")
    print(f"  name: {user_payload.get('name')}")
    print(f"  azp: {user_payload.get('azp')}")
    print()

    print("Exchanging user token for delegation token...")
    async with aiohttp.ClientSession() as session:
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "subject_token": USER_TOKEN,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "audience": AGENT_CLIENT,
        }
        async with session.post(TOKEN_URL, data=data) as resp:
            body = await resp.json()
            if resp.status != 200:
                print(f"FAIL ({resp.status}): {body.get('error')}")
                print(f"  {body.get('error_description')}")
                return
            
            print(f"SUCCESS! Token exchange worked.")
            print(f"  token_type: {body.get('token_type')}")
            print(f"  expires_in: {body.get('expires_in')}s")
            print(f"  issued_token_type: {body.get('issued_token_type')}")
            
            deleg = decode(body["access_token"])
            print(f"\nDelegation token claims:")
            print(f"  sub: {deleg.get('sub')}")
            print(f"  azp: {deleg.get('azp')}")
            print(f"  aud: {deleg.get('aud')}")
            print(f"  act: {deleg.get('act')}")
            print(f"  scope: {deleg.get('scope')}")
            print(f"  name: {deleg.get('name')}")
            
            # Verify key properties
            print(f"\nVerification:")
            print(f"  PASS: sub matches user" if deleg.get("sub") == user_payload["sub"] else "  FAIL: sub mismatch")
            print(f"  PASS: aud includes agent-service" if AGENT_CLIENT in str(deleg.get("aud", "")) else f"  INFO: aud = {deleg.get('aud')}")
            print(f"  PASS: act claim present" if deleg.get("act") else "  INFO: act claim not present (expected with scope mapper)")

asyncio.run(main())
