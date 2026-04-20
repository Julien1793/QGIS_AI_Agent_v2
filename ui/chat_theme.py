# ui/chat_theme.py
#
# Centralised visual theme for all chat messages.
# Uses HTML <table> elements and inline styles to guarantee correct rendering
# inside QTextBrowser (Qt): its CSS engine does not support display:table-cell,
# border-left on div, or border-radius.

import html as _html


# ═══════════════════════════════════════════════════════════════
# CSS — scoped to markdown elements only (.md class)
# Structural elements (chat bubbles, agent-steps blocks) use
# inline styles to work around Qt's CSS renderer limitations.
# ═══════════════════════════════════════════════════════════════

CHAT_CSS = """
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    color: #e8eaed;
    background-color: #1a1b1e;
}

h1.md { font-size: 17px; font-weight: bold; color: #e8eaed; margin: 8px 0 4px 0; }
h2.md { font-size: 15px; font-weight: bold; color: #e0e8f0; margin: 7px 0 3px 0; }
h3.md { font-size: 14px; font-weight: bold; color: #d0dcea; margin: 6px 0 3px 0; }
h4.md, h5.md, h6.md { font-size: 13px; font-weight: bold; color: #c8d4e0; margin: 5px 0 2px 0; }

p { margin: 3px 0; }

ul.md { margin: 4px 0 4px 18px; padding: 0; list-style: disc; }
ol.md { margin: 4px 0 4px 18px; padding: 0; list-style: decimal; }
li   { margin: 1px 0; }

pre.md {
    background-color: #0f1419;
    color: #d4d4d4;
    padding: 8px 12px;
    margin: 5px 0;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}

code.md {
    background-color: #2a2d35;
    color: #e0c080;
    padding: 1px 4px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}

blockquote.md {
    background-color: #1a2330;
    color: #a8c5e0;
    padding: 4px 10px;
    margin: 4px 0;
}

table.md {
    border-collapse: collapse;
    margin: 5px 0;
    font-size: 12px;
    background-color: #1c1e25;
}
table.md th, table.md td {
    border: 1px solid #2d3038;
    padding: 4px 8px;
    vertical-align: top;
    text-align: left;
}
table.md th {
    background-color: #252830;
    color: #c8d0d8;
    font-weight: bold;
}
table.md tr:nth-child(even) td { background-color: #1f2128; }

hr { border-top: 1px solid #32343c; }
a  { color: #7fb8ff; }
"""


# ═══════════════════════════════════════════════════════════════
# HELPERS HTML
# ═══════════════════════════════════════════════════════════════

def _initials(name: str) -> str:
    if not name:
        return "?"
    parts = name.strip().split()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _avatar_td(initials: str, bgcolor: str, color: str) -> str:
    """Build the avatar cell (left column of chat bubbles) with a colored initials badge."""
    return (
        f'<td width="36" valign="top" align="center" style="padding-right:8px;padding-top:2px;">'
        f'<table cellspacing="0" cellpadding="0"><tr>'
        f'<td width="32" align="center" bgcolor="{bgcolor}"'
        f' style="background-color:{bgcolor};color:{color};'
        f'font-size:11px;font-weight:bold;padding:8px 4px;">'
        f'{_html.escape(initials)}</td>'
        f'</tr></table>'
        f'</td>'
    )


