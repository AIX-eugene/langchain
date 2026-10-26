import ollama  # Ollama's own client, used to ask what a model can do
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage  # Message types for the conversation with the model
from langchain_ollama import ChatOllama  # LangChain connector for chat models served by Ollama

from config import CHAT_REASONING, JUDGE_MODEL, JUDGE_NUM_CTX, JUDGE_REASONING, KEEP_ALIVE, MAX_SEARCHES, OLLAMA_URL, read_prompt  # Settings and prompt files
from guidelines import asc_guidelines, format_passages, search  # The guideline search tool and helpers

_capabilities = {}  # Model name -> what it can do, remembered after the first successful check


def model_capabilities(model=JUDGE_MODEL):  # Asks Ollama what a model supports, e.g. {"completion", "tools", "thinking"}
    if model not in _capabilities:  # Not checked yet
        try:  # Ollama might not be running, or the model might not be downloaded
            _capabilities[model] = set(ollama.Client(host=OLLAMA_URL).show(model).capabilities or [])  # Ask Ollama
        except Exception:  # Couldn't find out
            return set()  # Assume nothing extra this time, and try again next time
    return _capabilities[model]  # The remembered answer


def thinking_setting(effort):  # How the model should think: an effort level for gpt-oss, on/off for other thinking models
    if "thinking" not in model_capabilities():  # The model can't think
        return None  # Don't ask it to (it would fail)
    if "gpt-oss" in JUDGE_MODEL and effort in ("low", "medium", "high"):  # gpt-oss supports effort levels
        return effort  # e.g. "low": think briefly, answer much sooner
    return True  # Other thinking models: thinking on


def get_judge(temperature=None, effort=JUDGE_REASONING):  # Creates the judge model client (also used for chat answers)
    return ChatOllama(  # Talk to the model through Ollama
        model=JUDGE_MODEL,  # gpt-oss:20b by default
        base_url=OLLAMA_URL,  # Where Ollama is
        num_ctx=JUDGE_NUM_CTX,  # Room for the instructions, the conversation and the search results
        reasoning=thinking_setting(effort),  # How long to think, kept separate from the answer
        temperature=temperature,  # Lower = sticks closer to the rules, less "creative" (None = the model's default, as in n8n)
        keep_alive=KEEP_ALIVE,  # Stay loaded between messages (reloading takes over a minute)
    )  # End of model setup


def warm_up():  # Loads the judge and pre-reads the chat instructions, so the first question is answered quickly
    from chat import system_prompt  # The chat instructions (imported here to avoid a circular import)
    try:  # Ollama might not be running yet
        get_judge(effort=CHAT_REASONING).invoke([SystemMessage(system_prompt()), HumanMessage("Reply OK.")], num_predict=1)  # Load the model and process the instructions once
    except Exception:  # Not available
        pass  # The first real question will load it instead


def search_loop(messages, stream_text=False, max_searches=MAX_SEARCHES, temperature=None, effort=JUDGE_REASONING):  # Lets the model think, search the ASC guidelines and answer; yields (kind, data) events
    llm = get_judge(temperature, effort)  # The model
    can_search = "tools" in model_capabilities()  # Only models with tool support can search the guidelines
    model = llm.bind_tools([asc_guidelines]) if can_search else llm  # Give it the search tool when it can use it
    searches, queries, seen = 0, set(), set()  # Searches made, their queries, and passages already shown
    while True:  # Until the model gives its final answer
        reply = None  # The model's full reply, built up piece by piece
        for chunk in model.stream(messages):  # Ask the model, piece by piece
            thinking = chunk.additional_kwargs.get("reasoning_content")  # Its thinking, if any
            if thinking:  # There is some
                yield "thinking", thinking  # Pass it on
            if stream_text and chunk.content:  # Chat answers are shown word by word
                yield "token", chunk.text  # Pass the text on
            reply = chunk if reply is None else reply + chunk  # Add the piece to the full reply
        if reply is None:  # The model sent nothing at all
            yield "answer", ""  # Report an empty answer
            return  # Stop
        used = (reply.usage_metadata or {}).get("total_tokens", 0)  # How much of the model's memory this conversation fills
        yield "tokens", used  # Report it (useful when tuning JUDGE_NUM_CTX)
        if not reply.tool_calls:  # No more searches: this is the final answer
            yield "answer", reply.text  # The full answer text
            return  # Done
        messages.append(reply)  # Keep the model's search request in the conversation
        for call in reply.tool_calls:  # Each search it asked for
            query = str(call["args"].get("query", "")).strip()  # The search words
            key = " ".join(sorted(query.lower().replace('"', " ").split()))  # The query ignoring case, quotes and word order
            if not query:  # Empty query
                result = "Error: give a short search query."  # Tell the model
            elif key in queries:  # Same search as before
                result = "You already made this search. Use the passages from before, or search a different topic."  # Don't repeat it
            else:  # A new search
                queries.add(key)  # Remember it
                searches += 1  # Count it
                result = format_passages(search(query), seen)  # The passages (ones already shown are not repeated)
                yield "search", {"query": query, "result": result}  # Show it on the page
            messages.append(ToolMessage(result, tool_call_id=call["id"]))  # Give the result back to the model
        if searches >= max_searches or used > JUDGE_NUM_CTX * 0.7:  # Enough searching, or memory getting full
            model = llm  # Take the tool away so the model has to answer now
            messages.append(HumanMessage("Stop searching now and write your final answer."))  # Tell it


def judge_stream(description, note=""):  # Step 2 of a check: judges the description against the ASC rules; yields (kind, data) events
    if note.strip():  # The user wrote something with the image
        description += (  # Add it after the description, clearly marked
            "\n\nNOTE FROM THE REVIEWER (context only, e.g. where the ad will run; it is NOT part of the ad, "
            f"so never quote it as evidence):\n{note.strip()}"
        )  # End of note
    prompt = read_prompt("judge.md").replace("{description}", description)  # The n8n AI Agent prompt, with this ad's description filled in
    yield from search_loop([HumanMessage(prompt)])  # Judge it, searching the guidelines as needed
