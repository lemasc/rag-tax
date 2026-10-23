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
# An item line the OCR did not mark (Ins91 writes "11." plain and "**11.2 เป็นดอกเบี้ย...** ..." bold run-in where Ins90 has
# headings): a boundary only when its number counts up, so a figure ("1.5 เท่า") or a reference does not cut.
ITEM_LINE = re.compile(r"^\**\s*(\d+)(?:\\?\.(\d+))?\\?\.?\s+\S")  # Typhoon sometimes escapes the dot: "1\\."
TABLE = re.compile(r"^(?:#{1,6}\s*)?\**\s*(ตารางที่\s*\d+)\s*\**\s*$")  # "ตารางที่ 2": a printed table, its own unit


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
    else:  # no number says nothing about depth, and `#` is as random as bold: hang it on the nearest ข้อ
        level = BOLD_LEVEL
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


def _item_line(line: str, number: int | None, sub: int) -> tuple[int, str, int, int] | None:
    """(level, label, number, sub) for an unmarked item line that continues the count: "N." after item N-1 (or as the first
    item under a ข้อ), "N.k" after N.(k-1) of the current item N."""
    m = ITEM_LINE.match(line.strip())
    if m is None:
        return None
    n, k = int(m[1]), int(m[2]) if m[2] else None
    label = " ".join(line.replace("**", "").replace("\\.", ".").split())[:70]
    if k is None and n == (number or 0) + 1:
        return NUMBERED_LEVEL, label, n, 0
    if k is not None and n == number and k == sub + 1:
        return DECIMAL_LEVEL, label, n, k
    return None


def split_guide(doc_id: str, text: str, unit_type: str = "guide") -> tuple[str, list[Unit]]:
    """Return (preamble, units): one unit per heading section of a Typhoon-OCR filling guide (ภ.ง.ด.90/91/94).

    Boundaries are the guide's own structure, not only what the OCR marked: `#` headings and lines that are only bold, an
    item line whose number counts up ("11.", "11.2 ...") whether it is marked or not, and a "ตารางที่ N" line, which starts
    a unit of its own named after the table's title. The OCR marks headings differently in each guide (Ins90 has "11.1"
    as a heading, Ins91 as a plain line), so cutting at the numbering is what makes the three guides' units line up. The heading trail ("วิธีกรอก... > ข้อ 3 ... > 2. เงินส่วนแบ่ง...") is
    the unit's `section`, the section's own heading its `label`. A section under GUIDE_MIN_CHARS (a heading followed
    at once by a sub-heading, a one-line item) takes in the section after it, whose heading stays in the text as a line.
    `unit_type` names the units: "guide", or "section" for a page whose headings were inserted (`text.insert_headings`);
    unmarked item lines are boundaries in a guide only (a web page's numbered steps are a list, not sections). A table
    is never joined to the short section before it.
    """
    secs: list[dict] = []  # {"section", "label", "head", "lines"}
    trail: list[tuple[int, str]] = []
    pre: list[str] = []
    number, sub = None, 0  # the item count under the current ข้อ
    lines = text.split("\n")
    for i, line in enumerate(lines):
        body: list[str] = []  # an unmarked item line is text as well as a boundary: it stays in its unit
        if m := TABLE.match(line.strip()):
            title = next((ln.strip() for ln in lines[i + 1 :] if ln.strip() and not ln.lstrip().startswith(("|", "<"))), "")
            h = (ITEM_LEVEL, f"{m[1]} {title}"[:70].strip())
            number, sub = None, 0
        elif h := _heading(line):
            if h[0] == ITEM_LEVEL:
                number, sub = None, 0
            elif im := LABEL_NUMBER.match(h[1] + " "):
                parts = [int(x) for x in im[1].split(".")]
                number, sub = parts[0], parts[1] if len(parts) > 1 else 0
        elif unit_type == "guide" and (it := _item_line(line, number, sub)):
            h, number, sub, body = it[:2], it[2], it[3], [line]
        else:
            (secs[-1]["lines"] if secs else pre).append(line)
            continue
        while trail and (trail[-1][0] >= h[0] or h[0] == BOLD_LEVEL and trail[-1][0] > ITEM_LEVEL):  # unnumbered: under a ข้อ, not an item
            trail.pop()
        secs.append(dict(section=" > ".join(t for _, t in trail) or None, label=h[1], head="" if body else line.strip(), lines=body,
                         table=bool(TABLE.match(line.strip()))))
        trail.append(h)

    merged: list[dict] = []
    for s in _split_decimal_items(secs):
        if merged and len("\n".join(merged[-1]["lines"]).strip()) < GUIDE_MIN_CHARS and not s.get("table"):
            merged[-1]["lines"] += [h for h in [s["head"]] if h] + s["lines"]
        else:
            merged.append(dict(s, lines=list(s["lines"])))
    if len(merged) > 1 and len("\n".join(merged[-1]["lines"]).strip()) < GUIDE_MIN_CHARS:
        last = merged.pop()
        merged[-1]["lines"] += [h for h in [last["head"]] if h] + last["lines"]

    units = [
        Unit(unit_id=f"{doc_id}#{i:03d}", doc_id=doc_id, type=unit_type, label=s["label"], section=s["section"],
             text=re.sub(r"\n{3,}", "\n\n", "\n".join(s["lines"])).strip())
        for i, s in enumerate(merged, 1)
    ]
    return "\n".join(pre).strip(), units


