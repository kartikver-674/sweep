"""What one résumé is aiming at, as opposed to what its owner has done.

DQ2a of Multi-Track derivation quality. DQ1
(MULTI_TRACK_DERIVATION_QUALITY_AUDIT.md) found that several targeted résumés
from one person derive nearly the same TrackContext: every derived field is
built from the skill list and the employment rows, which the résumés share,
and nothing reads the part of a targeted résumé that differs — its headline,
its summary, the projects it chose to describe.

This is that reading, and in DQ2a it is ONLY a reading:

    derive_track_intent(resume_text, derived)   -> TrackIntent
    for_sweep([(text, derived), ...])           -> one per résumé, 2-3 only
    compare(intents)                            -> overlap diagnostics
    relevance_contract(title, intents, floor)   -> DQ2c's free-row contract

Nothing in production calls any of it. Search, scoring, render() and
render_sweep() are untouched, and a one-résumé upload never reaches it.

HOW INTENT IS READ
------------------
Not from the text afresh. The derivation already recorded where every skill
occurs — section, status, shape, offsets, a sentence digest — in
`derived["skill_importance"]` (make_profile.reweight_from_evidence). This is a
projection of that record, so it can neither disagree with the derivation nor
be moved by an environment switch; a derivation without the record (v1) gets
an insufficient intent, which DQ2c treats as "derive exactly as today".

A concept is INTENT when the résumé positions it:

    header    named in the block above the first section heading
    summary   named in a summary / profile / objective section
    project   described with a verb in a project (skill_evidence's
              SUBSTANTIVE_USE — a stack line is not enough)

Work evidence alone is never intent. Apex used at the job three targeted
résumés share is a capability of the person, not a direction of this résumé;
it is recorded in `work_only`. Work evidence that the résumé ALSO positions is
the strongest intent there is, and is marked `work_overlap`.

The skills section is MEASURED (group labels and order) and never makes
intent: DQ1 did not adopt it, and DQ2a only records whether it would add
anything.

A header SPECIALISM is a declared title too (DQ6-F1-A): "Software Engineer |
Applied AI & Full-Stack" names a profession, then what it specialises in
without repeating the role word. Each "&" part borrows the head of the title
before its "|" — only there, never in the body — and is kept only when the
résumé's own summary or project text says the same words. It creates no
skill and no evidence; the corpus judges it later, like any title.

PRIVACY
-------
The record holds concept identifiers, validated job-title phrases, section
names, offsets, counts and skill_evidence's sentence digests. Never a
sentence, a contact value, a URL or the candidate's name: emails, URLs and
phone numbers are masked as spans of the original text, and so is the name
inside the header, before a concept or a title is read. A title on the same
line as a contact value survives; the contact value does not.
"""
import itertools
import re
from dataclasses import dataclass

import skill_concepts
import skill_evidence as se
import title_gate

POSITIONING = ("header", "summary", "project")
# A declared title read from a header specialism: "<title> | <specialism>".
SPECIALISM = "specialism"

# Provisional: DQ2b's synthetic target variants calibrate it (DQ1 §P, U5).
MIN_CONCEPTS = 2

# A job-title head, in any profession. Not a list of the tracks anyone tested:
# a title is "<qualifiers> <one of these>", whatever the field.
ROLE_HEADS = frozenset((
    "engineer", "developer", "programmer", "architect", "scientist", "analyst",
    "designer", "consultant", "manager", "administrator", "specialist",
    "researcher", "tester", "technician", "strategist", "lead", "sdet",
    "accountant", "teacher", "nurse", "recruiter", "writer", "editor",
    "coordinator", "director", "officer", "marketer", "economist",
    "statistician",
))

# Words that end a title when walking back from its head: grammar, and the
# self-praise that is not a role ("motivated engineer" names no job).
_STOP = frozenset((
    "a", "an", "the", "and", "or", "of", "for", "with", "in", "at", "as", "to",
    "on", "by", "from", "who", "i", "am", "my", "our", "is", "are", "was",
    "over", "years", "year", "yrs",
    "motivated", "self-motivated", "passionate", "results-driven",
    "results-oriented", "result-oriented", "detail-oriented", "dedicated",
    "driven", "experienced", "enthusiastic", "aspiring", "skilled", "seasoned",
    "dynamic", "hardworking", "hard-working", "creative", "innovative",
    "proactive", "versatile", "highly", "curious", "ambitious", "reliable",
    "accomplished", "talented", "certified",
))

MAX_QUALIFIERS = 4

