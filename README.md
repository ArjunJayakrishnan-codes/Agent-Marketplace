# Agent Marketplace

A complete agent marketplace system with 3 agents, Agent-to-Agent (A2A) communication, authentication, and real-time logging.

## Features

✅ **3 Intelligent Agents**
- Data Analyzer: Analyzes business metrics and trends
- Query Executive: Executes database queries and retrieval
- Report Generator: Generates comprehensive reports

✅ **Authentication System**
- JWT-based token authentication
- User registration and login
- Password hashing with bcrypt
- Role-based access control

✅ **Agent-to-Agent Communication (A2A)**
- Real-time message passing between agents
- Message queue and history tracking
- Full communication audit trail

✅ **Comprehensive Logging**
- Real-time event logging
- Multiple log levels (INFO, WARN, ERROR)
- Event filtering and viewing
- Log persistence and search

✅ **Beautiful Dashboard**
- Agent cards with capabilities
- A2A communication UI
- Live logs viewer with filtering
- Dark modern design with Tailwind CSS

## Project Structure

```
agent/
├── backend/
│   ├── main.py              # FastAPI backend server
│   ├── requirements.txt      # Python dependencies
│   └── marketplace.log       # Log file (generated)
├── frontend/
│   └── index.html           # Single-page application
└── README.md               # This file
```

## Installation & Setup

### 1. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Start the Backend Server

```bash
cd backend
python main.py
```

The API will be available at `http://localhost:8000`

### 3. Open Frontend

Open `frontend/index.html` in your web browser, or serve it using a simple HTTP server:

```bash
cd frontend
python -m http.server 8080
```

Then visit `http://localhost:8080`

## Demo Credentials

Login with these test accounts:

| Username | Password   | Role  |
|----------|-----------|-------|
| admin    | admin123  | Admin |
| user1    | user123   | User  |

## Security Features

✅ **Secure Access Credentials**
- JWT tokens and access keys are **NOT exposed in URLs**
- Credentials are only visible when you click "Access Details" button for owned agents
- Credentials are fetched via authenticated API calls (kept out of browser history)
- Each purchased agent gets a unique access key (UUID-based)
- Only authenticated users can view their own access details

## API Endpoints

### Authentication
- `POST /auth/login` - Login user
- `POST /auth/register` - Register new user

### Agents
- `GET /agents` - Get all agents
- `GET /agents/{agent_id}` - Get agent details
- `GET /agents/{agent_id}/access-details` - Get access URL and key for owned agent (requires purchase)
- `POST /agents/{agent_id}/purchase` - Purchase an agent
- `POST /agents/send-message` - Send A2A message
- `GET /agents/{agent_id}/messages` - Get agent messages
- `GET /agents/{agent_id}/ask` - Query an agent (supports both JWT and access key authentication)
- `GET /agents/communication/history` - Get communication history

### Logs
- `GET /logs` - Get system logs
- `GET /logs/events` - Get unique event types
- `DELETE /logs` - Clear all logs (admin only)

### Health
- `GET /health` - Health check
- `GET /` - API info

## Usage

### Login
1. Open the application
2. Enter credentials (admin/admin123 or user1/user123)
3. Click "Login" to authenticate

### View Agents
- Navigate to "Agent Cards" tab
- See all 3 available agents with their capabilities
- Each agent shows its purpose and capabilities

### Send A2A Messages
1. Go to "A2A Communication" tab
2. Select "From Agent" and "To Agent"
3. Enter a JSON payload (e.g., `{"action": "query", "data": "test"}`)
4. Click "Send Message"
5. View the response and communication history

### View System Logs
1. Navigate to "Logs Viewer" tab
2. Filter logs by event type
3. See real-time events including:
   - Authentication events
   - Agent communications
   - API access logs
   - System events

## Security Notes

⚠️ **Production Considerations:**
- Change `SECRET_KEY` in `main.py` to a secure random value
- Use environment variables for sensitive configuration
- Implement a real database (not in-memory)
- Add rate limiting and API key management
- Enable HTTPS/SSL for production
- Use proper user management system

## Architecture

```
┌─────────────────────────────────────────────────┐
│          Frontend (HTML/JS/Tailwind)            │
├─────────────────────────────────────────────────┤
│                   FastAPI Backend               │
│  ┌──────────────────────────────────────────┐   │
│  │          Authentication Layer             │   │
│  │  (JWT, Password Hashing, Permissions)    │   │
│  └──────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────┐   │
│  │      Agent Management System              │   │
│  │  (3 Agents with Capabilities)            │   │
│  └──────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────┐   │
│  │  A2A Communication Layer                  │   │
│  │  (Message Queue, History, Routing)       │   │
│  └──────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────┐   │
│  │        Logging System                     │   │
│  │  (Event Tracking, Audit Trail)           │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## Example: A2A Communication

From `Data Analyzer` to `Query Executive`:

```json
{
  "action": "fetch_metrics",
  "filters": {
    "date_range": "last_30_days",
    "category": "sales"
  },
  "format": "json"
}
```

This creates a log entry:
```
[2024-04-04 10:30:45] A2A_MESSAGE | {
  "message_id": "abc123...",
  "from": "agent-001",
  "to": "agent-002",
  "payload": {...}
}
```

## Troubleshooting

### CORS Errors
- Backend CORS is enabled for all origins (* format)
- Ensure backend is running on `http://localhost:8000`

### Authentication Failed
- Verify username and password match test credentials
- Check browser console for error details

### Logs Not Showing
- Ensure you're logged in with valid token
- Check backend logs at `backend/marketplace.log`

### A2A Messages Not Sending
- Verify agent IDs are correct (agent-001, agent-002, agent-003)
- Ensure JSON payload is valid
- Check that both agents exist

## Future Enhancements

- [ ] Database persistence (PostgreSQL/MongoDB)
- [ ] Advanced agent routing with ML
- [ ] Real-time WebSocket notifications
- [ ] Agent performance metrics
- [ ] Rate limiting and quotas
- [ ] Multi-tenant support
- [ ] Agent versioning and rollback
- [ ] Custom agent creation UI

## License

MIT License - Feel free to use and modify

---

**Created:** April 4, 2026  
**Version:** 1.0
