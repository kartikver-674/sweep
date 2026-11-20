"""Track-specific search intent: what ONE résumé of a Multi-Track Sweep should
search for (DQ2c). Pure and deterministic.

    derive_track_search(resume_text, derived, intent, market) -> TrackSearchIntent

Everything it reads belongs to one résumé: its text, its own derivation
(`derived`, never written), its own TrackIntent (track_intent.py), plus the
static corpus (`market`, a local_search.Market) and config's seniority lists.
It takes no sibling, no Sweep, no environment variable, no model and no
network, so a track's search intent cannot depend on the other résumés in its
Sweep: the signature has nowhere to put them.

make_profile.with_track_search (DQ2c-2) carries the result in
derived["track_search"] and render_sweep puts its `role_keywords` into
schema-2 SEARCH, for 2-3-track Sweeps behind SWEEP_TRACK_SEARCH_INTENT only.
derived["role_keywords"] is never rewritten: it also feeds the free title gate
(title_gate.build hands it to family_centrality), which DQ2c does not change.

A sufficiently positioned track — a declared title that may lead, or at least
MIN_CONCEPTS positioned concepts — searches for, in order:

  1. its leading declared titles (at most MAX_LEADING_TITLES, header first),
     spelled as the résumé writes them, never swapped for a corpus title;
  2. with at least MIN_CORPUS_KNOWN corpus-known concepts, the corpus titles
     those concepts alone retrieve, through today's validation and guards,
     kept only when anchored to the track's own qualifiers or concepts;
     otherwise the broad tier: today's role_keywords that are so anchored;
  3. today's anchored role_keywords again, only to reach MIN_TOP_UP. A title
     sharing no anchor never fills the list: a track may search one or two;
  4. only when nothing at all survived, today's first MIN_TOP_UP titles;

normalised, deduplicated in order and capped at MAX_ROLE_KEYWORDS. Anchored
means sharing a word that is neither a role word nor grammar, so "software
engineer" never agrees with a track merely by "engineer" (DQ2c-3: P1c). A
track that is not sufficiently positioned searches exactly today's list, byte
for byte.

A SPECIALISM-LED track — one whose leading titles include a header specialism
(track_intent: "Software Engineer | Applied AI" -> "ai engineer", grounded in
the résumé's own summary or project text, and here judged like any header
title) — searches exactly its leading titles, and nothing else (DQ6-F1-A).
Steps 2-4 exist to guess titles for a résumé that did not name its target;
one that did, in its header and its own text, with a title the market uses,
has stronger intent than retrieval from concepts its siblings share. So its
named roles replace that retrieval rather than adding to it: no corpus tier,
no top-up to MIN_TOP_UP (one leading title searches one), so never more than
MAX_LEADING_TITLES titles. A specialism reading is composed, not written by
the résumé, so besides the header-title judges it must be a title the market
uses (a corpus title contains it).
"""
import re
from dataclasses import dataclass

import canonical_guard
import hard_drop
import local_search
import role_evidence
import skill_concepts
import skill_evidence as se
import track_intent
import unknown_family_guard

VERSION = 2              # 2: P1c, today's titles only where they agree (DQ2c-3)

MIN_CONCEPTS = 2          # positioned concepts that make a track sufficient
MIN_CORPUS_KNOWN = 2      # corpus-known concepts before retrieval focuses on them
MAX_LEADING_TITLES = 2
MIN_TOP_UP = 3
MAX_ROLE_KEYWORDS = 8
FOCUSED_WANT = 12         # fields_for's own corpus tier size

# Words that name a role or the trade, never a specialism: never a title's
# qualifier, never an anchor, never a positioning concept on their own.
ROLE_WORDS = frozenset(track_intent.ROLE_HEADS) | {"engineering", "development", "software"}
# Positioning only inside a phrase ("data engineering"), never alone.
STANDALONE_GENERIC = frozenset(("data", "tools", "languages"))
# How someone works, never which résumé this is: a development methodology or
# an AI coding assistant. Capability evidence (base scoring still weighs it),
# not role positioning. A small declared class, not a corpus statistic
# (DQ6-F1-B); widening it needs its own audit.
PRACTICE = frozenset(("agile", "scrum",                        # methodology
                      "claude", "github copilot", "cursor"))   # AI coding assistants
_GRAMMAR = frozenset(("a", "an", "and", "or", "of", "the", "for", "in", "on", "at", "to",
                      "with", "&"))

