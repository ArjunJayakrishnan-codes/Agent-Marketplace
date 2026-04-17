import requests
import json

# Get a token first
register_resp = requests.post('http://localhost:8000/auth/register', json={'username': 'testuser5', 'password': 'pass123'})
token = register_resp.json().get('access_token')
headers = {'Authorization': f'Bearer {token}'}

queries = [
    ('agent-003', 'Music catalog report', 'Report Generator - Catalog Report'),
    ('agent-001', 'Catalog overview', 'Data Analyzer - Catalog Overview'),
    ('agent-001', 'What are the top genres?', 'Data Analyzer - Top Genres'),
    ('agent-001', 'Who are the top artists?', 'Data Analyzer - Top Artists'),
    ('agent-001', 'Top customers by spending?', 'Data Analyzer - Top Customers'),
    ('agent-003', 'Sales revenue report', 'Report Generator - Revenue Report'),
    ('agent-003', 'Employee staff report', 'Report Generator - Staff Report'),
    ('agent-002', 'How many rock tracks?', 'Query Executive - Rock Tracks'),
    ('agent-002', 'What genres are available?', 'Query Executive - All Genres'),
]

for agent_id, question, title in queries:
    print('\n' + '='*70)
    print(f'{title}')
    print('='*70)
    print(f'Query: "{question}"')
    print('-'*70)
    
    resp = requests.post(f'http://localhost:8000/agents/{agent_id}/ask', 
                         json={'question': question}, 
                         headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        print(data.get('response', str(data)))
    else:
        print(f"Error: {resp.status_code} - {resp.text[:200]}")
