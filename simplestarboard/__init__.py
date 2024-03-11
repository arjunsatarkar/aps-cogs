from .starboard import SimpleStarboard


async def setup(bot):
    await bot.add_cog(SimpleStarboard(bot))
