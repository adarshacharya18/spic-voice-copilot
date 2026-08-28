"""Rule-based instant speech cleaner, voice command parser, and self-correction engine."""

from __future__ import annotations

import re


class RuleCleaner:
    """Instant, zero-latency rule cleaner for voice commands, self-corrections, and verbal punctuation."""

    # Common spoken filler words
    FILLERS = [
        r"\b(um|uh|err|ah|umm|uhh)\b",
        r"\b(you know what I mean|you know)\b",
    ]

    # Verbal punctuation mappings
    PUNCTUATIONS = [
        (r"\b(period|full stop)\b", "."),
        (r"\b(comma)\b", ","),
        (r"\b(question mark)\b", "?"),
        (r"\b(exclamation mark|exclamation point)\b", "!"),
        (r"\b(colon)\b", ":"),
        (r"\b(semicolon)\b", ";"),
        (r"\b(dash|hyphen)\b", "-"),
        (r"\b(new line|next line)\b", "\n"),
        (r"\b(new paragraph)\b", "\n\n"),
        (r"\b(open quote|quote)\b", '"'),
        (r"\b(close quote|unquote)\b", '"'),
    ]

    # Spoken edit/delete commands
    DELETE_PATTERNS = [
        # "something ... scratch that, write something else" -> "write something else"
        r"(.*?)\b(scratch that|delete that|erase that|cancel that|ignore that)\b",
        # "delete the last sentence / statement"
        r"(.*?)\b(delete this sentence|delete this statement|delete the last sentence)\b",
    ]

    def clean(self, text: str, strip_trailing_period: bool = True) -> str:
        """Apply full rule-based cleaning, self-corrections, and inline command execution."""
        if not text:
            return ""

        result = text.strip()

        # 1. Process Spoken Delete / Scratch Commands
        result = self._process_inline_deletions(result)
        if not result:
            return ""

        # 2. Process Self-Corrections ("till 8pm. No make it 9pm" -> "till 9pm")
        result = self._process_self_corrections(result)

        # 3. Convert Spoken Punctuation
        for pattern, replacement in self.PUNCTUATIONS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # 4. Strip Verbal Filler Words
        for filler in self.FILLERS:
            result = re.sub(filler, "", result, flags=re.IGNORECASE)

        # 5. Clean up spaces around punctuation
        result = re.sub(r"\s+([.,?!:;])", r"\1", result)
        result = re.sub(r"([(\"'])\s+", r"\1", result)
        result = re.sub(r"\s+([)\"'])", r"\1", result)
        result = re.sub(r"[ \t]+", " ", result)
        result = re.sub(r"\n\s+", "\n", result)

        # 6. Fix sentence capitalization
        result = self._capitalize_sentences(result.strip())

        # 7. Strip automatic trailing full stops at the end
        if strip_trailing_period:
            result = result.rstrip(".")

        return result.strip()

    def _process_inline_deletions(self, text: str) -> str:
        """Execute inline 'scratch that' or 'delete that' commands."""
        for pat in self.DELETE_PATTERNS:
            match = re.search(pat, text, flags=re.IGNORECASE)
            if match:
                text = text[match.end():].strip()

        if re.search(r"^(delete that|scratch that|clear that|cancel that|erase that)$", text, flags=re.IGNORECASE):
            return ""

        return text

    def _process_self_corrections(self, text: str) -> str:
        """Execute conversational self-corrections like 'in the left drawer from the drawer', 'actually X', 'no make it X'."""
        # Pattern A: Cue-based self-corrections (sorry, wait, actually, i mean, or rather, no, instead)
        cue_pattern = (
            r"(.*?)(?:[.,;]?\s+)(?:sorry,?\s+|wait,?\s+|instead,?\s+|actually,?\s+|i\s+mean,?\s+|"
            r"or\s+rather,?\s+|no,?\s+make\s+(?:it|that)\s+|no,?\s+change\s+(?:it|that)\s+to\s+|no,?\s+)(.+?)(?:\.|$)"
        )
        m = re.search(cue_pattern, text, flags=re.IGNORECASE)
        if m:
            before = m.group(1).strip()
            replacement = m.group(2).strip()

            rep_words = [w.replace("-", " ") for w in replacement.split()]
            bef_words = [w.replace("-", " ") for w in before.split()]

            flat_rep = [re.sub(r"[^\w]", "", w.lower()) for item in rep_words for w in item.split() if w]
            flat_bef = [re.sub(r"[^\w]", "", w.lower()) for item in bef_words for w in item.split() if w]

            if flat_rep and flat_bef:
                last_rep_word = flat_rep[-1]
                for idx in range(len(flat_bef) - 1, -1, -1):
                    if flat_bef[idx] == last_rep_word:
                        start_idx = max(0, idx - len(flat_rep) + 1)
                        # Scan back across articles, adjectives and prepositions for full clause replacement
                        for p_idx in range(idx - 1, -1, -1):
                            w = flat_bef[p_idx]
                            if w in ("in", "at", "on", "to", "from", "for", "with", "into", "under", "over", "by"):
                                start_idx = p_idx
                                break
                            elif p_idx < idx - len(flat_rep) - 2:
                                break
                        prefix = bef_words[:start_idx]
                        return (" ".join(prefix) + " " + replacement).strip()

            time_rep = re.search(r"(\d+(?::\d+)?\s*(?:am|pm)?)", replacement, flags=re.IGNORECASE)
            if time_rep:
                time_bef_matches = list(re.finditer(r"(\d+(?::\d+)?\s*(?:am|pm)?)", before, flags=re.IGNORECASE))
                if time_bef_matches:
                    last_match = time_bef_matches[-1]
                    return (before[:last_match.start()] + replacement + before[last_match.end():]).strip()

            return (before + " " + replacement).strip()

        # Pattern B: Repetition / clause self-correction (e.g. 'in the left-drawer from the drawer')
        norm_text = text.replace("-", " ")
        prep_pattern = r"(.*?)\b(in|at|on|to|from|for|with|into)\s+([^,]+?)\s+\b(in|at|on|to|from|for|with|into)\s+(.+)$"
        m_prep = re.search(prep_pattern, norm_text, flags=re.IGNORECASE)
        if m_prep:
            prefix = m_prep.group(1).strip()
            prep1, phrase1 = m_prep.group(2), m_prep.group(3).strip()
            prep2, phrase2 = m_prep.group(4), m_prep.group(5).strip()

            words1 = [re.sub(r"[^\w]", "", w.lower()) for w in phrase1.split() if w]
            words2 = [re.sub(r"[^\w]", "", w.lower()) for w in phrase2.split() if w]

            if words1 and words2 and (words1[-1] == words2[-1]):
                return (prefix + " " + prep2 + " " + phrase2).strip()

        return text

    def _capitalize_sentences(self, text: str) -> str:
        """Capitalize the start of sentences."""
        if not text:
            return ""

        text = text[0].upper() + text[1:]

        def _cap(m):
            return m.group(1) + m.group(2).upper()

        text = re.sub(r"([.!?]\s+)([a-z])", _cap, text)
        text = re.sub(r"(\n+)([a-z])", _cap, text)

        return text
