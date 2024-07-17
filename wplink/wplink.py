import aiohttp
import async_lru
import discord
from redbot.core import commands
import logging
import re
import urllib.parse


class WPLink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        WIKILINK_PATTERN = r"\[\[(.+?)\]\]"
        MAX_LINKS_PER_MESSAGE = 6
        # Per https://www.mediawiki.org/wiki/Page_title_size_limitations
        MAX_TITLE_LEN = 255

        titles = re.findall(WIKILINK_PATTERN, message.content)
        titles = titles[:MAX_LINKS_PER_MESSAGE]

        formatted_page_urls = []
        for title in titles:
            if len(title) > MAX_TITLE_LEN:
                continue
            page_url = await self.look_up_page(title)
            if page_url is not None:
                formatted_page_urls.append(f"<{page_url}>")

        if formatted_page_urls:
            await message.reply(
                ", ".join(formatted_page_urls),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @async_lru.alru_cache(maxsize=512)
    async def look_up_page(self, title: str) -> str | None:
        logging.info("Looking up page title %s", title)
        MAX_URL_SIZE = 400
        query_url = f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(title)}&go=Go"
        async with aiohttp.ClientSession() as session:
            async with session.head(query_url, allow_redirects=True) as response:
                if response.status != 200:
                    return None
                result_url = str(response.url)
                if len(result_url) > MAX_URL_SIZE or result_url.startswith(
                    "https://en.wikipedia.org/wiki/Special:Search?"
                ):
                    return None
                return result_url
