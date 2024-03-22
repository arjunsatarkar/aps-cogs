import discord
from redbot.core import commands


class Teleport(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    async def teleport(
        self,
        ctx: commands.GuildContext,
        destination: discord.abc.GuildChannel | discord.Thread,
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
        ):
            await ctx.react_quietly("❌")
            return

        portal_to_template = "Portal opened to {dest}\n*(done by {user})*"
        source_message = await ctx.send(
            portal_to_template.format(
                dest=destination.mention, user=ctx.author.mention
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        dest_message = await destination.send(
            f"Portal opened from {source_message.jump_url}\n*(done by {ctx.author.mention})*",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await source_message.edit(
            content=portal_to_template.format(
                dest=dest_message.jump_url, user=ctx.author.mention
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
