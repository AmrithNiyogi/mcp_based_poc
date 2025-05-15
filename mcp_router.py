import requests

def call_model(model_name: str, prompt: str) -> str:
    url = f"http://localhost:11434/api/generate"
    response = requests.post(url, json={
        "model": model_name,
        "prompt": prompt,
        "stream": False
    })
    return response.json()["response"]

def build_prompt(context: str, user_input: str) -> str:
    return f"{context}\n\nUser: {user_input}\nAssistant:"
