"""
mcp_server/server.py — Japan Official Data MCP Server (Model Context Protocol)

Claude Desktop, Cursor, Windsurf, Cline, LangChain 等の AI エージェントから
日本の公的オープンデータ（全155データセット・1,016万件超：人口、地価、全省庁入札GEPS、
医療・病院、再エネ・系統空き容量、上場企業、防災ハザード等）を英語・日本語で直接検索・SQL集計できる
公式 MCP (JSON-RPC 2.0 over stdio) サーバー実装。

【動作モード】
1. Remote API モード (外部配布時):
   環境変数 `RAPIDAPI_KEY` (または `JAPAN_DATA_API_KEY`) が設定されている場合、
   RapidAPI Gateway / 本番 API エンドポイントへ HTTP リクエストを送信。
2. Local Direct モード (ローカル環境 / 統合テスト時):
   ローカルの FastAPI / DuckDB インメモリエンジンを直接呼び出し、ミリ秒単位で応答。
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
API_DIR = ROOT_DIR / "api"

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "japan-data-mcp"
SERVER_VERSION = "1.0.0"

DEFAULT_RAPIDAPI_HOST = os.environ.get("RAPIDAPI_HOST", "japan-official-data-megabank-api-us-standard-normalized.p.rapidapi.com")
DEFAULT_API_BASE_URL = os.environ.get("JAPAN_DATA_API_URL", f"https://{DEFAULT_RAPIDAPI_HOST}")


MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "list_japan_datasets",
        "description": (
            "Search and list all 155 official Japanese & US datasets in Global Data Megabank "
            "(demographics, real_estate, procurement, companies, medical, renewable_energy, grid_capacity, "
            "police_stations, dams, active_faults, etc.). Supports both English and Japanese keywords."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional keyword in English or Japanese (e.g. 'procurement', 'hospital', 'solar', '入札', '医療').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of datasets to return (default: 25, max: 155).",
                    "default": 25,
                },
            },
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "datasets": {"type": "array", "items": {"type": "object"}},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "audience": ["user", "assistant"],
            "priority": 1.0,
        },
    },
    {
        "name": "describe_japan_dataset",
        "description": (
            "Inspect the exact column schema, data types, historical coverage range, primary government source, "
            "and a sanitized sample record (with English prefecture_en / city_en) for a specific dataset."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "Dataset identifier (e.g. 'demographics', 'procurement', 'medical', 'renewable_energy', 'companies').",
                }
            },
            "required": ["dataset_id"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "schema": {"type": "object"},
                "sample_record": {"type": "object"},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "audience": ["user", "assistant"],
            "priority": 0.9,
        },
    },
    {
        "name": "search_japan_official_data",
        "description": (
            "Query records from any of the 155 official datasets using standardized filters. "
            "Supports English prefecture names (e.g., 'Tokyo', 'Osaka', 'Hokkaido'), 5-digit JIS municipality codes "
            "(e.g., '13101'), 13-digit NTA corporate numbers, and keyword search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "Target dataset ID (e.g., 'demographics', 'procurement', 'medical', 'companies', 'real_estate').",
                },
                "prefecture": {
                    "type": "string",
                    "description": "Prefecture name in English or Japanese (e.g., 'Tokyo', 'Osaka', 'Hokkaido', '東京都').",
                },
                "municipality_code": {
                    "type": "string",
                    "description": "5-digit JIS municipality code with leading zero preserved (e.g., '13101', '01101').",
                },
                "corporate_number": {
                    "type": "string",
                    "description": "13-digit Japan National Tax Agency corporate number (or 10-digit US SEC CIK).",
                },
                "q": {
                    "type": "string",
                    "description": "Free-text search keyword (company name, facility name, contract title, etc.).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of records to return (default: 10, max: 100).",
                    "default": 10,
                },
            },
            "required": ["dataset_id"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "records": {"type": "array", "items": {"type": "object"}},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "audience": ["user", "assistant"],
            "priority": 1.0,
        },
    },
    {
        "name": "execute_japan_megabank_sql",
        "description": (
            "Execute a read-only DuckDB SQL SELECT query across all 155 mounted datasets (10.16M+ records). "
            "Ideal for cross-table JOINs using 'municipality_code' (5-digit JIS code) or 'corporate_number' (13-digit ID). "
            "Note: Requires MEGA tier subscription on RapidAPI or local database access."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "Read-only SQL SELECT query (e.g., SELECT prefecture, count(*) AS cnt FROM medical GROUP BY 1 ORDER BY 2 DESC LIMIT 10).",
                }
            },
            "required": ["sql"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "row_count": {"type": "integer"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "object"}},
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "audience": ["user", "assistant"],
            "priority": 0.8,
        },
    },
    {
        "name": "list_flagship_b2b_bundles",
        "description": (
            "List the 5 Flagship Enterprise All-in-One Data Bundles (Real Estate, Government Procurement, "
            "Healthcare, Renewable Energy/GX, Municipal Finance/Resilience) with pricing, discounts, and B2B invoice details."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_code": {
                    "type": "string",
                    "description": "Optional bundle code filter (e.g., 'BUNDLE-01' through 'BUNDLE-05').",
                }
            },
        },
    },
]


class MegabankMCPHandler:
    """MCP ツール呼び出しおよび JSON-RPC 2.0 メッセージ処理ハンドラ"""

    def __init__(self, prefer_remote: Optional[bool] = None):
        self.rapidapi_key = os.environ.get("RAPIDAPI_KEY", "").strip()
        self.platform_api_key = os.environ.get("JAPAN_DATA_API_KEY", "").strip()
        self.base_url = DEFAULT_API_BASE_URL.rstrip("/")
        if prefer_remote is not None:
            self.use_remote = prefer_remote
        else:
            self.use_remote = bool(self.rapidapi_key or (self.platform_api_key and os.environ.get("JAPAN_DATA_API_URL")))
        self._local_client = None

    def _get_local_client(self):
        if self._local_client is None:
            if str(ROOT_DIR) not in sys.path:
                sys.path.insert(0, str(ROOT_DIR))
            if str(API_DIR) not in sys.path:
                sys.path.insert(0, str(API_DIR))
            os.environ.setdefault("ENVIRONMENT", "development")
            os.environ.setdefault("ALLOW_INSECURE_DEV", "true")
            from fastapi.testclient import TestClient
            import main as api_main
            self._local_client = TestClient(api_main.app)
        return self._local_client

    def _local_headers(self) -> Dict[str, str]:
        import config as api_cfg
        proxy_secret = os.environ.get("RAPIDAPI_PROXY_SECRET") or getattr(api_cfg, "RAPIDAPI_PROXY_SECRET", "")
        headers = {
            "X-RapidAPI-User": "mcp_local_agent",
            "X-RapidAPI-Subscription": "MEGA",
        }
        if proxy_secret:
            headers["X-RapidAPI-Proxy-Secret"] = proxy_secret
        if self.platform_api_key:
            headers["X-API-Key"] = self.platform_api_key
        elif not proxy_secret and getattr(api_cfg, "API_KEYS", None):
            first_key = next(iter(api_cfg.API_KEYS.keys()), None)
            if first_key:
                headers["X-API-Key"] = first_key
        return headers

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        if not self.use_remote:
            client = self._get_local_client()
            headers = self._local_headers()
            if method.upper() == "GET":
                resp = client.get(path, params=clean_params, headers=headers)
            else:
                resp = client.post(path, params=clean_params, json=json_body, headers=headers)
            try:
                body = resp.json()
                if resp.status_code >= 400 and isinstance(body, dict):
                    body.setdefault("status", "error")
                    body.setdefault("status_code", resp.status_code)
                return body
            except Exception:
                return {"status": "error", "status_code": resp.status_code, "detail": resp.text}

        # Remote HTTP Mode (RapidAPI / Direct Platform URL)
        query_str = urllib.parse.urlencode(clean_params)
        url = f"{self.base_url}{path}"
        if query_str:
            url = f"{url}?{query_str}"

        headers = {
            "Accept": "application/json",
            "User-Agent": f"{SERVER_NAME}/{SERVER_VERSION}",
        }
        if self.rapidapi_key:
            headers["X-RapidAPI-Key"] = self.rapidapi_key
            headers["X-RapidAPI-Host"] = DEFAULT_RAPIDAPI_HOST
        elif self.platform_api_key:
            headers["X-API-Key"] = self.platform_api_key

        data_bytes = None
        if json_body is not None:
            data_bytes = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(err_body)
                if isinstance(body, dict):
                    body.setdefault("status", "error")
                    body.setdefault("status_code", exc.code)
                return body
            except Exception:
                return {"status": "error", "status_code": exc.code, "detail": err_body}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}

        if name == "list_japan_datasets":
            q = args.get("query")
            limit = min(max(int(args.get("limit", 25)), 1), 155)
            res = self._request("GET", "/api/v1/catalog/", params={"q": q})
            if isinstance(res, dict) and isinstance(res.get("data"), list):
                res = dict(res)
                res["returned_datasets"] = len(res["data"][:limit])
                res["data"] = res["data"][:limit]
            return res

        if name == "describe_japan_dataset":
            dataset_id = str(args.get("dataset_id", "")).strip()
            if not dataset_id:
                return {"status": "error", "detail": "dataset_id is required."}
            return self._request("GET", f"/api/v1/catalog/{dataset_id}")

        if name == "search_japan_official_data":
            raw_id = str(args.get("dataset_id", "")).strip().lower()
            if not raw_id:
                return {"status": "error", "detail": "dataset_id is required."}
            norm_id = raw_id.replace("-", "_")
            endpoint_path = f"/api/v1/{raw_id.replace('_', '-')}/"
            try:
                from routers.catalog import DATASET_ENDPOINT_PATHS
                if norm_id in DATASET_ENDPOINT_PATHS:
                    endpoint_path = DATASET_ENDPOINT_PATHS[norm_id]
            except Exception:
                pass
            limit = min(max(int(args.get("limit", 10)), 1), 100)
            params = {
                "prefecture": args.get("prefecture"),
                "municipality_code": args.get("municipality_code"),
                "corporate_number": args.get("corporate_number"),
                "q": args.get("q"),
                "limit": limit,
            }
            return self._request("GET", endpoint_path, params=params)

        if name == "execute_japan_megabank_sql":
            sql = str(args.get("sql", "")).strip()
            if not sql:
                return {"status": "error", "detail": "sql query string is required."}
            return self._request("POST", "/api/v1/query/", json_body={"sql": sql})

        if name == "list_flagship_b2b_bundles":
            bundle_code = args.get("bundle_code")
            return self._request("GET", "/api/v1/catalog/bundles", params={"bundle_code": bundle_code})

        raise ValueError(f"Unknown MCP tool: {name}")

    def handle_jsonrpc_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """JSON-RPC 2.0 リクエストを処理し、レスポンス辞書を返す（通知の場合は None）。"""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        # Notification (no id)
        if msg_id is None:
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": MCP_TOOLS},
            }

        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            try:
                output = self.call_tool(tool_name, tool_args)
                is_err = isinstance(output, dict) and (
                    output.get("status") == "error"
                    or int(output.get("status_code", 200) or 200) >= 400
                    or ("detail" in output and "status" not in output)
                )
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(output, ensure_ascii=False, indent=2),
                            }
                        ],
                        "isError": is_err,
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error executing tool '{tool_name}': {exc}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def run_stdio_server() -> None:
    """MCP 標準入出力 (stdio) ループを起動する。"""
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stdin and hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    handler = MegabankMCPHandler()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        resp = handler.handle_jsonrpc_message(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
