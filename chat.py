import re  # Standard library module for finding patterns in text

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # Message types for the conversation

from config import CHAT_HISTORY, CHAT_REASONING, JUDGE_NUM_CTX, read_prompt  # Settings and prompt files
from judge import search_loop  # Think, search the ASC guidelines, answer

CHAT_SEARCHES = 3  # Most guideline searches per chat answer (keeps answers quick)
CHAT_TEMPERATURE = 0.2  # Low creativity: chat answers should stick to what the rules actually say
RESERVED_TOKENS = 11500  # Room kept for the instructions (~6,400 tokens), searches and the answer
HISTORY_CHARS = max(4000, int((JUDGE_NUM_CTX - RESERVED_TOKENS) * 3.5))  # Characters of earlier messages that fit (~3.5 characters per token)
MEASUREMENT = re.compile(  # A number with a unit, e.g. "12 pt", "1-2 inches", "10%", "30 m"
    r"\b\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?\s*(?:%|percent\b|pt\b|points?\b|px\b|pixels?\b|inch(?:es)?\b|in\b|cm\b|mm\b|ft\b|feet\b|foot\b|m\b|meters?\b|metres?\b)",
    re.IGNORECASE,  # Any capitalization
)  # End of pattern


def checklist():  # The ASC rule checklist, taken from the judge prompt so both always use the same rules
    text = read_prompt("judge.md")  # The judge instructions
    start, end = text.index("DECENCY CHECKLIST"), text.index("STRICT RULES")  # The checklist part (decency + G, C, P and R rules)
    return text[start:end].rstrip("=\n ")  # Without the banner line before "STRICT RULES"


def system_prompt():  # The chat instructions, with the checklist filled in
    return read_prompt("chat.md").replace("{checklist}", checklist())  # prompts/chat.md with the rules added


def recent_history(history):  # The newest earlier messages that fit in the AI's memory, oldest first
    kept, used = [], 0  # Messages kept, and their total length
    for m in reversed(history[-CHAT_HISTORY:]):  # Newest first
        content = str(m.get("content", "")).strip()  # The message text
        if not content:  # Empty
            continue  # Skip it
        if used + len(content) > HISTORY_CHARS:  # It doesn't fit any more
            if not kept:  # Even the newest message is too long
                kept.append((m.get("role"), content[: HISTORY_CHARS] + "\n[…shortened]"))  # Keep its start
            break  # Older messages are dropped
        kept.append((m.get("role"), content))  # Keep it
        used += len(content)  # Count it
    return [AIMessage(c) if role == "assistant" else HumanMessage(c) for role, c in reversed(kept)]  # Back in time order


def measurements(text):  # Every measurement in a text, as (as written, comparable form), e.g. ("12 pt", "12pt")
    found = []  # Results
    for m in MEASUREMENT.finditer(text):  # Each one
        shown = re.sub(r"\s+", " ", m.group(0)).strip()  # As written (special spaces made normal)
        found.append((shown, re.sub(r"[\s–]+", "", shown.replace("–", "-")).lower()))  # Comparable: no spaces, plain dash, lowercase
    return found  # All of them


def unsupported_measurements(answer, sources):  # Measurements in the answer that appear neither in the rules nor in the passages read
    known = {key for _, key in measurements(sources)}  # Measurements written in what the AI was given
    return list(dict.fromkeys(shown for shown, key in measurements(answer) if key not in known))  # The ones not backed by the sources (no repeats)


def chat_stream(message, history):  # Answers a chat message (no image); yields (kind, data) events
    system = system_prompt()  # The instructions with the checklist
    messages = [SystemMessage(system), *recent_history(history), HumanMessage(message)]  # Instructions, conversation, new question
    answer, sources = "", checklist()  # The streamed answer, and the ASC texts the AI was given (to check its numbers against; not the instructions, whose examples mention made-up sizes)
    for kind, data in search_loop(messages, stream_text=True, max_searches=CHAT_SEARCHES, temperature=CHAT_TEMPERATURE, effort=CHAT_REASONING):  # Think (briefly), search, answer
        if kind == "token":  # A piece of the answer
            answer += data  # Keep it for the check below
        elif kind == "search":  # Passages the AI read
            sources += "\n" + data["result"]  # Measurements in these are backed by the guidelines
        if kind != "answer":  # The answer text was already streamed piece by piece
            yield kind, data  # Pass on thinking, searches, answer text and memory use
    extra = unsupported_measurements(answer, sources)  # Numbers the AI may have made up
    if extra:  # Some found
        yield "warning", (  # Shown under the answer
            f"This answer mentions {', '.join(extra)}, which is not in the ASC guidelines the assistant used. "  # What was found
            "Treat it as a suggestion, not an ASC requirement."  # How to read it
        )  # End of warning
