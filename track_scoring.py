"""Track-specific scoring intent: the résumé-supported positioning ONE track of
a Multi-Track Sweep may later score with (DQ3-1). Pure, deterministic and, for
now, unwired: nothing calls it, so no score can change.

    derive_track_scoring(intent, search_intent) -> TrackScoringIntent

It reads two records of one résumé and nothing else: its TrackIntent
(track_intent.py) and its TrackSearchIntent (track_search.py). From the search
record it reads only the decisions already reviewed there about the résumé's
own words — the accepted leading declared titles and the head-free
positioning concepts — never what search then does with them (role_keywords,
focused_titles, fallback_used, retrieval): those are acquisition artefacts,
and scoring must not learn from a search query. Both records must describe
the same résumé: a leading title the résumé never declared, or a concept it
never positioned, is refused. There is no sibling, Sweep, environment, model
or network in the signature, so there is nowhere for one to come from.

It holds positioning, not capability and not policy:

    concepts         positioned concept ids, in the résumé's order
    role_qualifiers  what each accepted title specialises in ("Full Stack
                     Engineer" -> "full stack"), at most MAX_LEADING_TITLES;
                     a header specialism keeps the head it borrowed ("Software
                     Engineer | Applied AI" -> "ai engineer", never "ai")

No weight, no evidence level, no alias beyond the ids the derivation already
resolved, and no scoring constant. DQ3-2 decides what a job must match for a
record to earn anything, and may only add to a concept the job matched and the
track's own ScoringContext already weighs: positioning modifies evidence, it
never creates it.

work_overlap is kept as a diagnostic (work_backed) and changes nothing else:
work evidence is largely shared between one person's résumés, and the evidence
weights already count demonstrated use.
"""
from dataclasses import dataclass

import track_search

VERSION = 1


@dataclass(frozen=True)
class TrackScoringIntent:
    version: int
    sufficient: bool        # some positioning concept or role qualifier to score with
    reason: str             # concepts_and_titles | concepts | titles | none
    concepts: tuple         # positioned concept ids, in the résumé's order
    role_qualifiers: tuple  # accepted leading titles' qualifiers, in their order
    concept_sources: tuple  # ((concept id, (header | summary | project, ...)), ...)
    title_sources: tuple    # ((qualifier, header | summary), ...)
    work_backed: tuple      # diagnostic only: positioned ids also used at work

    def as_dict(self):
        """Deterministic, JSON-ready: ids, qualifier phrases and source names."""
        return {
            "version": self.version, "sufficient": self.sufficient, "reason": self.reason,
            "concepts": list(self.concepts),
            "role_qualifiers": list(self.role_qualifiers),
            "concept_sources": [[cid, list(sources)] for cid, sources in self.concept_sources],
            "title_sources": [[qual, source] for qual, source in self.title_sources],
            "work_backed": list(self.work_backed),
        }


def accepted_titles(intent, search_intent):
    """((SearchTitle, qualifier), ...): the leading titles this résumé declared
    and search accepted — header, summary or header specialism, never a
    retrieval title — at most MAX_LEADING_TITLES, in search order, each with
    the qualifier its title alignment matches. A title with no qualifier is
    left out. Raises ValueError for a leading title the résumé never declared.
    The one selection role positioning and the ALIGNMENT carrier (DQ6-F1-C1)
    both read, so the two can never pick differently."""
    declared = {(track_search.normalize_query(part), title.source)
                for title in intent.declared_titles for part in title.parts}
    out = []
    for title in search_intent.leading_titles[:track_search.MAX_LEADING_TITLES]:
        if (title.query, title.source) not in declared:
            raise ValueError(f"leading title {title.query!r} ({title.source}) is not a "
                             f"title this résumé declared")
        # A header specialism borrowed its head from the title before its "|":
        # the head stays ("ai engineer"), so title alignment needs the role
        # phrase, never the bare words ("ai").
        qualifier = (title.query if title.source == track_search.SPECIALISM
                     else track_search.qualifier(title.query))
        if qualifier:
            out.append((title, qualifier))
    return tuple(out)


def derive_track_scoring(intent, search_intent):
    """This résumé's TrackScoringIntent from its own two records. Reads, never
    writes, them; raises ValueError when they are not the same résumé's."""
    concepts, concept_sources, work_backed = [], [], []
    for cid in search_intent.concepts:
        concept = intent.concept(cid)
        if concept is None:
            raise ValueError(f"positioning concept {cid!r} is not in this résumé's TrackIntent")
        concepts.append(cid)
        concept_sources.append((cid, tuple(concept.sources)))
        if concept.work_overlap:
            work_backed.append(cid)
    qualifiers, title_sources = [], []
    for title, qualifier in accepted_titles(intent, search_intent):
        if qualifier not in qualifiers:
            qualifiers.append(qualifier)
            title_sources.append((qualifier, title.source))
    reason = ("concepts_and_titles" if concepts and qualifiers else "concepts" if concepts
              else "titles" if qualifiers else "none")
    return TrackScoringIntent(
        version=VERSION, sufficient=reason != "none", reason=reason,
        concepts=tuple(concepts), role_qualifiers=tuple(qualifiers),
        concept_sources=tuple(concept_sources), title_sources=tuple(title_sources),
        work_backed=tuple(work_backed))
