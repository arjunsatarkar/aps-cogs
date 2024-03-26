import discord
from redbot.core import commands
import redbot.core


class Teleport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def teleport(
        self,
        ctx: commands.GuildContext,
        destination: discord.abc.GuildChannel | discord.Thread,
        *,
        topic: str | None,
    ):
        if isinstance(destination, discord.Thread):
            parent = destination.parent
        else:
            parent = destination

        if not (
            hasattr(destination, "send")
            and parent.permissions_for(ctx.author).send_messages
            and (
                not isinstance(destination, discord.Thread)
                or parent.permissions_for(ctx.author).send_messages_in_threads
            )
        ) or (
            (type(ctx.channel) is type(destination))
            and ctx.channel.id == destination.id
        ):
            await ctx.react_quietly("❌")
            return

        formatted_topic = (
            redbot.core.utils.chat_formatting.italics(topic) if topic else ""
        )

        # The space before the colon is necessary to prevent unwanted embeds
        # of the link due to the way Discord parses messages as of 2024-03-24.
        portal_to_template = (
            "Portal opened to {dest}"
            + (f" : {formatted_topic}" if formatted_topic else "")
            + f"\n*(done by {ctx.author.mention})*"
        )
        source_message = await ctx.send(
            portal_to_template.format(dest=destination.mention),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        dest_message = await destination.send(
            f"Portal opened from {source_message.jump_url}"
            + (f" : {formatted_topic}" if formatted_topic else "")
            + f"\n*(done by {ctx.author.mention})*",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await source_message.edit(
            content=portal_to_template.format(dest=dest_message.jump_url),
            allowed_mentions=discord.AllowedMentions.none(),
        )
