# Simulate context memory
context_memory = {
    "user_1": "You are talking to a Linux kernel developer. Keep responses low-level and efficient.",
    "user_2": "You are explaining to a 12-year-old. Use simple language and analogies.",
}

def get_context(user_id: str) -> str:
    return context_memory.get(user_id, "")
