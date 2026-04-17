#!/usr/bin/env python3
"""Test authentication flow: register -> demo -> purchase -> use access key"""

import requests
import json
from urllib.parse import urljoin

BASE_URL = "http://localhost:8000"

def test_flow():
    print("\n" + "="*60)
    print("TESTING MARKETPLACE AUTH FLOW")
    print("="*60)
    
    # Step 1: Register user
    print("\n[1] REGISTER USER")
    username = "testuser_auth"
    password = "testpass123"
    
    register_response = requests.post(
        urljoin(BASE_URL, "/auth/register"),
        json={"username": username, "password": password}
    )
    print(f"Status: {register_response.status_code}")
    print(f"Response: {register_response.json()}")
    
    # Step 2: Login
    print("\n[2] LOGIN")
    login_response = requests.post(
        urljoin(BASE_URL, "/auth/login"),
        json={"username": username, "password": password}
    )
    print(f"Status: {login_response.status_code}")
    login_data = login_response.json()
    print(f"Response: {login_data}")
    
    jwt_token = login_data.get("access_token")
    token_type = login_data.get("token_type", "bearer")
    
    if not jwt_token:
        print("❌ Failed to get JWT token")
        return
    
    auth_header = {"Authorization": f"{token_type} {jwt_token}"}
    
    # Step 3: Load agents
    print("\n[3] LOAD AGENTS (first 2)")
    agents_response = requests.get(urljoin(BASE_URL, "/agents"), headers=auth_header)
    print(f"Status: {agents_response.status_code}")
    agents = agents_response.json()
    agent_ids = [a.get("id") for a in agents[:2]]
    print(f"Available agents: {[a.get('name') for a in agents[:2]]}")
    
    if not agent_ids:
        print("❌ No agents found")
        return
    
    agent_id = agent_ids[0]
    print(f"Using agent: {agent_id}")
    
    # Step 4: Ask question as demo user (should decrement counter)
    print(f"\n[4] ASK AGENT (DEMO - JWT TOKEN)")
    ask_response = requests.post(
        urljoin(BASE_URL, f"/agents/{agent_id}/ask"),
        json={"question": "How many rock tracks?"},
        headers={**auth_header, "Content-Type": "application/json"}
    )
    print(f"Status: {ask_response.status_code}")
    ask_data = ask_response.json()
    print(f"Response: {ask_data}")
    
    demo_uses_remaining = ask_data.get("demo_uses_left")
    print(f"✓ Demo uses remaining: {demo_uses_remaining}")
    
    # Step 5: Purchase access
    print(f"\n[5] PURCHASE AGENT ACCESS")
    purchase_response = requests.post(
        urljoin(BASE_URL, f"/agents/{agent_id}/purchase"),
        headers=auth_header
    )
    print(f"Status: {purchase_response.status_code}")
    purchase_data = purchase_response.json()
    print(f"Response keys: {purchase_data.keys()}")
    
    access_key = purchase_data.get("access_key")
    print(f"Access key: {access_key}")
    
    if not access_key:
        print("❌ Failed to get access key")
        return
    
    # Step 6: Use access key to query agent
    print(f"\n[6] ASK AGENT (ACCESS KEY)")
    access_header = {"Authorization": f"Bearer {access_key}"}
    ask_with_key_response = requests.post(
        urljoin(BASE_URL, f"/agents/{agent_id}/ask"),
        json={"question": "How many total tracks?"},
        headers={**access_header, "Content-Type": "application/json"}
    )
    print(f"Status: {ask_with_key_response.status_code}")
    ask_with_key_data = ask_with_key_response.json()
    print(f"Response: {ask_with_key_data}")
    
    if ask_with_key_response.status_code == 200:
        print("✓ ACCESS KEY AUTHENTICATION WORKS!")
    else:
        print(f"❌ Access key failed: {ask_with_key_data}")
    
    # Step 7: Test all three agents with demo
    print(f"\n[7] TEST ALL AGENTS WITH DEMO QUESTIONS")
    demo_questions = {
        "agent-001": "What are the top genres?",
        "agent-002": "How many total tracks?",
        "agent-003": "Music catalog report"
    }
    
    for aid, question in demo_questions.items():
        response = requests.post(
            urljoin(BASE_URL, f"/agents/{aid}/ask"),
            json={"question": question},
            headers={**auth_header, "Content-Type": "application/json"}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"\n  {aid}: ✓ Success")
            print(f"    Response: {data.get('response', '')[:60]}...")
        else:
            print(f"\n  {aid}: ❌ Failed ({response.status_code})")
            print(f"    Error: {response.json()}")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    test_flow()
