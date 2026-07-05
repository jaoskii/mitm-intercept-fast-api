import os
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app import db

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fastapi_app")

app = FastAPI(title="Mitmproxy API Interceptor Dashboard")

# Initialize SQLite tables on startup
@app.on_event("startup")
def startup_event():
    db.init_db()
    logger.info("Database initialized successfully.")

# Mount static files directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                # Remove stale connections
                logger.error(f"Error broadcasting to ws: {e}")
                self.active_connections.remove(connection)

manager = ConnectionManager()

# --- Pydantic Models for Validation ---

class RuleBase(BaseModel):
    name: str = Field(..., min_length=1, description="Rule description / friendly name")
    method: str = Field("ALL", description="HTTP Method (GET, POST, etc.) or ALL")
    url_pattern: str = Field(..., min_length=1, description="URL pattern or domain to match")
    action: str = Field(..., description="Action to perform (mock_response, modify_request_headers, modify_response_headers, modify_response_body, delay)")
    is_active: int = Field(1, description="Active status (0 or 1)")
    status_code: Optional[int] = Field(None, description="HTTP status code for mocks")
    response_body: Optional[str] = Field(None, description="Response body content")
    headers_json: Optional[str] = Field(None, description="JSON string of headers")
    body_search: Optional[str] = Field(None, description="String to search in response body")
    body_replace: Optional[str] = Field(None, description="String to replace matching content in body")
    delay_seconds: Optional[float] = Field(None, description="Network delay latency in seconds")

class RuleToggle(BaseModel):
    is_active: int = Field(..., ge=0, le=1)

class InternalLogCreate(BaseModel):
    method: str
    url: str
    request_headers: str
    request_body: Optional[str] = None
    response_status: Optional[int] = None
    response_headers: Optional[str] = None
    response_body: Optional[str] = None
    intercepted: int
    matched_rule_id: Optional[int] = None
    action_taken: Optional[str] = None

# --- UI Route ---

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Dashboard index.html template not found")
    with open(template_path, "r") as f:
        return f.read()

# --- Rules REST Routes ---

@app.get("/api/rules")
def list_rules():
    return db.get_all_rules()

@app.post("/api/rules", status_code=status.HTTP_201_CREATED)
def add_rule(rule: RuleBase):
    # Basic validation for parameters based on action
    validate_action_parameters(rule)
    rule_id = db.create_rule(
        name=rule.name,
        method=rule.method,
        url_pattern=rule.url_pattern,
        action=rule.action,
        is_active=rule.is_active,
        status_code=rule.status_code,
        response_body=rule.response_body,
        headers_json=rule.headers_json,
        body_search=rule.body_search,
        body_replace=rule.body_replace,
        delay_seconds=rule.delay_seconds
    )
    return {"status": "success", "rule_id": rule_id}

@app.put("/api/rules/{rule_id}")
def update_rule(rule_id: int, rule: RuleBase):
    validate_action_parameters(rule)
    existing = db.get_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    updated = db.update_rule(
        rule_id=rule_id,
        name=rule.name,
        method=rule.method,
        url_pattern=rule.url_pattern,
        action=rule.action,
        is_active=rule.is_active,
        status_code=rule.status_code,
        response_body=rule.response_body,
        headers_json=rule.headers_json,
        body_search=rule.body_search,
        body_replace=rule.body_replace,
        delay_seconds=rule.delay_seconds
    )
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update rule")
    return {"status": "success", "message": "Rule updated successfully"}

@app.patch("/api/rules/{rule_id}/toggle")
def toggle_rule(rule_id: int, toggle: RuleToggle):
    existing = db.get_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    updated = db.toggle_rule(rule_id, toggle.is_active)
    return {"status": "success", "is_active": toggle.is_active}

@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    existing = db.get_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete_rule(rule_id)
    return {"status": "success", "message": "Rule deleted"}

# --- Logs Routes ---

@app.get("/api/logs")
def get_logs(limit: int = 100):
    return db.get_all_logs(limit)

@app.delete("/api/logs")
def clear_all_logs():
    db.clear_logs()
    return {"status": "success", "message": "Logs cleared"}

# --- Mitmproxy Internal Logging & Real-time Stream ---

@app.post("/api/internal/log")
async def receive_proxy_log(log_entry: InternalLogCreate):
    # Log to sqlite
    log_id = db.add_log(
        method=log_entry.method,
        url=log_entry.url,
        request_headers=log_entry.request_headers,
        request_body=log_entry.request_body,
        response_status=log_entry.response_status,
        response_headers=log_entry.response_headers,
        response_body=log_entry.response_body,
        intercepted=log_entry.intercepted,
        matched_rule_id=log_entry.matched_rule_id,
        action_taken=log_entry.action_taken
    )
    
    # Enrich and broadcast
    rule_name = None
    if log_entry.matched_rule_id:
        rule = db.get_rule(log_entry.matched_rule_id)
        if rule:
            rule_name = rule["name"]

    broadcast_data = {
        "id": log_id,
        "timestamp": "Just now",  # UI will display or generate
        "method": log_entry.method,
        "url": log_entry.url,
        "request_headers": log_entry.request_headers,
        "request_body": log_entry.request_body,
        "response_status": log_entry.response_status,
        "response_headers": log_entry.response_headers,
        "response_body": log_entry.response_body,
        "intercepted": log_entry.intercepted,
        "matched_rule_id": log_entry.matched_rule_id,
        "rule_name": rule_name,
        "action_taken": log_entry.action_taken
    }
    await manager.broadcast(broadcast_data)
    return {"status": "success", "log_id": log_id}

# --- Certificate Download Route ---

@app.get("/api/cert")
def download_cert():
    # Look for certificate files in home dir or common paths
    paths_to_check = [
        os.getenv("MITMPROXY_CERT_PATH", "/root/.mitmproxy/mitmproxy-ca-cert.pem"),
        os.path.expanduser("~/.mitmproxy/mitmproxy-ca-cert.pem"),
        "./mitmproxy-ca-cert.pem" # local fallback
    ]
    for path in paths_to_check:
        if os.path.exists(path):
            return FileResponse(
                path=path,
                filename="mitmproxy-ca-cert.pem",
                media_type="application/x-x509-ca-cert"
            )
    
    raise HTTPException(
        status_code=404, 
        detail="Mitmproxy CA certificate file not found yet. Start the proxy at least once to generate it."
    )

# --- WebSocket Listener ---

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect messages from client for now, just keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)

# --- Helper Validation ---

def validate_action_parameters(rule: RuleBase):
    if rule.action == "mock_response":
        if rule.status_code is None:
            raise HTTPException(status_code=400, detail="status_code is required for mock_response action")
    elif rule.action == "modify_request_headers" or rule.action == "modify_response_headers":
        if not rule.headers_json:
            raise HTTPException(status_code=400, detail="headers_json is required for header modification actions")
        try:
            json.loads(rule.headers_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="headers_json must be a valid JSON object string")
    elif rule.action == "modify_response_body":
        if not rule.body_search:
            raise HTTPException(status_code=400, detail="body_search string is required for modify_response_body action")
    elif rule.action == "delay":
        if rule.delay_seconds is None or rule.delay_seconds <= 0:
            raise HTTPException(status_code=400, detail="delay_seconds must be a positive float/integer for delay action")
