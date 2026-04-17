#!/usr/bin/env python3
"""Simple test for purchase and access key authentication"""

import requests
import json

BASE_URL = "http://localhost:8000"

# Create fresh test user
username = "accesskey_test"
password = "pass123"

print("Testing Access Key Authentication\n" + "="*50)

# Register
print("\n1. Register user...")
resp = requests.post(f"{BASE_URL}/auth/register", 
    json={"username": username, "password": password})
print(f"   Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"   Error: {resp.json()}")
    exit(1)

token = resp.json()['access_token']
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Use demo once
print("\n2. Use demo once (agent-002)...")
resp = requests.post(f"{BASE_URL}/agents/agent-002/ask",
    json={"question": "How many total tracks?"},
    headers=headers)
print(f"   Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"   ✓ Demo uses left: {data.get('demo_uses_left')}")
else:
    print(f"   Error: {resp.json()}")
    exit(1)

# Purchase access
print("\n3. Purchase agent access...")
resp = requests.post(f"{BASE_URL}/agents/agent-002/purchase", headers=headers)
print(f"   Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"   Error: {resp.json()}")
    exit(1)

data = resp.json()
access_key = data.get('access_key')
print(f"   ✓ Got access key: {access_key}")

# Use access key to query agent
print("\n4. Query agent with access key...")
access_headers = {"Authorization": f"Bearer {access_key}", "Content-Type": "application/json"}
resp = requests.post(f"{BASE_URL}/agents/agent-002/ask",
    json={"question": "How many rock tracks?"},
    headers=access_headers)
print(f"   Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"   ✓ Response: {data.get('response', '')[:60]}...")
    print(f"   ✓ Is purchased: {data.get('is_purchased')}")
else:
    error = resp.json()
    print(f"   ❌ Error: {error.get('detail', error)}")

print("\n" + "="*50)
print("Test complete!")
