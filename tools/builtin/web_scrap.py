from urllib.parse import urlparse
import httpx

from config.config import Config
from lib import  MAX_FILE,resolve_path, IGNORED_DIRECTORIES
from lib.contants.config import MAX_CONTENT_SIZE
from lib.paths import MAX_FILE_SIZE
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

class WebScrapParams(BaseModel):
    url : str = Field(
            ..., 
            description= 'The URL of the webpage to scrape content from.',
    )

    timeout : int = Field(
            10,
            ge=1,
            le=60,
            description="The maximum time in seconds to wait for a response from the server. Default is 10 seconds."
    )


class WebScrapTool(Tool):
    name = "web_scrap"
    description = (
            "Scrape the content of a webpage given its URL. Returns the raw HTML content of the page."
            "Note: This tool is intended for scraping static content. It does not execute JavaScript, so it may not capture dynamically loaded content. "
            "Use this for simple pages or when you only need the initial HTML. "
            "For more complex scraping needs, consider using a headless browser or a specialized scraping tool."
    )
    kind = ToolKind.NETWORK
    schema = WebScrapParams


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebScrapParams(**invocation.params)

        try:
            parsed_url = urlparse(params.url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return ToolResult.error_result(f"Invalid URL: '{params.url}'")

            async with httpx.AsyncClient(timeout=params.timeout) as client:
                response = await client.get(params.url)
                response.raise_for_status()  # Raise an error for bad status codes

                # truncate content if it's too large to prevent excessive memory usage
                content = response.text
                if len(content) > MAX_CONTENT_SIZE:
                    content = content[:MAX_CONTENT_SIZE] + "\n\n[Content truncated due to size limits]"

                return ToolResult.success_result(
                    content,
                    truncated = len(response.text) > MAX_CONTENT_SIZE,
                    metadata={
                    "url": params.url,
                    "status_code": response.status_code,
                })


        except httpx.RequestError as e:
            return ToolResult.error_result(f"An error occurred while requesting the URL: {str(e)}")
        except httpx.HTTPStatusError as e:
            return ToolResult.error_result(f"Received bad status code {e.response.status_code} for URL: {str(e)}")
        except Exception as e:
            return ToolResult.error_result(f"An unexpected error occurred: {str(e)}")




if __name__ == "__main__":
    import asyncio
    config = Config()
    tool = WebScrapTool(config)
    invocation = ToolInvocation(
        params={"url": "https://pms.exilenext.com"},
        cwd='.'
    )

    result = asyncio.run(tool.execute(invocation))
    print(result)

