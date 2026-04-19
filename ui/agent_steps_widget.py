# ui/agent_steps_widget.py
#
# Progressive rendering of the agent execution trace.
# Uses <table> elements and inline styles to guarantee correct rendering
# inside QTextBrowser (Qt does not support CSS border-left on div elements
# or display:block via setDefaultStyleSheet for nested divs).

import html as _html


class AgentStepsRenderer:
    """
    Incrementally builds an HTML block representing the agent's execution steps.

    Usage:
        renderer = AgentStepsRenderer()
        renderer.add_event(event)
        html = renderer.to_html()
    """

    ICONS = {
        "thinking":       "◐",
        "intent":         "◉",
        "iteration":      "▸",
        "tool_call":      "⚙",
        "tool_result":    "✓",
        "tool_error":     "✗",
        "final":          "✔",
        "max_iterations": "⚠",
    }

    # Text color per event type.
    _COLORS = {
        "thinking":       "#8fb8d8",
        "intent":         "#a8c5e0",
        "iteration":      "#6a7a8a",
        "tool_call":      "#c0d0e0",
        "tool_result":    "#7fc98f",
        "tool_error":     "#e89090",
        "final":          "#8fb8d8",
        "max_iterations": "#e89090",
    }

    def __init__(self):
        self.events = []

    def add_event(self, event: dict):
        if event and isinstance(event, dict):
            self.events.append(event)

    def reset(self):
        self.events = []

    def to_html(self, show_final_marker: bool = False) -> str:
        if not self.events:
            return ""

        rows = [self._render_event(e) for e in self.events]
        if show_final_marker:
            rows.append(
                '<p style="color:#4a5565;font-size:10px;text-align:center;margin:6px 0 0 0;">'
                '• • •</p>'
            )

        inner = "".join(rows)
        # 2-column table: a 3px colored strip on the left simulates a CSS border-left,
        # which is not supported inside QTextBrowser.
        return (
            '<table cellspacing="0" cellpadding="0" width="100%"'
            ' style="margin:0 0 10px 0;">'
            '<tr valign="top">'
            '<td width="3" bgcolor="#5a8fbf"'
            ' style="background-color:#5a8fbf;padding:0;">&nbsp;</td>'
            '<td bgcolor="#1c2530"'
            ' style="background-color:#1c2530;padding:8px 12px;">'
            f'{inner}'
            '</td>'
            '</tr>'
            '</table>'
        )

    def _render_event(self, event: dict) -> str:
        etype = event.get("type", "")
        text  = event.get("text", "")
        icon  = self.ICONS.get(etype, "•")
        color = self._COLORS.get(etype, "#c0c5cc")

        safe_text = _html.escape(text).replace("\n", "<br>")
        if etype == "tool_call":
            safe_text = self._highlight_tool_name(event, safe_text)

        italic = "font-style:italic;" if etype in ("thinking", "final") else ""
        return (
            f'<p style="margin:2px 0;color:{color};font-size:12px;{italic}">'
            f'<b style="color:{color};">{icon}</b> {safe_text}'
            f'</p>'
        )

    def _highlight_tool_name(self, event: dict, safe_text: str) -> str:
        data = event.get("data") or {}
        tool_name = data.get("name")
        if tool_name and tool_name in safe_text:
            span = (
                f'<span style="font-family:\'Consolas\',monospace;'
                f'background-color:#2a3545;color:#a8d4f0;'
                f'padding:1px 4px;font-size:11px;">{tool_name}</span>'
            )
            return safe_text.replace(tool_name, span, 1)
        return safe_text


def make_agent_block_html(events: list, show_final_marker: bool = False) -> str:
    """Stateless helper: build the full agent-steps HTML from a list of event dicts."""
    r = AgentStepsRenderer()
    for e in events:
        r.add_event(e)
    return r.to_html(show_final_marker=show_final_marker)
