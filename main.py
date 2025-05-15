from fastapi import FastAPI, Request
from pydantic import BaseModel
from context_store import get_context
from mcp_router import call_model, build_prompt

app = FastAPI()

class Query(BaseModel):
    user_id: str
    input: str
    model: str  # e.g., 'llama3', 'mistral', 'gemma'

@app.post("/query")
def query_model(data: Query):
    context = get_context(data.user_id)
    prompt = build_prompt(context, data.input)
    response = call_model(data.model, prompt)
    return {"output": response}
