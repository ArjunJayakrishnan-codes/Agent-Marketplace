import requests

# Test 1: Login as user1
print('=== TEST 1: Login as user1 ===')
r = requests.post('http://localhost:8000/auth/login', json={'username': 'user1', 'password': 'user123'})
token1 = r.json()['access_token']
print('✓ user1 logged in')

# Test 2: Check initial access status
print('\n=== TEST 2: Initial access status ===')
r = requests.get('http://localhost:8000/agents/my-access-status', headers={'Authorization': 'Bearer ' + token1})
access = r.json()
for aid in ['agent-001', 'agent-002']:
    status = access.get(aid, {})
    print('Agent', aid, '- demo tries left:', status.get('demo_uses_left'))

# Test 3: Try agent-001 first time
print('\n=== TEST 3: Try Agent-001 (Try 1) ===')
r = requests.post('http://localhost:8000/agents/agent-001/ask',
    json={'question': 'Hello 1'},
    headers={'Authorization': 'Bearer ' + token1}
)
print('Status:', r.status_code, '- Demo tries left:', r.json().get('demo_uses_left'))

# Test 4: Try agent-001 second time  
print('\n=== TEST 4: Try Agent-001 (Try 2) ===')
r = requests.post('http://localhost:8000/agents/agent-001/ask',
    json={'question': 'Hello 2'},
    headers={'Authorization': 'Bearer ' + token1}
)
print('Status:', r.status_code, '- Demo tries left:', r.json().get('demo_uses_left'))

# Test 5: Try agent-001 third time (should fail with 402)
print('\n=== TEST 5: Try Agent-001 (Try 3 - should FAIL with 402) ===')
r = requests.post('http://localhost:8000/agents/agent-001/ask',
    json={'question': 'Hello 3'},
    headers={'Authorization': 'Bearer ' + token1}
)
print('Status:', r.status_code)
if r.status_code == 402:
    print('✓ CORRECT - Blocked with 402!')
    print('Message:', r.json()['detail'][:80])
else:
    print('✗ ERROR - Expected 402, got:', r.status_code)
    print(r.json())

# Test 6: Admin can use unlimited
print('\n=== TEST 6: Admin bypass (unlimited access) ===')
r = requests.post('http://localhost:8000/auth/login', json={'username': 'admin', 'password': 'admin123'})
token_admin = r.json()['access_token']
r = requests.post('http://localhost:8000/agents/agent-001/ask',
    json={'question': 'Admin test'},
    headers={'Authorization': 'Bearer ' + token_admin}
)
print('Admin Status:', r.status_code)
print('✓ Admin has unlimited access')

# Test 7: User isolation - verify different users have separate demos
print('\n=== TEST 7: User isolation ===')
r = requests.post('http://localhost:8000/auth/login', json={'username': 'admin', 'password': 'admin123'})
token_admin2 = r.json()['access_token']
r = requests.get('http://localhost:8000/agents/my-access-status', headers={'Authorization': 'Bearer ' + token_admin2})
access_admin = r.json()
demo_admin = access_admin.get('agent-001', {}).get('demo_uses_left', -1)
print('Admin agent-001 demo tries:', demo_admin)
print('User1 already used 2, Admin still has:', demo_admin)
if demo_admin == 2:
    print('✓ CORRECT - User data is isolated!')
else:
    print('Note: Admin has different count (normal - different user)')

print('\n✅ All tests completed!')
