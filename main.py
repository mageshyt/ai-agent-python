from cli import CLI
from llm.client import LLMProvider
from asyncio import run
from typing import Any
import click

async def run_main(
        messages:list[dict[str, Any]],
        stream: bool = True
        ):
     llm = LLMProvider()
     async for event in  llm.send_message(messages, stream):
         print(event)

     print("Done")

@click.command()
@click.option('--stream', is_flag=True, help='Whether to stream the response or not')
@click.option('--prompt', default="What is the capital of France?", help='The prompt to send to the LLM')
def main(
        stream: bool,
        prompt: str
        ):

    cli = CLI()
    message = [
        {
            "role": "user",
            "content": prompt
        }
    ]

    if prompt:
        run(cli.run_single(prompt))


if __name__ == "__main__":
    main()

