import streamlit as st
import asyncio
import os
import json
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import litellm
from litellm.utils import convert_to_dict
import nest_asyncio
from typing import List

nest_asyncio.apply()
load_dotenv()

# Initialize global loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

class MCPChatBot:
    def __init__(self):
        self.session: ClientSession = None
        self.available_tools: List[dict] = []
        self.model = os.getenv("LITELLM_MODEL_NAME")
        self.base_url = os.getenv("LITELLM_BASE_URL")
        self.api_key = os.getenv("LITELLM_API_KEY")

    async def initialize(self):
        server_params = StdioServerParameters(command="uv", args=["run", "research_server.py"])
        self.read, self.write = await stdio_client(server_params).__aenter__()
        self.session = ClientSession(self.read, self.write)
        await self.session.initialize()

        # List tools
        tool_list = await self.session.list_tools()
        self.available_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
            }
            for tool in tool_list.tools
        ]

    async def process_query(self, query: str) -> str:
        messages = [{'role': 'user', 'content': query}]
        result_log = f"\n### User:\n```\n{query}\n```\n"
        process_query = True

        while process_query:
            try:
                response = await litellm.acompletion(
                    model=self.model,
                    api_base=self.base_url,
                    api_key=self.api_key,
                    custom_llm_provider="openai",
                    messages=messages,
                    tools=self.available_tools,
                    tool_choice="auto",
                    max_tokens=2048
                )

                assistant_message = response.choices[0].message
                content = getattr(assistant_message, 'content', None)
                tool_calls = getattr(assistant_message, 'tool_calls', None)

                if content and (not tool_calls or len(tool_calls) == 0):
                    result_log += f"\n### Assistant:\n```\n{content}\n```\n"
                    process_query = False
                    return result_log

                elif tool_calls:
                    tool = tool_calls[0]
                    tool_name = tool['function']['name']
                    tool_args = json.loads(tool['function']['arguments'])
                    tool_id = tool['id']

                    result_log += f"\n### Tool Call: `{tool_name}`\n```json\n{json.dumps(tool_args, indent=2)}\n```\n"
                    result = await self.session.call_tool(tool_name, arguments=tool_args)
                    result_content = getattr(result, 'content', str(result))

                    result_log += f"\n### Tool Output:\n```\n{result_content}\n```\n"

                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [convert_to_dict(tool)]
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result_content,
                    })

                else:
                    process_query = False
                    return result_log

            except Exception as e:
                error_msg = f"[!] Error: {e}"
                result_log += f"\n### Error:\n```\n{str(e)}\n```\n"
                return result_log
        return None


# Persistent bot
if "chatbot" not in st.session_state:
    st.session_state.chatbot = MCPChatBot()
    loop.run_until_complete(st.session_state.chatbot.initialize())

st.title("🧠 MCP + LiteLLM ChatBot")
user_input = st.text_input("Enter your query:", "")

if st.button("Send"):
    if user_input.strip():
        result_md = loop.run_until_complete(
            st.session_state.chatbot.process_query(user_input)
        )

        # Append to file
        with open("chat_output.md", "a", encoding="utf-8") as f:
            f.write(result_md)

        # Display in Streamlit
        st.markdown(result_md)
