from .markov import Markov


async def setup(bot):
    await bot.add_cog(Markov(bot))
