"""Public mode's résumé reader: the same pypdf extraction, in a child on a leash.

pypdf is pure Python and holds the GIL while it works, and a PDF is a
compression format as much as a document. In the P4-S1A audit a 56 KiB file
took 42 s and 914 MiB to read, and one of 400 pages sharing a single stream
was still going after ten minutes — on a Render instance that has 512 MiB
and a tenth of a CPU for everybody. Parsed in the web process, one upload
takes the whole service down, and the restart that follows forgets every
visitor's session and every daily counter with it.

So the public app never parses in its own process. A child does, and:

  * lowers its own address-space ceiling BEFORE pypdf is imported
    (MEMORY_BYTES), so an allocation past it is a MemoryError in the child
    rather than an OOM kill of the parent;
  * refuses a document of more than MAX_PAGES pages before extracting any;
  * runs resume_parser.extract_text — the one extraction the product has, so
    an ordinary résumé reads exactly as it always did;
  * hands back at most MAX_TEXT_BYTES of text and nothing else: no path, no
    pypdf message, no traceback.

The parent runs one child at a time (a short wait for the slot, then
"busy"), kills it at TIMEOUT_SECONDS, and turns every way it can go wrong
into Unreadable, whose message is fixed text safe to put on the screen.
"""

import contextlib
import os
import subprocess
import sys
import threading

MAX_PAGES = 10
MAX_TEXT_BYTES = 100 * 1024
TIMEOUT_SECONDS = 15
# RLIMIT_AS counts address space, not resident memory, so it includes the
# interpreter and its libraries (~40-60 MiB on Linux). Render's instance is
# 512 MiB and the web process already holds ~150-200 MiB (the frozen market
# corpus and title table are in it). 288 MiB leaves a normal résumé — which
# peaks well under 100 MiB — room to spare, and cannot come near the 914 MiB
# the audit's PDF reached: the child hits its own ceiling long before the
# instance does.
MEMORY_BYTES = 288 * 1024 * 1024
# A second guard for the one case the wall clock cannot see: a parent that is
# itself gone. The kernel stops a child that has burned this much CPU.
CPU_SECONDS = 20
# How long a second upload waits for the one slot before being told the
# reader is busy. Short, so waiting can never become a queue of threads.
SLOT_WAIT_SECONDS = 3

_SLOT = threading.BoundedSemaphore(1)
_state = {"in_flight": 0}
_state_lock = threading.Lock()

_OK, _ERR = b"OK", b"ERR"
_UNREADABLE = ("Sweep could not read that PDF. Export your résumé again as a "
               "standard PDF and try again.")
MESSAGES = {
    "pages": (f"That PDF has more than {MAX_PAGES} pages. Upload just your "
              f"résumé — it is usually one or two pages."),
    "too_long": ("That PDF holds far more text than a résumé does. Upload "
                 "just your résumé and try again."),
    "encrypted": ("That PDF is password-protected. Export a copy without a "
                  "password and try again."),
    "busy": ("Sweep is reading another résumé right now. Try again in a "
             "moment."),
}


class Unreadable(Exception):
    """A PDF the public reader will not hand back text for.

    `category` is for the log (pages, too_long, encrypted, malformed,
    timeout, resource, busy, failed); `message` is for the screen, and is
    always one of the fixed sentences above; `status` is the HTTP answer —
    400 for the file, 503 for a reader that is busy with someone else's.
    """

    def __init__(self, category):
        self.category = category
        self.message = MESSAGES.get(category, _UNREADABLE)
        self.status = 503 if category == "busy" else 400
        super().__init__(category)


def in_flight():
    """Children running right now: 0 or 1. For /healthz."""
    return _state["in_flight"]


def _child_argv(path):
    # -I: isolated — no PYTHON* environment, no user site, no script
    # directory on sys.path. The child finds resume_parser itself.
    return [sys.executable, "-I", os.path.abspath(__file__), path]


def extract(path, timeout=None, memory=None, max_pages=None, max_text=None,
            slot_wait=None):
    """The résumé text of the PDF at `path`, or Unreadable.

    The same signature as resume_parser.extract_text for the caller; each
    keyword defaults to the module's limit, read at call time. `path` is the
    caller's own random temp file, which the caller deletes.
    """
    if not _SLOT.acquire(timeout=SLOT_WAIT_SECONDS if slot_wait is None else slot_wait):
        raise Unreadable("busy")
    try:
        with _state_lock:
            _state["in_flight"] += 1
        return _run_child(path, TIMEOUT_SECONDS if timeout is None else timeout,
                          MEMORY_BYTES if memory is None else memory,
                          MAX_PAGES if max_pages is None else max_pages,
                          MAX_TEXT_BYTES if max_text is None else max_text)
    finally:
        with _state_lock:
            _state["in_flight"] -= 1
        _SLOT.release()


