#!/usr/bin/env python3
"""Test Query Executive with genre queries"""

import requests

BASE_URL = "http://localhost:8000"

# Register test user
username = "genre_test_fixed"
password = "pass123"

resp = requests.post(f"{BASE_URL}/auth/register", 
    json={"username": username, "password": password})

if resp.status_code == 200:
    token = resp.json()['access_token']
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    print("Testing Query Executive Genre Queries\n" + "="*60)
    
    questions = [
        "What genres are available?",
        "How many rock tracks?",
        "How many total tracks?"
    ]
    
    for q in questions:
        print(f"\n❓ Question: {q}")
        resp = requests.post(f"{BASE_URL}/agents/agent-002/ask",
            json={"question": q},
            headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ {data.get('response')[:150]}...")
        else:
            print(f"✗ Error: {resp.json()}")
    
    print("\n" + "="*60)
else:
    print(f"Registration failed: {resp.json()}")
