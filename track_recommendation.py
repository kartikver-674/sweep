"""Which résumés to recommend for one job of a Multi-Track Sweep, from the
scores its tracks already earned (DQ4-1), plus the directly role-aligned
alternative a fit margin can miss (DQ6-F1-C1). Pure and deterministic.

    recommend(scores, order, direct_evidenced=()) -> Recommendation
    direct(role_titles, title) -> bool

`scores` is {track id: score} for exactly the tracks the caller already
evaluated for this job and kept: relevant (paid by it, or admitted by its
title gate), eligible, at or above min_score — the job's track_evals. Nothing
here decides relevance or eligibility, and a track the caller left out can
never be recommended. The scores are compared, never changed: no rounding,
normalising or new fit score. They are Evaluation.score, a whole number
(check_tracks keeps every weight, penalty and bonus integral).

A track is recommended when its score is within RECOMMENDATION_MARGIN of the
top score. The kind says only how the top relates to the rest:

    clear  one track recommended
    close  one top track, and others within the margin
    tied   two or more tracks share the top score

"tied" is about the TOP: 25 / 25 / 24 recommends all three and is tied — the
two 25s are tied, the 24 is a close follower. Members of a tied
recommendation need not share a score; the scores are in track_evals. A
clear recommendation is not a strong one: 2 against 0 is clear. The kind
describes scores among tracks already judged fit to show, not the fit of any
of them, and there is no absolute threshold.

Tracks are listed by score, highest first, then in `order` — the Sweep's
track order, which decides nothing else. Who is recommended never depends on
`order`; only the listing of equal scores does. So the first track is always
the one rank_clusters picks as best_track (highest score, ties to track
order), without this module choosing a winner of its own.

Ids only: no résumé name, filename or label, no row, copy or provenance.
found_by records which searches acquired a job; that is not suitability and
is not read here.

DIRECT ROLE ALIGNMENT (DQ6-F1-C1). The score is document fit, and a broader
sibling can out-score the résumé written for the job's very role. The fit is
never changed for it. Instead `direct_evidenced` names the evaluated tracks
whose own accepted role title IS the job's role (direct(), below) and whose
own evaluation matched a concept they position (the caller's P3a test); the
best-scoring of them, with any exact tie, joins the margin set. A lower one is
not added: it is neither fitter nor more aligned than that one. `split` then
says a member is outside the margin, and wins over tied/close/clear, which
otherwise keep their exact meaning — so a reader of those three may still
infer every member is within RECOMMENDATION_MARGIN of the top.

direct() reads a job title as its roles: split into segments, each one's
head is its right-most role word (English compounds are right-headed) and its
qualifier the words before it, less the role words and level words. A segment
that already names a specialisation keeps it ("Mobile Engineer - Frontend" is
a mobile role), and only a generic head ("Senior Software Engineer - React
Native") borrows an unheaded segment's words. A résumé role title
("frontend engineer") aligns when its qualifier is that reading's qualifier's
last words and the heads agree: the same word, or engineer and developer, the
one pair the repo's own title contracts treat as one qualified role. No other
head, no ontology, no sibling. A generic résumé role never aligns.
"""
import re
from dataclasses import dataclass

# One point: the smallest step the scorer takes — one weight step inside an
# evidence band, or one positioned concept. DQ4 audit: on DQ2b the intended
# résumé's inclusion stops rising at 1 (View A 38/40, View B 46/48); wider
# margins add only sibling résumés. Provisional until DQ6's real-job check.
RECOMMENDATION_MARGIN = 1

# A Sweep has one to three tracks (make_profile.MAX_TRACKS); more is a
# profile contract bug, not a bigger recommendation.
MAX_TRACKS = 3

CLEAR, CLOSE, TIED, SPLIT = "clear", "close", "tied", "split"

# The only equivalent role heads, and only after a qualifier: config's
# ATS_TITLE_HINTS and role_evidence's rules name each qualified build role
# with both ("mobile engineer" / "mobile developer"), while a bare "engineer"
# is any profession's.
HEAD_CLASS = frozenset(("engineer", "developer"))

# Where a job title's segments meet: a dash with space on either side, an en or
# em dash, , ; : | ( ) [ ], or a spaced slash. "Front-End" and "ERDS-MJ" are one.
_SEGMENT = re.compile(r"\s+[-–—]+\s*|\s*[-–—]+\s+|[–—,;:|()\[\]]|\s/\s")


