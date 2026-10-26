import os  # Standard library module for reading environment variables
from pathlib import Path  # Standard library module for working with file paths

from dotenv import load_dotenv  # Loads settings from the .env file into environment variables
from langchain_core.messages import ToolMessage  # Carries a tool's result back to the model
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder  # Builds the messages we send to the model
from langchain_ollama import ChatOllama  # LangChain connector for models served by Ollama

import ollama  # Ollama's own client, used to ask what the chat model can do

import tables  # Spreadsheet overview and the query_table tool

load_dotenv()  # Read .env (if it exists) so os.getenv can see our settings

MAX_TOOL_ROUNDS = 4  # How many times the model may query spreadsheets before it must answer

CHAT_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")  # Which chat model to use; defaults to gpt-oss:20b
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")  # Where Ollama runs; this PC by default
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))  # How much text (in tokens) the model can read at once


_capabilities = {}  # Model name -> what it can do, remembered after the first successful check


def model_capabilities():  # Asks Ollama what the chat model supports, e.g. {"completion", "tools", "thinking"}
    if CHAT_MODEL not in _capabilities:  # Not checked yet
        try:  # Ollama might not be running, or the model might not be downloaded
            _capabilities[CHAT_MODEL] = set(ollama.Client(host=OLLAMA_URL).show(CHAT_MODEL).capabilities or [])  # Ask Ollama
        except Exception:  # Couldn't find out
            return set()  # Assume nothing extra this time, and try again next time
    return _capabilities[CHAT_MODEL]  # The remembered answer


def get_llm():  # Creates the chat model client
    return ChatOllama(  # Talk to the model through Ollama
        model=CHAT_MODEL,  # Which model
        base_url=OLLAMA_URL,  # Where Ollama is
        num_ctx=NUM_CTX,  # Ollama's default (4096) is too small and silently cuts off the documents
        reasoning=True if "thinking" in model_capabilities() else None,  # Separate the "thinking" only for models that can think (others would fail)
    )  # End of model setup


prompt = ChatPromptTemplate.from_messages(  # The conversation template used for every question
    [  # List of messages sent to the model each turn
        (  # Instructions that shape the AI's behavior
            "system",  # Message role
            "You are a helpful assistant. Answer concisely. Use the information below when it is "  # Tell it to use the documents
            "relevant, and say so if it doesn't contain the answer.\n\n"  # Ask it to admit when the docs don't help
            "SPREADSHEETS in the knowledge base, with every column and its most common values:\n"  # The overview of every table
            "{tables}\n\n"  # Filled with tables.overview()
            "{tool_rules}\n\n"  # How to handle questions that need every row (depends on whether the model can use tools)
            "EXCERPTS (a few passages or rows that best match the question; not complete):\n{context}",  # {context} is filled with the chunks found in Qdrant
        ),  # End of system message
        MessagesPlaceholder("history"),  # Earlier messages in this conversation, so follow-up questions make sense
        ("human", "{question}"),  # The user's new message
    ]  # End of message list
)  # End of prompt template

TOOL_RULES = (  # Instructions for models that can use the spreadsheet tool
    "For any question about spreadsheet data that needs more than one or two rows (lists, counts, "  # When to use the tool
    "categories, \"which\", \"how many\", comparisons), call the query_table tool. It checks every row. "  # Why
    "Use the exact column names above. Never guess counts from the excerpts below."  # Avoid made-up numbers
)  # End of rules
NO_TOOL_RULES = (  # Instructions for models that can't use tools
    "You can only see the column summary above and the excerpts below, not every row. For lists or counts "  # What it can see
    "that need every row, use the counts in the summary if they answer the question; otherwise say that "  # Use summary counts when possible
    "the answer may be incomplete."  # Otherwise be honest
)  # End of rules


def source_label(doc, with_row=True):  # Short, readable name for where a chunk came from, e.g. "report.pdf, page 3"
    label = Path(doc.metadata.get("source", "unknown")).name  # File name without the folder
    if doc.metadata.get("page"):  # Chunk came from a PDF page
        label += f", page {doc.metadata['page']}"  # Add the page number
    if doc.metadata.get("sheet"):  # Chunk came from an Excel sheet
        label += f", sheet {doc.metadata['sheet']}"  # Add the sheet name
    if with_row and doc.metadata.get("row"):  # Chunk is one table row
        label += f", row {doc.metadata['row']}"  # Add the row number
    return label  # Hand back the label


def format_docs(docs):  # Joins the found chunks into one block of text for the prompt
    return "\n\n".join(  # Blank line between chunks
        d.page_content if "row" in d.metadata else f"[{source_label(d)}]\n{d.page_content}"  # Table rows already say where they're from
        for d in docs  # Every chunk found
    )  # End of join


def describe_call(args):  # Short, readable description of a spreadsheet query, shown in the chat
    parts = [args.get("file") or "spreadsheet"]  # Which file
    parts += [f'{c} contains "{v}"' for c, v in (args.get("filters") or {}).items()]  # Each filter
    if args.get("group_by"):  # A category breakdown
        parts.append(f"grouped by {args['group_by']}")  # Mention it
    return " · ".join(parts)  # e.g. 'sites.xlsx · Type contains "billboard" · grouped by Operator'


def answer_stream(llm, question, history, docs):  # Answers a question; yields (kind, data) events as the answer is produced
    sheets = tables.load_tables()  # Every spreadsheet in the knowledge base
    use_tool = bool(sheets) and "tools" in model_capabilities()  # Offer the tool only if there are spreadsheets and the model supports tools
    messages = prompt.invoke({  # Fill in the template
        "tables": tables.overview(sheets) or "(no spreadsheets)",  # Columns and categories of every spreadsheet
        "tool_rules": TOOL_RULES if use_tool else NO_TOOL_RULES,  # How to handle questions that need every row
        "context": format_docs(docs) or "(nothing found)",  # The best-matching excerpts
        "history": history,  # Earlier messages
        "question": question,  # The new question
    }).to_messages()  # As a list of messages we can add to
    model = llm.bind_tools([tables.query_table]) if use_tool else llm  # Give the model the spreadsheet tool when it can use it
    for round_number in range(MAX_TOOL_ROUNDS + 1):  # The model may query several times before answering
        if round_number == MAX_TOOL_ROUNDS:  # Too many queries
            model = llm  # Take the tool away so it has to answer now
        reply = None  # The model's full reply, built up piece by piece
        for chunk in model.stream(messages):  # Ask the model, piece by piece
            thinking = chunk.additional_kwargs.get("reasoning_content")  # gpt-oss's thinking, if any
            if thinking:  # There is some
                yield "thinking", thinking  # Pass it on
            if chunk.content:  # There is answer text
                yield "token", chunk.content  # Pass it on
            reply = chunk if reply is None else reply + chunk  # Add the piece to the full reply
        if reply is None or not reply.tool_calls:  # The model answered without asking for data
            return  # Done
        messages.append(reply)  # Keep the model's request in the conversation
        for call in reply.tool_calls:  # Each query the model asked for
            try:  # The model may send arguments in the wrong shape
                result = tables.query_table.invoke(call["args"])  # Run it on the full spreadsheet
            except Exception as e:  # Bad arguments
                result = f"Error: the query could not run ({e}). Fix the arguments and try again."  # Let the model correct itself
            yield "tool", {"label": describe_call(call["args"]), "summary": result.splitlines()[0]}  # Show it in the chat
            messages.append(ToolMessage(result, tool_call_id=call["id"]))  # Give the result back to the model
