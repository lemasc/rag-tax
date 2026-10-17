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
