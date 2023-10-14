from .pindelegate import PinDelegate


async def setup(bot):
    await bot.add_cog(PinDelegate(bot))
