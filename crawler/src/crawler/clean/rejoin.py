"""Rejoin Thai words split by a stray space or line break, and repair pdftotext's misplaced tone marks.

A break between two Thai characters is joined only when it cannot be a word boundary:
- "mark": the right side starts with a character that never starts a syllable (a following vowel, tone mark or
  other combining mark: "ได ้", "ชือ\\n่"), or the left side ends with a leading vowel ("ใ ช้").
- "fragment": one side's edge, segmented with newmm, is not a dictionary word, and joining makes one
  ("เสี ยภาษี" -> "เสีย", "รั ษฎากร" -> "รัษฎากร").
Everything else is left as it is. Joining whenever newmm finds a word across the break (the first idea) also joins
real phrase spaces: "แล้ว จะ" -> "วจะ", "นาย ก" -> "นายก"; on the 2026-10-18 corpus it proposed ~800 joins, most of
them in clean HTML. With this rule all joins but six are in the 17 pdftotext documents, and none are in OCR text.

Tone-mark repair applies to pdftotext only. It reorders the three shapes that are never valid Thai, as pdftotext
writes them: a mark after sara aa ("หนา้" -> "หน้า"), a mark after a leading vowel ("ทีไ่" -> "ที่ไ"), and a mark
after the อ/ย of a diphthong or the final consonant after mai han-akat ("ชือ่" -> "ชื่อ", "ตัง้" -> "ตั้ง").
Other damage (a vowel one consonant too late, "หกั"; dropped marks, "เงินได") is not repaired.
"""

import re
from functools import lru_cache

from pythainlp.corpus import thai_words
from pythainlp.tokenize import word_tokenize

FOLLOWING = re.compile("[ะ-ฺๅ็-๎]")  # vowels and marks that never start a syllable
LEADING = "เแโใไ"
TONE = "่-๋"
BREAK = re.compile("(?<=[ก-๎])[ \n](?=[ก-๎])")
ABBREV = re.compile(r"^[ก-ฮ]\.")  # "ก.", "พ.ศ.": a single letter before a dot is an abbreviation, not a fragment
OK_SINGLE = {"ณ", "ฯ", "ๆ"}  # real one-character words missing from the dictionary
CONTEXT = 12

# pdftotext's misplaced tone marks, as (pattern, the valid order or None to leave it). The third pattern also
# matches valid Thai ("มีน้ำ": ี + น + ้), so it only reorders after mai han-akat or before the อ/ย of a diphthong.
MISPLACED = [
    (re.compile(f"([าำ])([{TONE}])"), lambda m: m[2] + m[1]),         # หนา้ -> หน้า
    (re.compile(f"([{LEADING}])([{TONE}])"), lambda m: m[2] + m[1]),  # ทีไ่ -> ที่ไ
    (re.compile(f"([ัิ-ื])([ก-ฮ])([{TONE}])"),          # ชือ่ -> ชื่อ, ตัง้ -> ตั้ง
     lambda m: m[1] + m[3] + m[2] if m[1] == "ั" or m[2] in "อย" else None),
]


@lru_cache(maxsize=1)
def _words() -> frozenset[str]:
    return frozenset(thai_words())


def _tok(s: str) -> list[str]:
    return word_tokenize(s, engine="newmm", keep_whitespace=False)


def _fragment(t: str) -> bool:
    return t not in _words() and t not in OK_SINGLE and not (len(t) == 1 and "ก" <= t <= "ฮ")


def _decide(left: str, right: str) -> tuple[str, str] | None:
    """-> (reason, word) when the break between `left` and `right` should be joined."""
    if ABBREV.match(right):
        return None
    if FOLLOWING.match(right) or left[-1] in LEADING:
        return "mark", ""
    if not (_fragment(_tok(left)[-1]) or _fragment(_tok(right)[0])):
        return None
    pos = 0
    for t in _tok(left + right):
        end = pos + len(t)
        if pos < len(left) < end:
            return ("fragment", t) if t in _words() else None
        pos = end
    return None


def rejoin(text: str) -> tuple[str, list[dict]]:
    """Return (text with split words joined, one record per join)."""
    out, joins, last = [], [], 0
    for m in BREAK.finditer(text):
        i = m.start()
        left = (text[max(0, i - CONTEXT):i].split() or [""])[-1]
        right = (text[i + 1:i + 1 + CONTEXT].split() or [""])[0]
        if not left or not right or not (d := _decide(left, right)):
            continue
        out.append(text[last:i])
        last = i + 1
        joins.append(dict(pos=i, sep=m.group(), left=left, right=right, reason=d[0], word=d[1]))
    out.append(text[last:])
    return "".join(out), joins


def fix_tone_marks(text: str) -> tuple[str, list[dict]]:
    """Return (text with pdftotext's misplaced tone marks reordered, one record per repair)."""
    fixes = []
    for pat, valid in MISPLACED:
        def sub(m: re.Match) -> str:
            if (r := valid(m)) is None:
                return m[0]
            fixes.append(dict(pos=m.start(), before=m[0], after=r))
            return r
        text = pat.sub(sub, text)
    return text, fixes
