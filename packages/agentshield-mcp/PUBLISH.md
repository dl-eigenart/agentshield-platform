# Publish checklist — @eigenart/agentshield-mcp

Internal notes for releasing the MCP to the ecosystems where agents discover it.
Do NOT ship this file to npm (it's in `.npmignore`).

## 0. Preflight

```bash
cd packages/agentshield-mcp
npm install
npm run build
node dist/index.js    # should print "[agentshield-mcp] v0.1.0 running on stdio." to stderr then wait
# Ctrl-C to exit.
```

Smoke test against a real key:
```bash
AGENTSHIELD_API_KEY=ask_test_... node dist/index.js
# In another terminal, use an MCP test client to call classify_text.
```

## 1. npm publish

First-time setup (once per machine):
```bash
npm login   # use the @eigenart org account
```

Release:
```bash
# bump version in package.json first (start at 0.1.0)
npm publish --access public
```

Confirm at: https://www.npmjs.com/package/@eigenart/agentshield-mcp

## 2. Smithery submission

Smithery is the largest MCP directory; being listed there is the single highest-impact discoverability win.

1. Go to https://smithery.ai and sign in with GitHub.
2. Click "Submit a server".
3. Repo URL: `https://github.com/dl-eigenart/agentshield-platform`
4. Package path: `packages/agentshield-mcp`
5. Smithery will parse `package.json` and the tool schema automatically.
6. Category: **Security** (primary), **AI / Guardrails** (secondary).

## 3. Anthropic MCP Registry

Official registry, curated. Lower volume than Smithery but higher trust signal.

1. Fork `modelcontextprotocol/servers` on GitHub.
2. Add an entry under `community/` (not `reference/` — that's Anthropic-maintained).
3. PR with:
   - Name: `agentshield`
   - One-line: "Detect prompt-injection and jailbreak attempts in text before your agent processes it."
   - Link to this package's README.
4. Tag `@jspahrsummers` or current MCP maintainer for review.

## 4. Claude Desktop Extensions (.dxt)

Once npm is live, create a `.dxt` bundle so users can one-click-install in Claude Desktop:

1. Use `@anthropic-ai/dxt` CLI: `npx @anthropic-ai/dxt init` in the package.
2. Fill in manifest: name, description, icon, API-key prompt.
3. Output: `agentshield.dxt`
4. Submit to Anthropic's extensions directory when open.

## 5. Cursor / Cline / Zed / Continue

Each of these has its own MCP directory or wiki page. Once on Smithery most of them auto-pick-up; for the rest:

- Cursor: PR to https://github.com/cursor-ai/mcp-servers (community list)
- Cline: Add to their Discord's #mcp-servers thread
- Zed: PR to https://github.com/zed-industries/extensions
- Continue: Add to https://continue.dev/docs/mcp

## 6. Structured data / SEO

After npm is live, update `services/landing-page/llms.txt` (already drafted) to reflect the real npm URL, and add an `/.well-known/mcp.json` pointer at `agentshield.pro`:

```json
{
  "name": "agentshield",
  "version": "0.1.0",
  "package": "@eigenart/agentshield-mcp",
  "install": "npx -y @eigenart/agentshield-mcp",
  "tools": ["classify_text"],
  "docs": "https://agentshield.pro/mcp",
  "source": "https://github.com/dl-eigenart/agentshield-platform/tree/main/packages/agentshield-mcp"
}
```

## 7. Announce

Only after 1-6 are done:

- Show HN post: "AgentShield MCP — prompt-injection guard for any MCP-aware agent"
- X / LinkedIn from @eigenart_film
- Cross-post to r/LocalLLaMA, r/ChatGPTCoding (rules permitting)
- Update agentshield.pro `/blog` with one announcement post

## Version policy

- 0.x = pre-stable, breaking changes allowed with minor bumps.
- 1.0 only after: (a) 1 full month in production, (b) at least 3 external users on Discord/issues, (c) v0.2 tools shipped.

## Rollback

If a published version is broken, `npm deprecate @eigenart/agentshield-mcp@X.Y.Z "reason"` — do NOT unpublish (npm's 72-hour rule + breaks downstream lockfiles). Publish a patched `X.Y.Z+1` instead.
