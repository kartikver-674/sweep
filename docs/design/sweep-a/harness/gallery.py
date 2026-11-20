"""A2 evidence: one page of every shared Direction A component, rendered through the real Flask app in public mode.

    .venv/bin/python docs/design/sweep-a/harness/gallery.py      # prints the written path

The page extends base.html (so the real header, tracker and skin apply). The static hrefs are rewritten to file:// paths
of this repository so the file opens from disk. Not shipped; gallery-shots.mjs photographs it.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from sweep.tests.test_public import public_app  # noqa: E402

BODY = """{% extends "base.html" %}
{% from "_a.html" import peek, tip, stamp, mbar %}
{% block title %}Gallery{% endblock %}
{% block body %}
<div class="stack">
  <h1>Sort your <span class="scrib">résumé</span> into a search</h1>
  <p class="lede">Upload once. Sweep reads it, finds the job boards worth searching, and shows you what matched and why.</p>

  <div class="actions">
    <button type="button" class="primary">Start the sweep</button>
    <button type="button" class="secondary">Back</button>
    <button type="button" class="tertiary">Skip this</button>
    <a class="primary big" href="#">Big primary</a>
    <button type="button" class="primary" disabled>Disabled</button>
    <button type="button" class="secondary" disabled>Disabled</button>
  </div>
  <p>A body paragraph with an <a href="#">ordinary link</a> inside it, and <a class="tertiary" href="#">a tertiary link</a>.</p>

  <p><span class="chip">Chip</span> <span class="chip free">Free</span> <span class="chip quiet">Quiet</span>
     <span class="tag">react native</span> <span class="tag low">low</span> <span class="tag more">+3</span></p>

  <div class="panel"><h2>A panel</h2><p>Sticker border, hard offset shadow, 22px corners.</p>
    <div class="inset">An inset inside it keeps a hairline.</div></div>
  <details class="panel"><summary><h2>A closed disclosure</h2></summary><p>Dashed until it opens.</p></details>
  <details class="panel" open><summary><h2>An open disclosure</h2></summary><p>Solid sticker once open.</p></details>

  <div class="panel">
    <label>Profile name <input type="text" value="Ada Okonkwo"></label>
    <label>Seniority <select><option>Mid</option><option>Senior</option></select></label>
    <label>Notes <textarea rows="2">Remote only.</textarea></label>
    <label class="choice"><input type="radio" name="pick" checked><span><b>Quick Sweep</b><span class="why">Free boards only.</span></span></label>
    <label class="choice"><input type="radio" name="pick"><span><b>Deep Sweep</b><span class="why">Adds paid boards.</span></span></label>
  </div>

  {% call peek("Closed peek", "optional") %}<p>Hidden until you ask.</p>{% endcall %}
  <details class="peek" open><summary><span class="peek-label">Open peek</span><span class="peek-aside">aside</span></summary><div class="peek-body"><p>The marker turns from + to a minus; no triangle.</p></div></details>

  {{ tip("gallery", "Drop in a PDF and I will do the rest.") }}

  <p>{{ stamp("Done") }} <span class="sticker">Sticker</span> <span class="sticker cit">Citrus</span> <span class="sticker lav">Lavender</span></p>

  {% call mbar() %}<span class="mbar-text"><b>3 picked</b>of 12 boards</span><a class="primary" href="#">Continue</a>{% endcall %}
</div>
{% endblock %}
"""


LABELS = [("upload", "Upload"), ("review", "Review"), ("key", "Search"), ("configure", "Configure"),
          ("confirm", "Confirm"), ("running", "Progress"), ("results", "Results")]
# done / current / next / locked, so the tracker shows every marker state.
STEPS = [{"n": i + 1, "slug": slug, "label": label, "open": i <= 3, "current": i == 2, "done": i < 2, "next": i == 3}
         for i, (slug, label) in enumerate(LABELS)]


def main():
    app = public_app()
    from flask import render_template_string
    with app.test_request_context("/"):
        html = render_template_string(BODY, steps=STEPS, step="key", credit_left=4.2, active_run=None,
                                      public_mode=True)
    static = (ROOT / "sweep" / "static").as_uri()
    html = html.replace('"/static/', f'"{static}/')
    out = ROOT / "output" / "design-A2" / "gallery" / "gallery.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(out)


if __name__ == "__main__":
    main()
