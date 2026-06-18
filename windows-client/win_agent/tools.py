"""Windows-specific tool functions for the client-hosted agent.

Each returns ``{"_ui_components": [<astralprims dicts>], "_data": {...}}`` — the
same shape backend agents return — so results render natively in the desktop
client (and as HTML on the web). These execute on the host the agent runs on.
"""
from __future__ import annotations

import os
import platform
import subprocess
from typing import Any, Dict, List


def _alert(message: str, variant: str = "success", title: str = None) -> dict:
    a = {"type": "alert", "variant": variant, "message": message}
    if title:
        a["title"] = title
    return a


def _ok(components: List[dict], data: dict = None) -> Dict[str, Any]:
    return {"_ui_components": components, "_data": data or {}}


# --------------------------------------------------------------------------- #
# system info
# --------------------------------------------------------------------------- #

def get_system_info(**kwargs) -> Dict[str, Any]:
    """Report this Windows machine's OS, CPU, memory and disk usage."""
    info = {
        "OS": f"{platform.system()} {platform.release()}",
        "Version": platform.version(),
        "Machine": platform.machine(),
        "Hostname": platform.node(),
        "Processor": platform.processor() or "—",
        "Python": platform.python_version(),
    }
    metrics = []
    data: Dict[str, Any] = dict(info)
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        vm = psutil.virtual_memory()
        du = psutil.disk_usage(os.path.abspath(os.sep))
        data.update(cpu_percent=cpu, mem_percent=vm.percent, disk_percent=du.percent)
        metrics = [
            {"type": "metric", "title": "CPU", "value": f"{cpu:.0f}%"},
            {"type": "metric", "title": "Memory",
             "value": f"{vm.percent:.0f}%", "subtitle": f"{vm.used >> 30} / {vm.total >> 30} GB"},
            {"type": "metric", "title": "Disk",
             "value": f"{du.percent:.0f}%", "subtitle": f"{du.used >> 30} / {du.total >> 30} GB"},
        ]
    except Exception:
        pass

    content: List[dict] = []
    if metrics:
        content.append({"type": "grid", "columns": 3, "children": metrics})
    content.append({"type": "keyvalue", "title": "System",
                    "items": [{"label": k, "value": str(v)} for k, v in info.items()]})
    return _ok([{"type": "hero", "title": "Windows System Status", "eyebrow": "THIS PC",
                 "subtitle": info["Hostname"]},
                {"type": "card", "title": "Details", "content": content}], data)


# --------------------------------------------------------------------------- #
# clipboard
# --------------------------------------------------------------------------- #

def read_clipboard(**kwargs) -> Dict[str, Any]:
    """Return the current text contents of the Windows clipboard."""
    text = _clip_get()
    if not text:
        return _ok([_alert("The clipboard is empty (or holds non-text data).", "info")])
    return _ok([{"type": "card", "title": "Clipboard",
                 "content": [{"type": "code", "code": text}]}], {"text": text})


def write_clipboard(text: str = "", **kwargs) -> Dict[str, Any]:
    """Copy ``text`` to the Windows clipboard."""
    if not text:
        return _ok([_alert("Nothing to copy — provide text.", "warning")])
    _clip_set(text)
    return _ok([_alert(f"Copied {len(text)} characters to the clipboard.", "success",
                       "Clipboard updated")], {"length": len(text)})


def _clip_get() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        try:  # stdlib fallback
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                                 capture_output=True, text=True, timeout=8)
            return (out.stdout or "").rstrip("\n")
        except Exception:
            return ""


def _clip_set(text: str) -> None:
    try:
        import pyperclip
        pyperclip.copy(text)
        return
    except Exception:
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard", "-Value",
                        text], timeout=8)


# --------------------------------------------------------------------------- #
# notifications
# --------------------------------------------------------------------------- #

