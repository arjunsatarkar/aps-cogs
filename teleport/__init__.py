from .teleport import Teleport


async def setup(bot):
    await bot.add_cog(Teleport(bot))
