import google.generativeai as genai
import os
from dotenv import load_dotenv
load_dotenv()
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash", tools=[{"function_declarations": [{"name": "foo", "description": "bar", "parameters": {"type": "OBJECT", "properties": {"x": {"type": "STRING"}}}}] }])
resp = model.generate_content("Call foo with x='hi'")
print(resp.candidates[0].content.parts)
for p in resp.parts:
    print(dir(p))
    if hasattr(p, 'function_call'):
        print(p.function_call)
