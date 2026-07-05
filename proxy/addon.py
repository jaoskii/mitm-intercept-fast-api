import os
import sqlite3
import json
import time
import urllib.request
import urllib.error
from mitmproxy import http
from typing import Optional, Dict, Any, List

DB_DIR = os.getenv("DB_DIR", "data")
DB_PATH = os.path.join(DB_DIR, "proxy.db")

class InterceptorAddon:
    def __init__(self):
        print("Mitmproxy Interceptor Addon loaded.")

    def _get_active_rules(self) -> List[Dict[str, Any]]:
        if not os.path.exists(DB_PATH):
            return []
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rules WHERE is_active = 1")
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[addon] Error reading SQLite rules: {e}")
            return []

    def _match_rule(self, flow: http.HTTPFlow, rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        method = flow.request.method
        url = flow.request.pretty_url
        
        for rule in rules:
            rule_method = rule['method']
            url_pattern = rule['url_pattern']
            
            # Match HTTP Method
            if rule_method != 'ALL' and rule_method.upper() != method.upper():
                continue
                
            # Match URL (substring match)
            if url_pattern not in url:
                continue
                
            return rule
        return None

    def request(self, flow: http.HTTPFlow) -> None:
        rules = self._get_active_rules()
        rule = self._match_rule(flow, rules)
        
        if not rule:
            return

        action = rule['action']
        print(f"[addon] Match request: {flow.request.method} {flow.request.pretty_url} -> Action: {action}")

        # Initialize metadata
        flow.metadata["matched_rule_id"] = rule["id"]
        flow.metadata["action_taken"] = action

        # 1. Latency Delay
        if action == "delay":
            delay = rule['delay_seconds'] or 1.0
            print(f"[addon] Delaying request for {delay}s...")
            time.sleep(delay)
            flow.metadata["intercepted"] = 1

        # 2. Modify Request Headers
        elif action == "modify_request_headers":
            try:
                headers = json.loads(rule['headers_json'] or '{}')
                for k, v in headers.items():
                    flow.request.headers[k] = str(v)
                print(f"[addon] Request headers modified.")
                flow.metadata["intercepted"] = 1
            except Exception as e:
                print(f"[addon] Error modifying request headers: {e}")

        # 3. Mock Response
        elif action == "mock_response":
            try:
                status_code = rule['status_code'] or 200
                body = rule['response_body'] or ""
                
                headers = {"Content-Type": "text/plain"}
                if rule['headers_json']:
                    custom_headers = json.loads(rule['headers_json'])
                    headers.update({k: str(v) for k, v in custom_headers.items()})
                
                # Check if body looks like JSON and we don't have Content-Type specified, auto-set it
                if body.strip().startswith('{') and body.strip().endswith('}') and "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
                    
                flow.response = http.Response.make(
                    status_code,
                    body.encode('utf-8'),
                    headers
                )
                print(f"[addon] Mock response injected (Status {status_code}).")
                flow.metadata["intercepted"] = 1
            except Exception as e:
                print(f"[addon] Error mocking response: {e}")

    def response(self, flow: http.HTTPFlow) -> None:
        action_taken = flow.metadata.get("action_taken")
        matched_rule_id = flow.metadata.get("matched_rule_id")
        intercepted = flow.metadata.get("intercepted", 0)

        # If it wasn't mocked in request, check response modification rules
        if action_taken != "mock_response":
            rules = self._get_active_rules()
            rule = self._match_rule(flow, rules)
            
            if rule:
                action = rule['action']
                matched_rule_id = rule['id']
                action_taken = action
                
                # 4. Modify Response Headers
                if action == "modify_response_headers":
                    try:
                        headers = json.loads(rule['headers_json'] or '{}')
                        for k, v in headers.items():
                            flow.response.headers[k] = str(v)
                        print(f"[addon] Response headers modified.")
                        intercepted = 1
                    except Exception as e:
                        print(f"[addon] Error modifying response headers: {e}")
                
                # 5. Modify Response Body (Search & Replace)
                elif action == "modify_response_body":
                    try:
                        search_str = rule['body_search']
                        replace_str = rule['body_replace'] or ""
                        
                        if search_str and flow.response.text:
                            original_len = len(flow.response.text)
                            flow.response.text = flow.response.text.replace(search_str, replace_str)
                            print(f"[addon] Response body modified: replaced '{search_str}' with '{replace_str}'")
                            intercepted = 1
                    except Exception as e:
                        print(f"[addon] Error modifying response body: {e}")

        # Send flow report to FastAPI dashboard
        self._report_flow(flow, intercepted, matched_rule_id, action_taken)

    def _report_flow(self, flow: http.HTTPFlow, intercepted: int, rule_id: Optional[int], action: Optional[str]) -> None:
        try:
            req_body = ""
            if flow.request.content:
                try:
                    req_body = flow.request.text or ""
                except Exception:
                    req_body = f"[Binary Content: {len(flow.request.content)} bytes]"

            res_status = None
            res_headers_json = None
            res_body = ""
            
            if flow.response:
                res_status = flow.response.status_code
                res_headers_json = json.dumps(dict(flow.response.headers.items()))
                if flow.response.content:
                    try:
                        res_body = flow.response.text or ""
                        # Truncate extremely large bodies to keep logs clean
                        if len(res_body) > 15000:
                            res_body = res_body[:15000] + "\n... [truncated in dashboard log]"
                    except Exception:
                        res_body = f"[Binary Content: {len(flow.response.content)} bytes]"

            payload = {
                "method": flow.request.method,
                "url": flow.request.pretty_url,
                "request_headers": json.dumps(dict(flow.request.headers.items())),
                "request_body": req_body,
                "response_status": res_status,
                "response_headers": res_headers_json,
                "response_body": res_body,
                "intercepted": intercepted,
                "matched_rule_id": rule_id,
                "action_taken": action
            }

            # Ship log to FastAPI via local post request
            self._send_to_fastapi(payload)
        except Exception as e:
            print(f"[addon] Failed to compile log flow: {e}")

    def _send_to_fastapi(self, payload: dict) -> None:
        url = "http://localhost:8000/api/internal/log"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        try:
            # Short timeout to prevent proxy blocking
            with urllib.request.urlopen(req, timeout=1.5) as response:
                response.read()
        except urllib.error.URLError as e:
            # Silent fallback if FastAPI server is not fully up yet
            pass
        except Exception as e:
            print(f"[addon] Error sending log to FastAPI: {e}")

addons = [
    InterceptorAddon()
]