# ---------------------------------------------------------------- legal instruments ("ข้อ N" / "มาตรา N" / "(N)")

# The HTML gives each ข้อ and (N) item its own line (extract.html_text), so a heading is a number counting up at the start of
# a line. Text without lines (an older extraction, one OCR page) falls back to the same numbers inside a line, told from a
# reference ("ตามข้อ 2", "มาตรา 40 (7)") by following no reference word and, for (N), no digit.
INSTRUMENT_HEADS = ("ข้อ", "มาตรา")
LINE_HEADS = {w: re.compile(rf"(?m)^[ \t]*[“\"]?{w}[ \t]*(\d+)(?=\s)") for w in INSTRUMENT_HEADS}
FLAT_HEADS = {w: re.compile(rf"(?:(?<=[\s“\"])|^){w}\s*(\d+)(?=\s)") for w in INSTRUMENT_HEADS}
LINE_ITEM = re.compile(r"(?m)^[ \t]*[“\"]?\((\d+)\)(?=\s)")  # an amendment quotes its new items: "(1) ...
FLAT_ITEM = re.compile(r"(?:(?<=[\s“\"])|^)\((\d+)\)(?=\s)")
REFERENCE = re.compile(r"(?:ตาม|ใน|ของ|แห่ง|และ|หรือ|ตั้งแต่|ถึง|ภายใต้|ดู|(?:^|\s)(?:เว้นแต่|ยกเว้น|เฉพาะ))\s*$")  # "ให้ยกเว้น ข้อ 3" is not one
INSTRUMENT_MIN_HEADS = 2
INSTRUMENT_MIN_CHARS = 300  # a lead-in shorter than this ("ข้อ 2 ให้ยกเว้นเงินได้ดังต่อไปนี้") joins the first item after it
INSTRUMENT_SPLIT_CHARS = 1500  # about 450 bge-m3 tokens at 3.3 chars per token; a longer heading is cut at its (N) items

# The closing: the signature (กฎกระทรวง, ประกาศ, คำสั่ง: "ให้ไว้/ประกาศ/สั่ง ณ วันที่ ..."; พ.ร.ฎ.: "ผู้รับสนองพระบรมราชโองการ"), the
# name and title lines under it, then optionally a หมายเหตุ (the reason for the instrument) and attachments (forms, examples).
SIGNATURE = re.compile(r"(?m)^[ \t]*(?:(?:ประกาศ|สั่ง|ให้ไว้)[ \t]*ณ[ \t]*วันที่|ผู้รับสนอง)[^\n]*")
SIGNER_TITLE = re.compile(r"อธิบดี|รัฐมนตรี|ปลัดกระทรวง|ผู้ช่วย|แทน")
REMARK = re.compile(r"(?m)^[ \t]*หมายเหตุ")
ANNEX = re.compile(r"(?m)^[ \t]*(?:เอกสารแนบ|ตัวอย่าง|คำขอ|แบบ)[^\n]*|^[^\n]*>>[ \t]*$")
ANNEX_POINTER = 80  # a line this short that ends in ">>" ("แบบ ล.ย.02 >>") points at a form the page does not carry
ANNEX_EXAMPLE = re.compile(r"(?m)^[ \t]*ตัวอย่างที่\s*\d+[^\n]*")
SIGNATURE_LINES = 5  # name lines between the date and the title


def _in_sequence(text: str, pattern: re.Pattern, max_gap: int = 1, lines: bool = True, after_digit: bool = True) -> list[tuple[int, int]]:
    """(offset, number) of the matches that count up from 1. A consolidated text can skip a repealed item: a gap of up
    to `max_gap` is taken right after the `)` that closes an amendment note. Matches inside a line (`lines` false) must
    also follow no reference word, and for `(N)` (`after_digit` false) no digit."""
    found, last = [], 0
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 12) : m.start()].rstrip()
        gap = int(m[1]) - last
        if not (gap == 1 or 1 < gap <= max_gap and before.endswith(")")):
            continue
        if not lines and (REFERENCE.search(before) or (before[-1:].isdigit() and not after_digit)):
            continue
        found.append((m.start(), last := int(m[1])))
    return found


def _heads(text: str) -> tuple[str, list[tuple[int, int]]]:
    """(word, [(offset, number)]) of the heading kind that counts up furthest, at line starts if there are any."""
    best: tuple[str, list[tuple[int, int]]] = ("", [])
    for w in INSTRUMENT_HEADS:
        found = _in_sequence(text, LINE_HEADS[w])
        if len(found) < INSTRUMENT_MIN_HEADS:
            found = _in_sequence(text, FLAT_HEADS[w], lines=False)
        if len(found) > len(best[1]):
            best = (w, found)
    return best


