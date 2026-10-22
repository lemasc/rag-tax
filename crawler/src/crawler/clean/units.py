"""Structural units for the two document types with an unambiguous boundary: FAQ items and statute sections.

A unit is the smallest piece a consumer should never cut across. Text is kept verbatim (after `normalize`);
anything we recognise but do not remove (cross-reference and amendment notes, missing markers) is reported in
`flags`/`notes` so the review notebook can count it. Splitters take normalised text and never raise on odd input:
they flag instead.
"""

import re
from dataclasses import asdict, dataclass, field


@dataclass
class Unit:
    unit_id: str
    doc_id: str
    type: str  # faq | statute
    label: str  # "Q12", "ชื่อเรื่อง 3", "มาตรา 47 ทวิ"
    text: str
    section: str | None = None  # FAQ section heading ("3. การบันทึกเงินได้") when the page has them
    title: str | None = None  # FAQ item title (ร้อยเรื่องลดหย่อน format)
    flags: list[str] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)  # statute: [{"type": see|amendment|repeal, "text": ...}]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- FAQ

# Clear Cut pages: "Q1 : ...", "A1 : ...". The marker is sometimes split over two lines ("Q8" / ":text") and
# sometimes loses its "Q" in extraction ("2 : text"), so markers are matched against the expected sequence.
Q_MARK = re.compile(r"^Q\s*(\d+)\s*(?::\s*(.*)|$)")
A_MARK = re.compile(r"^A\s*(\d+)\s*(?::\s*(.*)|$)")
BARE_Q = re.compile(r"^(\d+)\s*:\s*(.*)$")
# ร้อยเรื่องลดหย่อน pages: "3. ชื่อเรื่อง : ...", "คำถาม : ...", "คำตอบ : ..." (spacing and dots vary: "6 .ชื่อเรื่อง", "1. .ชื่อเรื่อง")
TITLE_MARK = re.compile(r"^(\d+)\s*[.\s]*ชื่อเรื่อง\s*:?\s*(.*)$")
TH_Q = re.compile(r"^คำถาม\s*:")
ANSWER = re.compile(r"(?m)^คำตอบ|คำตอบ\s*:")


def split_faq(doc_id: str, text: str) -> tuple[str, list[Unit]]:
    """Return (preamble, units). The preamble is everything before the first item (page title, category)."""
    lines = text.split("\n")
    if any(Q_MARK.match(ln) for ln in lines):
        return _split_clearcut(doc_id, lines)
    if any(TH_Q.match(ln) for ln in lines):
        return _split_roi_rueang(doc_id, lines)
    return text, []


