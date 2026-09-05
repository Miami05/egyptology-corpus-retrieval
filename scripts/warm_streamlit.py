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

Usage (exits 0 on success, non-zero on failure; never blocks a service start
for longer than --timeout):

    python scripts/warm_streamlit.py --url http://127.0.0.1:8502 --timeout 300
"""

from __future__ import annotations

import argparse
import sys
import time
from urllib.parse import urlencode, urlparse, urlunparse

from tornado.httpclient import HTTPRequest
from tornado.ioloop import IOLoop
from tornado.websocket import websocket_connect

from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

HEALTH_PATH = "/_stcore/health"
STREAM_PATH = "/_stcore/stream"


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
    import asyncio

    await asyncio.sleep(seconds)


async def _run_once(base: str, deadline: float, query: str, verbose: bool) -> int:
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
        message = await conn.read_message()
        if message is None:
            print("warm-up: the server closed the connection", file=sys.stderr)
            return 1
        forward = ForwardMsg()
        forward.ParseFromString(message)
        kind = forward.WhichOneof("type")
        if verbose and kind:
            print(f"warm-up: <- {kind}")
        if kind != "script_finished":
            continue
        status = forward.script_finished
        conn.close()
        elapsed = time.monotonic() - started
        finished_ok = status in (
            ForwardMsg.FINISHED_SUCCESSFULLY,
            ForwardMsg.FINISHED_EARLY_FOR_RERUN,
        )
        name = ForwardMsg.ScriptFinishedStatus.Name(status)
        print(f"warm-up: script finished ({name}) in {elapsed:.1f}s")
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
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    try:
        return IOLoop.current().run_sync(
            lambda: _run_once(args.url, deadline, args.query, args.verbose)
        )
    except Exception as exc:
        # One line, not a traceback: this runs from a systemd ExecStartPost, where
        # the journal is read by someone asking "did the warm-up happen?".
        print(f"warm-up: failed — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
