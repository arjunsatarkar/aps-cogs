import aiohttp
import discord
from redbot.core import commands
import re
import urllib.parse


class WPLink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        wikilink_pattern = r"\[\[(.+)\]\]"
        match = re.search(wikilink_pattern, message.content)
        if match is not None:
            title = match.group(1)
            page_url = await self.look_up_page(title)
            if page_url is not None:
                await message.reply(
                    page_url, allowed_mentions=discord.AllowedMentions.none()
                )

    async def look_up_page(self, title: str) -> str | None:
        query_url = f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(title)}&go=Go"
        async with aiohttp.ClientSession() as session:
            async with session.get(query_url) as response:
                result_url = str(response.url)
                return (
                    result_url
                    if not result_url.startswith(
                        "https://en.wikipedia.org/wiki/Special:Search?"
                    )
                    else None
                )