def _split_clearcut(doc_id: str, lines: list[str]) -> tuple[str, list[Unit]]:
    starts: list[tuple[int, int, list[str]]] = []  # (line index, Q number, flags)
    last_q, a_seen = 0, True
    for i, ln in enumerate(lines):
        if m := Q_MARK.match(ln):
            n = int(m.group(1))
        elif (m := BARE_Q.match(ln)) and a_seen and int(m.group(1)) == last_q + 1:
            n = last_q + 1  # "2 : text": the Q was lost in extraction
            starts.append((i, n, ["marker_q_lost"]))
            last_q, a_seen = n, False
            continue
        elif (m := A_MARK.match(ln)) and starts and int(m.group(1)) == last_q:
            a_seen = True
            continue
        else:
            continue
        if not (n == last_q + 1 or n == 1 or n > last_q):
            continue  # a number going backwards that is not a section restart: ordinary text
        flags = [] if n in (1, last_q + 1) else ["number_gap"]
        starts.append((i, n, flags))
        last_q, a_seen = n, False

    bounds = [s[0] for s in starts] + [len(lines)]
    preamble_lines = lines[: bounds[0]]
    units: list[Unit] = []
    section_no = 0
    section = None
    # the heading of the first section sits in the preamble: "1. การลงทะเบียน"
    for j, ln in enumerate(preamble_lines):
        if re.match(r"^1\s*\.\s*\S", ln):
            section_no, section = 1, " ".join(preamble_lines[j:])
            preamble_lines = preamble_lines[:j]
            break
    for k, (i, n, flags) in enumerate(starts):
        body = lines[i : bounds[k + 1]]
        flags = list(flags)
        if n == 1 and units:  # a new section starts: its heading is the tail of the previous item
            prev_lines = units[-1].text.split("\n")
            if section_no:  # numbered headings ("3. การบันทึกเงินได้"): look for the next number near the end
                want = section_no + 1
                cut = next((r for r in range(len(prev_lines) - 1, 0, -1) if re.match(rf"^{want}\s*\.\s*\S", prev_lines[r])), None)
                if cut is not None and len(prev_lines) - cut <= 6:
                    section, section_no = " ".join(prev_lines[cut:]), want
                    units[-1].text = "\n".join(prev_lines[:cut]).rstrip()
                else:
                    flags.append("section_unresolved")
            elif len(prev_lines) > 1 and len(prev_lines[-1]) <= 40 and not A_MARK.match(prev_lines[-1]):
                # unnumbered headings ("คู่สมรส"): guess the last short line; reviewed by hand in the QA notebook
                section = prev_lines[-1]
                units[-1].text = "\n".join(prev_lines[:-1]).rstrip()
                flags.append("section_guessed")
            else:
                flags.append("section_unresolved")
        if not _has_answer(body, n):
            flags.append("no_answer")
        label = f"Q{n}"
        units.append(Unit(f"{doc_id}#{k + 1:03d}", doc_id, "faq", label, "\n".join(body).rstrip(), section=section, flags=flags))
    return "\n".join(preamble_lines).strip(), units


def _has_answer(body: list[str], n: int) -> bool:
    return any((m := A_MARK.match(ln)) and int(m.group(1)) == n for ln in body)


def _split_roi_rueang(doc_id: str, lines: list[str]) -> tuple[str, list[Unit]]:
    # Each คำถาม opens an item. A ชื่อเรื่อง line between the previous question and this one is its title; with none
    # (a second question under the same title, or a title the source skips) it inherits the previous title.
    q_idx = [i for i, ln in enumerate(lines) if TH_Q.match(ln)]
    starts: list[tuple[int, str | None, int | None, bool]] = []  # (start line, title, title number, inherited)
    for qi, i in enumerate(q_idx):
        floor = q_idx[qi - 1] if qi else -1
        t = next(((j, TITLE_MARK.match(lines[j])) for j in range(floor + 1, i) if TITLE_MARK.match(lines[j])), None)
        if t:
            j, m = t
            starts.append((j, m.group(2).strip(), int(m.group(1)), False))
        else:
            prev = starts[-1] if starts else (i, None, None, False)
            starts.append((i, prev[1], prev[2], True))
    bounds = [s[0] for s in starts] + [len(lines)]
    units = []
    seen: dict[int | None, int] = {}
    for k, (i, title, num, inherited) in enumerate(starts):
        body = lines[i : bounds[k + 1]]
        flags = ["title_inherited"] if inherited else []
        if title is None:
            flags.append("title_missing")
        n_a = len(ANSWER.findall("\n".join(body)))  # the colon is sometimes missing, or the answer is inline
        if n_a != 1:
            flags.append("no_answer" if n_a == 0 else "multiple_answers")
        seen[num] = seen.get(num, 0) + 1
        label = f"ชื่อเรื่อง {num}" + (f" ({seen[num]})" if seen[num] > 1 else "") if num else f"คำถามที่ {k + 1}"
        units.append(Unit(f"{doc_id}#{k + 1:03d}", doc_id, "faq", label, "\n".join(body).rstrip(), title=title, flags=flags))
    return "\n".join(lines[: bounds[0]]).strip(), units


# ---------------------------------------------------------------- statute