# "I am a …" / "I'm an …" in a summary: the résumé naming what its owner is.
# Only inside one may a lowercase, unknown word join a title ("I am a backend
# automation engineer"). The article is required: without it "I am seeking
# backend engineer roles" would read as one.
_SELF_ID = re.compile(r"(?<![A-Za-z0-9])I(?:\s+am|\s*['’]m)\s+an?\s+", re.I)

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-']*")
_BREAK = re.compile(r"[,;:()\[\]{}|—–•·!?\n]|\.(?:\s|$)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+|\b\S+\.\S+/\S*")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_LABEL = re.compile(r"^[a-z0-9 /&+.-]{1,40}$")


@dataclass(frozen=True)
class Ref:
    """One occurrence the intent rests on. No words: where, and a digest."""
    source: str
    span: tuple
    sha: str


@dataclass(frozen=True)
class IntentConcept:
    id: str                 # skill_concepts.resolve() id, as the derivation has it
    registered: bool        # the registry knows it (False = a literal term)
    sources: tuple          # sorted positioning sources
    work_overlap: bool      # also used in paid work
    refs: tuple


@dataclass(frozen=True)
class DeclaredTitle:
    title: str              # validated title phrase, lowercased, level words dropped
    source: str             # header | summary | specialism
    span: tuple
    parts: tuple            # " / "-separated alternatives that end in a head;
                            # a specialism's grounded readings, longest first
    canonical: tuple        # ((part, corpus title or None), ...); () with no corpus


@dataclass(frozen=True)
class TrackIntent:
    concepts: tuple
    declared_titles: tuple
    work_only: tuple        # used at work, positioned nowhere
    other_claimed: tuple    # claimed elsewhere (skills list, stack line) only
    skills_groups: tuple    # one per skills-section line: its short label or None
    skills_order: tuple     # ((concept id, group, position in group), ...)
    provenance: tuple       # ((category, count), ...)
    sufficient: bool
    reason: str

    @property
    def ids(self):
        return frozenset(c.id for c in self.concepts)

    @property
    def titles(self):
        return frozenset(t.title for t in self.declared_titles)

    def concept(self, cid):
        return next((c for c in self.concepts if c.id == cid), None)

    def as_dict(self):
        return {
            "concepts": [{"id": c.id, "registered": c.registered,
                          "sources": list(c.sources),
                          "work_overlap": c.work_overlap,
                          "refs": [{"source": r.source, "span": list(r.span),
                                    "sha": r.sha} for r in c.refs]}
                         for c in self.concepts],
            "declared_titles": [{"title": t.title, "source": t.source,
                                 "span": list(t.span), "parts": list(t.parts),
                                 "canonical": [list(p) for p in t.canonical]}
                                for t in self.declared_titles],
            "work_only": list(self.work_only),
            "other_claimed": list(self.other_claimed),
            "skills_groups": list(self.skills_groups),
            "skills_order": [list(o) for o in self.skills_order],
            "provenance": dict(self.provenance),
            "sufficient": self.sufficient,
            "reason": self.reason,
        }


def _header_span(spans):
    """The block above the first heading, or None when the parser found no
    heading at all (then "above the first heading" is the whole document)."""
    if spans and spans[0][0] == se.OTHER and any(k != se.OTHER for k, *_ in spans):
        return spans[0][2], spans[0][3]
    return None


def _masks(text, header, name):
    """Spans no intent may come from: every email, URL and phone number, and
    inside the header every word of the candidate's name.

    SPANS of the original text, never a rewritten copy, so every offset the
    record keeps still points into the résumé as written. A masked word stops
    a title the way a comma does, which is what lets "Jane Doe | Mobile
    Engineer | jane@…" keep its title while losing the name and the address.
    (Masking whole contact-bearing lines was the first version: private, and
    it threw the title away with them.) The name is masked in the header only:
    "Julia" in a summary is a language."""
    out = [m.span() for rx in (_EMAIL, _URL, _PHONE) for m in rx.finditer(text)]
    if header:
        low = text.lower()
        for word in re.findall(r"[a-z]{2,}", str(name or "").lower()):
            rx = re.compile(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])")
            out.extend(m.span() for m in rx.finditer(low, *header))
    return out


def _masked(span, masks):
    return any(s < span[1] and span[0] < e for s, e in masks)


def _source(occ, header):
    """Which intent source one recorded occurrence is, if any."""
    section, shape = occ["section"], occ["shape"]
    if section == se.OTHER:
        start = occ["span"][0]
        return "header" if header and header[0] <= start < header[1] else None
    if section == se.SUMMARY:
        return "summary"
    if section == se.PROJECT:
        return "project" if shape == se.SUBSTANTIVE_USE else "project_stack"
    if section == se.SKILLS:
        return "skills"
    if section == se.WORK and shape in (se.INCIDENTAL_USE, se.SUBSTANTIVE_USE):
        return "work"
    return None