# The only role-compound aliases (DQ2c design): one spelling, never a meaning.
COMPOUNDS = (("fullstack", "full stack"), ("front end", "frontend"), ("back end", "backend"))

_JOINER = re.compile(r"(?<=\S)[-_/]+(?=\S)")
_TOKEN = re.compile(r"[a-z0-9+#.]+")

# A leading title read from a header specialism (track_intent): it makes the
# track specialism-led, and scoring keeps its borrowed head (track_scoring).
SPECIALISM = track_intent.SPECIALISM

# Rejected-title reasons.
WILDCARD, VALIDATION, ROLE_GATE, UNSUPPORTED_HEADER, LIMIT = (
    "wildcard", "validation", "role_gate", "unsupported_header", "limit")


@dataclass(frozen=True)
class SearchTitle:
    query: str              # the declared title, normalised query spelling
    source: str             # header | specialism | summary


@dataclass(frozen=True)
class RejectedTitle:
    query: str
    source: str
    reason: str             # wildcard | validation | role_gate | unsupported_header | limit


@dataclass(frozen=True)
class TrackSearchIntent:
    version: int
    sufficient: bool
    reason: str             # title_and_concepts | title | concepts | insufficient
    leading_titles: tuple   # SearchTitle, in search order
    rejected_titles: tuple  # RejectedTitle
    concepts: tuple         # positioned concept ids that position (head-free)
    excluded_concepts: tuple  # ((id, generic | group_label | practice), ...)
    corpus_known: tuple     # the concepts the corpus vocabulary knows
    retrieval: str          # focused | broad | fallback | specialism
    focused_titles: tuple   # anchored focused corpus titles, normalised
    fallback_used: bool     # today's role_keywords reached role_keywords
    role_keywords: tuple

    def as_dict(self):
        """Deterministic, JSON-ready: ids and validated title phrases only."""
        return {
            "version": self.version, "sufficient": self.sufficient, "reason": self.reason,
            "leading_titles": [{"query": t.query, "source": t.source}
                               for t in self.leading_titles],
            "rejected_titles": [{"query": t.query, "source": t.source, "reason": t.reason}
                                for t in self.rejected_titles],
            "concepts": list(self.concepts),
            "excluded_concepts": [list(c) for c in self.excluded_concepts],
            "corpus_known": list(self.corpus_known),
            "retrieval": self.retrieval,
            "focused_titles": list(self.focused_titles),
            "fallback_used": self.fallback_used,
            "role_keywords": list(self.role_keywords),
        }


def normalize_query(text):
    """One spelling per query: lower case; a hyphen, underscore or slash joining
    two words is a space ("full-stack" -> "full stack", "ai/ml" -> "ai ml");
    "." "+" "#" inside a token stay (node.js, c++, c#); then COMPOUNDS, as
    whole words; whitespace collapsed. A spaced " / " separates alternatives
    and is left alone."""
    low = " ".join(_JOINER.sub(" ", str(text or "").lower()).split())
    for compound, spelling in COMPOUNDS:
        low = re.sub(rf"(?<![a-z0-9]){re.escape(compound)}(?![a-z0-9])", spelling, low)
    return " ".join(low.split())


def _tokens(text):
    return [t.strip(".") for t in _TOKEN.findall(normalize_query(text)) if t.strip(".")]


def qualifier(title):
    """The title minus its role words: "Backend Engineer" -> "backend",
    "Software Engineer" -> "" (nothing left to qualify it)."""
    return " ".join(t for t in _tokens(title) if t not in ROLE_WORDS)


def _contains(tokens, phrase):
    n = len(phrase)
    return n > 0 and any(tokens[i:i + n] == phrase for i in range(len(tokens) - n + 1))


