#!/usr/bin/env python3
"""Test the fixes"""

import requests

BASE_URL = "http://localhost:8000"

print("Testing Fixes\n" + "="*60)

# Test 1: Favicon
print("\n[1] Test favicon...")
resp = requests.get(f"{BASE_URL}/favicon.ico")
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    print(f"✓ Favicon loaded ({len(resp.content)} bytes)")
else:
    print(f"✗ Favicon failed")

# Test 2: Register and test agent page
print("\n[2] Register user...")
resp = requests.post(f"{BASE_URL}/auth/register",
    json={"username": "fix_test", "password": "pass123"})
token = resp.json()['access_token']
print(f"✓ Got token")

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Test 3: Query agent with fixed template literal
print("\n[3] Query agent (tests template literal fix)...")
resp = requests.post(f"{BASE_URL}/agents/agent-002/ask",
    json={"question": "How many rock tracks?"},
    headers=headers)

if resp.status_code == 200:
    data = resp.json()
    print(f"✓ Query worked!")
    print(f"  Response: {data.get('response', '')[:80]}...")
else:
    print(f"✗ Query failed: {resp.status_code}")
    print(f"  Error: {resp.json()}")

print("\n" + "="*60)
