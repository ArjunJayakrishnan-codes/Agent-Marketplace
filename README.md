# Agent Marketplace

Production-style full-stack marketplace for data agents with secure MCP tooling, agent purchases, access keys, and operational dashboards.

## Current Version

Version: 2.0.0  
Last updated: April 17, 2026

## What Is Implemented

1. Five Chinook-focused agents:
- Catalog Intelligence Agent
- Revenue Intelligence Agent
- Customer Lifecycle Agent
- Artist Performance Agent
- Operations Workforce Agent

2. Secure authentication and purchases:
- JWT login and registration
- Per-agent purchase records
- Access key generation for purchased ask endpoints

3. Agent-gated MCP model:
- MCP tools are provisioned through purchased agents
- Direct MCP purchase endpoint is disabled
- MCP execute path enforces entitlement from purchased agents

4. Working MCP tool execution:
- Filesystem, Git, Web, Database, API, and Code tool categories
- Input validation, rate limiting, readonly SQL restrictions, URL safety checks

5. Frontend marketplace dashboard:
- Agent listing and purchase flow
- MCP tools runner with per-server tool execution
- Logs view and A2A panel
- Updated branding and consistent UI styling

## MCP Servers And Active Tools

- mcp-001 Filesystem Tools:
  - list_directory
  - read_file
  - write_file

- mcp-002 Git Integration:
  - git_status
  - view_diff
  - recent_commits

- mcp-003 Web Search and Browsing:
  - search
  - fetch_url
  - get_page_content

- mcp-004 Database Query:
  - execute_query
  - list_tables
  - describe_table

- mcp-005 API Client:
  - set_headers
  - get_request
  - post_request

- mcp-006 Code Analysis:
  - parse_code
  - analyze_syntax
  - format_code

## Project Structure

```text
agent/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── Chinook.db
│   └── inspect_db.py
├── frontend/
│   ├── package.json
│   ├── public/
│   └── src/
├── diagnostic.html
├── examples.html
└── README.md
```

## Local Setup

### Backend

```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

API base URL:

```text
http://127.0.0.1:8000
```

### Frontend

```powershell
cd frontend
npm install
npm start
```

Frontend URL (default):

```text
http://localhost:3000
```

## Demo Credentials

| Username | Password |
| --- | --- |
| admin | admin123 |
| user1 | user123 |

## Core API Endpoints

### Auth
- POST /auth/login
- POST /auth/register

### Agents
- GET /agents
- GET /agents/{agent_id}
- POST /agents/{agent_id}/purchase
- GET /agents/{agent_id}/access-details
- GET /agents/{agent_id}/ask
- POST /agents/send-message
- GET /agents/{agent_id}/messages

### MCP
- GET /users/me/mcp-purchases
- GET /mcp-servers
- GET /mcp-servers/{server_id}
- POST /mcp-servers/{server_id}/execute

### Logs
- GET /logs
- GET /logs/events
- DELETE /logs

## MCP Execution Request Format

Supported request body for MCP execute:

```json
{
  "tool": "get_page_content",
  "arguments": {
    "url": "https://example.com",
    "max_chars": 2000
  }
}
```

Compatibility behavior:
- Top-level tool arguments are accepted for common fields.
- If a full execute envelope is pasted inside arguments, it is auto-unwrapped.

## Security Notes

1. Web/API MCP tools only allow public http/https targets.
2. Localhost, internal domains, private IPs, and non-standard ports are blocked.
3. Database MCP is readonly and allows SELECT-only queries.
4. MCP calls are rate-limited per user.
5. Sensitive files and workspace-protected paths are blocked for destructive operations.

## Troubleshooting

1. MCP returns purchase error:
- Purchase an agent that includes that MCP server.

2. MCP arguments error:
- Ensure arguments is valid JSON object.
- Use tool-specific fields shown in examples.

3. Search/web fetch error:
- Verify URL starts with http or https.
- Verify target host is publicly reachable.

4. Git tools unavailable:
- Ensure project is inside a valid git repository.

## License

MIT
