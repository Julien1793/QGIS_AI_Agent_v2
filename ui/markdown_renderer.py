# ui/markdown_renderer.py
import re
import html as _html
import json

# Private-use Unicode characters used as safe placeholders (won't appear in user text)
_PRE_MARK = ""   # wraps code-block placeholders
_CODE_MARK = ""  # wraps inline-code placeholders
_BR_MARK = ""    # wraps BR token
_PH_MARK = ""    # protects block placeholders during html.escape
_CELL_CODE_MARK = ""  # wraps code spans inside table cells


def looks_like_html(s: str) -> bool:
    """Lightweight heuristic: detect HTML containing list/table/blockquote/code elements."""
    return bool(re.search(r"<(ul|ol|li|table|thead|tbody|tr|th|td|pre|code|blockquote|h[1-6]|p)\b", s or "", re.I))


def pass_through_html_with_md_classes(html_str: str) -> str:
    """
    Pass through LLM-generated HTML while injecting class='md' on block elements.
    Also strips <script> tags and inline event handlers.
    """
    html_str = re.sub(r"(?is)<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", html_str)
    html_str = re.sub(r"\son[a-zA-Z]+\s*=", " data-on-removed=", html_str)
    html_str = re.sub(r"</?br\s*/?>", "<br>", html_str, flags=re.I)
    for tag in ("ul", "ol", "table", "pre", "code", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"):
        html_str = re.sub(rf"<{tag}\b(?![^>]*\bclass=)", rf"<{tag} class='md'", html_str, flags=re.I)
    return html_str


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<\|\w+\|>", "", s)
    s = re.sub(r"\bto\s*=\s*[\w\-/]+", "", s, flags=re.I)
    s = re.sub(r"\bjson\b(?=\s*\{)", "", s, flags=re.I)
    if "<|" in s or "to=" in s:
        m = re.search(r"(\{[^{}]*\}|\{[\s\S]*\})\s*$", s, flags=re.S)
        if m:
            raw = m.group(1)
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    for k in ("response", "content", "message", "text"):
                        v = obj.get(k)
                        if isinstance(v, str) and v.strip():
                            s = s[:m.start(1)].strip() + (" " if s[:m.start(1)].strip() else "") + v
                            break
            except Exception:
                pass
    s = _html.unescape(s)
    s = (s
        .replace(" ", " ")
        .replace(" ", " ")
        .replace(" ", " ")
        .replace("‑", "-"))
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s


def render_markdownish_chat(text: str) -> str:
    src = text or ""
    src = normalize_text(src)

    if looks_like_html(src):
        return pass_through_html_with_md_classes(src)

    def _apply_strong_em(s: str) -> str:
        s = re.sub(r"(?<!\\)(\*\*|__)\s*([^\s].*?[^\s])\s*\1", r"<b>\2</b>", s, flags=re.DOTALL)
        s = re.sub(r"(?<!\\)(?<!\*)\*(?!\*)\s*([^\s].*?[^\s])\s*(?<!\*)\*(?!\*)", r"<i>\1</i>", s, flags=re.DOTALL)
        s = re.sub(r"(?<!\\)(?<!_)_(?!_)\s*([^\s].*?[^\s])\s*(?<!_)_(?!_)", r"<i>\1</i>", s, flags=re.DOTALL)
        return s

    def _protect_codeblocks(s: str):
        blocks = []

        def _protect_html_pre(m):
            blocks.append(m.group(0))
            return f"{_PRE_MARK}PRE{len(blocks)-1}{_PRE_MARK}"
        s = re.sub(r"<pre\b[\s\S]*?</pre>", _protect_html_pre, s, flags=re.I)

        def _protect_fence(m):
            inner = m.group(2) or ""
            inner = _html.escape(inner)
            html_block = f"<pre class='md'><code class='md'>{inner}</code></pre>"
            blocks.append(html_block)
            return f"{_PRE_MARK}PRE{len(blocks)-1}{_PRE_MARK}"
        s = re.sub(r"```(\w+)?\s*\n([\s\S]*?)\n```", _protect_fence, s, flags=re.MULTILINE)
        return s, blocks

    def _restore_codeblocks(s: str, blocks):
        return re.sub(
            f"{re.escape(_PRE_MARK)}PRE(\\d+){re.escape(_PRE_MARK)}",
            lambda m: blocks[int(m.group(1))], s
        )

    def _inline_pass(s: str) -> str:
        s = normalize_text(s)
        s = (s.replace("&lt;br&gt;", "<br>")
            .replace("&lt;br/&gt;", "<br>")
            .replace("&lt;br /&gt;", "<br>"))

        BR_TOKEN = f"{_BR_MARK}BR{_BR_MARK}"
        s = s.replace("<br>", BR_TOKEN)

        code_spans = []
        def _protect_inline_code(m):
            code_spans.append(m.group(1))
            return f"{_CODE_MARK}CODE{len(code_spans)-1}{_CODE_MARK}"
        s = re.sub(r"`([^`]+)`", _protect_inline_code, s)

        PH = _PH_MARK + "PH"
        s = s.replace(_PRE_MARK, PH + "A").replace(_CODE_MARK, PH + "B")

        s = _html.escape(s).replace("\r\n", "\n")

        s = s.replace(PH + "A", _PRE_MARK).replace(PH + "B", _CODE_MARK)

        s = _apply_strong_em(s)

        def _mk_link(m):
            label = m.group(1)
            url = _html.escape(m.group(2))
            return f"<a href='{url}'>{label}</a>"
        s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", _mk_link, s)

        def _auto(m):
            u = m.group(1)
            return f"<a href='{_html.escape(u)}'>{_html.escape(u)}</a>"
        s = re.sub(r"(?<!['\">])(https?://[^\s<]+)", _auto, s)

        def _restore_code(m):
            idx = int(m.group(1))
            return f"<code class='md'>{_html.escape(code_spans[idx])}</code>"
        s = re.sub(
            f"{re.escape(_CODE_MARK)}CODE(\\d+){re.escape(_CODE_MARK)}",
            _restore_code, s
        )

        s = s.strip("\n")
        s = s.replace("\n", "<br>")
        s = s.replace(BR_TOKEN, "<br>")

        return s

    def _render_blockquote(block: str) -> str:
        inner = "\n".join([re.sub(r"^\s*>\s?", "", ln) for ln in block.splitlines()])
        return f"<blockquote class='md'>{_inline_pass(inner)}</blockquote>"

    if re.search(r"<(table|pre|code|ul|ol|blockquote|h[1-6])\b[^>]*class=['\"]md['\"]", src, re.I):
        safe, blocks = _protect_codeblocks(src)
        safe = _inline_pass(safe)
        return _restore_codeblocks(safe, blocks)

    work, blocks = _protect_codeblocks(src)
    paragraphs = re.split(r"\n{2,}", work)
    out = []

    for para in paragraphs:
        p = para.strip()
        if not p:
            continue

        lines = p.splitlines()

        if all(re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", ln) for ln in lines):
            out.append("<hr>")
            continue

        def is_sep_row(s: str) -> bool:
            return bool(re.match(r"^\s*\|?\s*:?-{3,}.*\|\s*(?:\:?-{3,}\:?\s*\|.*)*$", s.strip()))

        i = 0
        emitted_table = False
        while i < len(lines):
            if ("|" in lines[i] and i+1 < len(lines) and "|" in lines[i+1] and is_sep_row(lines[i+1])):
                j = i + 2
                while j < len(lines) and "|" in lines[j]:
                    j += 1
                tbl_lines = lines[i:j]
                out.append(md_table_block_to_html(tbl_lines))
                emitted_table = True
                i = j
            else:
                i += 1
        if emitted_table:
            continue

        if all(ln.strip().startswith(">") for ln in lines):
            out.append(_render_blockquote(p))
            continue

        m_h = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", p)
        if m_h:
            lvl = min(6, len(m_h.group(1)))
            inner = _inline_pass(m_h.group(2).strip())
            out.append(f"<h{lvl} class='md'>{inner}</h{lvl}>")
            continue

        if all(re.match(r"^\s*\d+\.\s+.+", ln) for ln in lines) and len(lines) > 1:
            items = []
            for ln in lines:
                item = re.sub(r"^\s*\d+\.\s+", "", ln).strip()
                items.append(f"<li>{_inline_pass(item)}</li>")
            out.append("<ol class='md'>" + "".join(items) + "</ol>")
            continue

        if all((ln.strip().startswith("- ") or ln.strip().startswith("* ")) for ln in lines) and len(lines) > 1:
            items = []
            for ln in lines:
                it = ln.strip()[2:]
                m_task = re.match(r"^\[( |x|X)\]\s+(.*)$", it)
                if m_task:
                    checked = (m_task.group(1).lower() == "x")
                    label = _inline_pass(m_task.group(2))
                    cb = "<input type='checkbox' disabled " + ("checked>" if checked else ">")
                    items.append(f"<li>{cb} {label}</li>")
                else:
                    items.append(f"<li>{_inline_pass(it)}</li>")
            out.append("<ul class='md'>" + "".join(items) + "</ul>")
            continue

        def _process_mixed(lines_):
            parts = []
            i = 0
            while i < len(lines_):
                ln = lines_[i]
                m_hx = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", ln.rstrip())
                if m_hx:
                    lvl = min(6, len(m_hx.group(1)))
                    parts.append(
                        f"<h{lvl} class='md'>{_inline_pass(m_hx.group(2).strip())}</h{lvl}>"
                    )
                    i += 1
                    continue
                if re.match(r"^\s*[-*]\s+", ln):
                    items = []
                    while i < len(lines_) and re.match(r"^\s*[-*]\s+", lines_[i]):
                        it = re.sub(r"^\s*[-*]\s+", "", lines_[i])
                        m_task = re.match(r"^\[( |x|X)\]\s+(.*)$", it)
                        if m_task:
                            checked = m_task.group(1).lower() == "x"
                            cb = "<input type='checkbox' disabled " + (
                                "checked>" if checked else ">")
                            items.append(f"<li>{cb} {_inline_pass(m_task.group(2))}</li>")
                        else:
                            items.append(f"<li>{_inline_pass(it)}</li>")
                        i += 1
                    parts.append("<ul class='md'>" + "".join(items) + "</ul>")
                    continue
                if re.match(r"^\s*\d+\.\s+", ln):
                    items = []
                    while i < len(lines_) and re.match(r"^\s*\d+\.\s+", lines_[i]):
                        it = re.sub(r"^\s*\d+\.\s+", "", lines_[i]).strip()
                        items.append(f"<li>{_inline_pass(it)}</li>")
                        i += 1
                    parts.append("<ol class='md'>" + "".join(items) + "</ol>")
                    continue
                parts.append(_inline_pass(ln))
                i += 1
            return "<br>".join(pt for pt in parts if pt)

        out.append(_process_mixed(lines))

    final_html = "<br>".join(out)
    return _restore_codeblocks(final_html, blocks)


def md_table_block_to_html(lines):
    r"""Convert a block of markdown table lines to HTML <table>."""

    def _apply_strong_em_cell(s: str) -> str:
        s = re.sub(r"(?<!\\)(\*\*|__)\s*([^\s].*?[^\s])\s*\1", r"<b>\2</b>", s, flags=re.DOTALL)
        s = re.sub(r"(?<!\\)(?<!\*)\*(?!\*)\s*([^\s].*?[^\s])\s*(?<!\*)\*(?!\*)", r"<i>\1</i>", s, flags=re.DOTALL)
        s = re.sub(r"(?<!\\)(?<!_)_(?!_)\s*([^\s].*?[^\s])\s*(?<!_)_(?!_)", r"<i>\1</i>", s, flags=re.DOTALL)
        return s

    def smart_split(row: str):
        s = row.strip()
        if s.startswith("|"): s = s[1:]
        if s.endswith("|"): s = s[:-1]
        cells, buf = [], []
        in_code = False
        esc = False
        i = 0
        while i < len(s):
            ch = s[i]
            if esc:
                buf.append(ch); esc = False
            elif ch == "\\":
                esc = True
            elif ch == "`":
                in_code = not in_code
                buf.append(ch)
            elif ch == "|" and not in_code:
                cells.append("".join(buf).strip()); buf = []
            else:
                buf.append(ch)
            i += 1
        cells.append("".join(buf).strip())
        return cells

    if len(lines) < 2:
        return _html.escape("\n".join(lines))

    header = smart_split(lines[0])
    sep    = smart_split(lines[1])
    body   = [smart_split(r) for r in lines[2:]] if len(lines) > 2 else []

    ncols = max(len(header), len(sep), max((len(r) for r in body), default=0))

    def normalize(row):
        r = list(row)
        if len(r) < ncols:
            r += [""] * (ncols - len(r))
        elif len(r) > ncols:
            r = r[:ncols]
        return r

    header = normalize(header)
    sep    = normalize(sep)
    body   = [normalize(r) for r in body]

    aligns = []
    for cell in sep:
        c = cell.replace(" ", "")
        if c.startswith(":") and c.endswith(":"): aligns.append("center")
        elif c.endswith(":"): aligns.append("right")
        elif c.startswith(":"): aligns.append("left")
        else: aligns.append(None)
    if len(aligns) < ncols:
        aligns += [None] * (ncols - len(aligns))
    elif len(aligns) > ncols:
        aligns = aligns[:ncols]

    def render_cell(cell, idx, tag="td"):
        txt_raw = (cell or "").strip()
        txt_raw = _html.unescape(txt_raw)
        txt_raw = (txt_raw
                .replace("<br/>", "<br>")
                .replace("<br />", "<br>")
                .replace("&lt;br/&gt;", "<br>")
                .replace("&lt;br /&gt;", "<br>")
                .replace("&lt;br&gt;", "<br>"))
        txt_raw = txt_raw.replace("\\|", "|")
        txt_raw = normalize_text(txt_raw)
        BR_TOKEN = f"{_BR_MARK}BR{_BR_MARK}"
        txt_raw = txt_raw.replace("<br>", BR_TOKEN)
        esc = _html.escape(txt_raw)
        code_spans = []
        def _protect_code(m):
            code_spans.append(m.group(1))
            return f"{_CELL_CODE_MARK}CODE{len(code_spans)-1}{_CELL_CODE_MARK}"
        esc = re.sub(r"`([^`]+)`", _protect_code, esc)
        esc = _apply_strong_em_cell(esc)
        def _restore_code(m):
            idxc = int(m.group(1))
            return f"<code class='md'>{code_spans[idxc]}</code>"
        esc = re.sub(
            f"{re.escape(_CELL_CODE_MARK)}CODE(\\d+){re.escape(_CELL_CODE_MARK)}",
            _restore_code, esc
        )
        esc = esc.replace(BR_TOKEN, "<br>")
        a = aligns[idx] if idx < len(aligns) else None
        style = f" style='text-align:{a};'" if a else ""
        return f"<{tag}{style}>{esc}</{tag}>"

    ths = "".join(render_cell(h, i, "th") for i, h in enumerate(header))
    trs = []
    for row in body:
        tds = "".join(render_cell(v, i, "td") for i, v in enumerate(row))
        trs.append(f"<tr>{tds}</tr>")

    return f"<table class='md'><thead><tr>{ths}</tr></thead><tbody>{''.join(trs)}</tbody></table>"
