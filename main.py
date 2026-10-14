from langchain_core.messages import AIMessage, HumanMessage  # Message types used to remember the conversation

from db import get_vector_store, search  # Our helpers for the Qdrant database
from rag import answer_stream, get_llm  # Shared answering logic (also used by the web UI)


def main():  # Entry point of the program
    store = get_vector_store()  # Open the Qdrant database
    llm = get_llm()  # Create the chat model client
    history = []  # Messages so far, so follow-up questions make sense

    print("LangChain chat — type 'exit' to quit.")  # Welcome message
    while True:  # Keep chatting until the user quits
        question = input("\nYou: ").strip()  # Read what the user typed, trimming extra spaces
        if question.lower() in {"exit", "quit"}:  # Did the user ask to stop?
            break  # Leave the chat loop
        if not question:  # Did the user just press Enter?
            continue  # Ignore empty input and ask again
        docs = search(store, question)  # Find the most relevant chunks (exact codes + closest meaning)
        print("AI: ", end="", flush=True)  # Print the label before the answer, on the same line
        answer = ""  # Collects the full answer so it can be remembered
        for kind, data in answer_stream(llm, question, history, docs):  # Answer, querying spreadsheets if needed
            if kind == "tool":  # A spreadsheet query was run
                print(f"\n  [checked {data['label']} -> {data['summary']}]\n", end="", flush=True)  # Show what was checked
            elif kind == "token":  # Answer text
                print(data, end="", flush=True)  # Show each piece immediately as it arrives
                answer += data  # Add it to the full answer
        print()  # Finish the answer with a new line
        history += [HumanMessage(question), AIMessage(answer)]  # Remember this exchange
        history = history[-10:]  # Keep only the last 5 exchanges so the prompt doesn't grow forever


if __name__ == "__main__":  # Only run when this file is executed directly (not imported)
    main()  # Start the chat