def positioning_concepts(intent):
    """(concepts that position, excluded (id, reason) pairs), both in intent order.

    `generic`: nothing is left once role words are removed ("software
    engineering"), or the whole concept is a STANDALONE_GENERIC word
    ("data"); "data engineering" and "software testing" keep a residue and
    stay. `group_label`: every skills-section occurrence of the concept is the
    label of its own skills line — the derivation read the label as a skill,
    so its presence depends on the layout (DQ2b: "test automation" in the
    two-column SDET résumé only). `practice`: the concept is in PRACTICE — real
    capability, still in the evidence and the weights, but it names no role."""
    labels = {g: normalize_query(label) for g, label in enumerate(intent.skills_groups) if label}
    kept, excluded = [], []
    for concept in intent.concepts:
        spelled = normalize_query(concept.id)
        residue = [t for t in _tokens(concept.id) if t not in ROLE_WORDS and t not in _GRAMMAR]
        at = [g for cid, g, _pos in intent.skills_order if cid == concept.id]
        if not residue or spelled in STANDALONE_GENERIC:
            excluded.append((concept.id, "generic"))
        elif at and all(labels.get(g) == spelled for g in at):
            excluded.append((concept.id, "group_label"))
        elif spelled in PRACTICE:
            excluded.append((concept.id, "practice"))
        else:
            kept.append(concept)
    return tuple(kept), tuple(excluded)


def _positioning_text(resume_text):
    """Token lists of this résumé's summary and project sections, one per
    section, so a phrase never spans two."""
    text = str(resume_text or "")
    return [_tokens(text[start:end]) for kind, _entry, start, end in se.sections(text)
            if kind in (se.SUMMARY, se.PROJECT)]


def _supported_header(title, sections, concepts):
    """A header title leads only when the same résumé supports its qualifier:
    as whole words in its own summary or project text, or as a concept it
    positions somewhere other than the header itself."""
    qual = qualifier(title)
    if not qual:
        return False
    if any(_contains(tokens, qual.split()) for tokens in sections):
        return True
    wanted = {qual, normalize_query(skill_concepts.resolve(qual))}
    return any(normalize_query(c.id) in wanted
               or normalize_query(skill_concepts.resolve(c.id)) in wanted
               for c in concepts if set(c.sources) - {"header"})


def _gate(role, queries, legacy):
    """The role gate as the derivation applies it: judged beside the track's
    own already-gated list, so a query only survives on its own verdict,
    never through the gate's everything-would-go fail-open."""
    if role is None:
        return set(queries)
    kept, _rejected = role_evidence.filter_queries(role, list(queries) + list(legacy))
    return set(kept)


def _titles(resume_text, derived, intent, market, concepts, legacy):
    """(leading SearchTitles, RejectedTitles). Header parts first, then header
    specialisms, then summary parts, each in résumé order."""
    candidates = []
    for source in ("header", SPECIALISM, "summary"):
        for declared in intent.declared_titles:
            if declared.source != source:
                continue
            for part in declared.parts:
                query = normalize_query(part)
                if query and all(query != q for q, _s in candidates):
                    candidates.append((query, source))
    passed = _gate(derived.get("role_evidence"), [q for q, _s in candidates], legacy)
    sections = _positioning_text(resume_text)
    leading, rejected = [], []
    for query, source in candidates:
        bought = local_search.profile_of(query, market.titles, ())
        if bought["share"] > local_search.WILDCARD_SHARE:
            reason = WILDCARD
        elif not local_search.validated([query], market.rows, market.seniority):
            reason = VALIDATION
        elif source == SPECIALISM and not bought["listings"]:
            # A specialism reading is composed (it borrowed its head), not
            # written by the résumé: the market must attest it as a title.
            reason = VALIDATION
        elif query not in passed:
            reason = ROLE_GATE
        elif source != "summary" and not _supported_header(query, sections, concepts):
            reason = UNSUPPORTED_HEADER
        elif len(leading) >= MAX_LEADING_TITLES:
            reason = LIMIT
        else:
            leading.append(SearchTitle(query, source))
            continue
        rejected.append(RejectedTitle(query, source, reason))
    return tuple(leading), tuple(rejected)


