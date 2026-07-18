# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project uses Semantic Versioning.

## [0.1.1] - 2026-07-18

### Added

- Reproducible local MySQL fixture for benchmarking 10 long trajectories with 210 messages.
- Development record covering the long-trajectory performance investigation and results.

### Changed

- Long collapsed trajectory messages now use bounded previews and defer rich Markdown, JSON, and tool-call rendering until expansion.
- Off-screen trajectory messages can skip layout and paint work through `content-visibility`.

### Fixed

- Trajectory selection, inversion, fullscreen, and scrolling no longer stall for multiple seconds on long-message comparisons.
- SPA entry HTML no longer reuses stale cached asset hashes after a frontend deployment.
- Annotation delete result typing remains stable across frontend builds.

## [0.1.0] - 2026-06-01

### Added

- MySQL connector
- SELECT-only SQL query engine
- Row-level table view
- Markdown / JSON / Code / Timestamp renderers
- Trajectory single view
- Trajectory compare view
- Label schema and labeling system
- Batch labeling
- CSV/Excel export
- View config save and restore
- Global field render rules
- Agent Bridge
- AgentLens CLI
- AgentLens MCP Server
- Context Export
- Annotation reverse visualization
- Selection Snapshot
- Copy Agent Prompt
- Docker distribution
- pipx distribution
- 0.1.0 documentation set
- Basic GitHub Actions CI

### Changed

- Removed planned built-in LLM analysis from 0.1.0 in favor of external CLI/MCP agent integration.

### Known Issues

- Single-user, no permission system.
- 0.1.0 only supports MySQL.
- Image fields do not have dedicated visualization.
- Docker does not directly integrate with the user's local Claude Code configuration.
- Embedded SDK is planned for v2.
