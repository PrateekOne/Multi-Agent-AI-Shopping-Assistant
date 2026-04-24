# llm_client.py
import requests

URL = "http://localhost:8080"

def send_prompt_to_llm(prompt: str) -> str:
    try:
        response = requests.post(
            URL,
            json={
                "prompt": prompt,
                "max_tokens": 200,
                "temperature": 0.7
            },
            timeout=25
        )
        return response.json().get("content", "")
    except:
        return ""