def wrap_user(body_html: str, label: str = "Vous",
              avatar_initials: str = None, footer: str = "",
              context_badge: bool = False) -> str:
    initials = avatar_initials or _initials(label)
    badge = " 📌" if context_badge else ""
    footer_html = (
        f'<p style="font-size:10px;color:#707880;font-style:italic;margin:4px 0 0 0;">'
        f'{_html.escape(footer)}</p>'
    ) if footer else ""

    return (
        f'<table cellspacing="0" cellpadding="0" width="100%" style="margin:6px 0;">'
        f'<tr valign="top">'
        + _avatar_td(initials, "#4a4a7a", "#e0e0ff") +
        f'<td bgcolor="#2a2a3f" style="background-color:#2a2a3f;color:#e8eaed;'
        f'border:1px solid #3d3d55;padding:10px 14px;">'
        f'<p style="font-size:11px;color:#a8b2d8;font-weight:bold;margin:0 0 4px 0;">'
        f'{_html.escape(label)}{badge}</p>'
        f'{body_html}'
        f'{footer_html}'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


def wrap_assistant(body_html: str, label: str = "Assistant",
                   avatar_initials: str = "AI",
                   tokens_info: str = "",
                   agent_steps_html: str = "",
                   context_badge: bool = False) -> str:
    badge = " 📌" if context_badge else ""
    footer_html = (
        f'<p style="font-size:10px;color:#707880;font-style:italic;margin:4px 0 0 0;">'
        f'{_html.escape(tokens_info)}</p>'
    ) if tokens_info else ""
    inner = (agent_steps_html or "") + body_html

    return (
        f'<table cellspacing="0" cellpadding="0" width="100%" style="margin:6px 0;">'
        f'<tr valign="top">'
        + _avatar_td(avatar_initials, "#3a5a7f", "#c8e0ff") +
        f'<td bgcolor="#22232a" style="background-color:#22232a;color:#e8eaed;'
        f'border:1px solid #32343c;padding:10px 14px;">'
        f'<p style="font-size:11px;color:#8fb8d8;font-weight:bold;margin:0 0 6px 0;">'
        f'{_html.escape(label)}{badge}</p>'
        f'{inner}'
        f'{footer_html}'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


def wrap_system(text: str) -> str:
    return (
        f'<p style="margin:4px 36px;padding:6px 10px;'
        f'background-color:#1e2330;color:#b8c8e0;'
        f'font-size:12px;font-style:italic;border:1px solid #2d3545;">'
        f'{_html.escape(text)}</p>'
    )


def wrap_code(code_text: str, language: str = "python", title: str = "") -> str:
    header = _html.escape(title or language.upper())
    escaped = _html.escape(code_text)
    return (
        f'<table cellspacing="0" cellpadding="0" width="100%" style="margin:6px 0;border:1px solid #2a2d35;">'
        f'<tr><td bgcolor="#1a1d24" style="background-color:#1a1d24;padding:5px 10px;">'
        f'<span style="font-size:11px;color:#8a9aa8;font-weight:bold;">{header}</span>'
        f'</td></tr>'
        f'<tr><td bgcolor="#0f1419" style="background-color:#0f1419;padding:8px 12px;">'
        f'<pre style="margin:0;font-family:\'Consolas\',\'Courier New\',monospace;font-size:12px;color:#d4d4d4;">'
        f'{escaped}</pre>'
        f'</td></tr>'
        f'</table>'
    )


def _wrap_banner_table(border_color: str, bg_color: str, text_color: str,
                       title: str, body: str = "") -> str:
    body_html = (
        f'<p style="margin:2px 0;color:{text_color};">{_html.escape(body)}</p>'
    ) if body else ""
    return (
        f'<table cellspacing="0" cellpadding="0" width="100%" style="margin:6px 0;">'
        f'<tr valign="top">'
        f'<td width="3" bgcolor="{border_color}" style="background-color:{border_color};padding:0;">&nbsp;</td>'
        f'<td bgcolor="{bg_color}" style="background-color:{bg_color};color:{text_color};padding:8px 12px;font-size:12px;">'
        f'<p style="font-weight:bold;margin:0 0 2px 0;">{_html.escape(title)}</p>'
        f'{body_html}'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


def wrap_banner(kind: str, title: str, body: str = "") -> str:
    _cfg = {
        "error":   ("#c85050", "#2a1818", "#f0b0b0"),
        "warning": ("#c89030", "#2a2418", "#f0d490"),
        "success": ("#50a060", "#182a1c", "#a0d0a8"),
        "info":    ("#5a8fbf", "#182430", "#a8c5e0"),
    }
    bc, bg, tc = _cfg.get(kind, ("#5a8fbf", "#182430", "#a8c5e0"))
    return _wrap_banner_table(bc, bg, tc, title, body)


def wrap_error(title: str, body: str = "") -> str:
    return wrap_banner("error", title, body)


def wrap_warning(title: str, body: str = "") -> str:
    return wrap_banner("warning", title, body)


def wrap_success(title: str, body: str = "") -> str:
    return wrap_banner("success", title, body)


def wrap_info(title: str, body: str = "") -> str:
    return wrap_banner("info", title, body)
