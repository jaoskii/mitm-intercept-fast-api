import os
import sqlite3
import json
from typing import List, Dict, Any, Optional

# Database path configuration
DB_DIR = os.getenv("DB_DIR", "data")
DB_PATH = os.path.join(DB_DIR, "proxy.db")

def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create rules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        method TEXT NOT NULL,
        url_pattern TEXT NOT NULL,
        action TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        status_code INTEGER,
        response_body TEXT,
        headers_json TEXT,
        body_search TEXT,
        body_replace TEXT,
        delay_seconds REAL
    )
    """)
    
    # Create logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        method TEXT NOT NULL,
        url TEXT NOT NULL,
        request_headers TEXT,
        request_body TEXT,
        response_status INTEGER,
        response_headers TEXT,
        response_body TEXT,
        intercepted INTEGER NOT NULL DEFAULT 0,
        matched_rule_id INTEGER,
        action_taken TEXT,
        FOREIGN KEY (matched_rule_id) REFERENCES rules(id) ON DELETE SET NULL
    )
    """)
    
    conn.commit()
    conn.close()

# --- Rule CRUD Operations ---

def get_all_rules() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rules ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_active_rules() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rules WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_rule(rule_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rules WHERE id = ?", (rule_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_rule(
    name: str,
    method: str,
    url_pattern: str,
    action: str,
    is_active: int = 1,
    status_code: Optional[int] = None,
    response_body: Optional[str] = None,
    headers_json: Optional[str] = None,
    body_search: Optional[str] = None,
    body_replace: Optional[str] = None,
    delay_seconds: Optional[float] = None
) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO rules (
        name, method, url_pattern, action, is_active, 
        status_code, response_body, headers_json, 
        body_search, body_replace, delay_seconds
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, method.upper(), url_pattern, action, is_active,
        status_code, response_body, headers_json,
        body_search, body_replace, delay_seconds
    ))
    rule_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return rule_id

def update_rule(
    rule_id: int,
    name: str,
    method: str,
    url_pattern: str,
    action: str,
    is_active: int,
    status_code: Optional[int] = None,
    response_body: Optional[str] = None,
    headers_json: Optional[str] = None,
    body_search: Optional[str] = None,
    body_replace: Optional[str] = None,
    delay_seconds: Optional[float] = None
) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE rules SET 
        name = ?, method = ?, url_pattern = ?, action = ?, is_active = ?, 
        status_code = ?, response_body = ?, headers_json = ?, 
        body_search = ?, body_replace = ?, delay_seconds = ?
    WHERE id = ?
    """, (
        name, method.upper(), url_pattern, action, is_active,
        status_code, response_body, headers_json,
        body_search, body_replace, delay_seconds,
        rule_id
    ))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def toggle_rule(rule_id: int, is_active: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE rules SET is_active = ? WHERE id = ?", (is_active, rule_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def delete_rule(rule_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

# --- Log Operations ---

def add_log(
    method: str,
    url: str,
    request_headers: str,
    request_body: Optional[str],
    response_status: Optional[int],
    response_headers: Optional[str],
    response_body: Optional[str],
    intercepted: int,
    matched_rule_id: Optional[int],
    action_taken: Optional[str]
) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO logs (
        method, url, request_headers, request_body, 
        response_status, response_headers, response_body, 
        intercepted, matched_rule_id, action_taken
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        method, url, request_headers, request_body,
        response_status, response_headers, response_body,
        intercepted, matched_rule_id, action_taken
    ))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def get_all_logs(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*, r.name as rule_name 
        FROM logs l 
        LEFT JOIN rules r ON l.matched_rule_id = r.id 
        ORDER BY l.id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_logs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
