"""Versioned comparison transforms; never modify authoritative source records."""

import re
import unicodedata

NORMALIZATION_VERSION = "arabic-comparison-v1"


def normalize(text):
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]", "", text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("Mn", "Me") and c != "ـ")
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"}))
    return re.sub(r"[^\w\s]", " ", text).split()


def edit_counts(reference, hypothesis):
    """Minimum word edits; ties prefer substitution, then deletion, then insertion."""
    previous = [(0, 0, j) for j in range(len(hypothesis) + 1)]
    for i, word in enumerate(reference, 1):
        current = [(0, i, 0)]
        for j, heard in enumerate(hypothesis, 1):
            if word == heard:
                current.append(previous[j - 1])
            else:
                a, b, c = previous[j - 1], previous[j], current[j - 1]
                current.append(min(((a[0] + 1, a[1], a[2]),
                                    (b[0], b[1] + 1, b[2]),
                                    (c[0], c[1], c[2] + 1)), key=sum))
        previous = current
    return dict(zip(("substitutions", "deletions", "insertions"), previous[-1]))


def reference_words(records, basmala="exclude"):
    if basmala not in ("include", "exclude"):
        raise ValueError("Invalid basmala scope")
    opening = [v for v in records if v["surah"] == 1 and v["ayah"] == 1]
    selected = [v for v in records if v["surah"] == 112]
    if len(opening) != 1 or [v["ayah"] for v in selected] != [1, 2, 3, 4]:
        raise ValueError("Reference boundaries are not unique and ordered")
    prefix = normalize(opening[0]["text_clean"])
    words = normalize(" ".join(v["text_clean"] for v in selected))
    if len(prefix) != 4:
        raise ValueError("Unexpected basmala word count")
    if words[:len(prefix)] == prefix:
        words = words[len(prefix):]
    if len(words) != 15:
        raise ValueError("Unexpected Al-Ikhlas word count")
    return prefix + words if basmala == "include" else words
