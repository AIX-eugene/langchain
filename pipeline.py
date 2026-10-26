import time  # Standard library module for measuring how long each step takes
from datetime import datetime  # Standard library module for the date and time of the check

from checks import error_result, finalize  # Step 3: verify the judge's answer
from config import JUDGE_MODEL, VISION_MODEL  # Model names, recorded in the result
from judge import judge_stream  # Step 2: judge the description against the ASC rules
from vision import describe_image  # Step 1: describe the image


def check_image(image_bytes, note=""):  # Runs the whole check on one image (note: optional text the user sent with it); yields (kind, data) events
    start = time.time()  # When the check started

    yield "stage", "describe"  # Step 1 starts
    description = ""  # The vision model's description, built up piece by piece
    for piece in describe_image(image_bytes):  # Each piece of the description
        description += piece  # Add it
        yield "describe", piece  # Show it live on the page
    if not description.strip():  # The vision model said nothing
        yield "result", {**error_result("The vision model returned no description. Please try again."), "seconds": round(time.time() - start)}  # Stop
        return  # Done

    yield "stage", "judge"  # Step 2 starts
    raw = ""  # The judge's final answer
    for kind, data in judge_stream(description, note):  # The judge's thinking, searches and answer
        if kind == "answer":  # The final answer
            raw = data  # Keep it
        elif kind != "token":  # Thinking, a guideline search, or memory use (the raw JSON text isn't shown)
            yield kind, data  # Show it on the page

    yield "stage", "verify"  # Step 3 starts
    result = finalize(raw, description)  # Remove made-up violations, add missed decency problems, explain the rules
    result["description"] = description  # Include the description, for the reviewer
    result["seconds"] = round(time.time() - start)  # How long it took
    result["checked_at"] = datetime.now().strftime("%B %d, %Y %I:%M %p")  # When it was checked, e.g. "October 23, 2026 10:15 AM"
    result["vision_model"], result["judge_model"] = VISION_MODEL, JUDGE_MODEL  # Which models made this result (for the report)
    yield "result", result  # The final result