def focused_candidates(corpus_known, derived, market, legacy=()):
    """The corpus titles these concepts ALONE retrieve, through today's
    corpus-tier path (keywords_for, canonicalise, validated) and the guards
    this résumé's own derivation ran — decided from its records, never from
    the environment. Normalised; not yet anchored."""
    admission, trace = {}, []
    found = local_search.validated(
        local_search.canonicalise(
            local_search.keywords_for(set(corpus_known), market.rows, market.index,
                                      market.total, want=FOCUSED_WANT,
                                      seniority=market.seniority, stats=admission),
            market.rows, market.seniority, trace=trace),
        market.rows, market.seniority)
    legacy = list(legacy)
    canonical_record = derived.get("canonical_guard_record")
    if canonical_record is not None:
        hard_terms, _soft = local_search.seniority_lists()
        exempt, _r = hard_drop.restore(
            {"role_keywords": [], "role_signals": derived.get("role_signals") or {},
             "role_evidence": derived.get("role_evidence")}, market)
        kept, record = canonical_guard.revalidate(
            found + legacy, trace, market.titles, exempt, hard_terms,
            fallback=canonical_record.get("fallback_policy"))
        found = [q for q in found if q in kept] + list(record.get("recovered") or ())
    if derived.get("unknown_family_record") is not None:
        kept, _r = unknown_family_guard.filter_queries(found + legacy, (), admission, trace)
        found = [q for q in found if q in kept]
    passed = _gate(derived.get("role_evidence"), found, legacy)
    out = []
    for query in found:
        spelled = normalize_query(query)
        if query in passed and spelled and spelled not in out:
            out.append(spelled)
    return out


def anchors(leading, concepts):
    """Non-generic words of the leading titles' qualifiers and of the
    positioning concepts: what a corpus suggestion must share to be kept."""
    words = {t for title in leading for t in qualifier(title.query).split()}
    words |= {t for concept in concepts for t in _tokens(concept.id)}
    return words - ROLE_WORDS - _GRAMMAR


def anchored(titles, words):
    """The corpus titles that share at least one anchor word, in order."""
    return [t for t in titles if (set(_tokens(t)) - ROLE_WORDS - _GRAMMAR) & words]


def derive_track_search(resume_text, derived, intent, market):
    """This résumé's TrackSearchIntent. Reads, never writes, its inputs."""
    derived = derived or {}
    legacy = [k for k in (derived.get("role_keywords") or ())]
    concepts, excluded = positioning_concepts(intent)
    leading, rejected = _titles(resume_text, derived, intent, market, concepts, legacy)
    known = tuple(c.id for c in concepts if market.vocab.get(c.id, 0) > 0)
    by_title, by_concepts = bool(leading), len(concepts) >= MIN_CONCEPTS
    reason = ("title_and_concepts" if by_title and by_concepts else "title" if by_title
              else "concepts" if by_concepts else "insufficient")
    common = dict(version=VERSION, reason=reason, rejected_titles=rejected,
                  concepts=tuple(c.id for c in concepts), excluded_concepts=excluded,
                  corpus_known=known)
    if reason == "insufficient":
        return TrackSearchIntent(sufficient=False, leading_titles=(), retrieval="fallback",
                                 focused_titles=(), fallback_used=True,
                                 role_keywords=tuple(legacy), **common)
    if any(title.source == SPECIALISM for title in leading):
        # The résumé named its roles (header specialism, grounded in its own
        # text, valid in the corpus): retrieval from shared concepts exists to
        # guess titles for a résumé that did not, so it is not searched here.
        return TrackSearchIntent(sufficient=True, leading_titles=leading, retrieval=SPECIALISM,
                                 focused_titles=(), fallback_used=False,
                                 role_keywords=tuple(title.query for title in leading), **common)

    focused = ()
    words = anchors(leading, concepts)
    if len(known) >= MIN_CORPUS_KNOWN:
        retrieval = "focused"
        focused = tuple(anchored(focused_candidates(known, derived, market, legacy), words))
    else:
        retrieval = "broad"
    # Today's titles only where they agree with this track's own intent.
    consistent = anchored(legacy, words)
    out, from_legacy = [], set()

    def add(query, legacy_source=False):
        spelled = normalize_query(query)
        if spelled and spelled not in out:
            out.append(spelled)
            if legacy_source:
                from_legacy.add(spelled)

    for title in leading:
        add(title.query)
    for query in (focused if retrieval == "focused" else consistent):
        add(query, legacy_source=retrieval == "broad")
    for query in consistent:
        if len(out) >= MIN_TOP_UP:
            break
        add(query, legacy_source=True)
    if not out:
        # Nothing of its own survived: today's first titles, in its spelling.
        for query in legacy:
            if len(out) >= MIN_TOP_UP:
                break
            add(query, legacy_source=True)
    role_keywords = tuple(out[:MAX_ROLE_KEYWORDS])
    return TrackSearchIntent(sufficient=True, leading_titles=leading, retrieval=retrieval,
                             focused_titles=focused,
                             fallback_used=any(q in from_legacy for q in role_keywords),
                             role_keywords=role_keywords, **common)
