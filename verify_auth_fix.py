#!/usr/bin/env python3
"""
Manual verification of authentication fix without requiring dependencies.
"""

import os
import re

print("=" * 70)
print("Authentication Fix Verification")
print("=" * 70)

# 1. Check backend auth.py for token query parameter extraction
print("\n1. Checking backend/orchestrator/auth.py for token query parameter support...")
with open("backend/orchestrator/auth.py", 'r', encoding='utf-8') as f:
    auth_content = f.read()
    
# Check for token query parameter extraction
if "token_param = request.query_params.get(\"token\")" in auth_content:
    print("   [OK] Found token query parameter extraction")
else:
    print("   [FAIL] Missing token query parameter extraction")
    
# Check that token from query is used
if "if token_param:\n            token = token_param" in auth_content:
    print("   [OK] Token from query parameter is assigned")
else:
    print("   [FAIL] Token from query parameter not assigned")

# 2. Check SSE endpoint uses verify_admin dependency
print("\n2. Checking SSE endpoint authentication...")
# Find the generate-with-progress endpoint
match = re.search(r'@app\\.api_route\(\"/api/agent-creator/generate-with-progress\".*?async def agent_creator_generate_with_progress\([^)]*admin=Depends\(verify_admin\)', auth_content, re.DOTALL)
if match:
    print("   [OK] SSE endpoint uses verify_admin dependency")
else:
    print("   [FAIL] SSE endpoint missing verify_admin dependency")

# 3. Check frontend hook
print("\n3. Checking frontend/src/hooks/useProgressSSE.ts...")
try:
    with open("frontend/src/hooks/useProgressSSE.ts", 'r', encoding='utf-8') as f:
        hook_content = f.read()
    
    # Check for token parameter in function signature
    if "token?: string" in hook_content:
        print("   [OK] Hook accepts optional token parameter")
    else:
        print("   [FAIL] Hook missing token parameter")
        
    # Check for token in URLSearchParams
    if "params.append('token', token)" in hook_content:
        print("   [OK] Hook adds token to URLSearchParams")
    else:
        print("   [FAIL] Hook missing token in URLSearchParams")
        
    # Check for EventSource construction with query string
    if "EventSource(`${endpoint}?${params.toString()}`" in hook_content:
        print("   [OK] Hook constructs EventSource with query parameters")
    else:
        print("   [FAIL] Hook missing query parameter construction")
        
except FileNotFoundError:
    print("   [FAIL] Hook file not found")

# 4. Check mock auth support
print("\n4. Checking mock authentication support...")
if "VITE_USE_MOCK_AUTH" in auth_content and "dev-token" in auth_content:
    print("   [OK] Mock authentication with dev-token is supported")
else:
    print("   [FAIL] Mock authentication not found")

# 5. Verify the complete flow
print("\n5. Verifying complete authentication flow...")
print("   Expected flow:")
print("   1. Frontend calls useProgressSSE(sessionId, phase, token)")
print("   2. Hook constructs URL: /api/agent-creator/generate-with-progress?session_id=...&token=...")
print("   3. Backend get_current_user_payload extracts token from query parameter")
print("   4. verify_admin validates token and returns admin user")
print("   5. SSE endpoint streams progress events")

# Check all critical components
components_ok = True
if "token_param = request.query_params.get(\"token\")" not in auth_content:
    components_ok = False
    print("   [FAIL] Missing: Backend token query extraction")
    
if "params.append('token', token)" not in hook_content:
    components_ok = False
    print("   [FAIL] Missing: Frontend token in URL")
    
if "admin=Depends(verify_admin)" not in auth_content:
    components_ok = False
    print("   [FAIL] Missing: SSE endpoint admin dependency")

if components_ok:
    print("\n[SUCCESS] All critical authentication fix components are present!")
    print("\nThe authentication fix appears to be correctly implemented.")
    print("The SSE endpoint should now accept authentication via query parameter.")
else:
    print("\n[FAILURE] Some components are missing or incorrect.")
    print("Please review the implementation.")

print("\n" + "=" * 70)
