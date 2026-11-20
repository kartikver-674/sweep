# D7A motion prototype (Results)

An isolated prototype of Sweep's proposed motion, on the real Results page. **It is not part of the application**:
nothing under `sweep/` was changed, nothing here is served by a production route, and no dependency was added to
the app. The note that explains it is [../../SWEEP_D7_MOTION_DIRECTION.md](../../SWEEP_D7_MOTION_DIRECTION.md).

## Run it

```bash
python3 docs/design/prototype/motion/serve.py --variant proposed      # http://127.0.0.1:8770/results
python3 docs/design/prototype/motion/serve.py --variant baseline --port 8771   # the page as it ships today
python3 docs/design/prototype/motion/serve.py --variant proposed-vt --port 8773 # the view-transition alternative
python3 docs/design/prototype/motion/serve.py --variant gsap --port 8772       # the GSAP spike (fetches gsap@3.15.0 on first use)
python3 docs/design/prototype/motion/serve.py --variant proposed --latency 700 # a slow worker
```

The first run builds the fixtures (about two seconds, needs the repository's `.venv`). Open the page from
another page of the same origin to see the arrival (a fresh tab opened by typing the address has no referrer and
also counts as an arrival). Press a résumé tab, Filter and sort, Export, Apply filters. A quick tab change is an instant swap by
design; run the server with `--latency 700` to see the dim and un-dim. Turn on "reduce motion" in the operating system to see
the alternative.

## What is in here

| File | What it is |
|---|---|
| `build_fixtures.py` | Renders the **real** `results.html` through the worker-backed test harness with invented rows, then derives the variants. Fixtures are generated, not committed |
| `serve.py` | Standard-library server. Keeps production's URL shape (`/results?track=<id>`) so a tab is a same-path navigation |
| `motion-proposed.css` | The proposed layer, loaded after `sweep.css` |
| `motion-vt-alt.css` | The cross-document view transition, kept as a measured alternative (`--variant proposed-vt`). It loses: a press during the transition is dropped |
| `motion-gsap-spike.css`, `motion-gsap-spike.js` | The same arrival written in GSAP 3.15.0, for the dependency evaluation only. GSAP itself is **not committed**: `vendor/` is git-ignored, and `serve.py --variant gsap` and the harness fetch exactly `gsap@3.15.0` from npm into it |
| `harness/` | How the evidence was made: `record.mjs` (real-time recordings), `verify.mjs` (the brief's safeguards as assertions), `verify-gsap.mjs` (GSAP against CSS, with fault injection), `filmstrip.mjs` and `make-sheets.mjs` (frames cut from a recording), `lib.mjs` |

The two edits that are not CSS are a 15-line head script (sets `html.arrive`, or `html.swap` after a slow answer, and removes it 500 ms after the first frame) and a
22-line script that marks the list "pending" if an answer takes more than 160 ms (armed on a link to the same page or on a valid GET
submit, and given up after 10 s). Both are in `build_fixtures.py`
as `HEAD_SCRIPT` and `BODY_SCRIPT`, next to the string edits that stand in for template changes.

Fonts: the page asks Google for its two typefaces, and the harness loads them once into the browser's HTTP cache before each
take; offline, the system fonts are used and nothing else changes.

The recordings (`harness/record.mjs`) are real time, 25 fps, one continuous take each. A cursor and a press ring are
drawn into them (the recorder has no pointer), and each clip starts and ends with a 160 ms white flash at a known time,
which is how the trace's clock is aligned with the video's and any drift measured. None of that is part of the
prototype, and `verify.mjs` runs without it.

The filters do not filter in the prototype (the page is a fixture): Apply filters reloads the same rows, which is
what is needed to see what a same-screen navigation does.