def _known_words(ids):
    words = set()
    for cid in itertools.chain(ids, skill_concepts.CONCEPTS):
        for alias in skill_concepts.aliases_for(cid):
            words.update(re.findall(r"[a-z0-9+#.\-]+", alias))
    return words


def _walk(tokens, i, text, masks, known, slot=None):
    """(kept, first, qualifiers) walking back from the head at tokens[i].
    Inside a self-identification — `slot` is where the words after its
    article start — any word qualifies. The walk never crosses the article:
    "a" and "an" are _STOP words."""
    word, start, _end, _dot = tokens[i]
    kept, first, qualifiers = [word.lower()], start, 0
    j = i - 1
    while j >= 0 and qualifiers < MAX_QUALIFIERS:
        prev, p_start, p_end, p_dot = tokens[j]
        gap = text[p_end:first]
        low = prev.lower()
        if p_dot or _BREAK.search(gap) or _masked((p_start, p_end), masks):
            break
        joint = gap.strip()
        if joint not in ("", "/", "&") or low in _STOP:
            break
        if title_gate._LEVEL.fullmatch(low):
            j -= 1
            continue
        if slot is None and not (any(c.isupper() for c in prev) or low in known):
            break
        sep = {"": " ", "&": " & "}.get(joint, "/" if gap == "/" else " / ")
        kept[:0] = [low, sep]
        first, qualifiers = p_start, qualifiers + 1
        j -= 1
    return kept, first, qualifiers


def _fills(tokens, slot, first):
    """Nothing but level words stands between the article and the title."""
    return all(title_gate._LEVEL.fullmatch(word.lower())
               for word, start, _end, _dot in tokens if slot <= start < first)


def _titles_in(text, lo, hi, masks, known, slots=()):
    """[(title, (start, end))] declared between lo and hi. Walks back from each
    job-title head over qualifiers that look like part of a title — written
    capitalised, or a known technology — and stops at grammar, self-praise, a
    masked word or a break. Level words ride along and are dropped.

    `slots` are self-identifications ("I am a …", summary only). A head after
    one may also take the words between its article and the head, whatever
    their case, but only when the title then fills that gap: "I am a backend
    automation engineer" reads "backend automation engineer"; "I am on a
    backend engineer team" still reads as today."""
    tokens = []
    for m in _TOKEN.finditer(text, lo, hi):
        word = m.group().rstrip(".-'")
        tokens.append((word, m.start(), m.start() + len(word),
                       m.group().endswith(".")))
    out = []
    for i, (word, start, end, _dot) in enumerate(tokens):
        if word.lower() not in ROLE_HEADS or _masked((start, end), masks):
            continue
        kept, first, qualifiers = _walk(tokens, i, text, masks, known)
        slot = max((s for s in slots if s <= start), default=None)
        if slot is not None:
            own = _walk(tokens, i, text, masks, known, slot)
            if own[2] and _fills(tokens, slot, own[1]):
                kept, first, qualifiers = own
        if qualifiers:
            out.append(("".join(kept), (first, end)))
    return out


_SPECIALISM = re.compile(r"[ \t]*\|([^|\n]*)")
_JOINER = re.compile(r"(?<=\S)[-_/]+(?=\S)")


def _words(text):
    """Lower-case words, a hyphen/underscore/slash joiner read as a space."""
    return [t.strip(".") for t in re.findall(r"[a-z0-9+#.]+", _JOINER.sub(" ", text.lower()))
            if t.strip(".")]


def _recurs(words, sections):
    n = len(words)
    return any(tokens[i:i + n] == words for tokens in sections
               for i in range(len(tokens) - n + 1))


