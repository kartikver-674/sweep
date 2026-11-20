"""D7A prototype server. Standard library only; serves one variant of the rendered Results page.

    python3 docs/design/prototype/motion/serve.py --variant proposed        # http://127.0.0.1:8770/results
    python3 docs/design/prototype/motion/serve.py --variant baseline --port 8771
    python3 docs/design/prototype/motion/serve.py --variant gsap --port 8772

It exists so the prototype behaves like the application, not like a folder of files:

  /results                          All Jobs              (the real page's URL, so a move between views is a
  /results?track=<16 hex chars>     one résumé's view      same-path navigation, which is what the motion keys on)
  /results?set=long[&track=...]     the same with 240 jobs and "Show all" on
  /static/...                       sweep/static, unmodified (the application's own stylesheet and Alpine)
  /motion/...  /vendor/...          this directory's layers, and the vendored GSAP used only by the spike
  anything else                     204: the prototype is not the application

--latency MS holds every /results answer for that long, to see how the page behaves when the worker is slow.
Nothing here writes a file, calls a model, or leaves loopback.
"""
import argparse
import mimetypes
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TRACKS = {"a" * 16: "a", "b" * 16: "b", "c" * 16: "c"}


def ensure_gsap():
    """vendor/ is git-ignored: fetch exactly GSAP 3.15.0's core file from npm when the spike needs it."""
    dest = HERE / "vendor" / "gsap.min.js"
    if dest.is_file():
        return
    print("fetching gsap@3.15.0 from npm (not committed: see README) …", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["npm", "pack", "gsap@3.15.0", "--silent"], cwd=tmp, check=True, stdout=subprocess.DEVNULL)
        tgz = next(pathlib.Path(tmp).glob("*.tgz"))
        with tarfile.open(tgz) as t:
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(t.extractfile("package/dist/gsap.min.js").read())


def make(variant, latency):
    pages = HERE / "fixtures" / variant

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, body=b"", ctype="text/plain; charset=utf-8", extra=(), cache="no-store"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _file(self, base, rel):
            p = (base / rel).resolve()
            if base.resolve() not in p.parents or not p.is_file():
                return self._send(404, b"not found")
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            # Cached like the application's static files, so a move between pages costs what it costs in
            # production (no stylesheet round trip). Edit a layer and reload with the cache disabled.
            self._send(200, p.read_bytes(), ctype, cache="public, max-age=300")

        do_HEAD = do_GET = lambda self: self._route()

        def _route(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/results":
                time.sleep(latency / 1000)
                key = TRACKS.get((q.get("track") or [""])[0], "all")
                name = f"{'long' if q.get('set') == ['long'] else 'results'}-{key}.html"
                f = pages / name
                if not f.is_file():
                    f = pages / f"results-{key}.html"
                return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
            if u.path.startswith("/static/"):
                return self._file(ROOT / "sweep" / "static", u.path[len("/static/"):])
            if u.path.startswith("/motion/"):
                return self._file(HERE, u.path[len("/motion/"):])
            if u.path.startswith("/vendor/"):
                return self._file(HERE / "vendor", u.path[len("/vendor/"):])
            if u.path == "/favicon.ico":
                return self._send(204)
            self._send(204)

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=("baseline", "proposed", "proposed-vt", "gsap"), default="proposed")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--latency", type=int, default=0, help="milliseconds to hold each /results answer")
    a = ap.parse_args()
    if not (HERE / "fixtures" / a.variant / "results-all.html").is_file():
        py = ROOT / ".venv" / "bin" / "python"
        print("building fixtures (real Results template, synthetic rows) …", file=sys.stderr)
        subprocess.run([str(py if py.exists() else sys.executable), str(HERE / "build_fixtures.py")],
                       check=True, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if a.variant == "gsap":
        ensure_gsap()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make(a.variant, a.latency))
    print(f"{a.variant}: http://127.0.0.1:{a.port}/results   (Ctrl-C to stop)", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
