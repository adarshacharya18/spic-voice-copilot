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
        """Execute conversational self-corrections like 'no make it X', 'actually X', 'I mean X'."""
        # Pattern A: "... till 8pm. No make it 9pm." / "5 copies, no make that 10 copies"
        m = re.search(
            r"(.*?)(?:[.,;]?\s+)(?:no,?\s+make\s+(?:it|that)\s+|no,?\s+change\s+(?:it|that)\s+to\s+)(.+?)(?:\.|$)",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            before = m.group(1).strip()
            replacement = m.group(2).strip()

            # Check if replacement ends with words matching before (e.g. '10 copies' vs '5 copies')
            rep_words = replacement.split()
            bef_words = before.split()
            if len(rep_words) > 1 and len(bef_words) >= len(rep_words):
                if [w.lower() for w in bef_words[-len(rep_words) + 1:]] == [w.lower() for w in rep_words[1:]]:
                    return (" ".join(bef_words[:-len(rep_words)]) + " " + replacement).strip()

            # If replacement has a number or time (e.g. '9pm' or '10'), find matching entity in 'before'
            time_rep = re.search(r"(\d+(?::\d+)?\s*(?:am|pm)?)", replacement, flags=re.IGNORECASE)
            if time_rep:
                time_bef_matches = list(re.finditer(r"(\d+(?::\d+)?\s*(?:am|pm)?)", before, flags=re.IGNORECASE))
                if time_bef_matches:
                    last_match = time_bef_matches[-1]
                    return before[:last_match.start()] + replacement + before[last_match.end():]

            return before + " " + replacement

        # Pattern B: "... at 3pm, actually 4pm" / "... on Friday, I mean Monday"
        m2 = re.search(
            r"(.*?)(?:[.,;]?\s+)(?:actually|i mean|or rather)\s+(.+?)(?:\.|$)",
            text,
            flags=re.IGNORECASE,
        )
        if m2:
            before = m2.group(1).strip()
            replacement = m2.group(2).strip()
            rep_words = replacement.split()
            bef_words = before.split()
            if len(rep_words) > 1 and len(bef_words) >= len(rep_words):
                if [w.lower() for w in bef_words[-len(rep_words) + 1:]] == [w.lower() for w in rep_words[1:]]:
                    return (" ".join(bef_words[:-len(rep_words)]) + " " + replacement).strip()

            time_rep = re.search(r"(\d+(?::\d+)?\s*(?:am|pm)?)", replacement, flags=re.IGNORECASE)
            if time_rep:
                time_bef_matches = list(re.finditer(r"(\d+(?::\d+)?\s*(?:am|pm)?)", before, flags=re.IGNORECASE))
                if time_bef_matches:
                    last_match = time_bef_matches[-1]
                    return before[:last_match.start()] + replacement + before[last_match.end():]

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
