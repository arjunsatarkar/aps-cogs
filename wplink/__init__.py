from .wplink import WPLink


async def setup(bot):
    await bot.add_cog(WPLink(bot))
