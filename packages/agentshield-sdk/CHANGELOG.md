# Changelog

All notable changes to the `agentshield` Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-18

### Added
- Initial public release.
- Synchronous `AgentShield` and asynchronous `AsyncAgentShield` HTTP clients.
- `classify()` and `classify_detailed()` methods wrapping `POST /v1/classify`.
- Typed response models `Verdict` and `ClassifyResponse`.
- Exception hierarchy: `AgentShieldError`, `AuthenticationError`,
  `RateLimitError` (with `retry_after`), `APIError`, `AgentShieldTimeoutError`.
- Configuration via kwargs or `AGENTSHIELD_API_KEY` / `AGENTSHIELD_BASE_URL` env vars.
