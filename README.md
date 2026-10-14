# Model Context Protocol (MCP) Server for Japanese Public Open Data (`japan-data-mcp`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Standard](https://img.shields.io/badge/MCP-JSON--RPC%202.0-blue)](https://modelcontextprotocol.io/)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![RapidAPI Hub](https://img.shields.io/badge/Production%20API-RapidAPI%20Hub-orange)](https://rapidapi.com/organization/japan-opendata-lab)

**Model Context Protocol (MCP) Server for Japanese Public Open Data (maintained independently by Japan Open Data Lab).**

Connect **Claude Desktop, Cursor, Windsurf, Cline, and LangChain** agents directly to clean, standardized Japanese government open data.

---

## ⚡ Quick Start (Claude Desktop / Cursor)

### Option 1: Direct Run via Python (Zero Dependencies)

Add the following to your Claude Desktop configuration file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "japan-data-mcp": {
      "command": "python",
      "args": ["-m", "server"],
      "env": {
        "RAPIDAPI_KEY": "YOUR_RAPIDAPI_KEY_HERE"
      }
    }
  }
}
```

### Option 2: Run in Cursor IDE

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "japan-data-mcp": {
      "command": "python server.py",
      "env": {
        "RAPIDAPI_KEY": "YOUR_RAPIDAPI_KEY_HERE"
      }
    }
  }
}
```

---

## 🛠️ Available MCP Tools

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `list_japan_datasets` | `query`, `limit` | Search and list across 155 normalized Japanese public datasets in English or Japanese. |
| `describe_japan_dataset` | `dataset_id` | Inspect schema definitions, historical time-series range, primary sources, and sample rows. |
| `search_japan_official_data` | `dataset_id`, `prefecture`, `municipality_code`, `corporate_number`, `q` | Fast targeted search filtered by English/Japanese prefecture name, 5-digit JIS code, or 13-digit Corporate ID. |
| `execute_japan_megabank_sql` | `sql` | Execute multi-table in-memory analytical DuckDB SQL queries across datasets (MEGA tier / local). |

---

## 💡 Example Prompts to Ask Your AI Agent

Once connected, your AI assistant can execute prompts like:

- *"Using `search_japan_official_data`, find the top 5 central government tender awards in `procurement` related to AI or cloud infrastructure."*
- *"Look up Tokyo's Minato-ku and Shibuya-ku in `demographics` and compare their per capita taxable income and aging rate."*
- *"Use `execute_japan_megabank_sql` to calculate the total public procurement amount won by company with corporate_number '1010001008844'."*
- *"Find all hospitals with more than 300 beds in Osaka from `medical`."*

---

## 📦 Data Domains Covered

- **Government Procurement (GEPS)**: 2020–2026 Nationwide central ministry contract awards (100% electronic disclosure archive).
- **Corporate Tax Registry**: Nationwide registered commercial entities (13-digit NTA key, zero PII).
- **Land Valuation Benchmark (MLIT)**: 1983–2026 (44-year archive) official land price points.
- **Healthcare & Senior Care**: 220,000+ hospitals/clinics and 250,000+ nursing care welfare facilities.
- **Demographics & Public Finance**: All 1,741 Japanese municipalities (taxable income, population, aging).
- **GHG Emissions**: Mandatory industrial emission disclosures from Ministry of the Environment.

---

## 🔑 Authentication & API Access

This MCP server connects to the live **[Japan Official Data Megabank API](https://rapidapi.com/organization/japan-opendata-lab)** on RapidAPI.
- **BASIC Tier**: Free ($0/mo, 50 requests/mo) for testing and development.
- **PRO / ULTRA / MEGA Tiers**: High-volume quotas, 40+ year archives, and direct multi-table DuckDB SQL execution.

Get your API key at: **[RapidAPI Hub](https://rapidapi.com/organization/japan-opendata-lab)**

---

## ⚠️ Disclaimer & Attribution

- **Independent Project**: This MCP server is developed and maintained independently by **Japan Open Data Lab**.
- **Not Government Affiliated**: This project is **not** endorsed by, operated by, or affiliated with the Government of Japan or any public ministry.
- **Source Attribution**: All underlying public domain/CC BY data is cited with full attribution to original government ministries pursuant to the Government of Japan Standard Terms of Use (Version 2.0).

---

## 📄 License & Attribution

- **MCP Server Code**: [MIT License](LICENSE)
- **Source Data**: Government of Japan Standard Terms of Use v2.0 (CC BY 4.0 compatible).
- **Maintained by**: Japan Open Data Lab (`japan.opendata.lab@gmail.com`)