SUFFIXES = ["ทวิ", "ตรี", "จัตวา", "เบญจ", "ฉ", "สัตต", "อัฏฐ", "นว", "ทศ"]
SECTION = re.compile(rf"^มาตรา\s*(\d+)(?!\d)(?:\s+({'|'.join(SUFFIXES)})(?=\s|$))?")
NOTE = re.compile(r"^(?:\(\d+\)\s*)?\(\s*(ดู|พระราช|ประกาศ|แก้ไข|ยกเลิก)")


def section_label(m: re.Match) -> str:
    return f"มาตรา {m.group(1)}" + (f" {m.group(2)}" if m.group(2) else "")


def _rank(m: re.Match) -> tuple[int, int]:
    return int(m.group(1)), SUFFIXES.index(m.group(2)) + 1 if m.group(2) else 0


def note_type(line: str) -> str | None:
    """Classify a whole-line parenthetical annotation, or None if the line is ordinary text."""
    if not (NOTE.match(line) and line.endswith(")")):
        return None
    if re.search(r"\(\s*ยกเลิก|ยกเลิกโดย|ยกเลิกตาม", line):
        return "repeal"
    return "see" if re.match(r"^\(\s*ดู", line) else "amendment"


def split_statute(doc_id: str, text: str) -> tuple[str, list[Unit]]:
    """One unit per มาตรา. A heading must come after the previous one in (number, suffix) order, so a
    cross-reference that happens to start a line is not taken for a section."""
    lines = text.split("\n")
    heads, last = [], (0, 0)
    for i, ln in enumerate(lines):
        if (m := SECTION.match(ln)) and _rank(m) > last:
            heads.append((i, section_label(m)))
            last = _rank(m)
    if not heads:
        return text, []
    bounds = [h[0] for h in heads] + [len(lines)]
    units = []
    for k, (i, label) in enumerate(heads):
        body = lines[i : bounds[k + 1]]
        notes = [{"type": t, "text": ln} for ln in body if (t := note_type(ln))]
        flags = ["has_repeal_note"] if any(n["type"] == "repeal" for n in notes) else []
        units.append(Unit(f"{doc_id}#{k + 1:03d}", doc_id, "statute", label, "\n".join(body).rstrip(), flags=flags, notes=notes))
    return "\n".join(lines[: bounds[0]]).strip(), units


# ---------------------------------------------------------------- filling guides (OCR with markdown headings)

HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
BOLD_HEADING = re.compile(r"^\*\*([^*\n]{2,100})\*\*$")  # a line that is only bold: "**ข้อ 4 รายการเงินได้พึงประเมินตามมาตรา 40 (5)**"
BOLD_LEVEL = 7  # below every `#` level, so a bold heading is a child of the heading above it
ITEM = re.compile(r"ข้อ\s*\d+")
ITEM_LEVEL = 2
NUMBERED = re.compile(r"\d+\.\s")
NUMBERED_LEVEL = 3
DECIMAL = re.compile(r"\d+\.\d+")
DECIMAL_LEVEL = 4
GUIDE_MIN_CHARS = 300  # a section shorter than this is joined with the one after it
GUIDE_SPLIT_CHARS = 3000  # a section longer than this is cut at its decimal items ("7.1", "7.2")
LABEL_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")


def _heading(line: str) -> tuple[int, str] | None:
    if m := HEADING.match(line):
        level, title = len(m[1]), m[2]
    elif m := BOLD_HEADING.match(line):
        level, title = BOLD_LEVEL, m[1]
    else:
        return None
    title = re.sub(r"^[•\s]+|\*\*", "", title).strip()
    if ITEM.match(title):  # the OCR gives "ข้อ N" and "7." lines `#`, `##`, `###` or bold at random: one level for each kind
        level = ITEM_LEVEL
    elif DECIMAL.match(title):
        level = DECIMAL_LEVEL
    elif NUMBERED.match(title):
        level = NUMBERED_LEVEL
    return level, title


