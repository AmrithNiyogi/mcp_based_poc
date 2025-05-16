import os
import asyncio
import json
from dotenv import load_dotenv
import nest_asyncio
from typing import List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import litellm
from litellm.utils import convert_to_dict

# Allow nested asyncio event loops (useful in some environments like Jupyter or Streamlit)
nest_asyncio.apply()

# Load environment variables from .env file (e.g., API keys, model names)
load_dotenv()


class MCPChatBot:
    def __init__(self):
        # MCP ClientSession instance for communicating with the backend server (initialized later)
        self.session: ClientSession = None

        # List of available tools fetched from the backend, prepared for the LLM model
        self.available_tools: List[dict] = []

        # Load LiteLLM config from environment variables
        self.model = os.getenv("LITELLM_MODEL_NAME")   # e.g., "gpt-4o-mini"
        self.base_url = os.getenv("LITELLM_BASE_URL")  # e.g., OpenAI endpoint or custom API
        self.api_key = os.getenv("LITELLM_API_KEY")    # API key for authentication

    async def process_query(self, query: str):
        """
        Sends the user query to the LLM, handles model responses including tool calls,
        and writes conversation logs to a markdown file.
        """
        # Initialize conversation messages starting with user input
        messages = [{'role': 'user', 'content': query}]
        process_query = True  # Loop control for ongoing exchanges (e.g., when tools are called)

        # Open log file in append mode to save chat history and tool calls
        with open("chat_output.md", "a", encoding="utf-8") as f:
            # Log user query in Markdown format
            f.write(f"\n### User:\n```\n{query}\n```\n")

            while process_query:
                try:
                    # Call the LLM asynchronously to get a response or tool call suggestion
                    response = await litellm.acompletion(
                        model=self.model,
                        api_base=self.base_url,
                        api_key=self.api_key,
                        custom_llm_provider="openai",
                        messages=messages,
                        tools=self.available_tools,   # Pass tool specs so LLM can suggest calls
                        tool_choice="auto",           # Let model decide if a tool should be called
                        max_tokens=2048
                    )

                    # Extract the assistant's message (could be text or tool calls)
                    assistant_message = response.choices[0].message

                    # Try to get textual content and any tool call info
                    content = getattr(assistant_message, 'content', None)
                    tool_calls = getattr(assistant_message, 'tool_calls', None)

                    # Support cases where assistant_message might be dict instead of object
                    if isinstance(assistant_message, dict):
                        content = content or assistant_message.get('content')
                        tool_calls = tool_calls or assistant_message.get('tool_calls')

                    # If there's a textual reply and no tool calls, respond and stop looping
                    if content and (not tool_calls or len(tool_calls) == 0):
                        print(f"\n[Assistant]: {content}")
                        f.write(f"\n### Assistant:\n```\n{content}\n```\n")
                        process_query = False  # Conversation turn complete

                    # If the assistant requested tool calls, handle those
                    elif tool_calls and len(tool_calls) > 0:
                        # Handle first tool call in the list
                        tool = tool_calls[0]

                        # Extract tool details: name, arguments, and id, supporting different formats
                        if hasattr(tool, 'function'):
                            tool_name = tool.function.name
                            tool_args = tool.function.arguments
                            tool_id = tool.id
                        else:
                            tool_name = tool['function']['name']
                            tool_args = tool['function']['arguments']
                            tool_id = tool['id']

                        # Tool arguments might be a JSON string, try to parse it to dict
                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError:
                                print("[!] Failed to decode tool_args JSON string, using raw string")

                        # Log and print the tool call details
                        print(f"\nCalling tool '{tool_name}' with args: {tool_args}")
                        f.write(f"\n### Tool Call: `{tool_name}`\n```json\n{json.dumps(tool_args, indent=2)}\n```\n")

                        # Execute the tool via the MCP session asynchronously
                        result = await self.session.call_tool(tool_name, arguments=tool_args)

                        # Extract result content safely
                        result_content = getattr(result, 'content', str(result))

                        # Print and log the tool output
                        print(f"[Tool '{tool_name}' output]: {result_content}")
                        f.write(f"\n### Tool Output:\n```\n{result_content}\n```\n")

                        # Append the assistant's tool call info back to the conversation history
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [convert_to_dict(tool)]
                        })

                        # Append the tool response message to feed back to the LLM
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result_content,
                        })

                    else:
                        # If neither content nor tool calls present, end loop to avoid infinite loop
                        process_query = False

                except Exception as e:
                    # On any exception, log and print error, then stop processing this query
                    print(f"[!] Error during completion: {e}")
                    f.write(f"\n### Error:\n```\n{str(e)}\n```\n")
                    process_query = False

    async def chat_loop(self):
        """
        Interactive console loop for chatting.
        User enters queries, 'quit' exits the program.
        """
        print("MCP LiteLLM Chatbot started!\nType 'quit' to exit.")

        while True:
            query = input("\nQuery: ").strip()
            if query.lower() == 'quit':
                exit(0)  # Exit the program cleanly

            # Process the user input query asynchronously
            await self.process_query(query)

    async def connect_to_server_and_run(self):
        """
        Connects to the MCP backend server over stdio and runs the chatbot interaction.
        - Starts the backend server process via MCP's stdio_client.
        - Initializes a ClientSession.
        - Fetches tool list and prepares it for LLM.
        - Launches the chat interaction loop.
        """
        server_params = StdioServerParameters(
            command="uv",               # Command to run the backend server
            args=["run", "research_server.py"]  # Args to pass to the server command
        )

        # Establish connection to backend using MCP stdio_client (runs server subprocess)
        async with stdio_client(server_params) as (read, write):
            # Create MCP client session using stdio read/write streams
            async with ClientSession(read, write) as session:
                self.session = session

                # Initialize the MCP session (handshake with server)
                await session.initialize()

                # Retrieve available tools from MCP backend
                tool_list = await session.list_tools()

                # Prepare the tools for the LLM in OpenAI function call format
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

                # Print tools available for function calls
                print("\nConnected to MCP server with tools:",
                      [tool["function"]["name"] for tool in self.available_tools])

                # Enter interactive chat loop with user
                await self.chat_loop()


# Entrypoint for running this bot as a script
async def main():
    bot = MCPChatBot()
    await bot.connect_to_server_and_run()


if __name__ == "__main__":
    # Run the async main() function using asyncio event loop
    asyncio.run(main())
