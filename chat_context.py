"""Approximate rolling context shared by the API and chat pipeline."""
import math
from config import CHAT_EFFECTIVE_CONTEXT


def estimate_tokens(text):
    return math.ceil(len(text) / 3.5)


def select_context(message, history, limit=CHAT_EFFECTIVE_CONTEXT):
    """Keep a contiguous suffix of complete user/assistant exchanges."""
    used = estimate_tokens(message) + 8
    if used > limit:
        raise ValueError(f"Your message is too long. Shorten it to fit approximately {max(0, limit - 8):,} tokens.")
    valid = []
    if isinstance(history, list):
        valid = [m for m in history if isinstance(m, dict)
                 and m.get('role') in ('user', 'assistant')
                 and isinstance(m.get('content'), str) and m['content'].strip()]
    pairs = []
    pending = None
    for m in valid:
        if m['role'] == 'user':
            pending = m
        elif pending is not None:
            pairs.append([pending, m])
            pending = None
    kept = []
    for pair in reversed(pairs):
        cost = sum(estimate_tokens(m['content']) + 8 for m in pair)
        if used + cost > limit:
            break
        kept[0:0] = pair
        used += cost
    return kept, {'estimated_tokens': used, 'limit_tokens': limit,
                  'omitted': len(kept) < len(valid), 'approximate': True}
