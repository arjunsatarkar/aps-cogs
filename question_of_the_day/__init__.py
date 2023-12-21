from .question_of_the_day import QuestionOfTheDay


async def setup(bot):
    await bot.add_cog(QuestionOfTheDay(bot))
