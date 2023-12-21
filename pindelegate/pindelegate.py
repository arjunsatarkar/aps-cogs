import discord
from redbot.core import Config
from redbot.core import checks
from redbot.core import commands


class PinDelegate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier="551742410770612234|6772870d-1739-4ada-a2c5-1821b4f3a618"
        )
        self.config.register_channel(pin_capable_members={})

    @commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def pindelegate(self, ctx, user: discord.Member):
        """
        Grant a user the ability to pin messages in this channel with the pin command.
        """
        async with self.config.channel(
            ctx.channel
        ).pin_capable_members() as pin_capable_members:
            pin_capable_members[user.id] = True
        await ctx.reply(
            f"User {user.name} ({user.id}) is now pin-capable in this channel."
        )

    @commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def pinundelegate(self, ctx, user: discord.Member):
        """
        Remove a user's ability to pin messages in this channel.
        """
        async with self.config.channel(
            ctx.channel
        ).pin_capable_members() as pin_capable_members:
            try:
                del pin_capable_members[str(user.id)]
            except KeyError:
                await ctx.reply(
                    f"User {user.name} ({user.id}) was already not pin-capable in this channel."
                )
                return
        await ctx.reply(
            f"User {user.name} ({user.id}) removed from pin-capable users in this channel."
        )

    async def is_pin_capable(self, channel, member_id):
        try:
            await self.config.channel(channel).pin_capable_members.get_raw(
                str(member_id)
            )
        except KeyError:
            return False
        return True

    @commands.command()
    async def pin(self, ctx):
        """
        Pin the replied-to message.
        """
        if await self.is_pin_capable(ctx.channel, ctx.author.id):
            await ctx.message.reference.resolved.pin()

    @commands.command()
    async def unpin(self, ctx):
        """
        Unpin the replied-to message.
        """
        replied_to_message = ctx.message.reference.resolved
        if await self.is_pin_capable(ctx.channel, ctx.author.id):
            if replied_to_message.pinned:
                await replied_to_message.unpin()
                await ctx.reply("Unpinned message!")
            else:
                await ctx.reply("That message was already not pinned.")
