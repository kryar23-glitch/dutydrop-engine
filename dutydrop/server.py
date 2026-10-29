"""HTTP endpoints (Spec 5). Standard library only; swap for FastAPI without touching the engine.

  POST /identify   {images[], user_text?}                                  -> ProductDescription
  POST /classify   {description?, answers?, audit_id?, images?, user_text?} -> decision or questions
  POST /estimate   {code, origin, value, entry_date?, mode?, quantity?, quantity_unit?}
  POST /receipt    {images? | description_text?, origin?, value?, tier?, answers?, audit_id?}
  GET  /hts/{code}

Images are base64 strings or data URLs. Run: python3 -m dutydrop.server --port 8080
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .adapters.base import ModelOutputError, ProviderNotConfigured
from .engine import Engine, InputError

ENGINE = None


def _engine() -> Engine:
    global ENGINE
    if ENGINE is None:
        ENGINE = Engine()
    return ENGINE


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code: int, msg: str):
        self._send(code, {"error": msg, "disclaimer": config.DISCLAIMER, "link": config.PUBLIC_LINK})

    def do_GET(self):
        if self.path.startswith("/hts/"):
            try:
                return self._send(200, _engine().hts(self.path.split("/hts/", 1)[1]))
            except InputError as e:
                return self._err(404, str(e))
        if self.path == "/health":
            e = _engine()
            return self._send(200, {"ok": True, "data_version": e.data.label, "counts": e.data.counts})
        self._err(404, "not found")

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._err(400, "body must be JSON")
        e = _engine()
        try:
            if self.path == "/identify":
                desc, _, hashes, ledger = e.identify(req.get("images"), req.get("user_text"))
                return self._send(200, {"description": desc, "photo_refs": hashes, "cost": ledger.to_dict()})
            if self.path == "/classify":
                return self._send(200, e.classify(req.get("description"), req.get("answers"), req.get("audit_id"),
                                                  req.get("images"), req.get("user_text")))
            if self.path == "/estimate":
                return self._send(200, e.estimate(req["code"], req["origin"], req["value"], req.get("entry_date"),
                                                  req.get("mode", "current"), req.get("quantity"),
                                                  req.get("quantity_unit")))
            if self.path == "/receipt":
                return self._send(200, e.receipt(req.get("images"), req.get("description_text"), req.get("origin"),
                                                 req.get("value"), req.get("tier", "anonymous"), req.get("entry_date"),
                                                 req.get("quantity"), req.get("quantity_unit"), req.get("answers"),
                                                 req.get("audit_id"), req.get("description")))
            return self._err(404, "not found")
        except ProviderNotConfigured as ex:
            return self._err(503, str(ex))           # fail loudly, never guess
        except (InputError, ValueError, KeyError) as ex:
            return self._err(400, str(ex))
        except ModelOutputError as ex:
            return self._err(502, str(ex))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    _engine()
    print(f"DutyDrop engine on http://{a.host}:{a.port}  data {ENGINE.data.label}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