def _specialisms(text, header_end, masks, known, spans, declared):
    """[(title, span, parts)]: the header's specialisms (DQ6-F1-A).

    "Software Engineer | Applied AI & Full-Stack": a declared header title,
    then on its own line "|" and a segment naming no role head of its own.
    Each "&"-separated part of that segment — capitalised or known words, no
    grammar, no break, no "/" — borrows the title's head, and so does each
    shorter reading ending the same way ("applied ai engineer", "ai
    engineer"). A reading is kept only when its words recur, in order, in this
    résumé's own summary or project text: the header alone, the skills list
    and the work history never ground one, and nothing outside this header
    relationship ever borrows a head. The title is the part as written (it
    names no role); the corpus judges the readings later, in track_search, as
    it judges any declared title."""
    body = [_words(text[s:e]) for kind, _n, s, e in spans if kind in (se.SUMMARY, se.PROJECT)]
    out = []
    for title in declared:
        found = _SPECIALISM.match(text, title.span[1], header_end)
        if not found or _masked(found.span(1), masks) or "/" in found.group(1):
            continue
        head = title.title.split()[-1]
        at = found.start(1)
        for piece in found.group(1).split("&"):
            lo = at + len(piece) - len(piece.lstrip())
            at += len(piece) + 1
            piece = piece.strip()
            words = [w.rstrip(".-'") for w in _TOKEN.findall(piece)]
            words = [w for w in words if not title_gate._LEVEL.fullmatch(w.lower())]
            if (not words or len(words) > MAX_QUALIFIERS or _BREAK.search(piece)
                    or any(w.lower() in ROLE_HEADS or w.lower() in _STOP for w in words)
                    or not all(any(c.isupper() for c in w) or w.lower() in known for w in words)):
                continue
            parts = tuple(" ".join(w.lower() for w in words[i:]) + " " + head
                          for i in range(len(words)) if _recurs(_words(" ".join(words[i:])), body))
            if parts:
                out.append((" ".join(w.lower() for w in words), (lo, lo + len(piece)), parts))
    return out


def _canonical(parts, titles, seniority):
    if titles is None:
        return ()
    import local_search
    return tuple((p, local_search.canonical(p, titles, seniority)) for p in parts)


def _skills_emphasis(text, spans, occurrences):
    """(labels, order): each skills-section line is a group; its label is the
    text before a colon when that is a short plain label, else None."""
    lines = []
    for kind, _entry, start, end in spans:
        if kind != se.SKILLS:
            continue
        at = start
        for line in text[start:end].splitlines(keepends=True):
            if line.strip():
                head, colon, _rest = line.partition(":")
                label = head.strip().lower() if colon else ""
                ok = _LABEL.match(label) and len(label.split()) <= 4
                lines.append((at, at + len(line), label if ok else None))
            at += len(line)
    placed = sorted((lo, cid) for cid, lo in occurrences)
    order, seen = [], set()
    for g, (lo, hi, _label) in enumerate(lines):
        here = [cid for at, cid in placed if lo <= at < hi]
        for pos, cid in enumerate(dict.fromkeys(here)):
            if cid not in seen:
                seen.add(cid)
                order.append((cid, g, pos))
    return tuple(label for _lo, _hi, label in lines), tuple(order)


def derive_track_intent(resume_text, derived, titles=None, seniority=()):
    """One résumé's TrackIntent. Pure: no model, no network, no environment,
    no sibling, no label; `derived` is read and never written.

    `titles` (a Counter of corpus titles) and `seniority` are optional and
    only fill DeclaredTitle.canonical — the declaration itself never depends
    on the corpus, so a low-reachability title is never lost.
    """
    text = str(resume_text or "")
    rows = derived.get("skill_importance")
    if not rows:
        return TrackIntent((), (), (), (), (), (), (), False,
                           "no evidence record in the derivation (a v1 "
                           "derivation, or no skills); nothing to project")

    spans = se.sections(text)
    header = _header_span(spans)
    masks = _masks(text, header, derived.get("candidate_name"))

    concepts, work_only, other = [], [], []
    skills_at = []
    for row in rows:
        refs, work = [], False
        for occ in row.get("occurrences") or ():
            if occ["status"] not in se.CLAIMED:
                continue
            source = _source(occ, header)
            if source is None or _masked(occ["span"], masks):
                continue
            if source == "work":
                work = True
            elif source == "skills":
                skills_at.append((row["id"], occ["span"][0]))
            refs.append(Ref(source, tuple(occ["span"]), occ["sha"]))
        positioned = sorted({r.source for r in refs} & set(POSITIONING))
        if positioned:
            concepts.append(IntentConcept(
                row["id"], row["id"] in skill_concepts.CONCEPTS,
                tuple(positioned), work,
                tuple(r for r in refs if r.source in POSITIONING)))
        elif work:
            work_only.append(row["id"])
        elif refs:
            other.append(row["id"])

    known = _known_words([r["id"] for r in rows])
    declared, seen = [], set()
    segments = [("header", *header)] if header else []
    segments += [("summary", s, e) for k, _n, s, e in spans if k == se.SUMMARY]
    for source, lo, hi in segments:
        slots = ([m.end() for m in _SELF_ID.finditer(text, lo, hi)]
                 if source == "summary" else ())
        for title, span in _titles_in(text, lo, hi, masks, known, slots):
            if title in seen:
                continue
            seen.add(title)
            parts = tuple(p for p in title.split(" / ")
                          if p.split()[-1] in ROLE_HEADS)
            declared.append(DeclaredTitle(title, source, span, parts,
                                          _canonical(parts, titles, seniority)))
        if source == "header":
            for title, span, parts in _specialisms(text, hi, masks, known, spans, declared):
                if title not in seen:
                    seen.add(title)
                    declared.append(DeclaredTitle(title, SPECIALISM, span, parts,
                                                  _canonical(parts, titles, seniority)))

    groups, order = _skills_emphasis(text, spans, skills_at)
    provenance = tuple(
        [(s, sum(1 for c in concepts if s in c.sources)) for s in POSITIONING]
        + [("work_overlap", sum(1 for c in concepts if c.work_overlap)),
           ("declared_header", sum(1 for t in declared if t.source == "header")),
           ("declared_summary", sum(1 for t in declared if t.source == "summary"))])

    if declared:
        sufficient, reason = True, f"{len(declared)} declared title(s)"
    elif len(concepts) >= MIN_CONCEPTS:
        sufficient, reason = True, f"{len(concepts)} positioned concept(s)"
    elif not concepts:
        sufficient, reason = False, "no header, summary or project positioning"
    else:
        sufficient, reason = False, (f"{len(concepts)} positioned concept(s), "
                                     f"fewer than {MIN_CONCEPTS}")
    return TrackIntent(tuple(concepts), tuple(declared), tuple(sorted(work_only)),
                       tuple(sorted(other)), groups, order, provenance,
                       sufficient, reason)