def _split_decimal_items(secs: list[dict]) -> list[dict]:
    """Cut a long section at its decimal items. A section numbered "7." only breaks at "7.N" lines ("7.1 การลดหย่อน...",
    "7.2 ..."), so a figure like "1.5 เท่า" at the start of a line does not; a section whose label has no number is left
    whole. The text before the first item stays with the section, each item becomes a child named after its number
    and first words."""
    out = []
    for s in secs:
        body = "\n".join(s["lines"])
        m = LABEL_NUMBER.match(s["label"] + " ")
        if len(body) <= GUIDE_SPLIT_CHARS or not m:
            out.append(s)
            continue
        item = re.compile(rf"^({re.escape(m[1])}\.\d+(?:\.\d+)*)\.?\s+(.*)$")
        cur = dict(s, lines=[])
        parent = " > ".join(filter(None, [s["section"], s["label"]]))
        for line in s["lines"]:
            if im := item.match(line.strip()):
                out.append(cur)
                cur = dict(section=parent, label=f"{im[1]} {im[2][:60]}".strip(), head=s["head"], lines=[line])
            else:
                cur["lines"].append(line)
        out.append(cur)
    return out


def split_guide(doc_id: str, text: str) -> tuple[str, list[Unit]]:
    """Return (preamble, units): one unit per heading section of a Typhoon-OCR filling guide (ภ.ง.ด.90/91/94).

    Boundaries are `#` headings and lines that are only bold; the OCR marks few of them (8-17 per guide), so a section
    can still be long and the chunker windows it. The heading trail ("วิธีกรอก... > ข้อ 3 ... > 2. เงินส่วนแบ่ง...") is
    the unit's `section`, the section's own heading its `label`. A section under GUIDE_MIN_CHARS (a heading followed
    at once by a sub-heading, a one-line item) takes in the section after it, whose heading stays in the text as a line.
    """
    secs: list[dict] = []  # {"section", "label", "head", "lines"}
    trail: list[tuple[int, str]] = []
    pre: list[str] = []
    for line in text.split("\n"):
        h = _heading(line)
        if h is None:
            (secs[-1]["lines"] if secs else pre).append(line)
            continue
        while trail and trail[-1][0] >= h[0]:
            trail.pop()
        secs.append(dict(section=" > ".join(t for _, t in trail) or None, label=h[1], head=line.strip(), lines=[]))
        trail.append(h)

    merged: list[dict] = []
    for s in _split_decimal_items(secs):
        if merged and len("\n".join(merged[-1]["lines"]).strip()) < GUIDE_MIN_CHARS:
            merged[-1]["lines"] += [s["head"], *s["lines"]]
        else:
            merged.append(dict(s, lines=list(s["lines"])))
    if len(merged) > 1 and len("\n".join(merged[-1]["lines"]).strip()) < GUIDE_MIN_CHARS:
        last = merged.pop()
        merged[-1]["lines"] += [last["head"], *last["lines"]]

    units = [
        Unit(unit_id=f"{doc_id}#{i:03d}", doc_id=doc_id, type="guide", label=s["label"], section=s["section"],
             text=re.sub(r"\n{3,}", "\n\n", "\n".join(s["lines"])).strip())
        for i, s in enumerate(merged, 1)
    ]
    return "\n".join(pre).strip(), units


# ---------------------------------------------------------------- legal instruments (flat text, "ข้อ N" / "มาตรา N" / "(N)")

