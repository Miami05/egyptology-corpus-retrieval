"""Drive one real Streamlit session so the server's in-process caches are built
before the first visitor arrives.

Why a websocket client and not "just run the builders in another process": every
expensive object the app holds lives in `st.cache_resource`, which is a
*process-global* cache inside the running Streamlit server. A second process
(`ExecStartPost` calling a plain Python script) builds its own copies and throws
them away — it warms the OS page cache and nothing else. Streamlit also has no
HTTP route that runs the script: `/_stcore/health` answers from the web layer,
and `GET /` serves the static bundle. A session — and therefore a script run —
begins only when a client opens the `/_stcore/stream` websocket and asks for a
rerun. So that is what this does, with `tornado`, which Streamlit already
depends on, and Streamlit's own protobufs. No new dependency.

The script run this triggers is a *real* one: whatever the app builds eagerly
during a run (see `WARM_STAGE_RESOURCES` in `app/ui/whyptology_app.py`) is
built here, into the cache every later session shares.

The run is also a smoke test (audit A11). When the app's code is broken, Streamlit
does not fail the run: it renders the traceback as an `exception` element and then
reports `script_finished` with FINISHED_SUCCESSFULLY, so "the script finished" says
nothing about the page working. This client therefore watches the elements as they
arrive and fails on any `exception` element (not a warning), and with
`--expect-text` it also fails unless some element shows that text, which proves a
real search rendered a real result. `<style>` blocks and HTML comments do not count:
the app injects its whole theme stylesheet on every page, and that names every result
class (`.suggestion-card {`) whether or not a result was drawn. An expectation shaped
like an attribute (`class="suggestion-card"`) is stricter: it passes only on a real
start tag carrying that attribute, in an element that renders HTML (`st.html`, or
`st.markdown` with unsafe_allow_html), outside any non-rendering element (style,
script, template, textarea, title, noscript) and, for Markdown, only where the Markdown
parser passes it through as raw HTML: never inside code, fenced, indented or inline, at
any depth of block quotes and list items (see `markdown_html`). The same markup shown as
text, quoted in a comment or a code span, or written inside a `<textarea>` is not a
result.

Usage (never blocks a service start for longer than --timeout):

    python scripts/warm_streamlit.py --url http://127.0.0.1:8502 --timeout 300
    python scripts/warm_streamlit.py --query "..." --expect-text 'class="suggestion-card"'

Exit codes: 0 the run finished and rendered no exception (and the expected text, if
asked for, appeared); 1 anything else: timeout, closed connection, compile error,
an exception element, or the expected text missing.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import re
import sys
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlencode, urlparse, urlunparse

from tornado.httpclient import HTTPRequest
from tornado.ioloop import IOLoop
from tornado.websocket import websocket_connect

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

HEALTH_PATH = "/_stcore/health"
STREAM_PATH = "/_stcore/stream"

# A <style> block, or an unclosed one running to the end of the element.
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?(?:</style\s*>|\Z)", re.IGNORECASE | re.DOTALL)
# An HTML comment, or an unclosed one running to the end of the element.
_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
# `name="value"`: an expectation that names an attribute a real element must carry.
_ATTRIBUTE_EXPECTATION = re.compile(r'^([A-Za-z_:][-A-Za-z0-9_:.]*)="([^"<>]*)"$')
# Elements whose content the browser never draws as markup.
_NON_RENDERING = frozenset({"style", "script", "template", "textarea", "title", "noscript", "xmp"})


# --- Markdown: what an st.markdown body draws as HTML --------------------------------
#
# Streamlit renders Markdown as CommonMark (react-markdown), so a tag only draws when the
# Markdown parser passes it through as raw HTML. The code below is a small CommonMark
# block parser (block quotes, list items, fenced and indented code, HTML blocks,
# paragraphs, headings, thematic breaks) and an inline scanner that, left to right like
# CommonMark, takes a backtick run as a code span or a `<` as a raw tag, whichever starts
# first. Only raw HTML (HTML blocks verbatim, inline tags exactly as written) reaches the
# HTML parser; every other character goes in escaped. Nothing is ever cut out of a tag,
# so no attribute can be put together from the pieces around a code span.
#
# Where it is simpler than CommonMark it hides more, never less: an unclosed inline
# comment hides the rest of its paragraph, a paragraph that starts like a link reference
# definition is hidden whole, and a link destination or title is never read as a tag.

# CommonMark's raw-HTML grammar (spec 0.31, section 6.6).
_ATTRIBUTE = r"""(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?)"""
_INLINE_TAG = re.compile(
    rf"<[A-Za-z][A-Za-z0-9-]*{_ATTRIBUTE}*\s*/?>|</[A-Za-z][A-Za-z0-9-]*\s*>"
)
_INLINE_COMMENT = re.compile(r"<!-->|<!--->|<!--.*?-->", re.DOTALL)
# Processing instructions, declarations, CDATA and autolinks: never a start tag.
_INLINE_OTHER = re.compile(
    r"<\?.*?\?>|<![A-Za-z][^>]*>|<!\[CDATA\[.*?\]\]>"
    r"|<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*>|<[^\s<>@]+@[A-Za-z0-9.-]+>",
    re.DOTALL,
)
# `](destination "title")`: a `<...>` destination is a URL, not a tag.
_LINK_TAIL = re.compile(
    r"""\]\(\s*(?:<[^<>\n]*>|[^\s<>()]*)(?:\s+(?:"[^"]*"|'[^']*'|\([^()]*\)))?\s*\)"""
)
_BACKTICKS = re.compile(r"`+")
_REFERENCE_DEFINITION = re.compile(r"^\[(?:[^\]\\]|\\.)+\]:")
_ASCII_PUNCTUATION = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")

_BLOCK_HTML_TAGS = frozenset(
    "address article aside base basefont blockquote body caption center col colgroup dd "
    "details dialog dir div dl dt fieldset figcaption figure footer form frame frameset "
    "h1 h2 h3 h4 h5 h6 head header hr html iframe legend li link main menu menuitem nav "
    "noframes ol optgroup option p param search section summary table tbody td tfoot th "
    "thead title tr track ul".split()
)
# HTML block start conditions 1-5, each with the end condition that closes it.
_HTML_BLOCK_ENDS = (
    (re.compile(r"<(?:script|pre|style|textarea)(?:\s|>|$)", re.I),
     re.compile(r"</(?:script|pre|style|textarea)>", re.I)),
    (re.compile(r"<!--"), re.compile(r"-->")),
    (re.compile(r"<\?"), re.compile(r"\?>")),
    (re.compile(r"<![A-Za-z]"), re.compile(r">")),
    (re.compile(r"<!\[CDATA\["), re.compile(r"\]\]>")),
)
_HTML_BLOCK_6 = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)(?:\s|/?>|$)")
_HTML_BLOCK_7 = re.compile(
    rf"(?:<[A-Za-z][A-Za-z0-9-]*{_ATTRIBUTE}*\s*/?>|</[A-Za-z][A-Za-z0-9-]*\s*>)\s*$"
)
_ATX_HEADING = re.compile(r"#{1,6}(?:[ \t]|$)")
_FENCE_OPEN = re.compile(r"(`{3,}|~{3,})")
_SETEXT_EQUALS = re.compile(r"=+[ \t]*$")
_THEMATIC_BREAK = re.compile(r"(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_BULLET = re.compile(r"[*+-]")
_ORDERED = re.compile(r"(\d{1,9})[.)]")

_CONTAINERS = ("document", "quote", "item")
_TAKES_LINES = ("fence", "indented", "html")


@dataclass(eq=False)
class _Block:
    kind: str  # document, quote, item, paragraph, heading, rule, fence, indented, html
    parent: "_Block | None" = None
    children: list["_Block"] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    open: bool = True
    offset: int = 0  # item: columns a continuation line must be indented by
    fence: str = ""  # fence: the opening run of backticks or tildes
    html_end: "re.Pattern[str] | None" = None  # html, kinds 1-5: what closes it


def _nonspace(line: str, pos: int) -> int:
    while pos < len(line) and line[pos] == " ":
        pos += 1
    return pos


class _MarkdownBlocks:
    """CommonMark's block phase (the two-pass algorithm in the spec's appendix), reduced
    to the blocks that decide whether a line is code, raw HTML or Markdown text."""

    def __init__(self) -> None:
        self.document = _Block("document")
        self.tip = self.document

    def _finalize(self, block: _Block) -> None:
        block.open = False
        self.tip = block.parent

    def _add(self, kind: str, **fields) -> _Block:
        while self.tip.kind not in _CONTAINERS:
            self._finalize(self.tip)
        block = _Block(kind, parent=self.tip, **fields)
        self.tip.children.append(block)
        self.tip = block
        return block

    def _close_unmatched(self, last_matched: _Block) -> None:
        while self.tip is not last_matched:
            self._finalize(self.tip)

    def _continues(self, block: _Block, line: str, pos: int) -> int | None | bool:
        """Column after this block's continuation marker; False when the line does not
        continue it; None when the line closed it (a closing fence)."""
        nxt = _nonspace(line, pos)
        indent, blank = nxt - pos, nxt >= len(line)
        if block.kind == "quote":
            if not blank and indent <= 3 and line[nxt] == ">":
                pos = nxt + 1
                return pos + 1 if line[pos:pos + 1] == " " else pos
            return False
        if block.kind == "item":
            if blank:
                return nxt if block.children else False
            return pos + block.offset if indent >= block.offset else False
        if block.kind == "fence":
            closing = _FENCE_OPEN.match(line, nxt) if indent <= 3 else None
            if closing and closing.group(1)[0] == block.fence[0] \
                    and len(closing.group(1)) >= len(block.fence) and not line[closing.end():].strip():
                self._finalize(block)
                return None
            return pos
        if block.kind == "indented":
            return pos + 4 if indent >= 4 else (nxt if blank else False)
        if block.kind == "html":
            return False if blank and block.html_end is None else pos
        if block.kind == "paragraph":
            return False if blank else pos
        return False  # heading, rule

    def _html_start(self, line: str, nxt: int, after_paragraph: bool):
        """(True, end condition or None) when an HTML block starts at `nxt`."""
        for start, end in _HTML_BLOCK_ENDS:
            if start.match(line, nxt):
                return True, end
        tag = _HTML_BLOCK_6.match(line, nxt)
        if tag and tag.group(1).lower() in _BLOCK_HTML_TAGS:
            return True, None
        if not after_paragraph and _HTML_BLOCK_7.match(line, nxt):
            return True, None
        return False, None

    def feed(self, line: str) -> None:
        line = line.expandtabs(4)
        container, pos, all_matched = self.document, 0, True
        while container.children and container.children[-1].open:
            child = container.children[-1]
            result = self._continues(child, line, pos)
            if result is None:
                return
            if result is False:
                all_matched = False
                break
            container, pos = child, result
        last_matched = container
        old_tip_is_paragraph = self.tip.kind == "paragraph"
        all_closed = self.tip is last_matched

        def start(kind: str, **fields) -> _Block:
            nonlocal all_closed
            if not all_closed:
                self._close_unmatched(last_matched)
                all_closed = True
            return self._add(kind, **fields)

        while container.kind not in _TAKES_LINES:
            nxt = _nonspace(line, pos)
            indent, blank = nxt - pos, nxt >= len(line)
            if blank:
                break
            if indent >= 4:
                if not old_tip_is_paragraph:
                    container, pos = start("indented"), pos + 4
                break
            char = line[nxt]
            if char == ">":
                container = start("quote")
                pos = nxt + 1
                pos += 1 if line[pos:pos + 1] == " " else 0
                continue
            if _ATX_HEADING.match(line, nxt):
                start("heading", lines=[line[nxt:].lstrip("#")])
                return
            fence = _FENCE_OPEN.match(line, nxt)
            if fence and not (fence.group(1)[0] == "`" and "`" in line[fence.end():]):
                start("fence", fence=fence.group(1))
                return
            if char == "<":
                lazy = not all_closed and old_tip_is_paragraph
                found, end = self._html_start(line, nxt, container.kind == "paragraph" or lazy)
                if found:
                    container, pos = start("html", html_end=end), nxt
                    break
            if container.kind == "paragraph" and _SETEXT_EQUALS.match(line, nxt):
                container.kind = "heading"
                self._finalize(container)
                return
            if _THEMATIC_BREAK.match(line, nxt):
                start("rule")
                self._finalize(self.tip)
                return
            marker = _BULLET.match(line, nxt) or _ORDERED.match(line, nxt)
            if marker:
                after = marker.end()
                rest_blank = not line[after:].strip()
                interrupts = container.kind == "paragraph"
                if (after == len(line) or line[after] == " ") and not (
                    interrupts and (rest_blank or (marker.re is _ORDERED and marker.group(1) != "1"))
                ):
                    spaces = _nonspace(line, after) - after
                    width = after - nxt
                    padding = width + 1 if rest_blank or spaces >= 5 else width + spaces
                    container = start("item", offset=indent + padding)
                    pos = min(len(line), nxt + padding)
                    continue
            pos = nxt
            break

        blank = _nonspace(line, pos) >= len(line)
        if not all_closed and not blank and self.tip.kind == "paragraph":
            self.tip.lines.append(line[pos:])  # lazy continuation
            return
        if not all_closed:
            self._close_unmatched(last_matched)
        if self.tip.kind in _TAKES_LINES or self.tip.kind == "paragraph":
            self.tip.lines.append(line[pos:])
            if self.tip.kind == "html" and self.tip.html_end is not None \
                    and self.tip.html_end.search(line[pos:]):
                self._finalize(self.tip)
        elif not blank:
            self._add("paragraph", lines=[line[pos:]])


def _inline_html(text: str) -> str:
    """Paragraph text as HTML: raw tags and comments exactly as written, the rest escaped,
    code spans and link destinations dropped."""
    out: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and text[i + 1:i + 2] in _ASCII_PUNCTUATION:
            out.append(html.escape(text[i + 1]))
            i += 2
        elif char == "`":
            run = _BACKTICKS.match(text, i).end() - i
            closing = re.compile(rf"(?<!`)`{{{run}}}(?!`)").search(text, i + run)
            if closing:
                i = closing.end()  # a code span draws its content as text
            else:
                out.append(char * run)
                i += run
        elif char == "<":
            raw = _INLINE_COMMENT.match(text, i) or _INLINE_TAG.match(text, i)
            other = _INLINE_OTHER.match(text, i)
            if other:
                i = other.end()
            elif raw:
                out.append(raw.group(0))
                i = raw.end()
            elif text.startswith("<!--", i):
                break  # an unclosed comment: hide the rest rather than guess
            else:
                out.append("&lt;")
                i += 1
        elif char == "]" and _LINK_TAIL.match(text, i):
            i = _LINK_TAIL.match(text, i).end()
        else:
            out.append(html.escape(char))
            i += 1
    return "".join(out)


def markdown_html(body: str) -> str:
    """The HTML a Markdown `body` draws, as far as tags go: HTML blocks verbatim, raw tags
    in paragraphs and headings as written, all text escaped, code (fenced, indented, inline)
    left out. Containers (block quotes, list items) are parsed, so code inside them is code."""
    blocks = _MarkdownBlocks()
    for line in re.split(r"\r\n|\r|\n", body):
        blocks.feed(line)
    parts: list[str] = []

    def walk(block: _Block) -> None:
        for child in block.children:
            if child.kind in _CONTAINERS:
                walk(child)
            elif child.kind == "html":
                parts.append("\n".join(child.lines))
            elif child.kind in ("paragraph", "heading"):
                text = "\n".join(line.strip() for line in child.lines)
                if child.kind == "paragraph" and _REFERENCE_DEFINITION.match(text):
                    continue  # link reference definitions draw nothing
                parts.append(_inline_html(text))

    walk(blocks.document)
    return "\n".join(parts)


def rendered_markup(body: str) -> str:
    """The part of an element's body that can draw something: no <style> blocks, no comments."""
    return _COMMENT.sub("", _STYLE_BLOCK.sub("", body))


class _StartTagFinder(HTMLParser):
    """Looks for one start tag carrying `name="value"` outside comments and non-rendering
    elements. For `class` the value is a list of class names, so `class="a b"` carries
    `class="a"` too; any other attribute must match exactly."""

    def __init__(self, name: str, value: str):
        super().__init__(convert_charrefs=True)
        self.name, self.value = name.lower(), value
        self.hidden: list[str] = []
        self.found = False

    def _carries(self, attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name != self.name or value is None:
                continue
            if name == "class":
                wanted = set(self.value.split())
                if wanted and wanted <= set(value.split()):
                    return True
            elif value == self.value:
                return True
        return False

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.append(tag)
            return
        if tag in _NON_RENDERING:
            self.hidden.append(tag)
        elif self._carries(attrs):
            self.found = True

    def handle_startendtag(self, tag, attrs):
        if not self.hidden and tag not in _NON_RENDERING and self._carries(attrs):
            self.found = True

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()


def renders_start_tag(body: str, name: str, value: str) -> bool:
    """True when the HTML `body` draws an element carrying `name="value"`."""
    finder = _StartTagFinder(name, value)
    finder.feed(body)
    finder.close()
    return finder.found


def element_shows(kind: str, element, expect_text: str) -> bool:
    """Does this markdown/html/text element show `expect_text`? See the module docstring."""
    body = getattr(element, kind).body
    attribute = _ATTRIBUTE_EXPECTATION.match(expect_text)
    if attribute is None:
        return expect_text in rendered_markup(body)
    if kind == "html":
        return renders_start_tag(body, *attribute.groups())
    if kind == "markdown" and element.markdown.allow_html:
        return renders_start_tag(markdown_html(body), *attribute.groups())
    return False


@dataclass
class RunState:
    """What one script run has shown so far; see `inspect_forward`."""

    expect_text: str = ""
    # (exception type or "<redacted>", first 200 chars of the message)
    exceptions: list[tuple[str, str]] = field(default_factory=list)
    expect_seen: bool = False


def inspect_forward(forward: ForwardMsg, state: RunState) -> None:
    """Record exception elements, and the expected text, from one ForwardMsg.

    With `[client] showErrorDetails = "none"` the exception element still arrives, with
    an empty type and a generic message, so detection keys on the element kind only.
    `is_warning` marks the non-fatal flavour, which is not a failure.
    """
    if forward.WhichOneof("type") != "delta":
        return
    delta = forward.delta
    if delta.WhichOneof("type") != "new_element":
        return
    element = delta.new_element
    kind = element.WhichOneof("type")
    if kind == "exception":
        if not element.exception.is_warning:
            state.exceptions.append(
                (element.exception.type or "<redacted>", element.exception.message[:200])
            )
    elif kind in ("markdown", "html", "text") and state.expect_text and not state.expect_seen:
        if element_shows(kind, element, state.expect_text):
            state.expect_seen = True


def _query_string(query: str) -> str:
    if not query:
        return ""
    return urlencode({"view": "workspace", "q": query})


def _ws_url(base: str) -> str:
    parts = urlparse(base)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunparse((scheme, parts.netloc, STREAM_PATH, "", "", ""))


async def _wait_for_health(base: str, deadline: float) -> None:
    """Block until `/_stcore/health` answers, or raise once past `deadline`."""
    from tornado.httpclient import AsyncHTTPClient

    client = AsyncHTTPClient()
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            await client.fetch(base.rstrip("/") + HEALTH_PATH, request_timeout=5)
            return
        except Exception as exc:  # connection refused while the server boots
            last = exc
            await _sleep(1.0)
    raise TimeoutError(f"{base}{HEALTH_PATH} never answered: {last}")


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _run_once(
    base: str, deadline: float, query: str, verbose: bool, expect_text: str = ""
) -> int:
    await _wait_for_health(base, deadline)
    started = time.monotonic()

    # No `Sec-WebSocket-Protocol` header is sent on purpose: the server reads it
    # only to recover an existing session id and to check an XSRF token that
    # belongs to a signed cookie we do not have, and it catches the KeyError when
    # the header is absent (streamlit/web/server/browser_websocket_handler.py).
    conn = await websocket_connect(
        HTTPRequest(_ws_url(base), request_timeout=None, connect_timeout=30),
        ping_interval=20,
        ping_timeout=20,
    )

    state = RunState(expect_text=expect_text)
    request = BackMsg()
    # `?q=` is the app's shareable-search link: `consume_query_param` fills the
    # box and arms the search, and the same script run performs it. So passing a
    # query here times a real paste, end to end, over the same code a visitor
    # runs — which is how the "< 5 s first paste" gate is measured.
    request.rerun_script.query_string = _query_string(query)
    conn.write_message(request.SerializeToString(), binary=True)

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            conn.close()
            print("warm-up: timed out waiting for the script to finish", file=sys.stderr)
            return 1
        try:
            # Bounded by the deadline: a hung script run must fail a deploy, not hang it.
            message = await asyncio.wait_for(conn.read_message(), timeout=remaining)
        except asyncio.TimeoutError:
            conn.close()
            print("warm-up: timed out waiting for the script to finish", file=sys.stderr)
            return 1
        if message is None:
            print("warm-up: the server closed the connection", file=sys.stderr)
            return 1
        forward = ForwardMsg()
        forward.ParseFromString(message)
        kind = forward.WhichOneof("type")
        if verbose and kind:
            print(f"warm-up: <- {kind}")
        inspect_forward(forward, state)
        if kind != "script_finished":
            continue
        status = forward.script_finished
        name = ForwardMsg.ScriptFinishedStatus.Name(status)
        if expect_text and status == ForwardMsg.FINISHED_EARLY_FOR_RERUN:
            # The app's own `?q=` handling may rerun the script; what the aborted
            # run drew does not count, so wait for the run that completes.
            state = RunState(expect_text=expect_text)
            continue
        conn.close()
        elapsed = time.monotonic() - started
        print(f"warm-up: script finished ({name}) in {elapsed:.1f}s")
        if state.exceptions:
            error_type, error_message = state.exceptions[0]
            print(
                "warm-up: the app raised an exception during the run — "
                f"{error_type}: {error_message} (details in the service journal)",
                file=sys.stderr,
            )
            return 1
        if expect_text and not state.expect_seen:
            print(f'warm-up: the run finished but never rendered "{expect_text}"', file=sys.stderr)
            return 1
        finished_ok = status in (
            ForwardMsg.FINISHED_SUCCESSFULLY,
            ForwardMsg.FINISHED_EARLY_FOR_RERUN,
        )
        return 0 if finished_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8502")
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="seconds to wait for health plus the first script run",
    )
    parser.add_argument(
        "--query",
        default="",
        help=(
            "run this text as a search in the session (via the app's ?q= link), "
            "which times a real paste; omit to warm without searching"
        ),
    )
    parser.add_argument(
        "--expect-text",
        default="",
        help=(
            "fail unless an element shows this text outside <style> blocks and "
            "comments; an attribute such as 'class=\"suggestion-card\"' must be on a "
            "real start tag in an element that renders HTML"
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    try:
        return IOLoop.current().run_sync(
            lambda: _run_once(args.url, deadline, args.query, args.verbose, args.expect_text)
        )
    except Exception as exc:
        # One line, not a traceback: this runs from a systemd ExecStartPost, where
        # the journal is read by someone asking "did the warm-up happen?".
        print(f"warm-up: failed — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
