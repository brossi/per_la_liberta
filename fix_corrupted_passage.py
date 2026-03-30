"""One-off: Send corrupted p2_ch18 passage + page images to Sonnet 4.6 and Gemini 3 Pro.

Compares OCR correction quality between the two models for a heavily garbled passage.
"""

import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
IMAGE_DIR = BASE_DIR / "assets" / "page_images"

# The corrupted passage spans pages 197-198 in the output
# Extract it from italian_clean.md
output = (BASE_DIR / "output" / "italian_clean.md").read_text(encoding="utf-8")

# Grab the corrupted section — starts at "della vita, avrebbe potuto"
# and ends at "cervello ne doveva essere rimasta scossa e quasi scalfita."
start_marker = "della vita, avrebbe potuto rassegnarsi"
end_marker = "cervello ne doveva essere rimasta scossa e quasi scalfita."

start_idx = output.index(start_marker)
end_idx = output.index(end_marker) + len(end_marker)
corrupted_text = output[start_idx:end_idx]

print(f"Corrupted passage: {len(corrupted_text)} chars")
print("=" * 60)
print(corrupted_text[:200])
print("...")
print("=" * 60)

# Load page images as base64, resizing if needed to stay under 5MB
page_images = {}
for pg in [197, 198]:
    img_path = IMAGE_DIR / f"page_{pg:04d}.png"
    raw = img_path.read_bytes()
    from PIL import Image
    import io
    img = Image.open(img_path)
    if img.mode == "RGBA":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    raw = buf.getvalue()
    page_images[pg] = base64.standard_b64encode(raw).decode("utf-8")
    print(f"Loaded {img_path.name} ({len(raw) // 1024}KB, {len(page_images[pg]) // 1024}KB base64)")

SYSTEM_PROMPT = (
    "You are an expert in 19th/early 20th century Italian literature and OCR correction. "
    "You are correcting OCR artifacts in a digitized 1913 Italian book titled "
    "'Per la libertà!' by Cesare Crespi, about Count Carlo di Rudio and Felice Orsini.\n\n"
    "Rules:\n"
    "- Fix obvious OCR errors (garbled characters, wrong letters) while preserving the original Italian\n"
    "- Do NOT modernize the language or spelling — keep 1913-era Italian conventions\n"
    "- Preserve all paragraph breaks\n"
    "- Do NOT translate — output must be in Italian\n"
    "- Do NOT add or remove content — only fix OCR errors\n"
    "- Use the attached page images as the authoritative reference for the correct text\n"
    "- Return ONLY the corrected text, no commentary"
)

USER_PROMPT = (
    "The following passage has severe OCR corruption. I am attaching the original page scans "
    "(pages 197-198) so you can read the actual printed text. Please correct the OCR text "
    "to match what is printed on the pages.\n\n"
    f"CORRUPTED TEXT:\n{corrupted_text}"
)


# --- Sonnet 4.6 ---
def run_sonnet():
    import anthropic

    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout=600.0,
    )

    content = []
    for pg in [197, 198]:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": page_images[pg],
            },
        })
    content.append({"type": "text", "text": USER_PROMPT})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


# --- Gemini 3 Pro ---
def run_gemini():
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    parts = []
    for pg in [197, 198]:
        parts.append(types.Part.from_bytes(
            data=base64.standard_b64decode(page_images[pg]),
            mime_type="image/jpeg",
        ))
    parts.append(types.Part.from_text(text=USER_PROMPT))

    response = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=16000,
        ),
    )
    return response.text


if __name__ == "__main__":
    import concurrent.futures

    print("\nSending to both models in parallel...\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        sonnet_future = pool.submit(run_sonnet)
        gemini_future = pool.submit(run_gemini)

        sonnet_result = sonnet_future.result()
        gemini_result = gemini_future.result()

    print("=" * 60)
    print("SONNET 4.6 RESULT")
    print("=" * 60)
    print(sonnet_result)

    print("\n" + "=" * 60)
    print("GEMINI 3 PRO RESULT")
    print("=" * 60)
    print(gemini_result)

    # Save both for comparison
    out_dir = BASE_DIR / "data"
    (out_dir / "p2_ch18_sonnet_fix.txt").write_text(sonnet_result, encoding="utf-8")
    (out_dir / "p2_ch18_gemini_fix.txt").write_text(gemini_result, encoding="utf-8")
    print(f"\nSaved to data/p2_ch18_sonnet_fix.txt and data/p2_ch18_gemini_fix.txt")
