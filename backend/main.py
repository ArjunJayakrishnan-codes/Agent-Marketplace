import time
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
from uuid import uuid4
import sqlite3
import subprocess
import os
import re
import ast
import html as html_lib
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, unquote
import ipaddress
import socket
import requests
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================
# 1. CONFIGURATION & SETUP
# ============================================

app = FastAPI(title="Agent Marketplace API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Groq LLM Setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None
    logging.getLogger(__name__).warning("GROQ_API_KEY not set. LLM responses are disabled.")

# Security Config
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password Hashing
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer()

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('marketplace.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global logs store
logs_store: List[Dict] = []
MAX_LOGS = 1000

# MCP security limits
MCP_MAX_ARGUMENT_CHARS = 20000
MCP_SQL_MAX_LENGTH = 4000
MCP_RATE_WINDOW_SECONDS = 60
MCP_RATE_MAX_CALLS = 30
MCP_ALLOWED_HOSTS = [h.strip().lower() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
MCP_ENABLE_PUBLIC_DISCOVERY = os.getenv("MCP_ENABLE_PUBLIC_DISCOVERY", "false").strip().lower() == "true"
MCP_MAX_SOURCE_CODE_CHARS = 50000
MCP_MAX_WRITE_CHARS = 20000
mcp_rate_limits: Dict[str, List[float]] = {}

# ============================================
# 2. DATABASE MODELS (In-Memory for MVP)
# ============================================

class Agent(BaseModel):
    id: str
    name: str
    description: str
    purpose: str
    status: str = "active"
    version: str = "1.0"
    capabilities: List[str]
    mcp_server_ids: List[str] = []  # Bundled MCP tools
    
class User(BaseModel):
    username: str
    email: str
    password: str = None

class UserInDB(User):
    hashed_password: str

# ============================================
# 3. AUTHENTICATION SYSTEM
# ============================================

# Sample users (in production, use a real database)
fake_users_db = {
    "admin": {
        "username": "admin",
        "email": "admin@marketplace.com",
        "hashed_password": pwd_context.hash("admin123"),
        "purchased_agents": {},
        "purchased_mcp_servers": {}  # {mcp_server_id: {purchase_date, license_key}}
    },
    "user1": {
        "username": "user1",
        "email": "user1@marketplace.com",
        "hashed_password": pwd_context.hash("user123"),
        "purchased_agents": {},
        "purchased_mcp_servers": {}  # {mcp_server_id: {purchase_date, license_key}}
    }
}

class Token(BaseModel):
    access_token: str
    token_type: str
    user: str

class LoginRequest(BaseModel):
    username: str
    password: str

class QuestionRequest(BaseModel):
    question: str


class MCPToolExecuteRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

    # Accept top-level tool arguments for compatibility with clients that don't nest under "arguments".
    query: Optional[str] = None
    limit: Optional[int] = None
    url: Optional[str] = None
    max_chars: Optional[int] = None
    html: Optional[str] = None
    path: Optional[str] = None
    table_name: Optional[str] = None
    params: Optional[Any] = None
    headers: Optional[Dict[str, Any]] = None
    body: Optional[Any] = None
    timeout: Optional[int] = None
    source_code: Optional[str] = None
    prompt: Optional[str] = None
    content: Optional[str] = None
    append: Optional[bool] = None
    staged: Optional[bool] = None

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials = Depends(security)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return verify_token(credentials.credentials)

async def get_current_user_or_access_key(credentials = Depends(security)) -> str:
    """Allow authentication via JWT token OR access key (UUID)"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = credentials.credentials
    
    # Try to verify as JWT first
    try:
        username = verify_token(token)
        return username
    except Exception as jwt_error:
        pass
    
    # Fall back to access key lookup
    try:
        for username, user_data in fake_users_db.items():
            purchases = user_data.get("purchased_agents", {})
            for agent_id, purchase_record in purchases.items():
                if purchase_record.get("access_key") == token:
                    # Mark that we're using access key auth for this request
                    # Return format: "username:access_key:agent_id"
                    return f"{username}:access_key:{agent_id}"
    except:
        pass
    
    raise HTTPException(status_code=401, detail="Invalid token or access key")

# ============================================
# 4. AGENT-TO-AGENT COMMUNICATION & STORAGE
# ============================================

agents_db: Dict[str, Agent] = {
    "agent-001": Agent(
        id="agent-001",
        name="Catalog Intelligence Agent",
        description="Analyzes Chinook catalog structure across genres, media types, and playlists",
        purpose="Provide inventory mix and catalog coverage insights",
        capabilities=["catalog-analysis", "genre-mix", "playlist-coverage", "media-distribution"],
        status="active",
        mcp_server_ids=["mcp-004", "mcp-006"]  # Database Query, Code Analysis
    ),
    "agent-002": Agent(
        id="agent-002",
        name="Revenue Intelligence Agent",
        description="Tracks Chinook revenue trends by month, geography, and customer value",
        purpose="Provide sales performance and monetization analytics",
        capabilities=["revenue-trends", "country-revenue", "aov-analysis", "customer-value"],
        status="active",
        mcp_server_ids=["mcp-004", "mcp-005"]  # Database Query, API Client
    ),
    "agent-003": Agent(
        id="agent-003",
        name="Customer Lifecycle Agent",
        description="Segments Chinook customers by activity, frequency, and retention patterns",
        purpose="Surface retention risk and engagement segment insights",
        capabilities=["retention-analysis", "lifecycle-segmentation", "churn-signals", "repeat-rate"],
        status="active",
        mcp_server_ids=["mcp-004", "mcp-003"]  # Database Query, Web Search & Browsing
    ),
    "agent-004": Agent(
        id="agent-004",
        name="Artist Performance Agent",
        description="Analyzes artist and album commercial performance from Chinook invoice data",
        purpose="Identify strongest artists, albums, and revenue-driving content",
        capabilities=["artist-ranking", "album-performance", "content-revenue", "catalog-prioritization"],
        status="active",
        mcp_server_ids=["mcp-004", "mcp-005"]  # Database Query, API Client
    ),
    "agent-005": Agent(
        id="agent-005",
        name="Operations Workforce Agent",
        description="Evaluates Chinook support structure, staffing hierarchy, and territory distribution",
        purpose="Provide operational and workforce intelligence for support teams",
        capabilities=["support-load", "employee-hierarchy", "territory-analysis", "ops-reporting"],
        status="active",
        mcp_server_ids=["mcp-004", "mcp-001", "mcp-002"]  # Database Query, Filesystem Tools, Git Integration
    )
}

class AgentMessage(BaseModel):
    message_id: str = None
    from_agent: str
    to_agent: str
    payload: Dict
    timestamp: str = None

class MCPServer(BaseModel):
    id: str
    name: str
    description: str
    category: str
    tools: List[str]
    status: str = "active"
    price: float = 0.0

# MCP Servers Database
mcp_servers_db: Dict[str, MCPServer] = {
    "mcp-001": MCPServer(
        id="mcp-001",
        name="Filesystem Tools",
        description="Read, write, and manage files on the system",
        category="file-operations",
        tools=["list_directory", "read_file", "write_file"],
        status="active",
        price=0.0
    ),
    "mcp-002": MCPServer(
        id="mcp-002",
        name="Git Integration",
        description="Secure read-only Git inspection tools for repository visibility",
        category="version-control",
        tools=["git_status", "view_diff", "recent_commits"],
        status="active",
        price=0.0
    ),
    "mcp-003": MCPServer(
        id="mcp-003",
        name="Web Search & Browsing",
        description="Search the web and fetch website content",
        category="web-tools",
        tools=["search", "fetch_url", "get_page_content"],
        status="active",
        price=0.0
    ),
    "mcp-004": MCPServer(
        id="mcp-004",
        name="Database Query",
        description="Read-only SQL and schema inspection for Chinook database",
        category="database",
        tools=["execute_query", "list_tables", "describe_table"],
        status="active",
        price=0.0
    ),
    "mcp-005": MCPServer(
        id="mcp-005",
        name="API Client",
        description="Make HTTP requests to external APIs with authentication support",
        category="api-integration",
        tools=["set_headers", "get_request", "post_request"],
        status="active",
        price=0.0
    ),
    "mcp-006": MCPServer(
        id="mcp-006",
        name="Code Analysis",
        description="Analyze, parse, and generate code snippets",
        category="code-tools",
        tools=["parse_code", "analyze_syntax", "format_code"],
        status="active",
        price=0.0
    )
}

workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
mcp_api_headers: Dict[str, Dict[str, str]] = {}


def get_chinook_db_path() -> Optional[str]:
    candidates = [
        os.path.join(os.path.dirname(__file__), "Chinook.db"),
        os.path.join(os.getcwd(), "backend", "Chinook.db"),
        "Chinook.db"
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def resolve_safe_path(path_value: str) -> str:
    if not path_value:
        raise HTTPException(status_code=400, detail="Path is required")
    target = path_value if os.path.isabs(path_value) else os.path.join(workspace_root, path_value)
    target = os.path.abspath(target)
    if os.path.commonpath([workspace_root, target]) != workspace_root:
        raise HTTPException(status_code=403, detail="Path is outside allowed workspace")
    return target


def is_protected_workspace_path(target: str) -> bool:
    rel = os.path.relpath(target, workspace_root).replace("\\", "/")
    protected_prefixes = (".git/", ".venv/", "frontend/node_modules/")
    protected_exact = {"backend/main.py"}
    return rel in protected_exact or any(rel.startswith(prefix) for prefix in protected_prefixes)


def run_git_command(args: List[str], timeout: int = 8) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "Git command failed").strip()
        raise HTTPException(status_code=400, detail=stderr[:300])
    return (proc.stdout or "").strip()


def run_internal_sql(query: str, params: Optional[List[Any]] = None, max_rows: int = 200) -> Dict[str, Any]:
    db_path = get_chinook_db_path()
    if not db_path:
        raise HTTPException(status_code=500, detail="Chinook.db not found")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA query_only = ON;")
        cur.execute(query, params or [])
        rows = cur.fetchmany(max_rows)
        columns = list(rows[0].keys()) if rows else [d[0] for d in (cur.description or [])]
        return {
            "columns": columns,
            "rows": [dict(r) for r in rows],
            "row_count": len(rows)
        }
    finally:
        conn.close()


def run_readonly_sql(query: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="SQL query is required")

    query_clean = query.strip()
    if len(query_clean) > MCP_SQL_MAX_LENGTH:
        raise HTTPException(status_code=400, detail="SQL query is too long")

    stripped_no_trailing = query_clean.rstrip().rstrip(";").strip()
    if ";" in stripped_no_trailing:
        raise HTTPException(status_code=400, detail="Multiple SQL statements are not allowed")

    lowered = query_clean.lower()
    blocked_keywords = [
        "pragma", "attach", "detach", "drop", "alter", "insert", "update",
        "delete", "replace", "create", "vacuum", "reindex", "analyze"
    ]
    for kw in blocked_keywords:
        if re.search(rf"\\b{kw}\\b", lowered):
            raise HTTPException(status_code=400, detail=f"SQL keyword '{kw}' is not allowed")

    if not query_clean.lower().startswith("select"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")

    db_path = get_chinook_db_path()
    if not db_path:
        raise HTTPException(status_code=500, detail="Chinook.db not found")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA query_only = ON;")
        cur.execute(query_clean, params or [])
        rows = cur.fetchmany(200)
        columns = list(rows[0].keys()) if rows else [d[0] for d in (cur.description or [])]
        result_rows = [dict(r) for r in rows]
        return {
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows)
        }
    finally:
        conn.close()


def enforce_mcp_rate_limit(username: str) -> None:
    now = time.time()
    recent = [t for t in mcp_rate_limits.get(username, []) if now - t <= MCP_RATE_WINDOW_SECONDS]
    if len(recent) >= MCP_RATE_MAX_CALLS:
        raise HTTPException(status_code=429, detail="MCP rate limit exceeded. Please retry shortly.")
    recent.append(now)
    mcp_rate_limits[username] = recent


def validate_mcp_arguments(arguments: Dict[str, Any]) -> None:
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="Tool arguments must be a JSON object")
    arg_size = len(json.dumps(arguments, ensure_ascii=True))
    if arg_size > MCP_MAX_ARGUMENT_CHARS:
        raise HTTPException(status_code=400, detail="Tool arguments are too large")


def is_admin_user(username: str) -> bool:
    return username == "admin"

def ensure_user_mcp_entitlements(username: str) -> List[str]:
    """Backfill MCP entitlements from purchased agents.

    This keeps existing users in sync when agent MCP bundles change over time.
    Returns newly provisioned MCP server IDs.
    """
    user = fake_users_db.get(username)
    if user is None:
        return []

    purchased_agents = user.get("purchased_agents", {})
    user_mcp = user.setdefault("purchased_mcp_servers", {})
    provisioned: List[str] = []

    for agent_id, purchase_rec in purchased_agents.items():
        agent = agents_db.get(agent_id)
        if not agent:
            continue
        purchased_at = purchase_rec.get("purchased_at") or datetime.now(timezone.utc).isoformat()
        for server_id in agent.mcp_server_ids:
            if server_id in mcp_servers_db and server_id not in user_mcp:
                user_mcp[server_id] = {
                    "license_key": str(uuid4()),
                    "purchased_at": purchased_at,
                    "source": "bundled-with-agent",
                    "agent_id": agent_id
                }
                provisioned.append(server_id)

    return provisioned


def get_user_agent_entitled_mcp_ids(username: str) -> set:
    """Return MCP server IDs unlocked through purchased agents only."""
    user = fake_users_db.get(username)
    if user is None:
        return set()

    entitled_ids = set()
    for agent_id in user.get("purchased_agents", {}).keys():
        agent = agents_db.get(agent_id)
        if not agent:
            continue
        for server_id in agent.mcp_server_ids:
            if server_id in mcp_servers_db:
                entitled_ids.add(server_id)
    return entitled_ids


def assert_safe_external_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Credentials in URL are not allowed")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=400, detail="URL host is required")
    if host == "localhost":
        raise HTTPException(status_code=400, detail="Localhost/private addresses are not allowed")
    if host.endswith(".local") or host.endswith(".internal"):
        raise HTTPException(status_code=400, detail="Local/internal domains are not allowed")

    port = parsed.port
    if port and port not in {80, 443}:
        raise HTTPException(status_code=400, detail="Only standard ports 80/443 are allowed")

    if MCP_ALLOWED_HOSTS:
        allowed = any(host == h or host.endswith(f".{h}") for h in MCP_ALLOWED_HOSTS)
        if not allowed:
            raise HTTPException(status_code=400, detail="Host is not in MCP_ALLOWED_HOSTS")

    try:
        addr_info = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Unable to resolve target host")

    for entry in addr_info:
        ip_value = entry[4][0]
        ip = ipaddress.ip_address(ip_value)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise HTTPException(status_code=400, detail="Target resolves to a non-public IP")


def normalize_url_input(url_value: Any) -> str:
    """Normalize URL values copied from JSON editors (quotes/newlines)."""
    if url_value is None:
        return ""
    candidate = str(url_value).strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {'"', "'", "`"}:
        candidate = candidate[1:-1].strip()
    return candidate


def execute_mcp_tool(server_id: str, tool: str, arguments: Dict[str, Any], username: str) -> Dict[str, Any]:
    if server_id not in mcp_servers_db:
        raise HTTPException(status_code=404, detail="MCP server not found")

    server = mcp_servers_db[server_id]
    if tool not in server.tools:
        raise HTTPException(status_code=400, detail=f"Tool '{tool}' is not available in {server.name}")

    if server_id == "mcp-001":
        if tool == "list_directory":
            path_value = arguments.get("path", ".")
            target = resolve_safe_path(path_value)
            if not os.path.isdir(target):
                raise HTTPException(status_code=400, detail="Target path is not a directory")
            entries = []
            for name in os.listdir(target):
                full = os.path.join(target, name)
                entries.append({
                    "name": name,
                    "is_dir": os.path.isdir(full),
                    "size": os.path.getsize(full) if os.path.isfile(full) else None
                })
            return {"path": target, "entries": entries}

        if tool == "read_file":
            path_value = arguments.get("path")
            max_chars = int(arguments.get("max_chars", 6000))
            if max_chars <= 0:
                raise HTTPException(status_code=400, detail="max_chars must be positive")
            max_chars = min(max_chars, 20000)
            target = resolve_safe_path(path_value)
            if not os.path.isfile(target):
                raise HTTPException(status_code=400, detail="Target path is not a file")
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars)
            return {"path": target, "content": content, "truncated": os.path.getsize(target) > max_chars}

        if tool == "write_file":
            path_value = arguments.get("path")
            content = arguments.get("content", "")
            append_mode = bool(arguments.get("append", False))
            if not isinstance(content, str):
                raise HTTPException(status_code=400, detail="'content' must be a string")
            if len(content) > MCP_MAX_WRITE_CHARS:
                raise HTTPException(status_code=400, detail="Content is too large")
            target = resolve_safe_path(path_value)
            if is_protected_workspace_path(target):
                raise HTTPException(status_code=403, detail="Writing to protected paths is not allowed")
            parent = os.path.dirname(target)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            mode = "a" if append_mode else "w"
            with open(target, mode, encoding="utf-8") as f:
                f.write(content)
            return {"path": target, "bytes_written": len(content), "append": append_mode}

        if tool == "move_file":
            source_path = arguments.get("source_path")
            target_path = arguments.get("target_path")
            allow_overwrite = bool(arguments.get("allow_overwrite", False))
            src = resolve_safe_path(source_path)
            dst = resolve_safe_path(target_path)
            if not os.path.isfile(src):
                raise HTTPException(status_code=400, detail="source_path must be an existing file")
            if is_protected_workspace_path(src) or is_protected_workspace_path(dst):
                raise HTTPException(status_code=403, detail="Moving protected paths is not allowed")
            if os.path.exists(dst) and not allow_overwrite:
                raise HTTPException(status_code=400, detail="target_path already exists")
            dst_parent = os.path.dirname(dst)
            if dst_parent and not os.path.exists(dst_parent):
                os.makedirs(dst_parent, exist_ok=True)
            os.replace(src, dst)
            return {"source_path": src, "target_path": dst, "moved": True}

        if tool == "delete_file":
            path_value = arguments.get("path")
            target = resolve_safe_path(path_value)
            if not os.path.isfile(target):
                raise HTTPException(status_code=400, detail="path must be an existing file")
            if is_protected_workspace_path(target):
                raise HTTPException(status_code=403, detail="Deleting protected paths is not allowed")
            os.remove(target)
            return {"path": target, "deleted": True}

        raise HTTPException(status_code=400, detail=f"Tool '{tool}' is disabled for safety in this deployment")

    if server_id == "mcp-003":
        if tool == "search":
            query = (arguments.get("query") or "").strip()
            if not query:
                raise HTTPException(status_code=400, detail="'query' is required")
            limit = min(int(arguments.get("limit", 5)), 10)
            links: List[str] = []

            # Primary source: Bing RSS is stable for server-side usage and easy to parse.
            try:
                bing_resp = requests.get(
                    "https://www.bing.com/search",
                    params={
                        "format": "rss",
                        "mkt": "en-US",
                        "setLang": "en-US",
                        "q": query,
                    },
                    timeout=12,
                    allow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if bing_resp.status_code == 200:
                    root = ET.fromstring(bing_resp.text)
                    for item in root.findall(".//item"):
                        link = (item.findtext("link") or "").strip()
                        if link.startswith("http://") or link.startswith("https://"):
                            links.append(link)
            except Exception:
                # Continue with fallback sources below.
                pass

            # Fallback source: DuckDuckGo HTML parsing.
            if not links:
                resp = requests.get(
                    f"https://duckduckgo.com/html/?q={quote_plus(query)}",
                    timeout=12,
                    allow_redirects=True,
                    headers={"User-Agent": "AgentMarketplace/1.0"}
                )
                href_values = re.findall(r'href="([^"]+)"', resp.text)

                for href in href_values:
                    candidate = html_lib.unescape(href.strip())
                    if not candidate:
                        continue

                    # Scheme-relative URLs from DuckDuckGo HTML: //duckduckgo.com/l/?uddg=...
                    if candidate.startswith("//"):
                        candidate = f"https:{candidate}"

                    # Direct absolute links.
                    if candidate.startswith("http://") or candidate.startswith("https://"):
                        parsed_candidate = urlparse(candidate)
                        if parsed_candidate.netloc.endswith("duckduckgo.com") and parsed_candidate.path.startswith("/l/"):
                            query_params = parse_qs(parsed_candidate.query)
                            uddg_values = query_params.get("uddg") or []
                            if uddg_values:
                                decoded = unquote(uddg_values[0]).strip()
                                if decoded.startswith("http://") or decoded.startswith("https://"):
                                    links.append(decoded)
                            continue

                        if parsed_candidate.netloc.endswith("duckduckgo.com"):
                            continue

                        links.append(candidate)
                        continue

                    # DuckDuckGo redirect format: /l/?uddg=<encoded_url>
                    if candidate.startswith("/l/"):
                        parsed_redirect = urlparse(candidate)
                        query_params = parse_qs(parsed_redirect.query)
                        uddg_values = query_params.get("uddg") or []
                        if uddg_values:
                            decoded = unquote(uddg_values[0]).strip()
                            if decoded.startswith("http://") or decoded.startswith("https://"):
                                links.append(decoded)

            deduped = []
            seen = set()
            for link in links:
                if link not in seen:
                    deduped.append(link)
                    seen.add(link)
                if len(deduped) >= limit:
                    break

            if not deduped:
                wiki_resp = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "format": "json",
                        "srlimit": limit,
                    },
                    timeout=12,
                    headers={"User-Agent": "AgentMarketplace/1.0 (contact: local)"},
                )
                if wiki_resp.status_code == 200:
                    wiki_json = wiki_resp.json()
                    search_items = (wiki_json.get("query") or {}).get("search") or []
                    for item in search_items:
                        title = (item.get("title") or "").strip()
                        if not title:
                            continue
                        wiki_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        if wiki_url not in seen:
                            deduped.append(wiki_url)
                            seen.add(wiki_url)
                        if len(deduped) >= limit:
                            break

            return {"query": query, "results": deduped}

        if tool in {"fetch_url", "get_page_content"}:
            url = normalize_url_input(arguments.get("url"))
            assert_safe_external_url(url)
            resp = requests.get(url, timeout=12, allow_redirects=False, headers={"User-Agent": "AgentMarketplace/1.0"})
            title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else None
            if tool == "fetch_url":
                return {"status_code": resp.status_code, "url": resp.url, "title": title}
            max_chars = min(int(arguments.get("max_chars", 6000)), 20000)
            return {
                "status_code": resp.status_code,
                "url": resp.url,
                "title": title,
                "content": resp.text[:max_chars],
                "truncated": len(resp.text) > max_chars
            }

        if tool == "extract_links":
            base_url = normalize_url_input(arguments.get("url"))
            html = arguments.get("html")
            if not html:
                assert_safe_external_url(base_url)
                html = requests.get(base_url, timeout=12, allow_redirects=False, headers={"User-Agent": "AgentMarketplace/1.0"}).text
            elif len(str(html)) > 200000:
                raise HTTPException(status_code=400, detail="Provided html is too large")
            links = re.findall(r'href=["\']([^"\']+)["\']', html)
            normalized = []
            for link in links[:200]:
                normalized.append(urljoin(base_url, link) if base_url else link)
            return {"links": normalized[:50], "count": len(normalized[:50])}

    if server_id == "mcp-004":
        if tool in {"execute_query", "fetch_data"}:
            query = arguments.get("query")
            params = arguments.get("params", [])
            if params is not None and not isinstance(params, list):
                raise HTTPException(status_code=400, detail="'params' must be an array")
            return run_readonly_sql(query, params)

        if tool == "list_tables":
            return run_internal_sql(
                "SELECT name AS table_name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )

        if tool == "describe_table":
            table_name = (arguments.get("table_name") or "").strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
                raise HTTPException(status_code=400, detail="Invalid table_name")
            return run_internal_sql(
                "SELECT name, type, [notnull] AS not_null, dflt_value AS default_value, pk FROM pragma_table_info(?)",
                [table_name]
            )

        raise HTTPException(status_code=400, detail=f"Tool '{tool}' is disabled (database server is read-only)")

    if server_id == "mcp-005":
        if tool == "set_headers":
            headers = arguments.get("headers", {})
            if not isinstance(headers, dict):
                raise HTTPException(status_code=400, detail="'headers' must be an object")
            if len(headers) > 20:
                raise HTTPException(status_code=400, detail="Too many headers")
            blocked = {
                "host", "content-length", "connection", "proxy-authorization",
                "proxy-authenticate", "te", "trailer", "transfer-encoding", "upgrade"
            }
            sanitized_headers: Dict[str, str] = {}
            for key, value in headers.items():
                k = str(key).strip()
                v = str(value).strip()
                if not k or len(k) > 100 or len(v) > 1000:
                    raise HTTPException(status_code=400, detail="Invalid header key/value length")
                if k.lower() in blocked:
                    raise HTTPException(status_code=400, detail=f"Header '{k}' is not allowed")
                sanitized_headers[k] = v
            mcp_api_headers[username] = sanitized_headers
            return {"headers": mcp_api_headers[username], "message": "Headers stored"}

        method_map = {
            "get_request": "GET",
            "post_request": "POST",
            "put_request": "PUT",
            "delete_request": "DELETE"
        }
        if tool in method_map:
            url = normalize_url_input(arguments.get("url"))
            assert_safe_external_url(url)
            timeout = min(max(int(arguments.get("timeout", 12)), 1), 15)
            params = arguments.get("params")
            body = arguments.get("body")
            if params is not None and not isinstance(params, dict):
                raise HTTPException(status_code=400, detail="'params' must be an object")
            resp = requests.request(
                method_map[tool],
                url,
                headers=mcp_api_headers.get(username, {}),
                params=params,
                json=body,
                timeout=timeout,
                allow_redirects=False
            )
            try:
                payload = resp.json()
            except Exception:
                payload = resp.text[:6000]
            return {
                "status_code": resp.status_code,
                "url": resp.url,
                "content_type": resp.headers.get("Content-Type"),
                "body": payload
            }

    if server_id == "mcp-006":
        source_code = arguments.get("source_code", "")
        if not isinstance(source_code, str):
            raise HTTPException(status_code=400, detail="'source_code' must be a string")
        if len(source_code) > MCP_MAX_SOURCE_CODE_CHARS:
            raise HTTPException(status_code=400, detail="'source_code' is too large")
        if tool == "parse_code":
            tree = ast.parse(source_code)
            return {"ast": ast.dump(tree, indent=2)}

        if tool in {"analyze_syntax", "lint_code"}:
            try:
                ast.parse(source_code)
                return {"valid": True, "errors": []}
            except SyntaxError as e:
                return {
                    "valid": False,
                    "errors": [{"line": e.lineno, "column": e.offset, "message": e.msg}]
                }

        if tool == "format_code":
            lines = source_code.splitlines()
            formatted = "\n".join([line.rstrip() for line in lines]).strip()
            return {"formatted_code": formatted + ("\n" if formatted else "")}

        if tool == "generate_code":
            prompt = (arguments.get("prompt") or "").strip()
            if not prompt:
                raise HTTPException(status_code=400, detail="'prompt' is required")
            if not groq_client:
                return {"generated_code": "# Code generation unavailable: configure GROQ_API_KEY"}
            generated = get_groq_response(
                "Code Generator",
                "Generate concise Python code from a prompt",
                prompt
            )
            return {"generated_code": generated}

    if server_id == "mcp-002":
        try:
            run_git_command(["rev-parse", "--is-inside-work-tree"])
        except HTTPException as e:
            if "not a git repository" in str(e.detail).lower():
                return {
                    "message": "Git tools are unavailable because this workspace is not a git repository.",
                    "repository_available": False
                }
            raise

        if tool == "git_status":
            branch = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
            status_text = run_git_command(["status", "--short", "--branch"])
            return {"branch": branch, "status": status_text.splitlines() if status_text else []}

        if tool == "view_diff":
            staged = bool(arguments.get("staged", False))
            path_filter = (arguments.get("path") or "").strip()
            cmd = ["diff", "--no-color"]
            if staged:
                cmd.append("--staged")
            if path_filter:
                safe_path = resolve_safe_path(path_filter)
                rel_path = os.path.relpath(safe_path, workspace_root).replace("\\", "/")
                cmd.extend(["--", rel_path])
            diff_text = run_git_command(cmd, timeout=12)
            max_chars = min(int(arguments.get("max_chars", 12000)), 20000)
            return {
                "staged": staged,
                "path": path_filter or None,
                "diff": diff_text[:max_chars],
                "truncated": len(diff_text) > max_chars
            }

        if tool == "list_branches":
            branches = run_git_command(["for-each-ref", "--format=%(refname:short)", "refs/heads"])
            return {"branches": [b for b in branches.splitlines() if b]}

        if tool == "recent_commits":
            limit = min(max(int(arguments.get("limit", 10)), 1), 20)
            output = run_git_command([
                "log", f"-n{limit}", "--date=short", "--pretty=format:%h|%an|%ad|%s"
            ])
            commits = []
            for line in output.splitlines():
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "subject": parts[3]
                    })
            return {"limit": limit, "commits": commits}

        raise HTTPException(status_code=400, detail=f"Tool '{tool}' is not supported for Git Integration")

    raise HTTPException(status_code=400, detail="Unsupported MCP tool request")

class A2ACommunication:
    """Agent-to-Agent Communication Handler"""
    
    def __init__(self):
        self.message_queue: List[AgentMessage] = []
        self.message_history: List[Dict] = []
    
    def send_message(self, from_agent: str, to_agent: str, payload: Dict) -> Dict:
        """Send message from one agent to another"""
        message_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        message = AgentMessage(
            message_id=message_id,
            from_agent=from_agent,
            to_agent=to_agent,
            payload=payload,
            timestamp=timestamp
        )
        
        self.message_queue.append(message)
        self.message_history.append(message.dict())
        
        log_event(f"A2A_MESSAGE", {
            "message_id": message_id,
            "from": from_agent,
            "to": to_agent,
            "payload": payload
        })
        
        return {
            "status": "delivered",
            "message_id": message_id,
            "timestamp": timestamp
        }
    
    def get_messages(self, agent_id: str) -> List[Dict]:
        """Get messages for a specific agent"""
        return [
            msg.dict() for msg in self.message_queue 
            if msg.to_agent == agent_id
        ]
    
    def get_history(self, limit: int = 100) -> List[Dict]:
        """Get message history"""
        return self.message_history[-limit:]

a2a_comm = A2ACommunication()

# ============================================
# 5. LOGGING SYSTEM
# ============================================

class LogEntry(BaseModel):
    timestamp: str
    level: str
    event_type: str
    user: Optional[str] = None
    details: Dict

def log_event(event_type: str, details: Dict, level: str = "INFO", user: str = None):
    """Log an event to both file and in-memory store"""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event_type": event_type,
        "user": user,
        "details": details
    }
    
    logs_store.append(log_entry)
    if len(logs_store) > MAX_LOGS:
        logs_store.pop(0)
    
    logger.info(f"{event_type} | {json.dumps(details)}")

def get_groq_response(agent_name: str, agent_purpose: str, user_question: str, agent_context: str = "") -> str:
    """Generate response using Groq LLM"""
    if not groq_client:
        return f"[{agent_name}] LLM integration is currently unavailable. Configure GROQ_API_KEY to enable generated responses."
    
    try:
        system_prompt = f"""You are {agent_name}, an AI agent in an Agent Marketplace system.
Your purpose: {agent_purpose}

You should provide clear, concise, and helpful responses to user questions within your domain of expertise.
Keep responses focused and actionable."""
        
        user_prompt = f"{agent_context}\n\nUser Question: {user_question}" if agent_context else f"User Question: {user_question}"
        
        message = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-8b-instant",
            max_tokens=500,
            temperature=0.7
        )
        
        return message.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API error: {str(e)}")
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg or "invalid" in error_msg.lower():
            return f"[{agent_name}] Invalid API Key: Please set a valid GROQ_API_KEY environment variable."
        return f"{agent_name} Error: Unable to generate response. Please try again later."

# ============================================
# 6. API ENDPOINTS
# ============================================

# AUTH ENDPOINTS
@app.post("/auth/login", response_model=Token)
async def login(login_request: LoginRequest):
    """Authenticate user and return JWT token"""
    user = fake_users_db.get(login_request.username)
    if not user or not verify_password(login_request.password, user["hashed_password"]):
        log_event("AUTH_FAILED", {"username": login_request.username}, level="WARN")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": login_request.username})
    
    log_event("AUTH_SUCCESS", {"username": login_request.username}, user=login_request.username)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": login_request.username
    }

@app.post("/auth/register", response_model=Token)
async def register(user: LoginRequest):
    """Register a new user"""
    if user.username in fake_users_db:
        log_event("REGISTER_FAILED", {"username": user.username, "reason": "User exists"}, level="WARN")
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_password = get_password_hash(user.password)
    fake_users_db[user.username] = {
        "username": user.username,
        "email": f"{user.username}@marketplace.com",
        "hashed_password": hashed_password,
        "purchased_agents": {}
    }
    
    access_token = create_access_token(data={"sub": user.username})
    
    log_event("USER_REGISTERED", {"username": user.username}, user=user.username)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user.username
    }


# PURCHASE ENDPOINTS
@app.post("/agents/{agent_id}/purchase")
async def purchase_agent(
    agent_id: str, 
    request: Request,
    current_user: str = Depends(get_current_user)
):
    """Simulate purchasing an agent. Grants the user access to the agent's endpoint."""
    if agent_id not in agents_db:
        log_event("AGENT_NOT_FOUND", {"agent_id": agent_id}, level="WARN", user=current_user)
        raise HTTPException(status_code=404, detail="Agent not found")

    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # Create a simple access record with an access key
    access_key = str(uuid4())
    purchased_at = datetime.now(timezone.utc).isoformat()
    purchase_record = {
        "access_key": access_key,
        "purchased_at": purchased_at
    }

    user.setdefault("purchased_agents", {})[agent_id] = purchase_record

    # Auto-provision MCP server access required by this agent.
    provisioned_mcp_ids = []
    user_mcp_purchases = user.setdefault("purchased_mcp_servers", {})
    for server_id in agents_db[agent_id].mcp_server_ids:
        if server_id in mcp_servers_db and server_id not in user_mcp_purchases:
            user_mcp_purchases[server_id] = {
                "license_key": str(uuid4()),
                "purchased_at": purchased_at,
                "source": "bundled-with-agent",
                "agent_id": agent_id
            }
            provisioned_mcp_ids.append(server_id)

    log_event("AGENT_PURCHASED", {"agent_id": agent_id, "user": current_user}, user=current_user)

    # Build full URL based on request
    agent_endpoint_path = f"/agents/{agent_id}/ask"
    # Get base URL from request
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    full_url = f"{base_url}{agent_endpoint_path}"

    return {
        "message": "Purchase successful",
        "agent_id": agent_id,
        "agent_name": agents_db[agent_id].name,
        "agent_endpoint": agent_endpoint_path,
        "url": full_url,
        "access_key": access_key,
        "access_token": access_key,
        "purchased_at": purchase_record["purchased_at"],
        "provisioned_mcp_servers": provisioned_mcp_ids,
        "usage_instructions": {
            "method": "POST",
            "url": full_url,
            "headers": {
                "Authorization": f"Bearer {access_key}",
                "Content-Type": "application/json"
            },
            "body": {
                "question": "Your question here"
            },
            "example_curl": f"curl -X POST {full_url} -H 'Authorization: Bearer {access_key}' -H 'Content-Type: application/json' -d '{{\"question\":\"How many jazz tracks?\"}}'",
            "example_javascript": f"fetch('{full_url}', {{ method: 'POST', headers: {{ 'Authorization': 'Bearer {access_key}', 'Content-Type': 'application/json' }}, body: JSON.stringify({{ question: 'Your question here' }}) }}).then(r => r.json()).then(d => console.log(d))"
        }
    }


@app.get("/users/me/purchases")
async def get_my_purchases(request: Request, current_user: str = Depends(get_current_user)):
    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    purchases = user.get("purchased_agents", {})
    # Enrich with agent name and endpoint
    result = {}
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    
    for aid, rec in purchases.items():
        agent = agents_db.get(aid)
        full_endpoint = f"{base_url}/agents/{aid}/ask"
        access_key = rec.get("access_key")
        result[aid] = {
            "agent_name": agent.name if agent else aid,
            "agent_endpoint": f"/agents/{aid}/ask",
            "url": full_endpoint,
            "access_key": access_key,
            "access_token": access_key,
            "purchased_at": rec.get("purchased_at"),
            "usage_instructions": {
                "method": "POST",
                "url": full_endpoint,
                "headers": {
                    "Authorization": f"Bearer {access_key}",
                    "Content-Type": "application/json"
                },
                "body": {
                    "question": "Your question here"
                },
                "example_curl": f"curl -X POST {repr(full_endpoint)} -H 'Authorization: Bearer {access_key}' -H 'Content-Type: application/json' -d '{{\"question\":\"How many jazz tracks?\"}}'",
                "example_javascript": "fetch(API_URL, { method: 'POST', headers: { 'Authorization': 'Bearer TOKEN', 'Content-Type': 'application/json' }, body: JSON.stringify({ question: 'Your question here' }) }).then(r => r.json()).then(d => console.log(d))"
            }
        }

    return {"user": current_user, "purchases": result}

# USER AGENT ACCESS STATUS
@app.get("/agents/my-access-status")
async def get_my_agent_access(current_user: str = Depends(get_current_user)):
    """Get access status for all agents."""
    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    ensure_user_mcp_entitlements(current_user)
    
    access_status = {}
    user_purchases = user.get("purchased_agents", {})
    
    for agent_id, agent in agents_db.items():
        is_purchased = agent_id in user_purchases
        
        access_status[agent_id] = {
            "agent_name": agent.name,
            "is_purchased": is_purchased,
            "can_use": is_purchased or current_user == "admin"
        }
    
    return access_status

# AGENT MARKETPLACE ENDPOINTS
@app.get("/agents", response_model=List[Agent])
async def get_agents(current_user: str = Depends(get_current_user)):
    """Get list of all available agents"""
    log_event("AGENTS_FETCHED", {"count": len(agents_db)}, user=current_user)
    return list(agents_db.values())

@app.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str, current_user: str = Depends(get_current_user)):
    """Get details of a specific agent"""
    if agent_id not in agents_db:
        log_event("AGENT_NOT_FOUND", {"agent_id": agent_id}, level="WARN", user=current_user)
        raise HTTPException(status_code=404, detail="Agent not found")
    
    log_event("AGENT_DETAILS_FETCHED", {"agent_id": agent_id}, user=current_user)
    return agents_db[agent_id]

# MCP SERVERS MARKETPLACE ENDPOINTS
@app.get("/mcp-servers", response_model=List[MCPServer])
async def get_mcp_servers(current_user: str = Depends(get_current_user)):
    """Get MCP servers visible to the current user.

    Public MCP discovery is disabled by default for security. Non-admin users only see
    servers they already have installed.
    """
    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    ensure_user_mcp_entitlements(current_user)

    entitled_ids = get_user_agent_entitled_mcp_ids(current_user)
    visible = [mcp_servers_db[sid] for sid in entitled_ids if sid in mcp_servers_db]

    log_event("MCP_SERVERS_FETCHED", {"count": len(visible)}, user=current_user)
    return visible

@app.get("/mcp-servers/{server_id}", response_model=MCPServer)
async def get_mcp_server(server_id: str, current_user: str = Depends(get_current_user)):
    """Get details of a specific MCP server"""
    if server_id not in mcp_servers_db:
        log_event("MCP_SERVER_NOT_FOUND", {"server_id": server_id}, level="WARN", user=current_user)
        raise HTTPException(status_code=404, detail="MCP server not found")

    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    ensure_user_mcp_entitlements(current_user)

    entitled_ids = get_user_agent_entitled_mcp_ids(current_user)
    if server_id not in entitled_ids:
        # Use 404 to avoid disclosing MCP inventory.
        raise HTTPException(status_code=404, detail="MCP server not found")
    
    log_event("MCP_SERVER_DETAILS_FETCHED", {"server_id": server_id}, user=current_user)
    return mcp_servers_db[server_id]

@app.post("/mcp-servers/{server_id}/purchase")
async def purchase_mcp_server(
    server_id: str,
    request: Request,
    current_user: str = Depends(get_current_user)
):
    """Direct MCP purchase is intentionally disabled; MCP tools come only via agent purchase."""
    raise HTTPException(
        status_code=403,
        detail="Direct MCP installation is disabled. Purchase an agent to get required MCP tools."
    )


@app.post("/mcp-servers/{server_id}/execute")
async def execute_mcp_server_tool(
    server_id: str,
    request: MCPToolExecuteRequest,
    current_user: str = Depends(get_current_user)
):
    """Execute a real MCP tool call for an installed server."""
    if server_id not in mcp_servers_db:
        log_event("MCP_SERVER_NOT_FOUND", {"server_id": server_id}, level="WARN", user=current_user)
        raise HTTPException(status_code=404, detail="MCP server not found")

    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    server = mcp_servers_db[server_id]
    if server.status != "active":
        raise HTTPException(status_code=403, detail="MCP server is not active")

    ensure_user_mcp_entitlements(current_user)
    entitled_ids = get_user_agent_entitled_mcp_ids(current_user)
    installed = server_id in entitled_ids
    if not installed:
        raise HTTPException(status_code=403, detail="Purchase an agent that includes this MCP server before using its tools")

    normalized_arguments = dict(request.arguments or {})

    # Compatibility: if client accidentally sends full execute envelope inside
    # `arguments`, unwrap it.
    # Example: { "tool": "read_file", "arguments": { "path": "README.md" } }
    nested_args = normalized_arguments.get("arguments")
    if isinstance(nested_args, dict):
        nested_tool = normalized_arguments.get("tool")
        if isinstance(nested_tool, str) and nested_tool.strip() and not request.tool:
            request.tool = nested_tool.strip()
        normalized_arguments = dict(nested_args)

    if request.query is not None and "query" not in normalized_arguments:
        normalized_arguments["query"] = request.query
    if request.limit is not None and "limit" not in normalized_arguments:
        normalized_arguments["limit"] = request.limit
    if request.url is not None and "url" not in normalized_arguments:
        normalized_arguments["url"] = request.url
    if request.max_chars is not None and "max_chars" not in normalized_arguments:
        normalized_arguments["max_chars"] = request.max_chars
    if request.html is not None and "html" not in normalized_arguments:
        normalized_arguments["html"] = request.html
    if request.path is not None and "path" not in normalized_arguments:
        normalized_arguments["path"] = request.path
    if request.table_name is not None and "table_name" not in normalized_arguments:
        normalized_arguments["table_name"] = request.table_name
    if request.params is not None and "params" not in normalized_arguments:
        normalized_arguments["params"] = request.params
    if request.headers is not None and "headers" not in normalized_arguments:
        normalized_arguments["headers"] = request.headers
    if request.body is not None and "body" not in normalized_arguments:
        normalized_arguments["body"] = request.body
    if request.timeout is not None and "timeout" not in normalized_arguments:
        normalized_arguments["timeout"] = request.timeout
    if request.source_code is not None and "source_code" not in normalized_arguments:
        normalized_arguments["source_code"] = request.source_code
    if request.prompt is not None and "prompt" not in normalized_arguments:
        normalized_arguments["prompt"] = request.prompt
    if request.content is not None and "content" not in normalized_arguments:
        normalized_arguments["content"] = request.content
    if request.append is not None and "append" not in normalized_arguments:
        normalized_arguments["append"] = request.append
    if request.staged is not None and "staged" not in normalized_arguments:
        normalized_arguments["staged"] = request.staged

    enforce_mcp_rate_limit(current_user)
    validate_mcp_arguments(normalized_arguments)

    try:
        result = execute_mcp_tool(server_id, request.tool, normalized_arguments, current_user)
        log_event(
            "MCP_TOOL_EXECUTED",
            {
                "server_id": server_id,
                "tool": request.tool,
                "installed": installed
            },
            user=current_user
        )
        return {
            "server_id": server_id,
            "server_name": mcp_servers_db[server_id].name,
            "tool": request.tool,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        log_event(
            "MCP_TOOL_EXECUTION_ERROR",
            {"server_id": server_id, "tool": request.tool, "error": str(e)[:200]},
            level="ERROR",
            user=current_user
        )
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")

@app.get("/users/me/mcp-purchases")
async def get_my_mcp_purchases(current_user: str = Depends(get_current_user)):
    """Get list of purchased MCP servers for current user"""
    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    newly_provisioned = ensure_user_mcp_entitlements(current_user)

    purchases = user.get("purchased_mcp_servers", {})
    entitled_ids = get_user_agent_entitled_mcp_ids(current_user)
    result = {}

    for server_id, rec in purchases.items():
        if server_id not in entitled_ids:
            continue
        server = mcp_servers_db.get(server_id)
        if server:
            result[server_id] = {
                "id": server.id,
                "server_name": server.name,
                "description": server.description,
                "category": server.category,
                "status": server.status,
                "price": server.price,
                "tools": server.tools,
                "license_key": rec.get("license_key"),
                "purchased_at": rec.get("purchased_at"),
                "source": rec.get("source", "direct"),
                "agents_using_this": [
                    agents_db[aid].name for aid in agents_db 
                    if server_id in agents_db[aid].mcp_server_ids
                ]
            }

    return {
        "user": current_user, 
        "purchased_mcp_servers": list(result.keys()),
        "details": result,  # Detailed info if needed
        "newly_provisioned": newly_provisioned
    }

# Example queries for each agent
AGENT_EXAMPLE_QUERIES = {
    "agent-001": [
        "Show the genre mix of the catalog",
        "What media formats are most common?",
        "Which playlists have the highest track coverage?"
    ],
    "agent-002": [
        "Show monthly revenue trend",
        "Which countries generate the most revenue?",
        "Top customers by lifetime value and average order value"
    ],
    "agent-003": [
        "Which customers are most at churn risk?",
        "Segment customers by purchase frequency",
        "What is the repeat customer rate?"
    ],
    "agent-004": [
        "Top artists by revenue",
        "Best performing albums",
        "Genre revenue performance ranking"
    ],
    "agent-005": [
        "Support representative workload summary",
        "Show employee hierarchy",
        "Customer territory distribution by country"
    ]
}

@app.get("/agents/{agent_id}/access-details")
async def get_access_details(
    agent_id: str, 
    request: Request,
    current_user: str = Depends(get_current_user)
):
    """Get access details (URL and access key) for a purchased agent - NEVER expose in URL"""
    if agent_id not in agents_db:
        log_event("AGENT_NOT_FOUND", {"agent_id": agent_id}, level="WARN", user=current_user)
        raise HTTPException(status_code=404, detail="Agent not found")
    
    user = fake_users_db.get(current_user)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Check if user has purchased this agent
    purchases = user.get("purchased_agents", {})
    if agent_id not in purchases:
        log_event("UNAUTHORIZED_ACCESS", {"agent_id": agent_id}, level="WARN", user=current_user)
        raise HTTPException(status_code=403, detail="You do not own this agent. Purchase it first.")
    
    # Get the access key from purchase record
    purchase_record = purchases[agent_id]
    access_key = purchase_record.get("access_key")
    
    # Build the access URL
    agent_endpoint_path = f"/agents/{agent_id}/ask"
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    full_url = f"{base_url}{agent_endpoint_path}"
    
    log_event("ACCESS_DETAILS_FETCHED", {"agent_id": agent_id}, user=current_user)
    
    return {
        "agent_id": agent_id,
        "agent_name": agents_db[agent_id].name,
        "url": full_url,
        "access_key": access_key,
        "purchased_at": purchase_record.get("purchased_at")
    }

# AGENT COMMUNICATION ENDPOINTS
@app.post("/agents/send-message")
async def send_agent_message(
    message: AgentMessage,
    current_user: str = Depends(get_current_user)
):
    """Send message from one agent to another"""
    if message.from_agent not in agents_db or message.to_agent not in agents_db:
        log_event(
            "INVALID_AGENT_MESSAGE",
            {"from": message.from_agent, "to": message.to_agent},
            level="ERROR",
            user=current_user
        )
        raise HTTPException(status_code=400, detail="Invalid agent IDs")
    
    result = a2a_comm.send_message(
        message.from_agent,
        message.to_agent,
        message.payload
    )
    
    return result

@app.post("/agents/communicate")
async def communicate_agents(
    request: Request,
    current_user: str = Depends(get_current_user)
):
    """Alternative endpoint for agent-to-agent communication (from frontend)"""
    try:
        data = await request.json()
        from_agent_id = data.get("from_agent_id")
        to_agent_id = data.get("to_agent_id")
        payload = data.get("payload", "")
        
        if not from_agent_id or not to_agent_id:
            raise HTTPException(status_code=400, detail="Missing from_agent_id or to_agent_id")
        
        if from_agent_id not in agents_db or to_agent_id not in agents_db:
            raise HTTPException(status_code=404, detail="Invalid agent IDs")
        
        result = a2a_comm.send_message(from_agent_id, to_agent_id, {"message": payload})
        
        log_event("A2A_COMMUNICATION", {
            "from": from_agent_id,
            "to": to_agent_id,
            "payload_length": len(str(payload))
        }, user=current_user)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/agents/{agent_id}/messages")
async def get_agent_messages(
    agent_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get messages for a specific agent"""
    if agent_id not in agents_db:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    messages = a2a_comm.get_messages(agent_id)
    log_event("MESSAGES_FETCHED", {"agent_id": agent_id, "count": len(messages)}, user=current_user)
    return messages

@app.get("/agents/communication/history")
async def get_communication_history(
    limit: int = 50,
    current_user: str = Depends(get_current_user)
):
    """Get agent communication history"""
    history = a2a_comm.get_history(limit)
    log_event("HISTORY_FETCHED", {"limit": limit}, user=current_user)
    return history

# AGENT QUESTION ENDPOINT
@app.post("/agents/{agent_id}/ask")
async def ask_agent(
    agent_id: str,
    request: QuestionRequest,
    current_user: str = Depends(get_current_user_or_access_key)
):
    """Ask a question to a specific agent"""
    if agent_id not in agents_db:
        log_event("AGENT_NOT_FOUND", {"agent_id": agent_id}, level="WARN", user=current_user)
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Extract the actual username from the auth result
    actual_user = current_user.split(":")[0] if ":" in current_user else current_user
    
    # Access control: Check if user purchased this agent
    user_record = fake_users_db.get(actual_user)
    has_purchased = user_record and agent_id in user_record.get("purchased_agents", {})
    
    if actual_user != "admin" and not has_purchased:
        raise HTTPException(status_code=403, detail="Purchase required to use this agent")

    agent = agents_db[agent_id]
    q_text = request.question
    
    # Generate intelligent response based on agent capabilities
    response_text = None

    # Revenue Intelligence Agent
    if agent_id == "agent-002":
        qlow = q_text.lower()
        try:
            if "month" in qlow or "trend" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT strftime('%Y-%m', InvoiceDate) AS month, ROUND(SUM(Total), 2) AS revenue, COUNT(*) AS invoices FROM Invoice GROUP BY month ORDER BY month DESC LIMIT 12;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Revenue Intelligence Agent: Monthly revenue trend (latest 12 months):\n" + "\n".join(
                    [f"- {r['month']}: ${r['revenue']:.2f} across {r['invoices']} invoices" for r in rows]
                )

            elif "country" in qlow or "region" in qlow or "geography" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT BillingCountry AS country, ROUND(SUM(Total), 2) AS revenue, COUNT(*) AS invoices FROM Invoice GROUP BY BillingCountry ORDER BY revenue DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Revenue Intelligence Agent: Revenue by country:\n" + "\n".join(
                    [f"- {r['country']}: ${r['revenue']:.2f} ({r['invoices']} invoices)" for r in rows]
                )

            elif "customer" in qlow or "aov" in qlow or "average order" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Customer.FirstName || ' ' || Customer.LastName AS customer, ROUND(SUM(Invoice.Total), 2) AS lifetime_value, COUNT(Invoice.InvoiceId) AS orders, ROUND(AVG(Invoice.Total), 2) AS avg_order_value FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId ORDER BY lifetime_value DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Revenue Intelligence Agent: Top customer value and AOV:\n" + "\n".join(
                    [f"- {r['customer']}: LTV ${r['lifetime_value']:.2f}, Orders {r['orders']}, AOV ${r['avg_order_value']:.2f}" for r in rows]
                )

            else:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT ROUND(SUM(Total), 2) AS total_revenue, COUNT(*) AS total_invoices, ROUND(AVG(Total), 2) AS avg_order_value, COUNT(DISTINCT CustomerId) AS active_customers FROM Invoice;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                if rows:
                    r = rows[0]
                    response_text = (
                        "Revenue Intelligence Agent:\n"
                        f"- Total Revenue: ${r['total_revenue']:.2f}\n"
                        f"- Total Invoices: {r['total_invoices']}\n"
                        f"- Average Order Value: ${r['avg_order_value']:.2f}\n"
                        f"- Active Customers: {r['active_customers']}\n\n"
                        "Ask for monthly trends, country performance, or customer value breakdown."
                    )
                else:
                    response_text = "Revenue Intelligence Agent: No revenue data available."
        except Exception as e:
            log_event("QUERY_ERROR", {"error": str(e)[:100]}, user=actual_user)
            response_text = "Revenue Intelligence Agent: Unable to process your request."
            
    # Catalog Intelligence Agent
    elif agent_id == "agent-001":
        qlow = q_text.lower()
        try:
            if "playlist" in qlow and ("coverage" in qlow or "top" in qlow or "largest" in qlow):
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Playlist.Name AS playlist_name, COUNT(PlaylistTrack.TrackId) AS tracks FROM Playlist LEFT JOIN PlaylistTrack ON Playlist.PlaylistId = PlaylistTrack.PlaylistId GROUP BY Playlist.PlaylistId ORDER BY tracks DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Catalog Intelligence Agent: Top playlist coverage:\n" + "\n".join(
                    [f"- {r['playlist_name']}: {r['tracks']} tracks" for r in rows]
                )
            elif "media" in qlow or "format" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT MediaType.Name AS media_type, COUNT(Track.TrackId) AS tracks FROM Track JOIN MediaType ON Track.MediaTypeId = MediaType.MediaTypeId GROUP BY MediaType.MediaTypeId ORDER BY tracks DESC;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Catalog Intelligence Agent: Media format distribution:\n" + "\n".join(
                    [f"- {r['media_type']}: {r['tracks']} tracks" for r in rows]
                )
            elif "genre" in qlow or "mix" in qlow:
                total_result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {"query": "SELECT COUNT(*) AS total_tracks FROM Track;"},
                    actual_user
                )
                total_tracks = total_result.get("rows", [{}])[0].get("total_tracks", 0)
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Genre.Name AS genre, COUNT(Track.TrackId) AS tracks FROM Track JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Genre.GenreId ORDER BY tracks DESC LIMIT 8;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                lines = []
                for r in rows:
                    pct = (r["tracks"] / total_tracks * 100) if total_tracks else 0
                    lines.append(f"- {r['genre']}: {r['tracks']} tracks ({pct:.1f}%)")
                response_text = "Catalog Intelligence Agent: Genre mix snapshot:\n" + "\n".join(lines)
            else:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT (SELECT COUNT(*) FROM Track) AS tracks, (SELECT COUNT(*) FROM Album) AS albums, (SELECT COUNT(*) FROM Artist) AS artists, (SELECT COUNT(*) FROM Genre) AS genres, (SELECT COUNT(*) FROM Playlist) AS playlists, (SELECT COUNT(*) FROM MediaType) AS media_types;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                if rows:
                    r = rows[0]
                    response_text = (
                        "Catalog Intelligence Agent:\n"
                        f"- Tracks: {r['tracks']}\n"
                        f"- Albums: {r['albums']}\n"
                        f"- Artists: {r['artists']}\n"
                        f"- Genres: {r['genres']}\n"
                        f"- Playlists: {r['playlists']}\n"
                        f"- Media Types: {r['media_types']}\n\n"
                        "Ask about genre mix, media format distribution, or playlist coverage."
                    )
                else:
                    response_text = "Catalog Intelligence Agent: No catalog data available."
        except Exception as e:
            response_text = f"Catalog Intelligence Agent: Unable to analyze catalog ({str(e)[:80]})."
    
    # Customer Lifecycle Agent
    elif agent_id == "agent-003":
        qlow = q_text.lower()
        try:
            if "churn" in qlow or "inactive" in qlow or "last purchase" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Customer.FirstName || ' ' || Customer.LastName AS customer, MAX(Invoice.InvoiceDate) AS last_purchase, CAST(julianday('now') - julianday(MAX(Invoice.InvoiceDate)) AS INTEGER) AS days_since_purchase FROM Customer JOIN Invoice ON Customer.CustomerId = Invoice.CustomerId GROUP BY Customer.CustomerId ORDER BY days_since_purchase DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Customer Lifecycle Agent: Most inactive customers:\n" + "\n".join(
                    [f"- {r['customer']}: last purchase {r['last_purchase']} ({r['days_since_purchase']} days ago)" for r in rows]
                )
            elif "segment" in qlow or "frequency" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT CASE WHEN purchase_count = 1 THEN 'One-time' WHEN purchase_count BETWEEN 2 AND 4 THEN 'Occasional' WHEN purchase_count BETWEEN 5 AND 9 THEN 'Frequent' ELSE 'Loyal' END AS segment, COUNT(*) AS customers FROM (SELECT CustomerId, COUNT(*) AS purchase_count FROM Invoice GROUP BY CustomerId) t GROUP BY segment ORDER BY customers DESC;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Customer Lifecycle Agent: Frequency segments:\n" + "\n".join(
                    [f"- {r['segment']}: {r['customers']} customers" for r in rows]
                )
            elif "repeat" in qlow or "retention" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT SUM(CASE WHEN purchase_count > 1 THEN 1 ELSE 0 END) AS repeat_customers, SUM(CASE WHEN purchase_count = 1 THEN 1 ELSE 0 END) AS one_time_customers, COUNT(*) AS total_customers FROM (SELECT CustomerId, COUNT(*) AS purchase_count FROM Invoice GROUP BY CustomerId) t;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                if rows:
                    r = rows[0]
                    repeat_rate = (r["repeat_customers"] / r["total_customers"] * 100) if r["total_customers"] else 0
                    response_text = (
                        "Customer Lifecycle Agent:\n"
                        f"- Repeat Customers: {r['repeat_customers']}\n"
                        f"- One-time Customers: {r['one_time_customers']}\n"
                        f"- Repeat Rate: {repeat_rate:.1f}%"
                    )
                else:
                    response_text = "Customer Lifecycle Agent: No retention data available."
            else:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT COUNT(*) AS customers, ROUND(AVG(order_count), 2) AS avg_orders_per_customer, ROUND(AVG(ltv), 2) AS avg_lifetime_value FROM (SELECT CustomerId, COUNT(*) AS order_count, SUM(Total) AS ltv FROM Invoice GROUP BY CustomerId) t;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                if rows:
                    r = rows[0]
                    response_text = (
                        "Customer Lifecycle Agent:\n"
                        f"- Customers with Purchases: {r['customers']}\n"
                        f"- Avg Orders per Customer: {r['avg_orders_per_customer']:.2f}\n"
                        f"- Avg Lifetime Value: ${r['avg_lifetime_value']:.2f}\n\n"
                        "Ask about churn risk, frequency segments, or repeat rate."
                    )
                else:
                    response_text = "Customer Lifecycle Agent: No lifecycle data available."
        except Exception as e:
            response_text = f"Customer Lifecycle Agent: Unable to analyze lifecycle data ({str(e)[:80]})."
    
    # Artist Performance Agent
    elif agent_id == "agent-004":
        qlow = q_text.lower()
        try:
            if "album" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Album.Title AS album, Artist.Name AS artist, ROUND(SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity), 2) AS revenue, COUNT(DISTINCT InvoiceLine.InvoiceId) AS invoices FROM InvoiceLine JOIN Track ON InvoiceLine.TrackId = Track.TrackId JOIN Album ON Track.AlbumId = Album.AlbumId JOIN Artist ON Album.ArtistId = Artist.ArtistId GROUP BY Album.AlbumId ORDER BY revenue DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Artist Performance Agent: Top albums by revenue:\n" + "\n".join(
                    [f"- {r['album']} ({r['artist']}): ${r['revenue']:.2f} from {r['invoices']} invoices" for r in rows]
                )
            elif "genre" in qlow and ("revenue" in qlow or "performance" in qlow):
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Genre.Name AS genre, ROUND(SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity), 2) AS revenue, COUNT(InvoiceLine.InvoiceLineId) AS sales_lines FROM InvoiceLine JOIN Track ON InvoiceLine.TrackId = Track.TrackId JOIN Genre ON Track.GenreId = Genre.GenreId GROUP BY Genre.GenreId ORDER BY revenue DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Artist Performance Agent: Genre revenue performance:\n" + "\n".join(
                    [f"- {r['genre']}: ${r['revenue']:.2f} ({r['sales_lines']} sales lines)" for r in rows]
                )
            else:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Artist.Name AS artist, ROUND(SUM(InvoiceLine.UnitPrice * InvoiceLine.Quantity), 2) AS revenue, COUNT(DISTINCT Track.TrackId) AS tracks_sold FROM InvoiceLine JOIN Track ON InvoiceLine.TrackId = Track.TrackId JOIN Album ON Track.AlbumId = Album.AlbumId JOIN Artist ON Album.ArtistId = Artist.ArtistId GROUP BY Artist.ArtistId ORDER BY revenue DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Artist Performance Agent: Top artists by revenue:\n" + "\n".join(
                    [f"- {r['artist']}: ${r['revenue']:.2f} ({r['tracks_sold']} tracks sold)" for r in rows]
                )
        except Exception as e:
            response_text = f"Artist Performance Agent: Unable to analyze artist performance ({str(e)[:80]})."
    
    # Operations Workforce Agent
    elif agent_id == "agent-005":
        qlow = q_text.lower()
        try:
            if "support" in qlow or "rep" in qlow or "workload" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Employee.FirstName || ' ' || Employee.LastName AS rep, COUNT(DISTINCT Customer.CustomerId) AS customers_supported, ROUND(SUM(Invoice.Total), 2) AS managed_revenue FROM Employee LEFT JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId LEFT JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId GROUP BY Employee.EmployeeId ORDER BY managed_revenue DESC;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Operations Workforce Agent: Support workload by representative:\n" + "\n".join(
                    [f"- {r['rep']}: {r['customers_supported']} customers, ${float(r['managed_revenue'] or 0):.2f} revenue" for r in rows]
                )
            elif "hierarchy" in qlow or "manager" in qlow or "organization" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT e.FirstName || ' ' || e.LastName AS employee, e.Title AS title, COALESCE(m.FirstName || ' ' || m.LastName, 'None') AS manager FROM Employee e LEFT JOIN Employee m ON e.ReportsTo = m.EmployeeId ORDER BY e.EmployeeId;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Operations Workforce Agent: Employee hierarchy:\n" + "\n".join(
                    [f"- {r['employee']} ({r['title']}) -> Manager: {r['manager']}" for r in rows]
                )
            elif "country" in qlow or "territory" in qlow or "geography" in qlow:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT Customer.Country AS country, COUNT(DISTINCT Customer.CustomerId) AS customers, ROUND(SUM(Invoice.Total), 2) AS revenue FROM Customer LEFT JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId GROUP BY Customer.Country ORDER BY customers DESC LIMIT 10;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                response_text = "Operations Workforce Agent: Customer territory distribution:\n" + "\n".join(
                    [f"- {r['country']}: {r['customers']} customers, ${float(r['revenue'] or 0):.2f} revenue" for r in rows]
                )
            else:
                result = execute_mcp_tool(
                    "mcp-004",
                    "execute_query",
                    {
                        "query": "SELECT (SELECT COUNT(*) FROM Employee) AS total_employees, (SELECT COUNT(*) FROM Customer) AS total_customers, (SELECT COUNT(DISTINCT Country) FROM Customer) AS customer_countries;"
                    },
                    actual_user
                )
                rows = result.get("rows", [])
                if rows:
                    r = rows[0]
                    response_text = (
                        "Operations Workforce Agent:\n"
                        f"- Total Employees: {r['total_employees']}\n"
                        f"- Total Customers: {r['total_customers']}\n"
                        f"- Countries Served: {r['customer_countries']}\n\n"
                        "Ask about support workload, hierarchy, or territory distribution."
                    )
                else:
                    response_text = "Operations Workforce Agent: No operations data available."
        except Exception as e:
            response_text = f"Operations Workforce Agent: Unable to analyze operations ({str(e)[:80]})."
    
    log_event("AGENT_QUESTION", {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "question": q_text[:100],
        "user": actual_user
    }, user=actual_user)
    
    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "question": q_text,
        "response": response_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_purchased": has_purchased
    }

# AGENT ACCESS HELPER ENDPOINT
@app.get("/agents/{agent_id}/ask", response_class=HTMLResponse)
async def get_agent_endpoint_info(agent_id: str):
    """Interactive query interface for the agent."""
    if agent_id not in agents_db:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents_db[agent_id]
    
    # Build domain-specific example questions
    if agent_id == "agent-001":  # Catalog Intelligence Agent
        example_questions_html = """
        <div class="space-y-4">
            <div>
                <h4 class="font-semibold text-blue-700 mb-2">Catalog Mix</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Show the genre mix of the catalog')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Show the genre mix of the catalog
                    </button>
                    <button onclick="fillQuestion('Which genres dominate the catalog?')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Which genres dominate the catalog?
                    </button>
                    <button onclick="fillQuestion('Catalog overview')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Catalog overview
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-green-700 mb-2">Media Types</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('What media formats are most common?')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        What media formats are most common?
                    </button>
                    <button onclick="fillQuestion('Show media type distribution')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Show media type distribution
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-purple-700 mb-2">Playlist Coverage</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Which playlists have the highest track coverage?')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Which playlists have the highest track coverage?
                    </button>
                    <button onclick="fillQuestion('Top playlists by number of tracks')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Top playlists by number of tracks
                    </button>
                </div>
            </div>
        </div>
        """
    elif agent_id == "agent-002":  # Revenue Intelligence Agent
        example_questions_html = """
        <div class="space-y-4">
            <div>
                <h4 class="font-semibold text-blue-700 mb-2">Revenue Trends</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Show monthly revenue trend')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Show monthly revenue trend
                    </button>
                    <button onclick="fillQuestion('Revenue trend for the last 12 months')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Revenue trend for the last 12 months
                    </button>
                    <button onclick="fillQuestion('Revenue overview')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Revenue overview
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-green-700 mb-2">Geography</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Which countries generate the most revenue?')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Which countries generate the most revenue?
                    </button>
                    <button onclick="fillQuestion('Show revenue by country')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Show revenue by country
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-purple-700 mb-2">Customer Value</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Top customers by lifetime value and average order value')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Top customers by lifetime value and average order value
                    </button>
                    <button onclick="fillQuestion('Show AOV by customer')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Show AOV by customer
                    </button>
                </div>
            </div>
        </div>
        """
    elif agent_id == "agent-003":  # Customer Lifecycle Agent
        example_questions_html = """
        <div class="space-y-4">
            <div>
                <h4 class="font-semibold text-blue-700 mb-2">Retention</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('What is the repeat customer rate?')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        What is the repeat customer rate?
                    </button>
                    <button onclick="fillQuestion('Show one-time vs repeat customers')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Show one-time vs repeat customers
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-green-700 mb-2">Segmentation</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Segment customers by purchase frequency')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Segment customers by purchase frequency
                    </button>
                    <button onclick="fillQuestion('Show lifecycle segments')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Show lifecycle segments
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-purple-700 mb-2">Churn Signals</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Which customers look most inactive?')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Which customers look most inactive?
                    </button>
                    <button onclick="fillQuestion('Show customers by days since last purchase')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Show customers by days since last purchase
                    </button>
                </div>
            </div>
        </div>
        """
    elif agent_id == "agent-004":  # Artist Performance Agent
        example_questions_html = """
        <div class="space-y-4">
            <div>
                <h4 class="font-semibold text-blue-700 mb-2">Artist Rankings</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Top artists by revenue')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Top artists by revenue
                    </button>
                    <button onclick="fillQuestion('Which artists generate the strongest sales?')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Which artists generate the strongest sales?
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-green-700 mb-2">Album Performance</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Best performing albums')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Best performing albums
                    </button>
                    <button onclick="fillQuestion('Top albums by revenue')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Top albums by revenue
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-purple-700 mb-2">Genre Performance</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Genre revenue performance ranking')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Genre revenue performance ranking
                    </button>
                    <button onclick="fillQuestion('Show genre performance by revenue')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Show genre performance by revenue
                    </button>
                </div>
            </div>
        </div>
        """
    elif agent_id == "agent-005":  # Operations Workforce Agent
        example_questions_html = """
        <div class="space-y-4">
            <div>
                <h4 class="font-semibold text-blue-700 mb-2">Support Load</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Support representative workload summary')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        Support representative workload summary
                    </button>
                    <button onclick="fillQuestion('How many customers does each support rep handle?')" class="w-full text-left px-4 py-2 hover:bg-blue-50 rounded border border-blue-200 hover:border-blue-300 transition text-sm">
                        How many customers does each support rep handle?
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-green-700 mb-2">Org Structure</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Show employee hierarchy')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Show employee hierarchy
                    </button>
                    <button onclick="fillQuestion('Who reports to whom in the organization?')" class="w-full text-left px-4 py-2 hover:bg-green-50 rounded border border-green-200 hover:border-green-300 transition text-sm">
                        Who reports to whom in the organization?
                    </button>
                </div>
            </div>
            <div>
                <h4 class="font-semibold text-purple-700 mb-2">Territory</h4>
                <div class="space-y-2">
                    <button onclick="fillQuestion('Customer territory distribution by country')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Customer territory distribution by country
                    </button>
                    <button onclick="fillQuestion('Which countries have the largest customer footprint?')" class="w-full text-left px-4 py-2 hover:bg-purple-50 rounded border border-purple-200 hover:border-purple-300 transition text-sm">
                        Which countries have the largest customer footprint?
                    </button>
                </div>
            </div>
        </div>
        """
    else:
        example_questions_html = "<p class='text-gray-600'>No examples available</p>"
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{agent.name} - Query Agent</title>
        <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0">
        <meta http-equiv="Pragma" content="no-cache">
        <meta http-equiv="Expires" content="0">
        <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3C/svg%3E">
        <link rel="shortcut icon" href="data:,">
        <link rel="apple-touch-icon" href="data:,">
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; }}
        </style>
    </head>
    <body class="bg-gradient-to-br from-blue-50 to-indigo-100 min-h-screen">
        <div class="container mx-auto p-8">
            <div class="max-w-2xl mx-auto">
                <!-- Header -->
                <div class="bg-white rounded-lg shadow-lg p-8 mb-6">
                    <h1 class="text-4xl font-bold text-gray-800 mb-2">{agent.name}</h1>
                    <p class="text-lg text-gray-600 mb-4">{agent.description}</p>
                    <div class="bg-blue-50 border border-blue-200 rounded p-4">
                        <p class="text-sm text-blue-900"><strong>Agent ID:</strong> {agent_id}</p>
                    </div>
                </div>

                <!-- Auth Section -->
                <div class="bg-white rounded-lg shadow-lg p-8 mb-6">
                    <h2 class="text-2xl font-bold text-gray-800 mb-4">Authentication</h2>
                    
                    <!-- Token Input -->
                    <div class="space-y-3">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">JWT Token or Access Key</label>
                            <input type="text" id="tokenInput" placeholder="Paste your JWT token or access key here or get one from Agent Exchange..." 
                                class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                            <p class="text-xs text-gray-500 mt-2">Get a token by logging in and purchasing at the <a href="/frontend/index.html" class="text-blue-600 hover:underline">Agent Exchange</a></p>
                        </div>
                    </div>
                </div>

                <!-- Query Section -->
                <div class="bg-white rounded-lg shadow-lg p-8">
                    <h2 class="text-2xl font-bold text-gray-800 mb-4">Ask a Question</h2>
                    
                    <div class="space-y-4">
                        <textarea id="questionInput" placeholder="Ask a question... Examples:&#10;- How many rock tracks?&#10;- How many total tracks?&#10;- What genres are available?"
                            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            rows="4"></textarea>
                        
                        <button onclick="askAgent()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg transition duration-200">Ask Agent</button>
                    </div>

                    <!-- Response Section -->
                    <div id="responseSection" class="mt-6 hidden">
                        <h3 class="text-lg font-bold text-gray-800 mb-3">Response:</h3>
                        <div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-3">
                            <p id="responseText" class="text-gray-700 whitespace-pre-wrap leading-relaxed"></p>
                        </div>
                    </div>

                    <!-- Error Section -->
                    <div id="errorSection" class="mt-6 hidden">
                        <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                            <p class="text-sm text-red-900"><strong>Error:</strong> <span id="errorText"></span></p>
                        </div>
                    </div>

                    <!-- Loading -->
                    <div id="loadingSection" class="mt-6 hidden">
                        <div class="flex items-center space-x-2">
                            <div class="animate-spin inline-block w-4 h-4 border-4 border-gray-300 border-t-blue-600 rounded-full"></div>
                            <span class="text-gray-600">Processing your question...</span>
                        </div>
                    </div>
                </div>

                <!-- Example Questions -->
                <div class="bg-white rounded-lg shadow-lg p-8 mt-6">
                    <h3 class="text-lg font-bold text-gray-800 mb-4">Example Questions by Domain</h3>
                    {example_questions_html}
                </div>
            </div>
        </div>

        <script>
        const AGENT_ID = '{agent_id}';

        function fillQuestion(question) {{
            document.getElementById('questionInput').value = question;
            document.getElementById('questionInput').focus();
        }}

        async function askAgent() {{
            let token = document.getElementById('tokenInput').value.trim();
            const question = document.getElementById('questionInput').value.trim();

            if (!token) {{
                showError('Please enter your JWT token or access key');
                return;
            }}
            if (!question) {{
                showError('Please enter a question');
                return;
            }}

            showLoading(true);
            hideError();

            try {{
                const response = await fetch(`http://localhost:8000/agents/${{AGENT_ID}}/ask`, {{
                    method: 'POST',
                    headers: {{
                        'Authorization': `Bearer ${{token}}`,
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{ question: question }})
                }});

                const data = await response.json();

                if (response.ok) {{
                    showResponse(data.response);
                }} else {{
                    showError(data.detail || 'Failed to query agent');
                }}
            }} catch (error) {{
                showError('Connection error: ' + error.message);
            }} finally {{
                showLoading(false);
            }}
        }}

        function showResponse(response) {{
            document.getElementById('responseText').textContent = response;
            document.getElementById('responseSection').classList.remove('hidden');
            document.getElementById('errorSection').classList.add('hidden');
        }}

        function showError(message) {{
            document.getElementById('errorText').textContent = message;
            document.getElementById('errorSection').classList.remove('hidden');
            document.getElementById('responseSection').classList.add('hidden');
        }}

        function hideError() {{
            document.getElementById('errorSection').classList.add('hidden');
        }}

        function showLoading(show) {{
            document.getElementById('loadingSection').classList.toggle('hidden', !show);
        }}

        // Allow Ctrl+Enter to submit
        document.getElementById('questionInput').addEventListener('keydown', (e) => {{
            if (e.ctrlKey && e.key === 'Enter') {{
                askAgent();
            }}
        }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# LOGGING ENDPOINTS
@app.get("/logs")
async def get_logs(
    limit: int = 100,
    event_type: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """Get system logs (filtered by event type if specified)"""
    filtered_logs = logs_store[-limit:]
    
    if event_type:
        filtered_logs = [log for log in filtered_logs if log["event_type"] == event_type]
    
    log_event("LOGS_FETCHED", {"limit": limit, "event_type": event_type, "count": len(filtered_logs)}, user=current_user)
    return filtered_logs

@app.get("/logs/events")
async def get_log_events(current_user: str = Depends(get_current_user)):
    """Get unique event types"""
    events = list(set(log["event_type"] for log in logs_store))
    return {"events": events}

@app.delete("/logs")
async def clear_logs(current_user: str = Depends(get_current_user)):
    """Clear all logs (admin only)"""
    if current_user != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    global logs_store
    logs_store = []
    log_event("LOGS_CLEARED", {"user": current_user}, user=current_user)
    return {"message": "Logs cleared"}

# HEALTH ENDPOINT
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_count": len(agents_db),
        "logs_count": len(logs_store)
    }

# ROOT ENDPOINT
@app.get("/favicon.ico")
async def favicon():
    """Return a blank icon with no-store headers to prevent stale cached branding icons."""
    transparent_gif = (
        b"GIF89a\x01\x00\x01\x00\x80\x01\x00\xff\xff\xff\x00\x00\x00"
        b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
        b"\x00\x02\x02D\x01\x00;"
    )
    return Response(
        content=transparent_gif,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/")
async def root():
    """API info"""
    return {
        "name": "Agent Marketplace API",
        "version": "1.0",
        "agents": 3,
        "endpoints": {
            "auth": [
                "/auth/login",
                "/auth/register"
            ],
            "agents": [
                "/agents",
                "/agents/{agent_id}"
            ],
            "communication": [
                "/agents/send-message",
                "/agents/{agent_id}/messages",
                "/agents/communication/history"
            ],
            "logs": [
                "/logs",
                "/logs/events",
                "/logs/delete"
            ],
            "health": "/health"
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Agent Marketplace API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)