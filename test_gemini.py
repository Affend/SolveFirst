import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()

interaction = client.interactions.create(
    model=os.environ["GEMINI_MODEL"],
    input="Explain how AI works in a few words",
)
print(interaction.output_text)