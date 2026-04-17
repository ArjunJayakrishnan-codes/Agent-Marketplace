#!/usr/bin/env python3
"""Test the fixed Report Generator staff report"""

import requests

BASE_URL = "http://localhost:8000"

# Register test user
username = "staff_test_fixed"
password = "pass123"

resp = requests.post(f"{BASE_URL}/auth/register", 
    json={"username": username, "password": password})

if resp.status_code == 200:
    token = resp.json()['access_token']
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    print("Testing Fixed Staff Report Query\n" + "="*50)
    
    # Test staff report
    resp = requests.post(f"{BASE_URL}/agents/agent-003/ask",
        json={"question": "Employee staff report"},
        headers=headers)
    
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ Response: {data.get('response')}")
    else:
        print(f"✗ Error: {resp.json()}")
else:
    print(f"Registration failed: {resp.json()}")
