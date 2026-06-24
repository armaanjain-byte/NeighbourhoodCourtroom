from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
load_dotenv()

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "fake_key"))
tools = [{"function_declarations": [{"name": "foo", "description": "bar", "parameters": {"type": "OBJECT", "properties": {"x": {"type": "STRING"}}}}] }]
chat = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(tools=tools)
)
# Example usage: resp = chat.send_message("Call foo with x='hi'")

