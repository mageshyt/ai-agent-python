import logging
import sys
from typing import Any
import click

from pathlib import Path

logging.basicConfig(level=logging.WARN, format='%(name)s - %(levelname)s - %(message)s')

from cli import CLI
from config.loader import load_config
from asyncio import run

logger = logging.getLogger(__name__)


@click.command()
@click.option('--stream', is_flag=True, help='Whether to stream the response or not')
@click.option('--prompt', help='The prompt to send to the LLM')
@click.option('--cwd', '-c', type=click.Path(exists = True , file_okay = False , path_type = Path), help='The current working directory to use for the agent')
def main(stream: bool, prompt: str, cwd: Path):

    try:
        config = load_config(cwd)
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return

    erros = config.validate()
    if erros:
        for error in erros:
            logger.error(error)

        sys.exit(1)



    cli = CLI(config)
    try:
        if prompt:
            result = run(cli.run_single(prompt))
            if result is None:
                sys.exit(1)
        else:
            run(cli.run_interactive())
    except Exception as e:
        sys.exit(1)

if __name__ == "__main__":
    main()