def _run_child(path, timeout, memory, max_pages, max_text):
    # No secret reaches the child: it gets an environment of its own, not a
    # copy of this one (SECRET_KEY, the worker and inference tokens).
    env = {"PATH": os.defpath, "SWEEP_PDF_MEMORY": str(memory),
           "SWEEP_PDF_CPU": str(CPU_SECONDS),
           "SWEEP_PDF_MAX_PAGES": str(max_pages),
           "SWEEP_PDF_MAX_TEXT": str(max_text)}
    try:
        child = subprocess.Popen(_child_argv(path), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, env=env)
    except OSError:
        raise Unreadable("failed") from None
    try:
        out, _ = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        with contextlib.suppress(Exception):
            child.communicate(timeout=5)
        raise Unreadable("timeout") from None
    except BaseException:
        child.kill()
        with contextlib.suppress(Exception):
            child.communicate(timeout=5)
        raise
    if child.returncode != 0:
        # Killed by the kernel (the CPU limit, an OOM) or died before it
        # could say why. Either way the ceiling did its job.
        raise Unreadable("resource")
    status, _, body = out.partition(b"\n")
    if status == _OK:
        if len(body) > max_text:
            raise Unreadable("too_long")
        return body.decode("utf-8", "surrogatepass")
    category = body.decode("ascii", "replace").strip() if status == _ERR else ""
    raise Unreadable(category if category in (
        "pages", "too_long", "encrypted", "malformed", "resource") else "failed")


# ---------------------------------------------------------------- the child
def _apply_limits(memory, cpu, resource_module=None, platform=None):
    """The ceilings, set on this process before anything is parsed.

    On Linux — what Render and Oracle run — a limit that cannot be set is a
    refusal to parse: an unbounded reader is the thing this module exists to
    prevent. Elsewhere (a developer's Mac, where RLIMIT_AS is not supported)
    the parent's wall clock is the guard and the child goes on.
    """
    if resource_module is None:
        import resource as resource_module
    platform = sys.platform if platform is None else platform
    try:
        resource_module.setrlimit(resource_module.RLIMIT_AS, (memory, memory))
        resource_module.setrlimit(resource_module.RLIMIT_CPU, (cpu, cpu))
    except (ValueError, OSError):
        if platform.startswith("linux"):
            raise


def _child(path, env):
    out = sys.stdout.buffer
    try:
        _apply_limits(int(env["SWEEP_PDF_MEMORY"]), int(env["SWEEP_PDF_CPU"]))
    except (ValueError, OSError, KeyError):
        out.write(_ERR + b"\nresource")
        return 0
    try:
        auto_apply = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "auto-apply")
        sys.path.insert(0, auto_apply)
        from pypdf import PdfReader
        from pypdf.errors import DependencyError, FileNotDecryptedError

        import resume_parser
        try:
            # Counted before a single page is extracted. pypdf tries the
            # empty password on its own, so a permissions-only PDF reads
            # exactly as it does today; one that needs a real password
            # refuses here.
            pages = len(PdfReader(path).pages)
            if pages > int(env["SWEEP_PDF_MAX_PAGES"]):
                out.write(_ERR + b"\npages")
                return 0
            text = resume_parser.extract_text(path)
        except (FileNotDecryptedError, DependencyError):
            out.write(_ERR + b"\nencrypted")
            return 0
        body = text.encode("utf-8", "surrogatepass")
        if len(body) > int(env["SWEEP_PDF_MAX_TEXT"]):
            out.write(_ERR + b"\ntoo_long")
            return 0
        out.write(_OK + b"\n" + body)
    except MemoryError:
        out.write(_ERR + b"\nresource")
    except Exception:
        # A malformed, truncated or hostile file. Which exception pypdf chose
        # is not the visitor's business and never leaves this process.
        out.write(_ERR + b"\nmalformed")
    return 0


if __name__ == "__main__":
    sys.exit(_child(sys.argv[1], os.environ))
