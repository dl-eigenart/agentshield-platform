# @eigenart/agentshield-mcp

Official **MCP (Model Context Protocol) server** for [AgentShield](https://agentshield.pro) — detect prompt-injection, jailbreak, and social-engineering attempts in text before your agent processes it.

Works with any MCP-compatible client: Claude Desktop, Cursor, Cline, Zed, Continue, and custom agents.

## What it does

Exposes one tool to the agent: `classify_text`. Call it on any untrusted text (user messages, retrieved documents, web scrapes, third-party tool outputs) and get back a verdict.

```json
{
  "is_injection": true,
  "confidence": 0.94,
  "category": "jailbreak",
  "latency_ms": 2.4,
  "model": "agentshield-minilm-v2",
  "request_id": "req_01HX…"
}
```

Classifier is hosted at `api.agentshield.dev`. No local GPU, no model download. Free tier: 100 classifications/day, no credit card.

## Install (Claude Desktop)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "agentshield": {
      "command": "npx",
      "args": ["-y", "@eigenart/agentshield-mcp"],
      "env": {
        "AGENTSHIELD_API_KEY": "ask_your_key_here"
      }
    }
  }
}
```

Restart Claude Desktop. The `classify_text` tool will be available.

## Install (Cursor / Cline / Zed / Continue)

Same pattern — each client has its own MCP config path, but the command + env block are identical to the Claude Desktop snippet above. See your client's MCP docs for the exact file.

## Get an API key

Free tier, no credit card: [agentshield.pro/signup](https://agentshield.pro/signup).

## Usage pattern (for your agent)

The tool description already tells the agent when to use this, but the core rule is:

> Before your agent processes any **external/untrusted text**, call `classify_text`. If `is_injection=true` and `confidence ≥ 0.8`, refuse to act and escalate.

Typical sources of untrusted text:
- User messages from public channels
- RAG / retrieved documents / web scrapes
- Tool-call results from third-party services
- Filenames, issue titles, commit messages from external contributors

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AGENTSHIELD_API_KEY` | yes | — | Your API key from agentshield.pro |
| `AGENTSHIELD_BASE_URL` | no | `https://api.agentshield.dev` | Override for self-hosted gateway |

## Benchmark

Public, reproducible: [agentshield.pro/benchmark](https://agentshield.pro/benchmark)

- F1: **0.921** on 5,972 samples (EN/DE/ES/ZH/FR + encoding-obfuscation)
- Latency: **p50 2.44 ms, p95 3.80 ms** (single RTX 5090)
- Dataset and scoring script are open source.

## Roadmap

- **v0.2** — `check_output` tool (output-side secret/PII leak detection, layer 3 of the Gateway)
- **v0.2** — `get_usage` tool (rate-limit status for the current API key, so the agent can self-manage budget)
- **v0.3** — streaming / batch classification
- **v0.3** — local-first mode (ship a distilled classifier in the package, zero network)

File issues at [github.com/dl-eigenart/agentshield-platform/issues](https://github.com/dl-eigenart/agentshield-platform/issues).

## Related

- Python SDK — `pip install agentshield`
- ElizaOS plugin (Solana transaction guard) — [`@eigenart/agentshield`](https://www.npmjs.com/package/@eigenart/agentshield)
- Full product & pricing — [agentshield.pro](https://agentshield.pro)

## License

MIT © Eigenart Filmproduktion. See `LICENSE`.
