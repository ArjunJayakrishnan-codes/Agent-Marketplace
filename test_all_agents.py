#!/usr/bin/env python3
"""Comprehensive test of all three agents with Chinook database queries"""

import requests
import json

BASE_URL = "http://localhost:8000"

# Create test user
username = "comprehensive_test"
password = "pass123"

print("\n" + "="*70)
print("COMPREHENSIVE AGENT TEST - CHINOOK DATABASE")
print("="*70)

# Register user
print("\n[Setup] Registering test user...")
resp = requests.post(f"{BASE_URL}/auth/register", 
    json={"username": username, "password": password})
if resp.status_code == 200:
    token = resp.json()['access_token']
    print(f"✓ User registered and authenticated")
else:
    print(f"✗ Registration failed: {resp.json()}")
    exit(1)

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Test data structure
agents_tests = {
    "agent-001": {
        "name": "Data Analyzer",
        "questions": [
            "What are the top genres?",
            "Who are the top artists?",
            "Top customers by spending?",
            "Database statistics",
        ]
    },
    "agent-002": {
        "name": "Query Executive",
        "questions": [
            "How many rock tracks?",
            "How many total tracks?",
            "What genres are available?",
            "Top artists by tracks?",
        ]
    },
    "agent-003": {
        "name": "Report Generator",
        "questions": [
            "Music catalog report",
            "Sales revenue report",
            "Employee staff report",
            "Database summary",
        ]
    }
}

# Test each agent
for agent_id, agent_data in agents_tests.items():
    print(f"\n{'─'*70}")
    print(f"Testing {agent_data['name']} ({agent_id})")
    print(f"{'─'*70}")
    
    # Get initial demo count
    resp = requests.get(f"{BASE_URL}/agents/my-access-status", headers=headers)
    if resp.status_code == 200:
        status = resp.json()
        initial_demos = status.get(agent_id, {}).get('demo_uses_left', 10)
        print(f"Initial demo tries: {initial_demos}")
    
    # Test each question
    for i, question in enumerate(agent_data['questions'][:3], 1):  # Test first 3 questions
        print(f"\n  Question {i}: {question}")
        
        resp = requests.post(
            f"{BASE_URL}/agents/{agent_id}/ask",
            json={"question": question},
            headers=headers
        )
        
        if resp.status_code == 200:
            data = resp.json()
            response = data.get('response', '')
            demo_left = data.get('demo_uses_left', 0)
            
            # Truncate response for display
            response_preview = response[:100] + "..." if len(response) > 100 else response
            
            print(f"  ✓ Status: {resp.status_code}")
            print(f"    Response: {response_preview}")
            print(f"    Demo uses left: {demo_left}")
        else:
            error_data = resp.json()
            print(f"  ✗ Status: {resp.status_code}")
            print(f"    Error: {error_data.get('detail', error_data)}")
    
    # Check final demo count
    resp = requests.get(f"{BASE_URL}/agents/my-access-status", headers=headers)
    if resp.status_code == 200:
        status = resp.json()
        final_demos = status.get(agent_id, {}).get('demo_uses_left', -1)
        queries_made = initial_demos - final_demos
        print(f"\n  Demo trend: {initial_demos} → {final_demos} ({queries_made} queries made)")

# Test Purchase and Access Key
print(f"\n{'─'*70}")
print("Testing Purchase & Access Key Flow")
print(f"{'─'*70}")

agent_to_purchase = "agent-002"
print(f"\nPurchasing {agents_tests[agent_to_purchase]['name']}...")

resp = requests.post(f"{BASE_URL}/agents/{agent_to_purchase}/purchase", headers=headers)
if resp.status_code == 200:
    purchase_data = resp.json()
    access_key = purchase_data.get('access_key')
    print(f"✓ Purchase successful")
    print(f"  Access Key: {access_key}")
    
    # Test with access key
    print(f"\nQuerying with access key...")
    access_headers = {"Authorization": f"Bearer {access_key}", "Content-Type": "application/json"}
    resp = requests.post(
        f"{BASE_URL}/agents/{agent_to_purchase}/ask",
        json={"question": "How many jazz tracks?"},
        headers=access_headers
    )
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ Access key query successful!")
        print(f"  Response: {data.get('response', '')[:80]}...")
        print(f"  Is Purchased: {data.get('is_purchased')}")
        print(f"  Demo Uses Left: {data.get('demo_uses_left')} (unlimited with purchased access)")
    else:
        print(f"✗ Access key query failed: {resp.json()}")
else:
    print(f"✗ Purchase failed: {resp.json()}")

print(f"\n{'='*70}")
print("TEST COMPLETE")
print(f"{'='*70}\n")
