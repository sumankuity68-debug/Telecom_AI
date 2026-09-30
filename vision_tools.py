import base64

from groq import Groq

from config import (
    GROQ_API_KEY,
    VISION_MODEL,
)


# ============================================================
# GROQ CLIENT
# ============================================================

client = Groq(
    api_key=GROQ_API_KEY
)


# ============================================================
# ANALYZE IMAGE
# ============================================================

def analyze_image(
    image_bytes,
    mime_type,
    question=None
):
    if not image_bytes:
        return "No image was provided."

    from backend.security import validate_image_file
    is_valid, err_msg = validate_image_file(image_bytes, mime_type)
    if not is_valid:
        return f"Image validation error: {err_msg}"


    # --------------------------------------------------------
    # BASE64
    # --------------------------------------------------------

    base64_image = base64.b64encode(
        image_bytes
    ).decode("utf-8")


    data_url = (
        f"data:{mime_type};base64,"
        f"{base64_image}"
    )


    # --------------------------------------------------------
    # QUESTION
    # --------------------------------------------------------

    if not question:

        question = """
Analyze this telecom-related image.

Determine whether it appears to be:

1. A speed-test screenshot
2. A router/modem screenshot
3. A telecom bill
4. A network status screenshot
5. Another telecom-related image

Extract useful visible information.

For a speed test, look for:
- download speed
- upload speed
- ping/latency
- jitter
- packet loss

For a bill, look for:
- plan charge
- add-ons
- roaming
- taxes
- total

For a router:
- status indicators
- warning indicators
- connection state

Do not invent values that are not visible.

Explain what the user should do next.
"""


    # --------------------------------------------------------
    # GROQ VISION
    # --------------------------------------------------------

    try:

        response = client.chat.completions.create(

            model=VISION_MODEL,

            messages=[
                {
                    "role": "system",

                    "content": (
                        "You are a telecom "
                        "visual diagnosis assistant. "
                        "Only report information "
                        "visible in the image."
                    ),
                },

                {
                    "role": "user",

                    "content": [

                        {
                            "type": "text",

                            "text": question,
                        },

                        {
                            "type": "image_url",

                            "image_url": {
                                "url": data_url
                            },
                        },
                    ],
                },
            ],

            temperature=0.2,

            max_completion_tokens=1500,

        )

        return response.choices[
            0
        ].message.content


    except Exception as error:

        return (
            "Vision analysis failed:\n"
            f"{error}"
        )