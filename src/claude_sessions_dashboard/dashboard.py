#!/usr/bin/env python3
"""
Claude Sessions Dashboard
A local web dashboard showing all active and inactive Claude Code sessions.
Run: python3 claude-sessions-dashboard.py
Open: http://localhost:8050
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PORT = 8050


def get_running_claude_pids():
    """Get set of PIDs for currently running claude processes."""
    pids = set()
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    pids.add(int(line))
                except ValueError:
                    pass
    except Exception:
        pass
    return pids


def get_active_sessions():
    """Read session files from ~/.claude/sessions/"""
    sessions = []
    sessions_dir = CLAUDE_DIR / "sessions"
    if not sessions_dir.exists():
        return sessions
    for f in sessions_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            stat = f.stat()
            data["_session_file"] = str(f)
            data["_file_created"] = stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime
            data["_file_modified"] = stat.st_mtime
            sessions.append(data)
        except Exception:
            pass
    return sessions


def get_session_file_paths(session_id):
    """Find all file/directory paths related to a session ID."""
    paths = {}

    # ~/.claude/sessions/<pid>.json — matched by content, not name
    sessions_dir = CLAUDE_DIR / "sessions"
    if sessions_dir.exists():
        for f in sessions_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("sessionId") == session_id:
                    paths["session_json"] = str(f)
            except Exception:
                pass

    # ~/.claude/session-env/<session_id>/
    env_dir = CLAUDE_DIR / "session-env" / session_id
    if env_dir.exists():
        paths["session_env"] = str(env_dir)

    # ~/.claude/projects/*/<session_id>.jsonl
    projects_dir = CLAUDE_DIR / "projects"
    if projects_dir.exists():
        for proj_dir in projects_dir.iterdir():
            if not proj_dir.is_dir():
                continue
            jsonl = proj_dir / f"{session_id}.jsonl"
            if jsonl.exists():
                paths["conversation_log"] = str(jsonl)
            # Also check for session dir inside project
            sess_dir = proj_dir / session_id
            if sess_dir.exists() and sess_dir.is_dir():
                paths["project_session_dir"] = str(sess_dir)

    return paths


def get_file_times(filepath):
    """Get creation and modification time for a file/directory."""
    try:
        stat = os.stat(filepath)
        created = stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime
        modified = stat.st_mtime
        return created, modified
    except Exception:
        return None, None


def get_history_sessions():
    """Parse history.jsonl to build session metadata."""
    history_file = CLAUDE_DIR / "history.jsonl"
    if not history_file.exists():
        return {}

    sessions = {}
    try:
        with open(history_file) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    sid = d.get("sessionId")
                    if not sid:
                        continue
                    proj = d.get("project", "")
                    ts = d.get("timestamp", 0)
                    display = d.get("display", "")
                    if sid not in sessions:
                        sessions[sid] = {
                            "project": proj,
                            "first_ts": ts,
                            "last_ts": ts,
                            "message_count": 1,
                            "first_message": display[:120] if display else "",
                            "last_message": display[:120] if display else "",
                        }
                    else:
                        s = sessions[sid]
                        s["last_ts"] = max(s["last_ts"], ts)
                        s["first_ts"] = min(s["first_ts"], ts)
                        s["message_count"] += 1
                        if display:
                            s["last_message"] = display[:120]
                except (json.JSONDecodeError, KeyError):
                    pass
    except Exception:
        pass
    return sessions


def get_project_sessions():
    """Scan ~/.claude/projects/ for per-project session JSONL files."""
    projects_dir = CLAUDE_DIR / "projects"
    project_sessions = {}
    if not projects_dir.exists():
        return project_sessions

    for proj_dir in projects_dir.iterdir():
        if not proj_dir.is_dir():
            continue
        for f in proj_dir.glob("*.jsonl"):
            sid = f.stem
            try:
                stat = f.stat()
                created = stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime
                project_sessions[sid] = {
                    "project_dir": proj_dir.name,
                    "project_dir_full": str(proj_dir),
                    "conversation_log": str(f),
                    "file_size": stat.st_size,
                    "modified": stat.st_mtime,
                    "created": created,
                }
            except Exception:
                pass
    return project_sessions


def format_timestamp(ts_sec):
    """Format unix timestamp (seconds) to human-readable string."""
    if not ts_sec:
        return "—"
    try:
        dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "—"


def format_timestamp_ms(ts_ms):
    """Format millisecond timestamp to human-readable string."""
    if not ts_ms:
        return "—"
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "—"


def time_ago(ts_ms):
    """Return human-friendly relative time."""
    if not ts_ms:
        return "—"
    try:
        diff = time.time() - (ts_ms / 1000)
        if diff < 0:
            return "just now"
        if diff < 60:
            return f"{int(diff)}s ago"
        if diff < 3600:
            return f"{int(diff / 60)}m ago"
        if diff < 86400:
            return f"{int(diff / 3600)}h ago"
        return f"{int(diff / 86400)}d ago"
    except Exception:
        return "—"


def time_ago_sec(ts_sec):
    """Return human-friendly relative time from seconds timestamp."""
    if not ts_sec:
        return "—"
    return time_ago(ts_sec * 1000)


def format_size(size_bytes):
    """Format bytes to human readable."""
    if not size_bytes:
        return "—"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def escape_html(text):
    """Escape HTML special characters."""
    if not text:
        return ""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def build_dashboard_data():
    """Combine all data sources into a unified session list."""
    running_pids = get_running_claude_pids()
    active_sessions = get_active_sessions()
    history = get_history_sessions()
    project_sessions = get_project_sessions()

    all_sessions = {}

    # Start with active session files (these have PIDs)
    for s in active_sessions:
        sid = s.get("sessionId", "")
        pid = s.get("pid")
        is_active = pid in running_pids if pid else False
        all_sessions[sid] = {
            "sessionId": sid,
            "pid": pid,
            "cwd": s.get("cwd", ""),
            "startedAt": s.get("startedAt", 0),
            "kind": s.get("kind", ""),
            "entrypoint": s.get("entrypoint", ""),
            "name": s.get("name", ""),
            "active": is_active,
            "source": "session_file",
            "file_created": s.get("_file_created", 0),
            "file_modified": s.get("_file_modified", 0),
            "session_json_path": s.get("_session_file", ""),
        }

    # Merge history data
    for sid, h in history.items():
        if sid in all_sessions:
            s = all_sessions[sid]
            s["project"] = h["project"]
            s["message_count"] = h["message_count"]
            s["first_ts"] = h["first_ts"]
            s["last_ts"] = h["last_ts"]
            s["first_message"] = h.get("first_message", "")
            s["last_message"] = h.get("last_message", "")
            if not s.get("startedAt"):
                s["startedAt"] = h["first_ts"]
        else:
            all_sessions[sid] = {
                "sessionId": sid,
                "pid": None,
                "cwd": "",
                "startedAt": h["first_ts"],
                "kind": "",
                "entrypoint": "cli",
                "name": "",
                "active": False,
                "source": "history",
                "project": h["project"],
                "message_count": h["message_count"],
                "first_ts": h["first_ts"],
                "last_ts": h["last_ts"],
                "first_message": h.get("first_message", ""),
                "last_message": h.get("last_message", ""),
            }

    # Merge project session data
    for sid, p in project_sessions.items():
        if sid in all_sessions:
            s = all_sessions[sid]
            s["file_size"] = p["file_size"]
            s["project_dir"] = p["project_dir"]
            s["conversation_log"] = p["conversation_log"]
            # Use file timestamps if we don't have better ones
            if not s.get("file_created"):
                s["file_created"] = p["created"]
            if not s.get("file_modified") or p["modified"] > s.get("file_modified", 0):
                s["file_modified"] = p["modified"]
        else:
            all_sessions[sid] = {
                "sessionId": sid,
                "pid": None,
                "cwd": "",
                "startedAt": p["created"] * 1000,
                "kind": "",
                "entrypoint": "",
                "name": "",
                "active": False,
                "source": "project_file",
                "file_size": p["file_size"],
                "project_dir": p["project_dir"],
                "conversation_log": p["conversation_log"],
                "message_count": 0,
                "last_ts": p["modified"] * 1000,
                "file_created": p["created"],
                "file_modified": p["modified"],
            }

    # Resolve full file paths for each session
    for sid, s in all_sessions.items():
        file_paths = get_session_file_paths(sid)
        s["file_paths"] = file_paths

        # Determine best creation and modification times from all related files
        best_created = s.get("file_created", 0)
        best_modified = s.get("file_modified", 0)
        for path in file_paths.values():
            c, m = get_file_times(path)
            if c and (not best_created or c < best_created):
                best_created = c
            if m and m > best_modified:
                best_modified = m
        s["file_created"] = best_created
        s["file_modified"] = best_modified

    # Sort: active first, then by last activity
    result = sorted(
        all_sessions.values(),
        key=lambda x: (not x.get("active", False), -(x.get("last_ts", 0) or x.get("startedAt", 0)))
    )
    return result


def build_html():
    """Generate the full dashboard HTML."""
    sessions = build_dashboard_data()
    active_count = sum(1 for s in sessions if s.get("active"))
    inactive_count = len(sessions) - active_count
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Collect unique projects and entrypoints for filter dropdowns
    all_projects = set()
    all_entrypoints = set()
    for s in sessions:
        p = s.get("project", "") or s.get("cwd", "")
        if p:
            # Use the last directory component as a short name
            all_projects.add(p)
        ep = s.get("entrypoint", "")
        if ep:
            all_entrypoints.add(ep)

    rows_html = ""
    for s in sessions:
        is_active = s.get("active", False)
        status_class = "active" if is_active else "inactive"
        status_badge = '<span class="badge active">ACTIVE</span>' if is_active else '<span class="badge inactive">INACTIVE</span>'

        sid = s.get("sessionId", "—")
        sid_short = sid[:8] + "..." if len(sid) > 8 else sid

        pid = s.get("pid", "")
        pid_display = str(pid) if pid else "—"

        project = s.get("project", "") or s.get("cwd", "")
        name = s.get("name", "") or "—"
        entrypoint = s.get("entrypoint", "") or "—"

        # Timestamp in ms for JS date filtering
        started_ts_ms = s.get("startedAt", 0) or s.get("first_ts", 0) or 0
        kind = s.get("kind", "") or "—"

        # File paths
        file_paths = s.get("file_paths", {})
        conv_log = s.get("conversation_log", "") or file_paths.get("conversation_log", "")
        session_json = s.get("session_json_path", "") or file_paths.get("session_json", "")
        session_env = file_paths.get("session_env", "")
        proj_sess_dir = file_paths.get("project_session_dir", "")

        # Build the full paths tooltip/display
        all_paths = []
        if session_json:
            all_paths.append(f"Session: {session_json}")
        if conv_log:
            all_paths.append(f"Log: {conv_log}")
        if session_env:
            all_paths.append(f"Env: {session_env}")
        if proj_sess_dir:
            all_paths.append(f"Dir: {proj_sess_dir}")
        paths_tooltip = escape_html("\n".join(all_paths)) if all_paths else "—"

        # Primary directory to display
        primary_dir = conv_log or session_json or session_env or proj_sess_dir or "—"

        # Timestamps
        created_ts = s.get("file_created", 0)
        modified_ts = s.get("file_modified", 0)
        created_str = format_timestamp(created_ts) if created_ts else "—"
        modified_str = format_timestamp(modified_ts) if modified_ts else "—"
        created_ago = time_ago_sec(created_ts) if created_ts else "—"
        modified_ago = time_ago_sec(modified_ts) if modified_ts else "—"

        started = format_timestamp_ms(s.get("startedAt", 0))
        last_active = time_ago(s.get("last_ts", 0) or s.get("startedAt", 0))
        msg_count = s.get("message_count", 0) or 0

        first_msg = s.get("first_message", "") or ""
        first_msg_escaped = escape_html(first_msg)
        last_msg = s.get("last_message", "") or ""
        last_msg_escaped = escape_html(last_msg)

        file_size = format_size(s.get("file_size", 0))

        project_escaped = escape_html(project)

        rows_html += f"""
        <tr class="session-row {status_class}" data-status="{status_class}" data-started="{started_ts_ms}" data-project="{project_escaped}" data-entrypoint="{escape_html(entrypoint)}" data-search="{escape_html(sid)} {project_escaped} {escape_html(name)} {first_msg_escaped} {last_msg_escaped} {escape_html(primary_dir)}">
            <td>{status_badge}</td>
            <td>
                <span class="session-id clickable" title="Click to copy resume command&#10;{escape_html(sid)}" onclick="copyResume('{escape_html(sid)}', '{escape_html(project)}')">{escape_html(sid_short)}</span>
                <span class="terminal-btn" onclick="openInTerminal('{escape_html(sid)}', '{escape_html(project)}')" title="Open in Terminal">&#9654;</span>
            </td>
            <td>{pid_display}</td>
            <td class="name-cell">{escape_html(name)}</td>
            <td class="project-cell" title="{project_escaped}">{project_escaped}</td>
            <td>{escape_html(entrypoint)}</td>
            <td>{escape_html(kind)}</td>
            <td class="path-cell" title="{paths_tooltip}">{escape_html(primary_dir)}</td>
            <td title="{created_ago}">{created_str}</td>
            <td title="{modified_ago}">{modified_str}</td>
            <td>{started}</td>
            <td>{last_active}</td>
            <td>{msg_count}</td>
            <td class="msg-cell" title="{first_msg_escaped}">{first_msg_escaped[:60]}{"..." if len(first_msg) > 60 else ""}</td>
            <td class="msg-cell" title="{last_msg_escaped}">{last_msg_escaped[:60]}{"..." if len(last_msg) > 60 else ""}</td>
            <td>{file_size}</td>
        </tr>"""

    # Build project options HTML
    home = str(Path.home())
    project_options = ""
    for p in sorted(all_projects):
        short = p.replace(home, "~") if p.startswith(home) else p
        project_options += f'<option value="{escape_html(p)}">{escape_html(short)}</option>\n'

    # Build entrypoint buttons HTML
    entrypoint_btns = ""
    for ep in sorted(all_entrypoints):
        entrypoint_btns += f'<button class="filter-btn ep-btn" onclick="filterEntrypoint(\'{escape_html(ep)}\')">{escape_html(ep.upper())}</button>\n'

    col_count = 16
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Sessions Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        html, body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}

        .header {{
            background: linear-gradient(135deg, #161b22 0%, #1a1f2b 100%);
            border-bottom: 1px solid #30363d;
            padding: 20px 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 16px;
        }}

        .header-left {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .logo {{
            font-size: 28px;
            font-weight: 700;
            background: linear-gradient(135deg, #d4a574 0%, #e8c49a 50%, #d4a574 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.5px;
        }}

        .stats {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}

        .stat {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 500;
        }}

        .stat.active-stat {{
            background: rgba(63, 185, 80, 0.15);
            border: 1px solid rgba(63, 185, 80, 0.3);
            color: #3fb950;
        }}

        .stat.inactive-stat {{
            background: rgba(139, 148, 158, 0.1);
            border: 1px solid rgba(139, 148, 158, 0.2);
            color: #8b949e;
        }}

        .stat.total-stat {{
            background: rgba(136, 132, 216, 0.15);
            border: 1px solid rgba(136, 132, 216, 0.3);
            color: #a5a0e4;
        }}

        .stat-num {{
            font-size: 20px;
            font-weight: 700;
        }}

        .dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }}

        .dot.green {{ background: #3fb950; box-shadow: 0 0 6px rgba(63, 185, 80, 0.5); }}
        .dot.gray {{ background: #8b949e; }}
        .dot.purple {{ background: #a5a0e4; }}

        .controls {{
            padding: 16px 32px;
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
            border-bottom: 1px solid #21262d;
            background: #0d1117;
        }}

        .search-box {{
            flex: 1;
            min-width: 250px;
            padding: 10px 16px;
            border-radius: 8px;
            border: 1px solid #30363d;
            background: #161b22;
            color: #c9d1d9;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }}

        .search-box:focus {{
            border-color: #d4a574;
        }}

        .search-box::placeholder {{ color: #484f58; }}

        .filter-btn {{
            padding: 8px 18px;
            border-radius: 8px;
            border: 1px solid #30363d;
            background: #161b22;
            color: #c9d1d9;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .filter-btn:hover {{ border-color: #d4a574; color: #d4a574; }}
        .filter-btn.selected {{ background: rgba(212, 165, 116, 0.15); border-color: #d4a574; color: #d4a574; }}

        .filters-row {{
            border-top: none;
            padding-top: 0;
            flex-wrap: wrap;
        }}

        .filter-label {{
            font-size: 12px;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            white-space: nowrap;
        }}

        .filter-divider {{
            width: 1px;
            height: 28px;
            background: #30363d;
            margin: 0 4px;
        }}

        .date-input {{
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid #30363d;
            background: #161b22;
            color: #c9d1d9;
            font-size: 12px;
            outline: none;
            width: 130px;
            transition: border-color 0.2s;
        }}

        .date-input:focus {{ border-color: #d4a574; }}
        .date-sep {{ color: #484f58; font-size: 12px; }}

        .filter-select {{
            padding: 7px 12px;
            border-radius: 6px;
            border: 1px solid #30363d;
            background: #161b22;
            color: #c9d1d9;
            font-size: 12px;
            outline: none;
            max-width: 280px;
            cursor: pointer;
            transition: border-color 0.2s;
        }}

        .filter-select:focus {{ border-color: #d4a574; }}

        .reset-btn {{
            margin-left: auto;
            color: #f85149;
            border-color: rgba(248, 81, 73, 0.3);
            font-size: 12px;
            padding: 6px 14px;
        }}

        .reset-btn:hover {{
            background: rgba(248, 81, 73, 0.15);
            border-color: #f85149;
            color: #f85149;
        }}

        .refresh-info {{
            font-size: 12px;
            color: #484f58;
            margin-left: auto;
        }}

        .table-wrapper {{
            flex: 1;
            overflow: auto;
            padding: 0 16px 32px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
            font-size: 13px;
            table-layout: fixed;
        }}

        thead th {{
            background: #161b22;
            padding: 12px 10px;
            text-align: left;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            font-size: 10px;
            letter-spacing: 0.5px;
            border-bottom: 2px solid #30363d;
            position: sticky;
            top: 0;
            z-index: 10;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            position: relative;
        }}

        thead th:hover {{ color: #d4a574; }}

        .th-resize {{
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 5px;
            cursor: col-resize;
            background: transparent;
            z-index: 20;
        }}

        .th-resize:hover, .th-resize.active {{
            background: #d4a574;
        }}

        tbody tr {{
            border-bottom: 1px solid #21262d;
            transition: background 0.15s;
        }}

        tbody tr:hover {{ background: #161b22; }}

        tbody td {{
            padding: 10px 10px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .col-toggle-wrapper {{
            position: relative;
            display: inline-block;
        }}

        .col-toggle-btn {{
            padding: 7px 14px;
            border-radius: 6px;
            border: 1px solid #30363d;
            background: #161b22;
            color: #c9d1d9;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .col-toggle-btn:hover {{ border-color: #d4a574; color: #d4a574; }}

        .col-dropdown {{
            display: none;
            position: absolute;
            top: 100%;
            right: 0;
            margin-top: 4px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 8px 0;
            z-index: 100;
            min-width: 200px;
            max-height: 400px;
            overflow-y: auto;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }}

        .col-dropdown.open {{ display: block; }}

        .col-dropdown label {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 16px;
            font-size: 13px;
            color: #c9d1d9;
            cursor: pointer;
            transition: background 0.15s;
        }}

        .col-dropdown label:hover {{ background: #21262d; }}

        .col-dropdown input[type="checkbox"] {{
            accent-color: #d4a574;
        }}

        .badge {{
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .badge.active {{
            background: rgba(63, 185, 80, 0.15);
            color: #3fb950;
            border: 1px solid rgba(63, 185, 80, 0.3);
        }}

        .badge.inactive {{
            background: rgba(139, 148, 158, 0.08);
            color: #6e7681;
            border: 1px solid rgba(139, 148, 158, 0.15);
        }}

        .session-id {{
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 12px;
            color: #79c0ff;
        }}

        .session-id.clickable {{
            cursor: pointer;
            border-bottom: 1px dashed #79c0ff;
            transition: all 0.2s;
        }}

        .session-id.clickable:hover {{
            color: #a5d6ff;
            border-bottom-color: #a5d6ff;
        }}

        .terminal-btn {{
            display: inline-block;
            margin-left: 6px;
            padding: 2px 6px;
            font-size: 10px;
            color: #3fb950;
            background: rgba(63, 185, 80, 0.1);
            border: 1px solid rgba(63, 185, 80, 0.25);
            border-radius: 4px;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s;
            vertical-align: middle;
        }}

        .terminal-btn:hover {{
            background: rgba(63, 185, 80, 0.25);
            border-color: #3fb950;
            color: #7ee787;
        }}

        .toast {{
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%) translateY(80px);
            background: #1f2937;
            color: #e5e7eb;
            padding: 12px 24px;
            border-radius: 10px;
            border: 1px solid #374151;
            font-size: 14px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
            z-index: 1000;
            opacity: 0;
            transition: all 0.3s ease;
            pointer-events: none;
        }}

        .toast.show {{
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }}

        .toast .toast-icon {{
            margin-right: 8px;
        }}

        .project-cell {{
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 11px;
            color: #d2a8ff;
        }}

        .path-cell {{
            max-width: 350px;
            overflow: hidden;
            text-overflow: ellipsis;
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 11px;
            color: #7ee787;
            cursor: help;
        }}

        .name-cell {{
            max-width: 180px;
            overflow: hidden;
            text-overflow: ellipsis;
            color: #ffa657;
            font-weight: 500;
        }}

        .msg-cell {{
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            color: #8b949e;
            font-size: 12px;
        }}

        .time-cell {{
            font-size: 12px;
            color: #8b949e;
        }}

        tr.inactive td {{ opacity: 0.65; }}
        tr.inactive:hover td {{ opacity: 0.85; }}
        tr.active {{ background: rgba(63, 185, 80, 0.03); }}

        .no-data {{
            text-align: center;
            padding: 60px 20px;
            color: #484f58;
            font-size: 16px;
        }}

        @media (max-width: 768px) {{
            .header {{ padding: 16px; }}
            .controls {{ padding: 12px 16px; }}
            .table-wrapper {{ padding: 0 8px 16px; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">
            <div class="logo">Claude Sessions</div>
        </div>
        <div class="stats">
            <div class="stat active-stat">
                <span class="dot green"></span>
                <span class="stat-num">{active_count}</span> Active
            </div>
            <div class="stat inactive-stat">
                <span class="dot gray"></span>
                <span class="stat-num">{inactive_count}</span> Inactive
            </div>
            <div class="stat total-stat">
                <span class="dot purple"></span>
                <span class="stat-num">{len(sessions)}</span> Total
            </div>
        </div>
    </div>

    <div class="controls">
        <input type="text" class="search-box" id="search" placeholder="Search sessions by ID, project, name, path, or message...">
        <button class="filter-btn selected" onclick="filterSessions('all')">All</button>
        <button class="filter-btn" onclick="filterSessions('active')">Active</button>
        <button class="filter-btn" onclick="filterSessions('inactive')">Inactive</button>
        <span class="refresh-info">Last refresh: {now_str} &nbsp;|&nbsp; Auto-refresh: 30s &nbsp;|&nbsp; <a href="/" style="color:#d4a574">Refresh now</a></span>
    </div>

    <div class="controls filters-row">
        <span class="filter-label">Date:</span>
        <button class="filter-btn date-btn selected" onclick="filterDate('all')">All Time</button>
        <button class="filter-btn date-btn" onclick="filterDate('today')">Today</button>
        <button class="filter-btn date-btn" onclick="filterDate('7d')">Last 7 Days</button>
        <button class="filter-btn date-btn" onclick="filterDate('30d')">Last 30 Days</button>
        <input type="date" class="date-input" id="dateFrom" title="From date">
        <span class="date-sep">to</span>
        <input type="date" class="date-input" id="dateTo" title="To date">
        <button class="filter-btn" onclick="filterDate('custom')" title="Apply custom date range">Apply</button>

        <span class="filter-divider"></span>

        <span class="filter-label">Project:</span>
        <select class="filter-select" id="projectFilter" onchange="applyFilters()">
            <option value="">All Projects</option>
            {project_options}
        </select>

        <span class="filter-divider"></span>

        <span class="filter-label">Source:</span>
        <button class="filter-btn ep-btn selected" onclick="filterEntrypoint('all')">All</button>
        {entrypoint_btns}

        <span class="filter-divider"></span>

        <div class="col-toggle-wrapper">
            <button class="col-toggle-btn" onclick="toggleColDropdown()">Columns</button>
            <div class="col-dropdown" id="colDropdown"></div>
        </div>

        <button class="filter-btn reset-btn" onclick="resetAllFilters()" title="Reset all filters">Reset</button>
    </div>

    <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th data-col="0">Status<span class="th-resize"></span></th>
                    <th data-col="1">Session ID<span class="th-resize"></span></th>
                    <th data-col="2">PID<span class="th-resize"></span></th>
                    <th data-col="3">Name<span class="th-resize"></span></th>
                    <th data-col="4">Project / CWD<span class="th-resize"></span></th>
                    <th data-col="5">Entry<span class="th-resize"></span></th>
                    <th data-col="6">Kind<span class="th-resize"></span></th>
                    <th data-col="7">Session Directory<span class="th-resize"></span></th>
                    <th data-col="8">Created<span class="th-resize"></span></th>
                    <th data-col="9">Last Updated<span class="th-resize"></span></th>
                    <th data-col="10">Started<span class="th-resize"></span></th>
                    <th data-col="11">Last Active<span class="th-resize"></span></th>
                    <th data-col="12">Msgs<span class="th-resize"></span></th>
                    <th data-col="13">First Message<span class="th-resize"></span></th>
                    <th data-col="14">Last Message<span class="th-resize"></span></th>
                    <th data-col="15">Size<span class="th-resize"></span></th>
                </tr>
            </thead>
            <tbody id="sessionTable">
                {rows_html if rows_html else f'<tr><td colspan="{col_count}" class="no-data">No sessions found</td></tr>'}
            </tbody>
        </table>
    </div>

    <div class="toast" id="toast"></div>

    <script>
        function showToast(message) {{
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }}

        function copyToClipboard(text) {{
            // execCommand fallback works on http:// (navigator.clipboard needs https)
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.top = '-9999px';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try {{
                document.execCommand('copy');
                showToast('Copied! Paste in terminal to resume.');
            }} catch(e) {{
                showToast('Failed to copy - select manually: ' + text);
            }}
            document.body.removeChild(ta);
        }}

        function copyResume(sessionId, project) {{
            let cmd = 'claude --resume ' + sessionId;
            if (project) {{
                cmd = 'cd ' + project + ' && ' + cmd;
            }}
            copyToClipboard(cmd);
        }}

        function openInTerminal(sessionId, project) {{
            // Call our server-side endpoint which opens Terminal directly
            fetch('/api/launch?id=' + encodeURIComponent(sessionId) + '&cwd=' + encodeURIComponent(project || ''))
                .then(r => r.json())
                .then(data => {{
                    if (data.ok) {{
                        showToast('Opening in Terminal...');
                    }} else {{
                        showToast('Error: ' + (data.error || 'unknown'));
                    }}
                }})
                .catch(() => showToast('Failed to launch terminal'));
        }}

        let currentStatusFilter = 'all';
        let currentDateFilter = 'all';
        let currentDateFrom = null;
        let currentDateTo = null;
        let currentEntrypoint = 'all';

        function filterSessions(filter) {{
            currentStatusFilter = filter;
            document.querySelectorAll('.controls:first-of-type .filter-btn').forEach(btn => {{
                const txt = btn.textContent.trim().toLowerCase();
                btn.classList.toggle('selected', txt === filter);
            }});
            applyFilters();
        }}

        function filterDate(preset) {{
            const now = Date.now();
            document.querySelectorAll('.date-btn').forEach(btn => {{
                btn.classList.toggle('selected', btn.textContent.trim().toLowerCase().split(' ').join('') ===
                    ({{ 'all': 'alltime', 'today': 'today', '7d': 'last7days', '30d': 'last30days', 'custom': '' }}[preset] || ''));
            }}
);

            if (preset === 'all') {{
                currentDateFilter = 'all';
                currentDateFrom = null;
                currentDateTo = null;
            }} else if (preset === 'today') {{
                currentDateFilter = 'range';
                const todayStart = new Date();
                todayStart.setHours(0, 0, 0, 0);
                currentDateFrom = todayStart.getTime();
                currentDateTo = now;
            }} else if (preset === '7d') {{
                currentDateFilter = 'range';
                currentDateFrom = now - 7 * 86400000;
                currentDateTo = now;
            }} else if (preset === '30d') {{
                currentDateFilter = 'range';
                currentDateFrom = now - 30 * 86400000;
                currentDateTo = now;
            }} else if (preset === 'custom') {{
                const fromVal = document.getElementById('dateFrom').value;
                const toVal = document.getElementById('dateTo').value;
                if (fromVal) {{
                    currentDateFilter = 'range';
                    currentDateFrom = new Date(fromVal).getTime();
                    currentDateTo = toVal ? new Date(toVal + 'T23:59:59').getTime() : now;
                    document.querySelectorAll('.date-btn').forEach(btn => btn.classList.remove('selected'));
                }} else {{
                    currentDateFilter = 'all';
                }}
            }}
            applyFilters();
        }}

        function filterEntrypoint(ep) {{
            currentEntrypoint = ep;
            document.querySelectorAll('.ep-btn').forEach(btn => {{
                const txt = btn.textContent.trim().toLowerCase();
                btn.classList.toggle('selected', txt === ep.toLowerCase() || (ep === 'all' && txt === 'all'));
            }});
            applyFilters();
        }}

        function resetAllFilters() {{
            currentStatusFilter = 'all';
            currentDateFilter = 'all';
            currentDateFrom = null;
            currentDateTo = null;
            currentEntrypoint = 'all';
            document.getElementById('search').value = '';
            document.getElementById('projectFilter').value = '';
            document.getElementById('dateFrom').value = '';
            document.getElementById('dateTo').value = '';

            document.querySelectorAll('.controls:first-of-type .filter-btn').forEach(btn => {{
                btn.classList.toggle('selected', btn.textContent.trim().toLowerCase() === 'all');
            }});
            document.querySelectorAll('.date-btn').forEach(btn => {{
                btn.classList.toggle('selected', btn.textContent.trim() === 'All Time');
            }});
            document.querySelectorAll('.ep-btn').forEach(btn => {{
                btn.classList.toggle('selected', btn.textContent.trim().toLowerCase() === 'all');
            }});
            applyFilters();
        }}

        function applyFilters() {{
            const search = document.getElementById('search').value.toLowerCase();
            const projectFilter = document.getElementById('projectFilter').value;
            let visible = 0;

            document.querySelectorAll('.session-row').forEach(row => {{
                // Status filter
                const matchesStatus = currentStatusFilter === 'all' || row.dataset.status === currentStatusFilter;

                // Text search
                const matchesSearch = !search || row.dataset.search.toLowerCase().includes(search);

                // Project filter
                const matchesProject = !projectFilter || row.dataset.project === projectFilter;

                // Entrypoint filter
                const matchesEntry = currentEntrypoint === 'all' || row.dataset.entrypoint.toLowerCase() === currentEntrypoint.toLowerCase();

                // Date filter
                let matchesDate = true;
                if (currentDateFilter === 'range' && currentDateFrom) {{
                    const ts = parseInt(row.dataset.started) || 0;
                    matchesDate = ts >= currentDateFrom && ts <= (currentDateTo || Date.now());
                }}

                const show = matchesStatus && matchesSearch && matchesProject && matchesEntry && matchesDate;
                row.style.display = show ? '' : 'none';
                if (show) visible++;
            }});
        }}

        document.getElementById('search').addEventListener('input', applyFilters);

        // Column sorting (click on th text, not on resize handle)
        document.querySelectorAll('thead th').forEach((th, idx) => {{
            th.addEventListener('click', (e) => {{
                if (e.target.classList.contains('th-resize')) return;
                const table = document.getElementById('sessionTable');
                const rows = Array.from(table.querySelectorAll('tr'));
                const asc = th.dataset.sort !== 'asc';
                document.querySelectorAll('thead th').forEach(h => delete h.dataset.sort);
                th.dataset.sort = asc ? 'asc' : 'desc';
                rows.sort((a, b) => {{
                    const aVal = a.cells[idx]?.textContent?.trim() || '';
                    const bVal = b.cells[idx]?.textContent?.trim() || '';
                    const aNum = parseFloat(aVal);
                    const bNum = parseFloat(bVal);
                    if (!isNaN(aNum) && !isNaN(bNum)) {{
                        return asc ? aNum - bNum : bNum - aNum;
                    }}
                    return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                }});
                rows.forEach(row => table.appendChild(row));
            }});
        }});

        // Column resizing
        (function() {{
            let resizing = null;
            let startX = 0;
            let startW = 0;

            document.querySelectorAll('.th-resize').forEach(handle => {{
                handle.addEventListener('mousedown', function(e) {{
                    e.preventDefault();
                    e.stopPropagation();
                    resizing = this.parentElement;
                    startX = e.pageX;
                    startW = resizing.offsetWidth;
                    this.classList.add('active');
                    document.body.style.cursor = 'col-resize';
                    document.body.style.userSelect = 'none';
                }});
            }});

            document.addEventListener('mousemove', function(e) {{
                if (!resizing) return;
                const diff = e.pageX - startX;
                const newW = Math.max(40, startW + diff);
                resizing.style.width = newW + 'px';
                resizing.style.minWidth = newW + 'px';
                resizing.style.maxWidth = newW + 'px';
            }});

            document.addEventListener('mouseup', function() {{
                if (resizing) {{
                    document.querySelectorAll('.th-resize').forEach(h => h.classList.remove('active'));
                    resizing = null;
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                }}
            }});
        }})();

        // Column visibility toggle
        const colNames = ['Status','Session ID','PID','Name','Project / CWD','Entry','Kind','Session Directory','Created','Last Updated','Started','Last Active','Msgs','First Message','Last Message','Size'];
        const hiddenCols = new Set();

        function buildColDropdown() {{
            const dd = document.getElementById('colDropdown');
            dd.textContent = '';
            colNames.forEach((name, i) => {{
                const label = document.createElement('label');
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = !hiddenCols.has(i);
                cb.addEventListener('change', function() {{
                    if (this.checked) {{
                        hiddenCols.delete(i);
                    }} else {{
                        hiddenCols.add(i);
                    }}
                    applyColumnVisibility();
                }});
                label.appendChild(cb);
                label.appendChild(document.createTextNode(name));
                dd.appendChild(label);
            }});
        }}

        function applyColumnVisibility() {{
            const ths = document.querySelectorAll('thead th');
            ths.forEach((th, i) => {{
                th.style.display = hiddenCols.has(i) ? 'none' : '';
            }});
            document.querySelectorAll('tbody tr').forEach(row => {{
                Array.from(row.cells).forEach((td, i) => {{
                    td.style.display = hiddenCols.has(i) ? 'none' : '';
                }});
            }});
        }}

        function toggleColDropdown() {{
            const dd = document.getElementById('colDropdown');
            dd.classList.toggle('open');
        }}

        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {{
            const wrapper = document.querySelector('.col-toggle-wrapper');
            if (wrapper && !wrapper.contains(e.target)) {{
                document.getElementById('colDropdown').classList.remove('open');
            }}
        }});

        buildColDropdown();

        // Auto-refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            html = build_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path == "/api/sessions":
            sessions = build_dashboard_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(sessions, default=str).encode())
        elif self.path.startswith("/api/launch"):
            self._handle_launch()
        else:
            self.send_error(404)

    def _handle_launch(self):
        """Open Terminal.app and resume a Claude session."""
        from urllib.parse import urlparse, parse_qs, unquote
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        session_id = params.get("id", [""])[0]
        cwd = params.get("cwd", [""])[0]

        if not session_id:
            self._json_response({"ok": False, "error": "No session ID"})
            return

        # Validate session_id is a UUID-like string (prevent injection)
        import re
        if not re.match(r'^[a-f0-9\-]+$', session_id):
            self._json_response({"ok": False, "error": "Invalid session ID"})
            return

        claude_cmd = f"claude --resume {session_id}"
        if cwd and os.path.isdir(cwd):
            # Escape single quotes for AppleScript
            cwd_escaped = cwd.replace("'", "'\\''")
            full_cmd = f"cd '{cwd_escaped}' && {claude_cmd}"
        else:
            full_cmd = claude_cmd

        # Use osascript to open Terminal.app with the command
        applescript = f'''
tell application "Terminal"
    activate
    do script "{full_cmd}"
end tell
'''
        try:
            subprocess.Popen(["osascript", "-e", applescript],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._json_response({"ok": True})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Claude Sessions Dashboard - view and manage Claude Code sessions"
    )
    parser.add_argument(
        "--port", type=int, default=PORT,
        help=f"Port to run the dashboard on (default: {PORT})"
    )
    args = parser.parse_args()

    port = args.port
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"\n  Claude Sessions Dashboard")
    print(f"  ─────────────────────────")
    print(f"  URL:  http://localhost:{port}")
    print(f"  Stop: Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dashboard stopped.\n")
        server.server_close()


if __name__ == "__main__":
    main()
