from provider.llm_provider import LLMProvider
from asyncio import run

async def main():
    llm = LLMProvider()
    message = [
        {"role": "user", "content": "What is the capital of France?"}
    ]

    async for event in  llm.send_message(message, stream=True):
        print(event)

    print("Done")

if __name__ == "__main__":
    run(main())

