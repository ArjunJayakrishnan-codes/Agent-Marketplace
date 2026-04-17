#!/usr/bin/env python3
"""Test if agents are loaded properly"""

import requests

BASE_URL = "http://localhost:8000"

print("Testing agent registration\n" + "="*60)

# Test 1: Get all agents
print("\n[1] GET /agents - List all agents")
resp = requests.get(f"{BASE_URL}/agents")
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    agents = resp.json()
    print(f"Agents found: {len(agents)}")
    for agent in agents:
        print(f"  - {agent.get('id')}: {agent.get('name')}")
else:
    print(f"Error: {resp.json()}")

# Test 2: Get specific agent details
print("\n[2] GET /agents/agent-002 - Get Query Executive details")
resp = requests.get(f"{BASE_URL}/agents/agent-002")
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    agent = resp.json()
    print(f"✓ Agent: {agent.get('name')}")
else:
    print(f"✗ Error: {resp.json()}")

# Test 3: Try to get the interactive page  
print("\n[3] GET /agents/agent-002/ask - Get interactive page")
resp = requests.get(f"{BASE_URL}/agents/agent-002/ask")
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    print(f"✓ Page returned ({len(resp.text)} bytes)")
else:
    print(f"✗ Error: {resp.json() if resp.headers.get('content-type') == 'application/json' else resp.text[:200]}")

print("\n" + "="*60)
