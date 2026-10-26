import ollama  # Ollama's own client, used to ask what the judge model can do
from langchain_core.messages import HumanMessage, ToolMessage  # Message types for the conversation with the judge
from langchain_ollama import ChatOllama  # LangChain connector for chat models served by Ollama

from config import JUDGE_MODEL, JUDGE_NUM_CTX, MAX_SEARCHES, OLLAMA_URL, read_prompt  # Settings and prompt files
from guidelines import asc_guidelines, format_passages, search  # The guideline search tool and helpers

_capabilities = {}  # Model name -> what it can do, remembered after the first successful check


def model_capabilities(model=JUDGE_MODEL):  # Asks Ollama what a model supports, e.g. {"completion", "tools", "thinking"}
    if model not in _capabilities:  # Not checked yet
        try:  # Ollama might not be running, or the model might not be downloaded
            _capabilities[model] = set(ollama.Client(host=OLLAMA_URL).show(model).capabilities or [])  # Ask Ollama
        except Exception:  # Couldn't find out
            return set()  # Assume nothing extra this time, and try again next time
    return _capabilities[model]  # The remembered answer


def get_judge():  # Creates the judge model client
    return ChatOllama(  # Talk to the model through Ollama
        model=JUDGE_MODEL,  # gpt-oss:20b by default
        base_url=OLLAMA_URL,  # Where Ollama is
        num_ctx=JUDGE_NUM_CTX,  # Room for the long instructions, the description and the search results
        reasoning=True if "thinking" in model_capabilities() else None,  # Keep the model's thinking separate (only for models that think)
    )  # End of model setup


def judge_stream(description):  # Step 2: checks the description against the ASC rules; yields (kind, data) events
    prompt = read_prompt("judge.md").replace("{description}", description)  # The n8n AI Agent prompt, with this ad's description filled in
    messages = [HumanMessage(prompt)]  # The conversation so far
    llm = get_judge()  # The judge model
    can_search = "tools" in model_capabilities()  # Only models with tool support can search the guidelines
    model = llm.bind_tools([asc_guidelines]) if can_search else llm  # Give it the search tool when it can use it
    searches, queries, seen = 0, set(), set()  # Searches made, their queries, and passages already shown
    while True:  # Until the judge gives its final answer
        reply = None  # The judge's full reply, built up piece by piece
        for chunk in model.stream(messages):  # Ask the judge, piece by piece
            thinking = chunk.additional_kwargs.get("reasoning_content")  # Its thinking, if any
            if thinking:  # There is some
                yield "thinking", thinking  # Pass it on
            reply = chunk if reply is None else reply + chunk  # Add the piece to the full reply
        if reply is None:  # The model sent nothing at all
            yield "answer", ""  # Report an empty answer (the checks will turn it into an error)
            return  # Stop
        used = (reply.usage_metadata or {}).get("total_tokens", 0)  # How much of the judge's memory this conversation fills
        yield "tokens", used  # Report it (useful when tuning JUDGE_NUM_CTX)
        if not reply.tool_calls:  # No more searches: this is the final answer
            yield "answer", reply.text  # The JSON verdict (as text)
            return  # Done
        messages.append(reply)  # Keep the judge's search request in the conversation
        for call in reply.tool_calls:  # Each search it asked for
            query = str(call["args"].get("query", "")).strip()  # The search words
            key = " ".join(sorted(query.lower().replace('"', " ").split()))  # The query ignoring case, quotes and word order
            if not query:  # Empty query
                result = "Error: give a short search query."  # Tell the judge
            elif key in queries:  # Same search as before
                result = "You already made this search. Use the passages from before, or search a different topic."  # Don't repeat it
            else:  # A new search
                queries.add(key)  # Remember it
                searches += 1  # Count it
                result = format_passages(search(query), seen)  # The passages (ones already shown are not repeated)
                yield "search", {"query": query, "result": result}  # Show it on the page
            messages.append(ToolMessage(result, tool_call_id=call["id"]))  # Give the result back to the judge
        if searches >= MAX_SEARCHES or used > JUDGE_NUM_CTX * 0.7:  # Enough searching, or memory getting full
            model = llm  # Take the tool away so the judge has to answer now
            messages.append(HumanMessage("Stop searching now. Write your final JSON answer."))  # Tell it