def _items(text: str) -> list[tuple[int, int]]:
    found = _in_sequence(text, LINE_ITEM, max_gap=3)
    return found if len(found) >= 2 else _in_sequence(text, FLAT_ITEM, max_gap=3, lines=False, after_digit=False)


def _cut_items(label: str, section: str | None, text: str, depth: int = 0) -> list[tuple[str, str | None, str]]:
    """[(label, section, text)]: the heading whole, or its lead-in and (N) items when it is long and has them. An item
    that is still long and holds a list of its own (an amendment quotes a whole new list) is cut once more."""
    items = _items(text)
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


def _annex_units(annex: str) -> list[tuple[str, str, str]]:
    """One `annex` unit, or one per worked example ("ตัวอย่างที่ 3") when the attachment has several; what comes before the
    first example (the attachment's title) goes with it, and each unit is named after its own first line."""
    examples = [m.start() for m in ANNEX_EXAMPLE.finditer(annex)]
    if len(examples) < 2:
        return [(annex.split("\n", 1)[0].strip()[:60], "annex", annex)]
    cuts = [0] + examples[1:] + [len(annex)]
    return [(ANNEX_EXAMPLE.search(annex[a:b]).group().strip()[:60], "annex", annex[a:b].strip()) for a, b in zip(cuts, cuts[1:])]


def _closing(text: str, after: int) -> tuple[int, list[tuple[str, str, str]]]:
    """(end of the last heading's text, [(label, type, text)] of what follows the signature). The signature is the first
    one after `after` (the first heading); the last heading keeps it with the name and title lines under it, and the
    separator lines and gazette reference that may follow. A หมายเหตุ before the first attachment is a unit of its own,
    and the attachments, if there is more than a pointer to them, `annex` units (one, or one per worked example); with neither, everything stays with the last heading."""
    sig = next((m for m in SIGNATURE.finditer(text) if m.start() >= after), None)
    if sig is None:
        return len(text), []
    end, titled, seen = sig.end(), False, 0
    for ln in re.finditer(r"[^\n]*\S[^\n]*", text[sig.end():]):
        line = ln.group().strip()
        if REMARK.match(line) or ANNEX.match(line) or seen >= SIGNATURE_LINES or (titled and not SIGNER_TITLE.search(line)):
            break
        end, seen, titled = sig.end() + ln.end(), seen + 1, bool(SIGNER_TITLE.search(line))
    annex = next((m for m in ANNEX.finditer(text, end) if not (m.group().strip().endswith(">>") and len(m.group().strip()) < ANNEX_POINTER)), None)
    if annex and len(text[annex.start() :].strip()) < INSTRUMENT_MIN_CHARS:  # a pointer ("เอกสารแนบ", "แบบ ล.ย.02 >>"), not the attachment
        annex = None
    remark = REMARK.search(text, end, annex.start() if annex else len(text))
    cuts = [m.start() for m in (remark, annex) if m]
    if not cuts:
        return len(text), []
    parts = []
    if remark:
        parts.append(("หมายเหตุ", "clause", text[remark.start() : annex.start() if annex else len(text)].strip()))
    if annex:
        parts += _annex_units(text[annex.start() :].strip())
    return min(cuts), parts


def split_instrument(doc_id: str, text: str) -> tuple[str, list[Unit]]:
    """Return (preamble, units) for a กฎกระทรวง, ประกาศ, คำสั่ง or พ.ร.ฎ.: one unit per `ข้อ N` (or `มาตรา N`, whichever counts
    up further), and a heading over INSTRUMENT_SPLIT_CHARS is cut at its `(N)` items, each with the lead-in in its section.
    What follows the signature is cut off the last heading (see `_closing`). Text is kept verbatim. Fewer than
    INSTRUMENT_MIN_HEADS headings means prose (a ruling): no units, the chunker windows it."""
    word, heads = _heads(text)
    if len(heads) < INSTRUMENT_MIN_HEADS:
        return text, []
    body_end, tail = _closing(text, heads[0][0])
    body = text[:body_end]
    word, heads = _heads(body)
    if len(heads) < INSTRUMENT_MIN_HEADS:
        return text, []
    bounds = [p for p, _ in heads] + [len(body)]
    units = []
    for (start, n), end in zip(heads, bounds[1:]):
        for label, section, part in _cut_items(f"{word} {n}", None, body[start:end].strip()):
            units.append(Unit(f"{doc_id}#{len(units) + 1:03d}", doc_id, "clause", label, part, section=section))
    for label, kind, part in tail:
        units.append(Unit(f"{doc_id}#{len(units) + 1:03d}", doc_id, kind, label, part))
    return body[: heads[0][0]].strip(), units
