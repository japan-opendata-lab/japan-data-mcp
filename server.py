"""
mcp_server/server.py — Japan Official Data MCP Server (Model Context Protocol)

Claude Desktop, Cursor, Windsurf, Cline, LangChain 等の AI エージェントから
日本の公的オープンデータ（全155データセット・1,016万件超：人口、地価、全省庁入札GEPS、
医療・病院、再エネ・系統空き容量、上場企業、防災ハザード等）を英語・日本語で直接検索・SQL集計できる
公式 MCP (JSON-RPC 2.0 over stdio) サーバー実装。
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

DEFAULT_RAPIDAPI_HOST = os.environ.get(
    "RAPIDAPI_HOST",
    "japan-official-data-megabank-api-us-standard-normalized.p.rapidapi.com",
)
DEFAULT_API_BASE_URL = os.environ.get(
    "JAPAN_DATA_API_URL", f"https://{DEFAULT_RAPIDAPI_HOST}"
)

DUMMY_KEYS = {
    "",
    "test_key",
    "test_dummy_key",
    "dummy",
    "your_rapidapi_key",
    "your_api_key",
    "123",
}

FALLBACK_DATASETS = [
    {
        "dataset_id": "procurement",
        "title_en": "Government Procurement & Winning Bids (GEPS)",
        "records": 83097,
        "coverage": "2020-2026",
    },
    {
        "dataset_id": "companies",
        "title_en": "13-Digit Corporate Registry & Invoice Master",
        "records": 5200000,
        "coverage": "Latest",
    },
    {
        "dataset_id": "medical",
        "title_en": "National Hospitals, Clinics & Pharmacies Master",
        "records": 382606,
        "coverage": "Latest",
    },
    {
        "dataset_id": "real_estate",
        "title_en": "Official Land Prices & Real Estate Transactions",
        "records": 26000,
        "coverage": "1983-2026",
    },
    {
        "dataset_id": "demographics",
        "title_en": "1,741 Municipalities Demographics & Projections",
        "records": 21642,
        "coverage": "2000-2026",
    },
]

FALLBACK_BUNDLES = [
    {
        "bundle_code": "BUNDLE-01",
        "title": "Real Estate Development & Trade Area Marketing All-in-One Pack",
        "datasets_included": 7,
        "records": 20138,
        "price_jpy": 49800,
    },
    {
        "bundle_code": "BUNDLE-02",
        "title": "Government Procurement (GEPS) & B2B Enterprise Targeting Pack",
        "datasets_included": 7,
        "records": 83097,
        "price_jpy": 59800,
    },
    {
        "bundle_code": "BUNDLE-03",
        "title": "National Healthcare, Hospitals & Nursing Care Strategy Pack",
        "datasets_included": 8,
        "records": 382606,
        "price_jpy": 59800,
    },
    {
        "bundle_code": "BUNDLE-04",
        "title": "Renewable Energy, Grid Capacity & GX Investment Pack",
        "datasets_included": 8,
        "records": 119020,
        "price_jpy": 69800,
    },
    {
        "bundle_code": "BUNDLE-05",
        "title": "1,741 Municipalities Finance, Waterworks & Disaster Resilience Master",
        "datasets_included": 9,
        "records": 21642,
        "price_jpy": 79800,
    },
]


MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "list_japan_datasets",
        "description": (
            "Discover and list available dataset IDs, titles, record counts, and coverage years across all 155 official "
            "Japanese datasets in Japan Official Data Megabank (demographics, real_estate, procurement, companies, medical, "
            "renewable_energy, grid_capacity, etc.). "
            "WHEN TO USE: Call this tool first when you do not know the exact 'dataset_id' to query. "
            "NEXT STEP: Pass a discovered 'dataset_id' to 'describe_japan_dataset' to inspect columns, or directly to "
            "'search_japan_official_data' to fetch rows. "
            "WHEN NOT TO USE: Do not use this tool to fetch actual data rows (use 'search_japan_official_data' instead) "
            "or B2B bulk product bundles (use 'list_flagship_b2b_bundles')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Optional case-insensitive keyword filter in English or Japanese to match dataset IDs or titles "
                        "(e.g., 'procurement', 'hospital', 'solar', '入札', '医療'). If omitted, returns the top catalog entries."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of dataset catalog entries to return (1 to 155, default: 25).",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 155,
                },
            },
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "total": {
                    "type": "integer",
                    "description": "Total number of datasets available in the catalog.",
                },
                "datasets": {
                    "type": "array",
                    "description": "List of matching dataset metadata objects containing dataset_id, title_en, records, and coverage.",
                    "items": {"type": "object"},
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "audience": ["user", "assistant"],
            "priority": 1.0,
        },
    },
    {
        "name": "describe_japan_dataset",
        "description": (
            "Retrieve the exact column schema, data types, historical coverage range, primary government ministry source, "
            "and a representative sample record (including English 'prefecture_en' and 'city_en') for a single dataset. "
            "WHEN TO USE: Call this after 'list_japan_datasets' and before 'execute_japan_megabank_sql' or "
            "'search_japan_official_data' to verify exact column names and data formats. "
            "WHEN NOT TO USE: Do not use this to search or filter multiple records (use 'search_japan_official_data' "
            "for filtered rows or 'execute_japan_megabank_sql' for aggregations)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": (
                        "Exact dataset identifier obtained from 'list_japan_datasets' "
                        "(lowercase snake_case, e.g., 'demographics', 'procurement', 'medical', 'renewable_energy', 'companies')."
                    ),
                }
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "The inspected dataset identifier.",
                },
                "schema": {
                    "type": "object",
                    "description": "Mapping of column names to their data types and formats.",
                },
                "sample_record": {
                    "type": "object",
                    "description": "A single sanitized sample row demonstrating actual field values.",
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "audience": ["user", "assistant"],
            "priority": 0.9,
        },
    },
    {
        "name": "search_japan_official_data",
        "description": (
            "Fetch and filter actual data records from a single dataset using standardized parameters "
            "(prefecture name, 5-digit JIS municipality code, 13-digit corporate number, target year with strict out-of-range validation, "
            "or free-text keyword). Multiple filters are combined using logical AND. "
            "WHEN TO USE: Use for fast, single-table record lookups and filtered sampling once you know the 'dataset_id'. "
            "WHEN NOT TO USE: Do not use for discovering dataset IDs (use 'list_japan_datasets'), inspecting column schemas "
            "(use 'describe_japan_dataset'), or performing cross-table JOINs and GROUP BY aggregations (use 'execute_japan_megabank_sql')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": (
                        "Target dataset ID obtained from 'list_japan_datasets' "
                        "(e.g., 'demographics', 'procurement', 'medical', 'companies', 'land_prices_official', 'real_estate')."
                    ),
                },
                "prefecture": {
                    "type": "string",
                    "description": (
                        "Optional prefecture filter in English romaji or Japanese kanji "
                        "(e.g., 'Tokyo', 'Osaka', 'Hokkaido', '東京都'). Case-insensitive."
                    ),
                },
                "municipality_code": {
                    "type": "string",
                    "description": (
                        "Optional 5-digit JIS municipality code string with leading zero preserved "
                        "(e.g., '13101' for Chiyoda-ku, '01101' for Sapporo)."
                    ),
                },
                "corporate_number": {
                    "type": "string",
                    "description": (
                        "Optional exact 13-digit Japan National Tax Agency corporate number string "
                        "(e.g., '1000012010019') or 10-digit US SEC CIK."
                    ),
                },
                "year": {
                    "type": "integer",
                    "description": (
                        "Optional target year in 4-digit format (e.g., 2024, 2025). "
                        "If outside dataset_available_range, returns 0 rows with an explicit range message instead of guessing from other years."
                    ),
                },
                "q": {
                    "type": "string",
                    "description": (
                        "Optional case-insensitive free-text substring search across company names, "
                        "facility names, address fields, or contract titles (e.g., 'Cloud', 'Hospital')."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of matching records to return (1 to 100, default: 10).",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of records returned or matched.",
                },
                "dataset_available_range": {
                    "type": "string",
                    "description": "Official historical range of this dataset.",
                },
                "primary_source": {
                    "type": "string",
                    "description": "Primary publishing government agency.",
                },
                "unit_and_field_semantics": {
                    "type": "object",
                    "description": "Explicit unit, date, and ID semantics.",
                },
                "records": {
                    "type": "array",
                    "description": "Array of normalized record objects matching the filter criteria.",
                    "items": {"type": "object"},
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "audience": ["user", "assistant"],
            "priority": 1.0,
        },
    },
    {
        "name": "execute_japan_megabank_sql",
        "description": (
            "Execute a read-only DuckDB SQL SELECT query across all 155 mounted datasets (10.16M+ records). "
            "Enables complex aggregations (COUNT, SUM, AVG, GROUP BY) and multi-table JOINs using 'municipality_code' "
            "(5-digit JIS code) or 'corporate_number' (13-digit ID). Enforces AST validation (single SELECT only, max 10,000 rows). "
            "PREREQUISITE: Requires a MEGA tier subscription on RapidAPI or local database access; always call "
            "'describe_japan_dataset' first to confirm table and column names. "
            "WHEN NOT TO USE: Do not use for simple single-table keyword or prefecture lookups (use 'search_japan_official_data' "
            "instead, which works on all tiers including BASIC) or for browsing available tables (use 'list_japan_datasets')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": (
                        "Single read-only DuckDB SQL SELECT statement. DDL/DML statements are rejected. "
                        "Always include a LIMIT clause (e.g., 'SELECT prefecture_en, COUNT(*) AS cnt FROM medical GROUP BY 1 ORDER BY 2 DESC LIMIT 10')."
                    ),
                }
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "row_count": {
                    "type": "integer",
                    "description": "Number of result rows returned by the SQL query.",
                },
                "columns": {
                    "type": "array",
                    "description": "Ordered list of column names in the query result.",
                    "items": {"type": "string"},
                },
                "rows": {
                    "type": "array",
                    "description": "List of result row objects mapped by column name.",
                    "items": {"type": "object"},
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "audience": ["user", "assistant"],
            "priority": 0.8,
        },
    },
    {
        "name": "list_flagship_b2b_bundles",
        "description": (
            "List the 5 Flagship Enterprise All-in-One Data Bundles (BUNDLE-01 Real Estate, BUNDLE-02 Government Procurement, "
            "BUNDLE-03 Healthcare, BUNDLE-04 Renewable Energy/GX, BUNDLE-05 Municipal Finance/Resilience) with included dataset counts, "
            "total records, JPY pricing, discount rates, and qualified B2B invoice availability. "
            "WHEN TO USE: Use only when the user asks about bulk downloadable ZIP packages, enterprise pricing, or B2B invoice options. "
            "WHEN NOT TO USE: Do not use for listing individual API datasets (use 'list_japan_datasets') or querying actual data "
            "records (use 'search_japan_official_data')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle_code": {
                    "type": "string",
                    "description": (
                        "Optional exact bundle identifier from 'BUNDLE-01' to 'BUNDLE-05' (case-insensitive). "
                        "If omitted, returns all 5 flagship bundles."
                    ),
                }
            },
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "total": {
                    "type": "integer",
                    "description": "Number of flagship bundles returned.",
                },
                "bundles": {
                    "type": "array",
                    "description": "List of bundle metadata objects with bundle_code, title, datasets_included, records, and price_jpy.",
                    "items": {"type": "object"},
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "audience": ["user", "assistant"],
            "priority": 0.9,
        },
    },
]

STANDALONE_EARLIEST_YEARS: Dict[str, int] = {
    "macro": 1986,
    "energy": 1983,
    "sec_form13f": 2001,
    "sec_insider": 2006,
    "crime": 1960,
    "climate": 2016,
    "procurement": 2020,
    "logistics": 2016,
    "patents": 2021,
    "wages": 2023,
    "demographics": 2023,
    "real_estate": 2026,
    "land_prices_official": 1983,
}

STANDALONE_AVAILABLE_RANGES: Dict[str, str] = {
    "macro": "1986-2026 (41 Years)",
    "energy": "1983-2026 (44 Years)",
    "sec_form13f": "2001-2026 (26 Years)",
    "sec_insider": "2006-2026 (21 Years)",
    "crime": "1960-2024 (65 Years)",
    "climate": "2016-2026 (11 Years)",
    "procurement": "2020-2026 (7 Years - 100% of official GEPS electronic records)",
    "logistics": "2016-2024 (9 Years)",
    "patents": "2021-2023 (3 Years - JPO/USPTO Top Rankings)",
    "wages": "2023-2024 (2 Years - Latest official MHLW/BLS snapshot)",
    "demographics": "2023-2024 (2 Years - Latest official census/tax income)",
    "real_estate": "2026 (Latest FHFA HPI & Land Price Snapshot - 1 Year)",
    "land_prices_official": "1983-2026 (44 Years - MLIT Official Land Price Points)",
}


class MegabankMCPHandler:
    """MCP ツール呼び出しおよび JSON-RPC 2.0 メッセージ処理ハンドラ"""

    def __init__(self, prefer_remote: Optional[bool] = None):
        self.rapidapi_key = os.environ.get("RAPIDAPI_KEY", "").strip()
        self.platform_api_key = os.environ.get("JAPAN_DATA_API_KEY", "").strip()
        self.base_url = DEFAULT_API_BASE_URL.rstrip("/")
        if prefer_remote is not None:
            self.use_remote = prefer_remote
        else:
            self.use_remote = bool(
                self.rapidapi_key
                or (self.platform_api_key and os.environ.get("JAPAN_DATA_API_URL"))
            )
        self._local_client = None

    def _is_dummy_key(self) -> bool:
        return self.rapidapi_key.lower() in DUMMY_KEYS and not self.platform_api_key

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

        proxy_secret = os.environ.get("RAPIDAPI_PROXY_SECRET") or getattr(
            api_cfg, "RAPIDAPI_PROXY_SECRET", ""
        )
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

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_params = {
            k: v for k, v in (params or {}).items() if v is not None and v != ""
        }
        if not self.use_remote:
            try:
                client = self._get_local_client()
                headers = self._local_headers()
                if method.upper() == "GET":
                    resp = client.get(path, params=clean_params, headers=headers)
                else:
                    resp = client.post(
                        path, params=clean_params, json=json_body, headers=headers
                    )
                body = resp.json()
                if resp.status_code >= 400 and isinstance(body, dict):
                    body.setdefault("status", "error")
                    body.setdefault("status_code", resp.status_code)
                return body
            except Exception:
                pass

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

        req = urllib.request.Request(
            url, data=data_bytes, headers=headers, method=method.upper()
        )
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
                return {
                    "status": "error",
                    "status_code": exc.code,
                    "detail": err_body,
                }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    def _resolve_dataset_metadata(self, norm_id: str) -> Dict[str, Any]:
        avail_range = STANDALONE_AVAILABLE_RANGES.get(
            norm_id, "2020-2026 / Latest Official Registry Snapshot"
        )
        earliest_year = STANDALONE_EARLIEST_YEARS.get(norm_id)
        prim_source = "Japan Official Government Open Data (e-Stat / GEPS / NTA / MLIT / MHLW)"
        semantics = {
            "dataset_id": norm_id,
            "primary_publisher": prim_source,
            "dataset_available_range": avail_range,
            "monetary_unit_rule": (
                "All monetary columns (*_jpy, capital_amount_jpy, amount_jpy) are normalized to exact 1-JPY units "
                "(already expanded from thousand/million-yen government tables). *_usd columns are in exact 1-USD units."
            ),
            "date_semantics_rule": (
                "All dates use ISO-8601 (YYYY-MM-DD, converted from Japanese imperial eras). "
                "'founded_date' / 'established_date' / 'contract_date' represents the official event, contract, or establishment reference date; "
                "'updated_at' represents the publication or pipeline refresh date."
            ),
            "entity_identifier_rule": (
                "'corporate_number' is a 13-digit zero-padded string (Japan National Tax Agency ID) or 10-digit US SEC CIK; "
                "'municipality_code' is a 5-digit zero-padded string (JIS Municipality Code)."
            ),
        }
        return {
            "primary_source": prim_source,
            "dataset_available_range": avail_range,
            "earliest_year": earliest_year,
            "latest_year": 2026,
            "unit_and_field_semantics": semantics,
        }

    def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        args = arguments or {}

        if name == "list_japan_datasets":
            q = str(args.get("query") or "").strip().lower()
            limit = min(max(int(args.get("limit", 25)), 1), 155)
            if self._is_dummy_key():
                items = [
                    d
                    for d in FALLBACK_DATASETS
                    if not q
                    or q in d["dataset_id"].lower()
                    or q in d["title_en"].lower()
                ][:limit]
                return {"total": 155, "datasets": items}
            res = self._request("GET", "/api/v1/catalog/", params={"q": q or None})
            if isinstance(res, dict) and "datasets" not in res:
                data_list = res.get("data") if isinstance(res.get("data"), list) else []
                return {
                    "total": int(res.get("total", len(data_list))),
                    "datasets": data_list[:limit],
                }
            return res

        if name == "describe_japan_dataset":
            dataset_id = str(args.get("dataset_id", "")).strip() or "procurement"
            if self._is_dummy_key():
                return {
                    "dataset_id": dataset_id,
                    "schema": {
                        "record_id": "string",
                        "corporate_number": "string (13-digit)",
                        "municipality_code": "string (5-digit JIS)",
                        "prefecture_en": "string",
                        "city_en": "string",
                        "latitude": "float (WGS84)",
                        "longitude": "float (WGS84)",
                    },
                    "sample_record": {
                        "dataset_id": dataset_id,
                        "prefecture_en": "Tokyo",
                        "city_en": "Chiyoda-ku",
                        "municipality_code": "13101",
                        "note": "Sandbox preview mode. Provide a valid RapidAPI key for live records.",
                    },
                }
            res = self._request("GET", f"/api/v1/catalog/{dataset_id}")
            if (
                isinstance(res, dict)
                and "schema" not in res
                and res.get("status") != "error"
            ):
                return {
                    "dataset_id": dataset_id,
                    "schema": res.get("columns", res),
                    "sample_record": res.get("sample", {}),
                }
            return res

        if name == "search_japan_official_data":
            raw_id = str(args.get("dataset_id", "")).strip().lower() or "procurement"
            limit = min(max(int(args.get("limit", 10)), 1), 100)
            norm_id = raw_id.replace("-", "_")
            meta = self._resolve_dataset_metadata(norm_id)

            raw_year = args.get("year")
            year_val: Optional[int] = None
            if raw_year is not None and str(raw_year).strip() != "":
                try:
                    year_val = int(str(raw_year).strip())
                except ValueError:
                    return {
                        "status": "error",
                        "status_code": 400,
                        "error_code": "INVALID_YEAR_FORMAT",
                        "dataset_id": norm_id,
                        "dataset_available_range": meta["dataset_available_range"],
                        "detail": f"Invalid year parameter: '{raw_year}'. Expected a 4-digit integer year.",
                    }
                earliest = meta.get("earliest_year")
                latest = meta.get("latest_year") or 2026
                effective_earliest = earliest if earliest is not None else 2020
                if year_val < effective_earliest or year_val > latest:
                    return {
                        "status": "error",
                        "status_code": 400,
                        "error_code": "YEAR_OUT_OF_AVAILABLE_RANGE",
                        "dataset_id": norm_id,
                        "requested_year": year_val,
                        "dataset_available_range": meta["dataset_available_range"],
                        "primary_source": meta["primary_source"],
                        "unit_and_field_semantics": meta["unit_and_field_semantics"],
                        "count": 0,
                        "total": 0,
                        "data": [],
                        "records": [],
                        "detail": (
                            f"Requested year {year_val} is outside the official available range "
                            f"({meta['dataset_available_range']}) for dataset '{norm_id}'. "
                            f"Returning 0 rows instead of substituting records from the nearest available year."
                        ),
                    }

            if self._is_dummy_key():
                return {
                    "count": 1,
                    "dataset_id": norm_id,
                    "primary_source": meta["primary_source"],
                    "dataset_available_range": meta["dataset_available_range"],
                    "unit_and_field_semantics": meta["unit_and_field_semantics"],
                    "records": [
                        {
                            "dataset_id": raw_id,
                            "prefecture_en": args.get("prefecture") or "Tokyo",
                            "municipality_code": args.get("municipality_code")
                            or "13101",
                            "status": "preview_mode",
                            "get_free_api_key": "https://rapidapi.com/organization/japan-opendata-lab",
                        }
                    ],
                }

            endpoint_path = f"/api/v1/{raw_id.replace('_', '-')}/"
            try:
                from routers.catalog import DATASET_ENDPOINT_PATHS

                if norm_id in DATASET_ENDPOINT_PATHS:
                    endpoint_path = DATASET_ENDPOINT_PATHS[norm_id]
            except Exception:
                pass
            params: Dict[str, Any] = {
                "prefecture": args.get("prefecture"),
                "municipality_code": args.get("municipality_code"),
                "corporate_number": args.get("corporate_number"),
                "q": args.get("q"),
                "limit": limit,
            }
            if year_val is not None:
                params["year"] = year_val
            res = self._request("GET", endpoint_path, params=params)
            if isinstance(res, dict):
                res = dict(res)
                res.setdefault("dataset_id", norm_id)
                res.setdefault("primary_source", meta["primary_source"])
                res.setdefault("dataset_available_range", meta["dataset_available_range"])
                res.setdefault("unit_and_field_semantics", meta["unit_and_field_semantics"])
                if "records" not in res and res.get("status") != "error":
                    recs = res.get("data") if isinstance(res.get("data"), list) else []
                    res["count"] = int(res.get("total", len(recs)))
                    res["records"] = recs
            return res

        if name == "execute_japan_megabank_sql":
            sql = str(args.get("sql", "")).strip()
            if not sql:
                return {"status": "error", "detail": "sql query string is required."}
            if self._is_dummy_key():
                return {
                    "row_count": 1,
                    "columns": ["status", "message", "executed_sql"],
                    "rows": [
                        {
                            "status": "preview_mode",
                            "message": "Provide a valid RapidAPI MEGA tier key to execute live DuckDB SQL.",
                            "executed_sql": sql,
                        }
                    ],
                }
            res = self._request("POST", "/api/v1/query/", json_body={"sql": sql})
            if (
                isinstance(res, dict)
                and "rows" not in res
                and res.get("status") != "error"
            ):
                rows = res.get("data") if isinstance(res.get("data"), list) else []
                cols = (
                    list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
                )
                return {"row_count": len(rows), "columns": cols, "rows": rows}
            return res

        if name == "list_flagship_b2b_bundles":
            bundle_code = str(args.get("bundle_code") or "").strip().upper()
            if self._is_dummy_key():
                bundles = [
                    b
                    for b in FALLBACK_BUNDLES
                    if not bundle_code or b["bundle_code"] == bundle_code
                ]
                return {"total": len(bundles), "bundles": bundles}
            res = self._request(
                "GET",
                "/api/v1/catalog/bundles",
                params={"bundle_code": bundle_code or None},
            )
            if (
                isinstance(res, dict)
                and "bundles" not in res
                and res.get("status") != "error"
            ):
                b_list = (
                    res.get("data")
                    if isinstance(res.get("data"), list)
                    else FALLBACK_BUNDLES
                )
                return {"total": len(b_list), "bundles": b_list}
            return res

        raise ValueError(f"Unknown MCP tool: {name}")

    def handle_jsonrpc_message(
        self, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """JSON-RPC 2.0 リクエストを処理し、レスポンス辞書を返す（通知の場合は None）。"""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

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
                result_payload: Dict[str, Any] = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                output, ensure_ascii=False, indent=2
                            ),
                        }
                    ],
                    "isError": is_err,
                }
                if not is_err and isinstance(output, dict):
                    result_payload["structuredContent"] = output

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": result_payload,
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing tool '{tool_name}': {exc}",
                            }
                        ],
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
