"""DQ2b baseline: today's derivation over the targeted families, measured.

Replays every bench/targeted.py document from its committed capture through
the production derivation (no model, no network), projects each one with
DQ2a's track_intent, and measures what DQ1 §M3 asks DQ2c to improve — so DQ2c
can re-run exactly this and compare. Ground truth comes from
bench/targeted_manifest.py and is used here, for scoring the measurement,
and nowhere else.

    env -i PATH=/usr/bin:/bin HOME=$HOME PYTHONDONTWRITEBYTECODE=1 \\
        SWEEP_PROFILE_ENGINE_VERSION=v2 .venv/bin/python -m bench.targeted_eval \\
        --out <file.json>

Plans are built in fresh interpreters over a temporary schema-2 profile
(render_sweep), sockets refused: multi_plans, plan_hash and max_charge_usd —
what --dry-run --json prices — without the engine's main(), so this file
never reaches its run path (sweep/tests/test_paid_dev_guard). No provider
is called and nothing is spent.
"""
import collections
import contextlib
import itertools
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "auto-apply"))

from bench import render, targeted
from bench import targeted_manifest as M

REPO = targeted.REPO


@contextlib.contextmanager
def no_network():
    real = socket.socket.connect

    def refuse(*_a, **_k):
        raise RuntimeError("the DQ2b replay must not open a connection")

    socket.socket.connect = refuse
    try:
        yield
    finally:
        socket.socket.connect = real


def jaccard(a, b):
    a, b = set(a), set(b)
    return round(len(a & b) / len(a | b), 3) if a | b else None


def weighted_jaccard(a, b):
    keys = set(a) | set(b)
    den = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return round(sum(min(a.get(k, 0), b.get(k, 0)) for k in keys) / den, 3) if den else None