def for_sweep(items, titles=None, seniority=()):
    """One TrackIntent per résumé of a Multi-Track Sweep, in order.

    Two or three résumés only: a one-résumé upload is schema 1 and must never
    get an intent. Each is derived on its own — the signature has no way to
    hand one résumé another's text.
    """
    items = list(items)
    if not 2 <= len(items) <= 3:
        raise ValueError(f"track intents are for a Sweep of 2 to 3 résumés, "
                         f"got {len(items)}")
    return tuple(derive_track_intent(text, derived, titles, seniority)
                 for text, derived in items)


# ------------------------------------------------------------- diagnostics

def _jaccard(a, b):
    """None when both are empty: two résumés that position themselves for
    nothing are not "identical intent", and 1.0 would read as exactly that."""
    return round(len(a & b) / len(a | b), 3) if a | b else None


def compare(intents):
    """Overlap between the tracks of one Sweep, {track id: TrackIntent}.
    Measures only: no intent is changed, subtracted or reordered."""
    names = list(intents)
    return {
        "pairs": {f"{a}|{b}": {
            "concepts": _jaccard(intents[a].ids, intents[b].ids),
            "titles": _jaccard(intents[a].titles, intents[b].titles)}
            for a, b in itertools.combinations(names, 2)},
        "unique": {n: sorted(intents[n].ids - frozenset().union(
            *(intents[o].ids for o in names if o != n))) for n in names},
        "sufficient": {n: intents[n].sufficient for n in names},
        "provenance": {n: dict(intents[n].provenance) for n in names},
    }


def admits(intent, title):
    """Does this intent claim a job title? A declared title inside it, or an
    intent concept named in it (registry-aware: "react" does not fire inside
    "react native", exactly as scoring counts it)."""
    low = str(title or "").lower()
    if any(p in low for t in intent.declared_titles for p in t.parts):
        return True
    return any(skill_concepts.own_spans(c, low) for c in
               skill_concepts.from_weights({c.id: 1 for c in intent.concepts}))


def relevance_contract(title, intents, floor_hints):
    """DQ2c's free-row contract, recorded in DQ2a and implemented nowhere.

    ACQUISITION: the generic floor OR any track's intent — fetched once.
    RELEVANCE: the tracks whose intent admits the title. Only when no intent
    does may the floor make every track relevant (today's behaviour). The
    floor preserves coverage; it must not erase track identity.
    `floor_hints` are matched as scraper.title_admits matches them.
    """
    low = str(title or "").lower()
    floor = any(h in low for h in floor_hints)
    matches = [n for n, i in intents.items() if admits(i, title)]
    if matches:
        relevant, fallback = matches, False
    elif floor:
        relevant, fallback = list(intents), True
    else:
        relevant, fallback = [], False
    return {"floor_admits": floor, "acquire": floor or bool(matches),
            "intent_matches": matches, "relevant": relevant,
            "fallback": fallback}
