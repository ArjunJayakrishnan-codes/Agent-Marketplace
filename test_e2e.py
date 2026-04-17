#!/usr/bin/env python3
"""Complete end-to-end test"""

import requests

BASE_URL = "http://localhost:8000"

print("End-to-End Agent Test\n" + "="*60)

# Register
print("\n[1] Register user...")
resp = requests.post(f"{BASE_URL}/auth/register",
    json={"username": "e2e_test", "password": "pass123"})
token = resp.json()['access_token']
print(f"✓ Registered, got token")

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Get agents with auth
print("\n[2] Get all agents (with auth)...")
resp = requests.get(f"{BASE_URL}/agents", headers=headers)
print(f"✓ Status: {resp.status_code}, Agents: {len(resp.json())}")

# Try all three agents
for agent_id in ["agent-001", "agent-002", "agent-003"]:
    print(f"\n[3.{agent_id[-1]}] Testing {agent_id}...")
    
    # Get agent details
    resp = requests.get(f"{BASE_URL}/agents/{agent_id}", headers=headers)
    if resp.status_code == 200:
        agent = resp.json()
        print(f"  ✓ Get details: {agent['name']}")
    else:
        print(f"  ✗ Get details failed: {resp.status_code}")
    
    # Query agent
    resp = requests.post(f"{BASE_URL}/agents/{agent_id}/ask",
        json={"question": "Hello"},
        headers=headers)
    if resp.status_code == 200:
        print(f"  ✓ Query works")
    else:
        print(f"  ✗ Query failed: {resp.status_code} - {resp.json()}")

print("\n" + "="*60)
print("Test complete!")