def _words():
    # The multi-résumé vocabulary, loaded only when a role is read: schema 1
    # and a Sweep without ALIGNMENT never import the search derivation.
    import title_gate
    import track_intent
    import track_search
    return track_intent.ROLE_HEADS, track_search, title_gate._LEVEL


def readings(title):
    """((qualifier words, head), ...) a job title names: "Senior Software
    Engineer - React Native" -> ((("react", "native"), "engineer"),)."""
    heads, ts, level = _words()
    headed, plain = [], []
    for piece in _SEGMENT.split(str(title or "")):
        words = [w for w in ts._tokens(piece) if not level.fullmatch(w)]
        at = [i for i, w in enumerate(words) if w in heads]
        if at:
            headed.append((tuple(w for w in words[:at[-1]] if w not in ts.ROLE_WORDS),
                           words[at[-1]]))
        else:
            words = tuple(w for w in words if w not in ts.ROLE_WORDS)
            if words:
                plain.append(words)
    own = [(q, h) for q, h in headed if q]
    if own:
        return tuple(own)
    return tuple((q, headed[0][1]) for q in plain) if headed else ()


def roles(role_titles):
    """((qualifier words, head), ...) for accepted role titles, generic ones
    left out: "full stack developer" -> (("full", "stack"), "developer")."""
    _heads, ts, _level = _words()
    out = []
    for title in role_titles:
        words = tuple(ts.qualifier(title).split())
        if words and not all(w in ts.STANDALONE_GENERIC for w in words):
            out.append((words, title.split()[-1]))
    return tuple(out)


def direct(role_titles, title):
    """Does one of a track's accepted role titles name this job title's role?"""
    mine = roles(role_titles)
    return bool(mine) and any(
        q[-len(w):] == w and (h == head or (h in HEAD_CLASS and head in HEAD_CLASS))
        for w, head in mine for q, h in readings(title))


@dataclass(frozen=True)
class Recommendation:
    tracks: tuple   # recommended track ids: score descending, then the supplied order
    kind: str       # clear | close | tied | split

    def as_dict(self):
        """Deterministic, JSON-ready."""
        return {"tracks": list(self.tracks), "kind": self.kind}


def recommend(scores, order, direct_evidenced=()):
    """The Recommendation for one job. `scores`: {track id: whole-number
    score}, one to MAX_TRACKS tracks. `order`: the same ids, each once, in
    the Sweep's track order. `direct_evidenced`: scored tracks that are
    DIRECT and evidenced on this job; none gives DQ4 exactly. Raises
    TypeError or ValueError on anything else rather than guess."""
    if not isinstance(scores, dict):
        raise TypeError(f"scores must be a dict of track id -> score, got {type(scores).__name__}")
    if not scores:
        raise ValueError("no evaluated track to recommend")
    if len(scores) > MAX_TRACKS:
        raise ValueError(f"a Sweep has at most {MAX_TRACKS} tracks, got {len(scores)}")
    for tid, score in scores.items():
        if not isinstance(tid, str) or not tid:
            raise TypeError(f"track id must be a non-empty string, got {tid!r}")
        if isinstance(score, bool) or not isinstance(score, int):
            raise TypeError(f"score of {tid!r} must be a whole number, got {score!r}")
    order = tuple(order)
    if len(set(order)) != len(order) or set(order) != set(scores):
        raise ValueError(f"order must list each scored track exactly once: "
                         f"order {list(order)}, scored {sorted(scores)}")
    aligned = frozenset(direct_evidenced)
    if not aligned <= set(scores):
        raise ValueError(f"an aligned track must be a scored one: aligned {sorted(aligned)}, "
                         f"scored {sorted(scores)}")
    top = max(scores.values())
    floor = top - RECOMMENDATION_MARGIN
    chosen = {tid for tid in order if scores[tid] >= floor}
    if aligned:
        best = max(scores[tid] for tid in aligned)
        chosen |= {tid for tid in aligned if scores[tid] == best}
    tracks = tuple(sorted((tid for tid in order if tid in chosen), key=lambda tid: -scores[tid]))
    if any(scores[tid] < floor for tid in tracks):
        return Recommendation(tracks, SPLIT)
    tied = sum(1 for score in scores.values() if score == top) > 1
    return Recommendation(tracks, TIED if tied else CLOSE if len(tracks) > 1 else CLEAR)
