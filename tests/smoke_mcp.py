"""Real stdio handshake; no browser required."""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "ie_mode_mcp.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            assert len(result.tools) == 21, [t.name for t in result.tools]
            assert 'browser_choose_file' in [t.name for t in result.tools]
            result = await session.call_tool("environment_check", {})
            assert not result.isError
            result = await session.call_tool("browser_snapshot", {})
            assert result.isError
            print("PASS: stdio handshake, 21 tools, diagnostics and missing-session error")


asyncio.run(main())