def med(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def track_id(variant_id):
    import hashlib
    return hashlib.sha256(variant_id.encode()).hexdigest()[:16]


# ===========================================================================
# Replay and projection
# ===========================================================================

def replay(captures):
    """{doc: {"text", "derived", "gate"}} for every captured document."""
    import skill_concepts
    assert skill_concepts.engine_version() == "v2", skill_concepts.engine_version()
    out = {}
    with tempfile.TemporaryDirectory() as empty, no_network():
        for doc, _vid, _layout in targeted.documents():
            text, derived, gate = targeted.derive(doc, captures, empty)
            out[doc] = {"text": text, "derived": derived, "gate": gate}
    return out


def market():
    import local_search
    m = local_search.frozen_market()
    return m, collections.Counter(t for t, _s, _sk, _c in m.rows)


def intents_for(docs, titles, seniority):
    import track_intent
    return {doc: track_intent.derive_track_intent(d["text"], d["derived"], titles,
                                                  seniority)
            for doc, d in docs.items()}


def weights(derived):
    return {e["term"].strip().lower(): e["weight"] for e in derived["skill_weights"]}


# ===========================================================================
# G. Sibling factual consistency
# ===========================================================================

def facts_of(entry, derived):
    import local_extract
    rows = entry["employment"].get("employment") or []
    parsed = entry["fields"]["parsed"] or {}
    return {
        "target_field": entry["employment"].get("target_field"),
        "employment": [(r.get("company"), r.get("title"),
                        local_extract.parse_month(r.get("start"), targeted.NOW),
                        local_extract.parse_month(r.get("end"), targeted.NOW),
                        r.get("relevant")) for r in rows],
        "months": derived.get("experience_months"),
        "years": derived.get("years_experience"),
        "companies": sorted(str(c).lower() for c in parsed.get("companies") or []),
        "titles": sorted(str(t).lower() for t in parsed.get("titles") or []),
        "education": sorted(str(e).lower() for e in parsed.get("education") or []),
        "institutions": sorted(str(e).lower() for e in parsed.get("institutions") or []),
        "skills": sorted({str(s).strip().lower() for s in parsed.get("skills") or []}),
    }


def truth_months(variant_id):
    import local_extract
    fam = targeted.FAMILIES[targeted.split(variant_id)[0]]
    rows = [{"title": j["title"], "start": render.fmt_date(j["start"]),
             "end": render.fmt_date(j["end"]), "relevant": True} for j in fam["jobs"]]
    return local_extract.months_from(rows, targeted.NOW)


def consistency(captures, docs):
    out = {}
    for family in M.FAMILIES:
        members = [vid for vid in M.VARIANTS if M.VARIANTS[vid]["family"] == family]
        per = {}
        for vid in members:
            for layout in targeted.LAYOUTS:
                doc = f"{vid}-{layout}"
                per[doc] = facts_of(captures["docs"][doc], docs[doc]["derived"])
        truth = targeted.facts(members[0])
        want_rows = [(j["company"], j["title"]) for j in
                     targeted.FAMILIES[family]["jobs"]]
        fam = {"truth_months": truth_months(members[0]), "docs": {}}
        base_skills = {s.lower() for s in truth["skills"]}
        for doc, f in per.items():
            got_rows = [(c, t) for c, t, *_ in f["employment"]]
            fam["docs"][doc] = {
                "months": f["months"], "years": f["years"],
                "rows_match_truth": got_rows == want_rows,
                "dates": [(s, e) for _c, _t, s, e, _r in f["employment"]],
                "relevant": [r for *_x, r in f["employment"]],
                "target_field": f["target_field"],
                "companies": f["companies"], "education": f["education"],
                "institutions": f["institutions"],
                "skills_n": len(f["skills"]),
                "skills_vs_base": jaccard(f["skills"], base_skills),
                "skills_missing_from_base": sorted(base_skills - set(f["skills"])),
                "skills_extra": sorted(set(f["skills"]) - base_skills),
            }
        docs_f = list(per.values())
        fam["months_distinct"] = sorted({f["months"] for f in docs_f})
        fam["dates_distinct"] = len({tuple((s, e) for _c, _t, s, e, _r in f["employment"])
                                     for f in docs_f})
        fam["companies_distinct"] = len({tuple(f["companies"]) for f in docs_f})
        fam["education_distinct"] = len({tuple(f["education"] + f["institutions"])
                                         for f in docs_f})
        fam["relevance_distinct"] = sorted({tuple(r for *_x, r in f["employment"])
                                            for f in docs_f})
        pairs = [jaccard(a["skills"], b["skills"])
                 for a, b in itertools.combinations(docs_f, 2)]
        fam["skills_pairwise_median"], fam["skills_pairwise_min"] = med(pairs), min(pairs)
        out[family] = fam
    return out


# ===========================================================================
# H-J. Convergence of today's derivation
# ===========================================================================

def admitted(hints, excludes, corpus_titles):
    hints = [h.strip().lower() for h in hints if h.strip()]
    excludes = [e.strip().lower() for e in excludes if e.strip()]
    return {t for t in corpus_titles if any(h in t for h in hints)
            and not any(e in t for e in excludes)}


def convergence(docs, corpus_titles, floor, market_obj):
    out = {}
    floor_set = admitted(floor, (), corpus_titles)
    for family, sibs in M.SIBLINGS.items():
        for layout in targeted.LAYOUTS:
            ds = {v: docs[f"{v}-{layout}"]["derived"] for v in sibs}
            gates = {v: docs[f"{v}-{layout}"]["gate"] for v in sibs}
            rk = {v: [k.lower() for k in ds[v]["role_keywords"]] for v in sibs}
            hints = {v: [h.lower() for h in ds[v]["title_hints"]] for v in sibs}
            adm = {v: admitted(gates[v], ds[v]["title_exclude"], corpus_titles)
                   for v in sibs}
            own_adm = {v: admitted(hints[v], (), corpus_titles) for v in sibs}
            w = {v: weights(ds[v]) for v in sibs}
            all3 = set.intersection(*(set(rk[v]) for v in sibs))
            prov = {v: {k.lower(): tier for k, tier, _why in ds[v]["local_ranking"]}
                    for v in sibs}
            rows = market_obj.rows
            bought = {v: {i for i, r in enumerate(rows) if any(k in r[0] for k in rk[v])}
                      for v in sibs}
            w5 = {v: sorted(t for t, x in w[v].items() if x == 5) for v in sibs}
            out[f"{family}-{layout}"] = {
                "role_keywords": rk,
                "rk_provenance": prov,
                "rk_pairs": {f"{a}|{b}": jaccard(rk[a], rk[b])
                             for a, b in itertools.combinations(sibs, 2)},
                "rk_shared_by_all": sorted(all3),
                "rk_exclusive": {v: sorted(set(rk[v]) - set().union(
                    *(set(rk[o]) for o in sibs if o != v))) for v in sibs},
                "rk_first_two": {v: rk[v][:2] for v in sibs},
                "hints_n": {v: len(hints[v]) for v in sibs},
                "gate_n": {v: len(gates[v]) for v in sibs},
                "hint_pairs": {f"{a}|{b}": jaccard(hints[a], hints[b])
                               for a, b in itertools.combinations(sibs, 2)},
                "own_hint_admission": {v: len(own_adm[v]) for v in sibs},
                "gate_admission": {v: len(adm[v]) for v in sibs},
                "gate_beyond_floor": {v: len(adm[v] - floor_set) for v in sibs},
                "gate_admission_pairs": {f"{a}|{b}": jaccard(adm[a], adm[b])
                                         for a, b in itertools.combinations(sibs, 2)},
                "weight_pairs": {f"{a}|{b}": weighted_jaccard(w[a], w[b])
                                 for a, b in itertools.combinations(sibs, 2)},
                "weight_terms_pairs": {f"{a}|{b}": jaccard(w[a], w[b])
                                       for a, b in itertools.combinations(sibs, 2)},
                "weight5": w5,
                "weight5_shared_by_all": sorted(set.intersection(*(set(w5[v]) for v in sibs))),
                "weight_mass": {v: sum(w[v].values()) for v in sibs},
                "weight_terms_n": {v: len(w[v]) for v in sibs},
                "coverage": {v: len(bought[v]) for v in sibs},
                "coverage_union": len(set().union(*bought.values())),
                "months": {v: ds[v]["experience_months"] for v in sibs},
                "target_field": {v: ds[v]["role_signals"]["target_field"] for v in sibs},
            }
    return out


# ===========================================================================
# K-L. TrackIntent and target alignment
# ===========================================================================

def aligned_title(title, terms):
    return any(M.has_phrase(title, t) for t in terms)


def intent_record(intent, vid, corpus_titles_list, market_obj, hard):
    import local_search
    spec = M.VARIANTS[vid]
    vocab = {M.norm(v) for v in spec["vocabulary"]}
    ids = sorted(intent.ids)
    parts = [(t.title, t.source, p) for t in intent.declared_titles for p in t.parts]
    share = {p: round(local_search.profile_of(p, corpus_titles_list, hard)["share"], 4)
             for _t, _s, p in parts}
    wildcard = {p for p, s in share.items() if s > local_search.WILDCARD_SHARE}
    in_vocab = sorted(c for c in ids if M.norm(c) in vocab)
    header_concepts = sorted(c.id for c in intent.concepts if "header" in c.sources)
    others = [o for o in M.SIBLINGS.get(spec["family"], []) if o != vid]
    return {
        "sufficient": intent.sufficient, "reason": intent.reason,
        "declared": [{"title": t.title, "source": t.source, "parts": list(t.parts),
                      "canonical": [list(c) for c in t.canonical]}
                     for t in intent.declared_titles],
        "declared_part_share": share,
        "declared_wildcard": sorted(wildcard),
        "concepts": [{"id": c.id, "registered": c.registered, "sources": list(c.sources),
                      "work_overlap": c.work_overlap} for c in intent.concepts],
        "n_concepts": len(ids),
        "n_registered": sum(c.registered for c in intent.concepts),
        "n_literal": sum(not c.registered for c in intent.concepts),
        "n_corpus_known": sum(1 for c in ids if market_obj.vocab.get(c, 0) > 0),
        "n_work_overlap": sum(c.work_overlap for c in intent.concepts),
        "work_only": list(intent.work_only),
        "other_claimed": list(intent.other_claimed),
        "skills_groups": list(intent.skills_groups),
        "skills_order": [list(o) for o in intent.skills_order],
        "provenance": dict(intent.provenance),
        # Alignment against the TEST-ONLY manifest.
        "title_aligned": any(aligned_title(p, spec["title_terms"]) for _t, _s, p in parts)
                         or any(aligned_title(t.title, spec["title_terms"])
                                for t in intent.declared_titles),
        "title_aligned_nonwildcard": any(aligned_title(p, spec["title_terms"])
                                         for _t, _s, p in parts if p not in wildcard),
        "title_misleading": [p for _t, _s, p in parts
                             if not aligned_title(p, spec["title_terms"])
                             and any(aligned_title(p, M.VARIANTS[o]["title_terms"])
                                     for o in others)],
        "vocab_in_intent": in_vocab,
        "concept_aligned": bool(in_vocab),
        "header_aligned": any(aligned_title(p, spec["title_terms"])
                              for _t, s, p in parts if s == "header")
                          or any(M.norm(c) in vocab for c in header_concepts),
    }


def carried_groups(intent):
    """Measurement only (not DQ2a's rule): each skills line's label carried
    forward over the unlabelled lines a two-column PDF wraps a group onto."""
    labels, carry = [], None
    for label in intent.skills_groups:
        carry = label if label is not None else carry
        labels.append(carry)
    groups = collections.OrderedDict()
    for cid, line, _pos in intent.skills_order:
        groups.setdefault(labels[line] if line < len(labels) else None, []).append(cid)
    return groups


def skills_experiment(intents, recs):
    out = {}
    for doc, intent in intents.items():
        vid = doc.rsplit("-", 1)[0]
        spec = M.VARIANTS[vid]
        vocab = {M.norm(v) for v in spec["vocabulary"]}
        groups = carried_groups(intent)
        labelled = [g for g in intent.skills_groups if g is not None]
        # The label is read from the lines themselves: a skills section whose
        # occurrences are all unclaimed (see skill_evidence's LEARNING
        # marker on "Machine Learning") still has its labels.
        lead_label = labelled[0] if labelled else None
        lead = groups.get(lead_label, []) if lead_label else []
        first_line = [cid for cid, line, _p in intent.skills_order if line == 0]
        out[doc] = {
            "labelled_lines": len(labelled),
            "claimed_in_skills": len(intent.skills_order),
            "lines": len(intent.skills_groups),
            "labels": list(dict.fromkeys(labelled)),
            "lead_label": lead_label,
            "lead_label_aligned": bool(lead_label) and (
                aligned_title(lead_label, spec["title_terms"])
                or M.norm(lead_label) in vocab),
            "lead_group": lead,
            "lead_group_in_vocab": sorted(c for c in lead if M.norm(c) in vocab),
            "first_line": first_line,
            "first_line_in_vocab": sorted(c for c in first_line if M.norm(c) in vocab),
            "intent_aligned": recs[doc]["title_aligned"] or recs[doc]["concept_aligned"],
        }
    return out


# ===========================================================================
# O-P. Generic-floor contract and the labelled jobs
# ===========================================================================

def floor_contract(intents, floor):
    import track_intent
    out = []
    for family, sibs in M.SIBLINGS.items():
        tracks = {v: intents[f"{v}-plain"] for v in sibs}
        for job in (j for j in M.JOBS if j["family"] == family):
            got = track_intent.relevance_contract(job["Title"], tracks, floor)
            out.append({"job": job["id"], "title": job["Title"], "kind": job["kind"],
                        "primary": job["primary"], **got})
    return out


def sweep_module(family, layout, docs):
    import make_profile
    sibs = M.SIBLINGS[family]
    tracks = [{"id": track_id(v), "engine": "v2",
               "derived": docs[f"{v}-{layout}"]["derived"]} for v in sibs]
    return make_profile.render_sweep(f"dq2b {family} {layout}", tracks,
                                     dict(targeted.PREFS))


def contexts(source):
    import scraper
    ns = {}
    exec(compile(source, "<dq2b sweep>", "exec"), ns)
    return [scraper.track_context(t, ns["SCORING"]) for t in ns["TRACKS"]]


def labelled_jobs(docs):
    import scraper
    out = {}
    for family, sibs in M.SIBLINGS.items():
        for layout in targeted.LAYOUTS:
            ctxs = contexts(sweep_module(family, layout, docs))
            by_id = dict(zip((c.id for c in ctxs), sibs))
            rows = []
            for job in (j for j in M.JOBS if j["family"] == family):
                row = {k: job[k] for k in ("Title", "Company", "Location", "Description")}
                facts = scraper.job_facts(row)
                evals = {by_id[c.id]: scraper.evaluate(row, c.scoring, facts) for c in ctxs}
                scores = {v: (e.score if e.eligible else None) for v, e in evals.items()}
                eligible = [v for v in sibs if scores[v] is not None]
                top = max((scores[v] for v in eligible), default=None)
                best = next((v for v in sibs if scores[v] == top), None)
                relevant = [by_id[c.id] for c in ctxs
                            if scraper.title_admits(job["Title"], c.title_hints,
                                                    c.title_exclude)]
                rows.append({"job": job["id"], "title": job["Title"], "kind": job["kind"],
                             "primary": job["primary"], "adjacent_to": job["adjacent_to"],
                             "scores": scores,
                             "matched": {v: e.matched_skills for v, e in evals.items()},
                             "best": best,
                             "tie": sum(1 for v in eligible if scores[v] == top) > 1,
                             "free_relevant": relevant})
            out[f"{family}-{layout}"] = rows
    return out


PLAN = r'''
import json, socket, sys
name, repo = sys.argv[1:3]
def no_network(*a, **k):
    raise RuntimeError("the DQ2b dry run opened a connection")
socket.socket.connect = no_network
socket.create_connection = no_network
sys.argv = ["dq2b-plan", "--profile", name, "--dry-run"]
sys.path[:0] = [".", repo, repo + "/auto-apply"]
import scraper
args = scraper.parse_args()
tracks = scraper.TRACK_CONTEXTS
plans = scraper.multi_plans(scraper.resolve_sites(args), args, tracks)
ceiling = {}
for s, p in plans.items():
    usd = scraper.max_charge_usd(s, scraper.effective_search(s, p[0])["max_results"]) if p else None
    ceiling[s] = None if usd is None else str(usd)
print(json.dumps({"dry": {"plan_hash": scraper.plan_hash(plans, tracks),
                          "charge_ceiling_usd": ceiling},
                  "units": {s: [[u["keywords"], u[scraper.PAID_TRACKS]] for u in p]
                            for s, p in plans.items()}}))
'''


def plans(docs):
    out = {}
    env = {"PATH": "/usr/bin:/bin", "HOME": "", "LANG": "en_US.UTF-8",
           "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    for family, sibs in M.SIBLINGS.items():
        ids = {track_id(v): v for v in sibs}
        for layout in targeted.LAYOUTS:
            with tempfile.TemporaryDirectory() as home:
                os.makedirs(os.path.join(home, "profiles"))
                open(os.path.join(home, "profiles", "__init__.py"), "w").close()
                name = f"dq2b_{family}_{layout}"
                with open(os.path.join(home, "profiles", f"{name}.py"), "w",
                          encoding="utf-8") as fh:
                    fh.write(sweep_module(family, layout, docs))
                got = subprocess.run([sys.executable, "-c", PLAN, name, REPO],
                                     capture_output=True, text=True, cwd=home,
                                     env=dict(env, HOME=home), timeout=300)
            if got.returncode != 0:
                raise RuntimeError(f"dry run {family}-{layout} failed:\n"
                                   f"{got.stderr[-3000:]}")
            data = json.loads(got.stdout)
            units = [(s, k, [ids[t] for t in who])
                     for s, us in data["units"].items() for k, who in us]
            n = len(units)
            track_units = sum(len(who) for *_x, who in units)
            shared_all = sum(1 for *_x, who in units if len(who) == len(sibs))
            exclusive = {v: sum(1 for *_x, who in units if who == [v]) for v in sibs}
            dry = data["dry"]
            ceiling = {site: float(usd) for site, usd in dry["charge_ceiling_usd"].items()}
            out[f"{family}-{layout}"] = {
                "bounded_exposure_usd": round(sum(ceiling[s] for s, *_x in units), 2),
                "separate_plans_exposure_usd": round(
                    sum(ceiling[s] * len(who) for s, _k, who in units), 2),
                "unique_requests": n, "track_units": track_units,
                "saved": round(1 - n / track_units, 3) if track_units else None,
                "shared_by_all": shared_all, "exclusive": exclusive,
                "by_site": {s: len(us) for s, us in data["units"].items()},
                "head": [(s, k, who) for s, k, who in units[:6]],
                "charge_ceiling_usd": dry["charge_ceiling_usd"],
                "plan_hash": dry.get("plan_hash"),
            }
    return out


# ===========================================================================
# N. Fail-open calibration inputs (measured; DQ2c decides)
# ===========================================================================

def group_of(vid):
    case = M.VARIANTS[vid]["case"]
    return {"strong_headline": "strong", "generic_headline": "weak",
            "misheaded": "weak"}.get(case, "control")


CRITERIA = {
    # What DQ2a does today (track_intent.MIN_CONCEPTS = 2).
    "dq2a_today": lambda r: bool(r["declared"]) or r["n_concepts"] >= 2,
    "specific_title_or_2": lambda r: (len(r["declared"]) > len(r["declared_wildcard_titles"])
                                      or r["n_concepts"] >= 2),
    "specific_title_or_3": lambda r: (len(r["declared"]) > len(r["declared_wildcard_titles"])
                                      or r["n_concepts"] >= 3),
    "specific_title_or_2_corpus_known": lambda r: (
        len(r["declared"]) > len(r["declared_wildcard_titles"])
        or r["n_corpus_known"] >= 2),
    "2_corpus_known": lambda r: r["n_corpus_known"] >= 2,
}


def failopen(recs):
    rows = {}
    for doc, r in recs.items():
        vid = doc.rsplit("-", 1)[0]
        wild_titles = [d["title"] for d in r["declared"]
                       if d["parts"] and all(p in r["declared_wildcard"] for p in d["parts"])]
        r = dict(r, declared_wildcard_titles=wild_titles)
        rows[doc] = {"group": group_of(vid), "case": M.VARIANTS[vid]["case"],
                     "n_concepts": r["n_concepts"], "n_corpus_known": r["n_corpus_known"],
                     "n_registered": r["n_registered"], "n_literal": r["n_literal"],
                     "n_declared": len(r["declared"]),
                     "n_declared_specific": len(r["declared"]) - len(wild_titles),
                     **{name: rule(r) for name, rule in CRITERIA.items()}}
    summary = {}
    for group in ("strong", "weak", "control"):
        mine = [x for x in rows.values() if x["group"] == group]
        summary[group] = {
            "documents": len(mine),
            **{f"{k}_range": [min(x[k] for x in mine), max(x[k] for x in mine)]
               for k in ("n_concepts", "n_corpus_known", "n_registered", "n_literal",
                         "n_declared", "n_declared_specific")},
            **{f"passes_{name}": sum(x[name] for x in mine) for name in CRITERIA}}
    return {"documents": rows, "summary": summary}


# ===========================================================================
# M3 baseline
# ===========================================================================

def m3(conv, jobs):
    out = {}
    for family, sibs in M.SIBLINGS.items():
        for layout in targeted.LAYOUTS:
            key = f"{family}-{layout}"
            c = conv[key]
            specific = [r for r in jobs[key] if r["kind"] == "specific"]
            wins = [r for r in specific if r["best"] == r["primary"]]
            clean = [r for r in wins if not r["tie"]]
            head = {v: any(aligned_title(k, M.VARIANTS[v]["title_terms"])
                           for k in c["rk_first_two"][v]) for v in sibs}
            discrim = {v: sum(1 for r in specific if r["primary"] == v
                              and r["free_relevant"] == [v]) for v in sibs}
            out[key] = {
                "rk_jaccard_median": med(c["rk_pairs"].values()),
                "rk_jaccard_max": max(c["rk_pairs"].values()),
                "exclusive": {v: [len(c["rk_exclusive"][v]),
                                  round(len(c["rk_exclusive"][v])
                                        / max(1, len(c["role_keywords"][v])), 2)]
                              for v in sibs},
                "specialism_in_first_two": head,
                "relevance_discrimination": discrim,
                "specific_jobs": len(specific),
                "intended_wins": len(wins), "intended_wins_untied": len(clean),
                "ties": sum(1 for r in jobs[key] if r["tie"]),
                "jobs": len(jobs[key]),
                "coverage_union": c["coverage_union"],
            }
    return out


# ===========================================================================

def run():
    import config
    import track_intent  # noqa: F401  (imported here, never by targeted.py)
    captures = targeted.load_captures()
    docs = replay(captures)
    market_obj, titles = market()
    hard = tuple(config.SCORING["hard_drop_terms"]) + tuple(config.SCORING["soft_drop_terms"])
    corpus_titles = sorted(titles)
    corpus_list = [(t, s) for t, s, _sk, _c in market_obj.rows]
    floor = [h.strip().lower() for h in config.ATS_TITLE_HINTS]
    intents = intents_for(docs, titles, hard)
    recs = {doc: intent_record(intents[doc], doc.rsplit("-", 1)[0], corpus_list,
                               market_obj, hard) for doc in intents}
    conv = convergence(docs, corpus_titles, floor, market_obj)
    jobs = labelled_jobs(docs)
    import track_intent as ti
    intent_pairs = {}
    for family, sibs in M.SIBLINGS.items():
        for layout in targeted.LAYOUTS:
            intent_pairs[f"{family}-{layout}"] = ti.compare(
                {v: intents[f"{v}-{layout}"] for v in sibs})
    layout_stability = {vid: {"concepts": jaccard(intents[f"{vid}-plain"].ids,
                                                  intents[f"{vid}-twocol"].ids),
                              "titles_equal": intents[f"{vid}-plain"].titles
                              == intents[f"{vid}-twocol"].titles,
                              "sufficient_equal": intents[f"{vid}-plain"].sufficient
                              == intents[f"{vid}-twocol"].sufficient,
                              "role_keywords_equal":
                                  docs[f"{vid}-plain"]["derived"]["role_keywords"]
                                  == docs[f"{vid}-twocol"]["derived"]["role_keywords"],
                              "weights_wj": weighted_jaccard(
                                  weights(docs[f"{vid}-plain"]["derived"]),
                                  weights(docs[f"{vid}-twocol"]["derived"]))}
                        for vid in M.VARIANTS}
    return {
        "meta": {"documents": len(docs), "model_calls": 0,
                 "floor_hints": len(floor), "corpus_titles": len(corpus_titles),
                 "floor_admission": len(admitted(floor, (), corpus_titles))},
        "consistency": consistency(captures, docs),
        "convergence": conv,
        "plans": plans(docs),
        "intent": recs,
        "intent_pairs": intent_pairs,
        "layout_stability": layout_stability,
        "skills_experiment": skills_experiment(intents, recs),
        "failopen": failopen(recs),
        "floor_contract": floor_contract(intents, floor),
        "jobs": jobs,
        "m3": m3(conv, jobs),
    }


def main():
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    result = run()
    text = json.dumps(result, indent=1, ensure_ascii=False, default=list)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
