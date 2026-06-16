import asyncio
from multiprocessing import context
from AgentX.providers import OpenaiCompactProvider, ProviderSpec
from AgentX.tools.weather import WeatherTool
from AgentX.tools.registry import ToolRegistry
from AgentX.agent.runner import AgentRunSpec, AgentRunner
from AgentX.agent.loop import AgentCoreLoop
from AgentX.bus import InboundMessage, OutboundMessage, MessageBus
from AgentX.config.schema import AgentDefaults

async def on_stream(delta: str) -> None:
    print(f"Streamed delta: {delta}")


async def _stream(delta: str) -> None:
    await on_stream(delta)
# class CalculatorTool:
#     name = "calculator"

#     async def execute(self, a: int, b: int):
#         return a + b
    
# tools = [
#     {
#         "type": "function",
#         "function": {
#             "name": "weather",
#             "description": "Add two integers together",
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "a": {
#                         "type": "integer",
#                         "description": "First number"
#                     },
#                     "b": {
#                         "type": "integer",
#                         "description": "Second number"
#                     }
#                 },
#                 "required": ["a", "b"]
#             }
#         }
#     }
# ]

# async def main():
#     weather_tool = WeatherTool()
#     # print(weather_tool.to_schema())
#     # print("\n---\n")
#     # print(weather_tool.parameters)
#     # print("\n---\n")
#     # print(weather_tool.get_definitions())
#     registry = ToolRegistry()
#     registry.register(weather_tool)
#     # print(registry.get("weather"))
#     # print(registry.get("weather").to_schema())
#     # print("\n----\n")
#     # print(registry.get_definitions())


#     spec = ProviderSpec(
#         name="ollama",
#         keywords=("ollama", "nemotron"),
#         env_key="OLLAMA_API_KEY",
#         display_name="Ollama",
#         backend="openai_compat",
#         is_local=True,
#         detect_by_base_keyword="11434",
#         default_api_base="http://localhost:11434/v1",
#     )
#     messages=[{"role": "user", "content": "what's the weather in New York?"}]

#     specRunner = AgentRunSpec(
#         initial_messages=[{"role": "user", "content": "what's the weather in New York?"}], #You are a helpful assistant
#         tools=registry,
#         model="qwen3.5:4b-mlx",
#         max_iterations=5,
#         max_tool_result_chars=1000,
#         llm_timeout_s=30.0,
#         reasoning_effort=0.5,
#     )

#     provider = OpenaiCompactProvider(
#         api_key="ollama",
#         base_url="http://localhost:11434/v1",
#         spec=spec
#     )
#     runner =  AgentRunner(provider)
#     # response = await runner.run(specRunner)
#     # response = await runner._request_model(specRunner, messages)
#     # print(response)
#     # print("\n\n---\n\n")
#     # print(response.tool_calls)

#     # response = await provider.chat_stream(
#     #     model="qwen3.5:4b-mlx",
#     #     messages=[{"role": "user", "content": "what's the weather in New York?"}],
#     #     tools=[weather_tool.to_schema()],
#     #     tool_choice="auto",

#     #     on_content_delta=_stream
#     # )
#     # print(response)
#     msg = InboundMessage(
#         "cli",
#         "123",
#         "322",
#         "hello"
#     )
#     bus = MessageBus
#     loop = AgentCoreLoop.fromConfig(AgentDefaults, bus,)
    
#     loop.process_direct("hi")

async def main():
    spec = ProviderSpec(
        name="ollama",
        keywords=("ollama", "nemotron"),
        env_key="OLLAMA_API_KEY",
        display_name="Ollama",
        backend="openai_compat",
        is_local=True,
        detect_by_base_keyword="11434",
        default_api_base="http://localhost:11434/v1",
    )

    provider = OpenaiCompactProvider(default_model="qwen3.5:4b-mlx", api_key="ollama", base_url="http://localhost:11434/v1", spec=spec)
    tools = ToolRegistry()
    tools.register(WeatherTool())

    loop = AgentCoreLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=None,
    )

    msg = InboundMessage(
        channel="cli",
        sender_id="user",
        chat_id="direct",
        content="What's the weather in New York?",
        metadata={},
    )

    result = await loop._process_message(
        msg,
        tools=tools,
    )

    print(result)

if __name__ == "__main__":
    asyncio.run(main())
