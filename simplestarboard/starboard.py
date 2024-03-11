import asyncio
import discord
import redbot.core
from redbot.core import Config
from redbot.core import commands


class SimpleStarboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier="551742410770612234|31374c1f-a5e9-470a-8fed-1137e980f27a"
        )
        self.config.register_guild(starboards={})

    def emoji_as_sendable_text(self, emoji: discord.Emoji | discord.PartialEmoji | str):
        if isinstance(emoji, str):
            return emoji
        if emoji.animated:
            return f"<a:{emoji.name}:{emoji.id}>"
        else:
            return f"<:{emoji.name}:{emoji.id}>"

    @commands.group()
    async def simplestarboard(self, _ctx):
        pass

    @simplestarboard.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def add(self, ctx, name: str, channel: discord.TextChannel, threshold: int):
        if threshold < 1:
            await ctx.reply("Error: threshold must be 1 or higher.")
            return
        async with self.config.guild(ctx.guild).starboards() as starboards:
            if name in starboards:
                await ctx.reply(
                    "Error: a starboard with that name already exists (see `starboard list`)."
                )
                return
            starboards[name] = {
                "channel_id": channel.id,
                "threshold": threshold,
                "allow_all_reactions": False,
                "reactions": {
                    "unicode": {},
                    "custom": {},
                },
            }

            wait_message_id = (
                await ctx.reply(
                    f"Creating starboard ``{name}`` posting to {channel.mention} requiring {threshold} reactions."
                    "\nReact to this message with all reactions you want the bot to consider for this starboard,"
                    " then send DONE, or else type ANY to check for all reactions. If you don't react, ⭐ will"
                    " be chosen by default.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            ).id

            try:
                done_message = await self.bot.wait_for(
                    "message",
                    check=lambda m: m.content.lower() in ["done", "any"],
                    timeout=120,
                )
            except asyncio.TimeoutError:
                await ctx.send(
                    f"Error: timed out; cancelling creation of starboard ``{name}``.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                del starboards[name]
                return

            # Accumulated to easily post the confirmation message
            emoji_text_list = []
            match done_message.content.lower():
                case "done":
                    reactions = (
                        await ctx.channel.fetch_message(wait_message_id)
                    ).reactions
                    if not reactions:
                        starboards[name]["reactions"]["unicode"]["⭐"] = 1
                        emoji_text_list.append("⭐")
                    else:
                        for reaction in reactions:
                            emoji = reaction.emoji
                            if isinstance(emoji, str):
                                starboards[name]["reactions"]["unicode"][emoji] = 1
                            else:
                                starboards[name]["reactions"]["custom"][emoji.id] = 1
                            emoji_text_list.append(self.emoji_as_sendable_text(emoji))
                case "any":
                    starboards[name]["allow_all_reactions"] = True

        confirmation_text = f"Created starboard ``{name}`` posting to {channel.mention} and requiring {threshold}"
        if not emoji_text_list:
            confirmation_text += " of any emoji."
        else:
            confirmation_text += f" reactions of {redbot.core.utils.chat_formatting.humanize_list(emoji_text_list, style='or')}."
        await ctx.send(
            confirmation_text, allowed_mentions=discord.AllowedMentions.none()
        )

    @simplestarboard.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def remove(self, ctx, name: str):
        async with self.config.guild(ctx.guild).starboards() as starboards:
            try:
                del starboards[name]
            except KeyError:
                await ctx.reply(
                    "Error: no starboard found with that name (see `starboard list`)."
                )
            else:
                await ctx.reply("Removed that starboard.")

    @simplestarboard.command()
    async def list(self, ctx):
        starboards = await self.config.guild(ctx.guild).starboards()
        list_text = "Name, Channel, Threshold, Reactions"
        for name in starboards:
            starboard = starboards[name]
            list_text += (
                f"\n* ``{name}``, {ctx.guild.get_channel(starboard['channel_id']).mention},"
                f" {starboard['threshold']}, "
            )
            if starboard["allow_all_reactions"]:
                list_text += "*any*"
            else:
                emoji_list = []
                for emoji in starboard["reactions"]["custom"]:
                    emoji_list.append(
                        self.emoji_as_sendable_text(self.bot.get_emoji(int(emoji)))
                    )
                for emoji in starboard["reactions"]["unicode"]:
                    emoji_list.append(emoji)
                list_text += redbot.core.utils.chat_formatting.humanize_list(emoji_list)
        pages = [
            *redbot.core.utils.chat_formatting.pagify(
                discord.utils.escape_mentions(list_text)
            )
        ]
        await redbot.core.utils.menus.menu(ctx, pages)
