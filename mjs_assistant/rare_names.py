"""Recognition-only recovery for reviewed rare spellings inside name ROIs.

Do not use this for board imports or free-form text. Both the normal read and
a separately rendered name crop must agree; the frame stabilizer still applies.
"""
import math

RARE_NAMES = {'左棻', '樊哙', '赵婕妤'}
OBSERVED = {'左菜': '左棻', '左菲': '左棻', '左芬': '左棻',
            '樊哈': '樊哙', '赵婕好': '赵婕妤'}


def candidate(text, names):
    # Exact complete readings only: never turn a surname, partial name or prose
    # into a hero, and never override a different canonical dictionary name.
    if text in names.names:
        return text if text in RARE_NAMES else None
    target = OBSERVED.get(text)
    return target if target in names.names else None


def confirm(raw, confidence, checked, names):
    target = candidate(raw, names)
    if not target or not checked or not math.isfinite(confidence) or confidence < .60:
        return None
    ordered = sorted(checked, key=lambda word: word.box[1])
    spelling = ''.join(word.text for word in ordered)
    scores = [word.confidence for word in ordered]
    if any(not math.isfinite(score) for score in scores):
        return None
    score = min(scores)
    if (candidate(spelling, names) == target and score >= .60
            and max(confidence, score) >= .68):
        # Keep the weaker measured confidence, not an invented high probability.
        return target, min(confidence, score)
    return None
