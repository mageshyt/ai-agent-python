from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from ddgs import DDGS
import asyncio


class WebSearchParams(BaseModel):
    query : str = Field(..., description="The search query to find content from websites")
    max_result : int =  Field(
            10,
            ge=1,
            le=50,
            description="The maximum number of search results to return. Default is 10."
    )

    page : int = Field(
            1,
            ge=1,
            description="The page number of search results to return. Default is 1."
    )

    safesearch : str = Field(
            "Off",
            description="Safe search setting. Can be 'Off', 'Moderate', or 'Strict'. Default is 'Off'."
    )

class WebSearchTool(Tool):
    name = "web_search"
    description = (
            "Search the web for content related to a query. Returns a list of search results with titles and URLs."

    )
    kind = ToolKind.NETWORK
    schema = WebSearchParams


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WebSearchParams(**invocation.params)

        def _do_search():
            ddgs = DDGS()
            return ddgs.text(
                    params.query,
                    region = "us-en",
                    safesearch = params.safesearch,
                    timelimit = "y",
                    page = params.page,
                    backend = "lite",
                    max_results=params.max_result
            )

        try:
            results = await asyncio.to_thread(_do_search)

            if not results:
                return ToolResult.success_result(f"No results found for query: '{params.query}'")

            output_results = []

            for idx , result  in enumerate(results):
                output_results.append({
                    "title": result["title"],
                    "url": result["href"],
                    "description": result["body"]
                })

            return ToolResult.success_result(
                    "\n".join([f"{idx+1}. {res['title']} - {res['url']}\n{res['description']}" for idx, res in enumerate(output_results)]),
                    metadata={
                        "results": output_results,
                        "query": params.query,
                        "max_result": params.max_result,
                        "page": params.page,
                        "safesearch": params.safesearch
                    }
                    )
                

        except Exception as e:
            return ToolResult.error_result(str(e))


if  __name__ == "__main__":
    import asyncio
    config = Config()
    tool = WebSearchTool(config)
    invocation = ToolInvocation(
            cwd= ".",
            params={
                "query": "ai agents",
                "max_result": "10",
            }
    )
    result = asyncio.run(tool.execute(invocation))
    print(result.to_model_output())