def notify(title: str = "AstralBody", message: str = "", **kwargs) -> Dict[str, Any]:
    """Show a native Windows toast notification."""
    t = (title or "AstralBody").replace("'", "")
    m = (message or "").replace("'", "")
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
        "$tpl=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$tx=$tpl.GetElementsByTagName('text');"
        f"$tx.Item(0).AppendChild($tpl.CreateTextNode('{t}'))|Out-Null;"
        f"$tx.Item(1).AppendChild($tpl.CreateTextNode('{m}'))|Out-Null;"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($tpl);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('AstralBody').Show($toast);"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=10,
                       capture_output=True)
        return _ok([_alert(f"Sent a notification: “{title}”.", "success")], {"sent": True})
    except Exception as exc:
        return _ok([_alert(f"Couldn't show a notification: {exc}", "error")])


# --------------------------------------------------------------------------- #
# open path / url
# --------------------------------------------------------------------------- #

def open_path(path: str = "", **kwargs) -> Dict[str, Any]:
    """Open a file, folder, or URL with its default Windows handler."""
    if not path:
        return _ok([_alert("Provide a path or URL to open.", "warning")])
    try:
        if path.startswith(("http://", "https://")):
            import webbrowser
            webbrowser.open(path)
        else:
            os.startfile(os.path.expandvars(os.path.expanduser(path)))  # noqa: S606 (Windows)
        return _ok([_alert(f"Opened: {path}", "success")], {"opened": path})
    except Exception as exc:
        return _ok([_alert(f"Couldn't open '{path}': {exc}", "error")])


# --------------------------------------------------------------------------- #
# list directory
# --------------------------------------------------------------------------- #

def list_directory(path: str = "", **kwargs) -> Dict[str, Any]:
    """List the entries of a folder (defaults to the user's home)."""
    target = os.path.expandvars(os.path.expanduser(path)) if path else os.path.expanduser("~")
    if not os.path.isdir(target):
        return _ok([_alert(f"Not a folder: {target}", "error")])
    rows = []
    for name in sorted(os.listdir(target))[:200]:
        full = os.path.join(target, name)
        is_dir = os.path.isdir(full)
        try:
            size = "" if is_dir else f"{os.path.getsize(full):,} B"
        except OSError:
            size = ""
        rows.append([("📁 " if is_dir else "📄 ") + name, "folder" if is_dir else "file", size])
    return _ok([{"type": "card", "title": f"{target}  ({len(rows)} items)",
                 "content": [{"type": "table", "headers": ["Name", "Type", "Size"], "rows": rows}]}],
               {"path": target, "count": len(rows)})


TOOL_REGISTRY: Dict[str, dict] = {
    "get_system_info": {"function": get_system_info, "scope": "tools:system",
                        "description": "Report this Windows PC's OS, CPU, memory and disk usage.",
                        "input_schema": {"type": "object", "properties": {}}},
    "read_clipboard": {"function": read_clipboard, "scope": "tools:system",
                       "description": "Read the current text on the Windows clipboard.",
                       "input_schema": {"type": "object", "properties": {}}},
    "write_clipboard": {"function": write_clipboard, "scope": "tools:write",
                        "description": "Copy text to the Windows clipboard.",
                        "input_schema": {"type": "object", "properties": {
                            "text": {"type": "string", "description": "Text to copy"}},
                            "required": ["text"]}},
    "notify": {"function": notify, "scope": "tools:write",
               "description": "Show a native Windows toast notification.",
               "input_schema": {"type": "object", "properties": {
                   "title": {"type": "string"}, "message": {"type": "string"}}}},
    "open_path": {"function": open_path, "scope": "tools:write",
                  "description": "Open a file, folder, or URL with its default Windows app.",
                  "input_schema": {"type": "object", "properties": {
                      "path": {"type": "string", "description": "Path or URL"}},
                      "required": ["path"]}},
    "list_directory": {"function": list_directory, "scope": "tools:system",
                       "description": "List the contents of a folder.",
                       "input_schema": {"type": "object", "properties": {
                           "path": {"type": "string", "description": "Folder path (default: home)"}}}},
}
