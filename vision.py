import ollama  # Ollama's own client; it can send images to vision models

from config import OLLAMA_URL, VISION_MODEL, VISION_NUM_CTX, read_prompt  # Settings and prompt files


def describe_image(image_bytes):  # Step 1: asks the vision model to describe the ad; yields the description piece by piece
    client = ollama.Client(host=OLLAMA_URL)  # Connection to Ollama
    stream = client.chat(  # Send the image and instructions
        model=VISION_MODEL,  # minicpm-v:8b by default
        messages=[  # The conversation
            {"role": "system", "content": read_prompt("describe_system.md")},  # Who it is: an English-only image describer (from the n8n node)
            {"role": "user", "content": read_prompt("describe.md"), "images": [image_bytes]},  # The 7-section description instructions, plus the image
        ],  # End of conversation
        stream=True,  # Send the answer back piece by piece
        options={"num_ctx": VISION_NUM_CTX},  # Room for the instructions, the image and a long description
    )  # End of request
    for part in stream:  # Each piece of the answer
        text = part.message.content  # The new text
        if text:  # Skip empty pieces
            yield text  # Pass it on
