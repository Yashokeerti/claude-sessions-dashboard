# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-26

### Added
- Web dashboard showing all Claude Code sessions (active and inactive)
- Real-time active session detection via process monitoring
- Session data from `~/.claude/sessions/`, `history.jsonl`, and `projects/`
- Complete file paths and directory locations for each session
- File creation and last updated timestamps
- Text search across session ID, project, name, and messages
- Status filter (All / Active / Inactive)
- Date range filter (Today / Last 7 Days / Last 30 Days / Custom)
- Project dropdown filter auto-populated from session data
- Source/entrypoint filter (CLI / Desktop)
- Column sorting on all columns
- Click session ID to copy resume command to clipboard
- Play button to open Terminal and resume session directly
- Auto-refresh every 30 seconds
- JSON API endpoint at `/api/sessions`
- Dark theme matching Claude Code aesthetic
- Native macOS app wrapper with menu bar icon
- `--port` CLI argument for custom port
- Installable via pip, Homebrew, or manual build
