# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project uses Semantic Versioning.

## [1.0.0] - 2026-06-01

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
- v1.0 documentation set
- Basic GitHub Actions CI

### Changed

- Removed planned built-in LLM analysis from v1 in favor of external CLI/MCP agent integration.

### Known Issues

- Single-user, no permission system.
- v1 only supports MySQL.
- Image fields do not have dedicated visualization.
- Docker does not directly integrate with the user's local Claude Code configuration.
- Embedded SDK is planned for v2.
