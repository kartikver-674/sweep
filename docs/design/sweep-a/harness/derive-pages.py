"""A4 evidence: the public single-résumé reading screen (/derive -> deriving.html), working and failed, rendered
through the real Flask app in public mode, with static hrefs rewritten to file:// (as gallery.py does). The harness's
own visitors run the multi-résumé setup, which reads on Review instead, so this screen is not in the regression set.

    .venv/bin/python docs/design/sweep-a/harness/derive-pages.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs" / "design" / "sweep-a" / "harness"))

from gallery import STEPS  # noqa: E402
from sweep.tests.test_public import public_app  # noqa: E402

def main():
    from flask import render_template
    app = public_app()
    steps = [dict(s, current=s["slug"] == "review", done=s["slug"] == "upload", next=s["slug"] == "key") for s in STEPS[:4]]
    out = ROOT / "output" / "design-A4" / "derive"; out.mkdir(parents=True, exist_ok=True)
    static = (ROOT / "sweep" / "static").as_uri()
    for name, kw in (("working", {}), ("waiting", {"waiting": True}),
                     ("failed", {"error": "Sweep could not read that résumé. Nothing was charged. Try uploading it "
                                          "again — a text-based PDF rather than a scan works best."})):
        with app.test_request_context("/review"):
            html = render_template("deriving.html", steps=steps, step="review", credit_left=None, active_run=None,
                                   public_mode=True, track_id="a" * 16, **kw)
        # The working page auto-submits its form after two frames; a photograph needs it still.
        html = html.replace("form.requestSubmit(); } else { form.submit(); }", "} else { }")
        (out / f"derive-{name}.html").write_text(html.replace('"/static/', f'"{static}/'))
    print(out)

if __name__ == "__main__":
    main()