INSTRUMENT_HEADS = {"ข้อ": re.compile(r"(?:(?<=[\s“\"])|^)ข้อ\s*(\d+)(?=\s)"), "มาตรา": re.compile(r"(?:(?<=[\s“\"])|^)มาตรา\s*(\d+)(?=\s)")}
PAREN_ITEM = re.compile(r"(?:(?<=[\s“\"])|^)\((\d+)\)(?=\s)")  # an amendment quotes its new items: "(1) ...
REFERENCE = re.compile(r"(?:ตาม|ใน|ของ|แห่ง|และ|หรือ|ตั้งแต่|ถึง|ภายใต้|ดู|(?:^|\s)(?:เว้นแต่|ยกเว้น|เฉพาะ))\s*$")  # "ตาม ข้อ 2" is a reference, not a heading; "ให้ยกเว้น ข้อ 3" is not
INSTRUMENT_MIN_HEADS = 2
INSTRUMENT_MIN_CHARS = 300  # a lead-in shorter than this ("ข้อ 2 ให้ยกเว้นเงินได้ดังต่อไปนี้") joins the first item after it
INSTRUMENT_SPLIT_CHARS = 1500  # about 450 bge-m3 tokens at 3.3 chars per token; a longer heading is cut at its (N) items


def _in_sequence(text: str, pattern: re.Pattern, max_gap: int = 1, after_digit: bool = True) -> list[tuple[int, int]]:
    """(offset, number) of the matches that count up from 1. Instruments are flat text, so a heading is told from a
    reference ("ตามข้อ 2 ข้อ 3 และข้อ 4", "มาตรา 40 (7)") by being the next number and not following a reference word
    or, for `(N)` (`after_digit` false), a digit. A consolidated text can skip a repealed item: a gap of up to `max_gap` is taken right after the `)`
    that closes an amendment note."""
    found, last = [], 0
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 12) : m.start()].rstrip()
        gap = int(m[1]) - last
        if REFERENCE.search(before) or (before[-1:].isdigit() and not after_digit) or not (gap == 1 or 1 < gap <= max_gap and before.endswith(")")):
            continue
        found.append((m.start(), last := int(m[1])))
    return found


def _cut_items(label: str, section: str | None, text: str, depth: int = 0) -> list[tuple[str, str | None, str]]:
    """[(label, section, text)]: the heading whole, or its lead-in and (N) items when it is long and has them. An item
    that is still long and holds a list of its own (an amendment quotes a whole new list) is cut once more."""
    items = _in_sequence(text, PAREN_ITEM, max_gap=3, after_digit=False)
    if len(text) <= INSTRUMENT_SPLIT_CHARS or len(items) < 2 or depth > 1:
        return [(label, section, text)]
    lead = text[: items[0][0]].strip()
    trail = " ".join(filter(None, [section, " ".join(lead[:80].split())]))  # the lead-in starts with its own label
    bounds = [p for p, _ in items] + [len(text)]
    parts = []
    for (a, n), b in zip(items, bounds[1:]):
        parts += _cut_items(f"({n})", trail, text[a:b].strip(), depth + 1)
    if len(lead) < INSTRUMENT_MIN_CHARS:
        parts[0] = (parts[0][0], parts[0][1], lead + "\n" + parts[0][2])
    else:
        parts.insert(0, (label, section, lead))
    return parts


def split_instrument(doc_id: str, text: str) -> tuple[str, list[Unit]]:
    """Return (preamble, units) for a กฎกระทรวง, ประกาศ or คำสั่ง: one unit per `ข้อ N` (or `มาตรา N`, whichever counts up
    further), and a heading over INSTRUMENT_SPLIT_CHARS is cut at its `(N)` items, each with the lead-in in its section.
    Text is kept verbatim. Fewer than INSTRUMENT_MIN_HEADS headings means prose (a ruling): no units, the chunker windows it."""
    heads = max((_in_sequence(text, p) for p in INSTRUMENT_HEADS.values()), key=len)
    if len(heads) < INSTRUMENT_MIN_HEADS:
        return text, []
    word = next(w for w, p in INSTRUMENT_HEADS.items() if _in_sequence(text, p) == heads)
    bounds = [p for p, _ in heads] + [len(text)]
    units = []
    for (start, n), end in zip(heads, bounds[1:]):
        for label, section, body in _cut_items(f"{word} {n}", None, text[start:end].strip()):
            units.append(Unit(f"{doc_id}#{len(units) + 1:03d}", doc_id, "clause", label, body, section=section))
    return text[: heads[0][0]].strip(), units
