import discord
from discord.ext import tasks
from redbot.core import Config
from redbot.core import checks
from redbot.core import commands
import redbot.core
import copy
import datetime
import logging
import random
import time

MAX_QUESTIONS_PER_GUILD = 1000
MAX_QUESTION_SIZE = 500


class QuestionOfTheDay(commands.Cog):
    def __init__(self, bot):
        self.logger = logging.getLogger("red.aps-cogs.question_of_the_day")
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier="551742410770612234|038a0658-85c9-416d-93ea-7c0bdb426734"
        )
        self.config.register_guild(
            questions=[],
            suggested_questions=[],
            post_at={"hour": 0, "minute": 0},
            post_in_channel=None,
            enabled=False,
        )
        self.config.register_global(last_posted_qotds_at=None, guild_to_post_at={})
        self.post_qotds.start()

    async def cog_unload(self):
        self.post_qotds.cancel()

    @tasks.loop(seconds=30)
    async def post_qotds(self):
        async def post_qotds_for_time(hour, minute):
            try:
                guilds_due = (await self.config.guild_to_post_at())[
                    repr((hour, minute))
                ].keys()
            except KeyError:
                guilds_due = []

            for guild_id in guilds_due:
                guild = await self.bot.fetch_guild(int(guild_id))
                channel_id = await self.config.guild(guild).post_in_channel()
                if not channel_id:
                    self.logger.info(
                        f"QOTD was due for guild {guild.name} ({guild_id}) but no channel was set, so it was not posted."
                    )
                async with self.config.guild(guild).questions() as questions:
                    channel = await guild.fetch_channel(channel_id)
                    questions_len = len(questions)
                    if not questions_len:
                        await channel.send(
                            "# Question of the Day\n**No questions left!**"
                        )
                        continue
                    question_index = random.randrange(0, questions_len)
                    question = questions[question_index]
                    await channel.send(
                        f"# Question of the Day\n"
                        f"{question['question']}\n{redbot.core.utils.chat_formatting.italics((await guild.fetch_member(question['asked_by'])).name)}"
                        f" ({question['asked_by']})"
                    )
                    del questions[question_index]
                    self.logger.info(
                        f"Posted QOTD for guild {guild.name} ({guild_id})."
                    )

        current_time = time.time()

        current_datetime = datetime.datetime.fromtimestamp(
            current_time, datetime.timezone.utc
        )
        hour = current_datetime.hour
        minute = current_datetime.minute

        last_posted_time = await self.config.last_posted_qotds_at()
        last_posted_datetime = datetime.datetime.fromtimestamp(
            last_posted_time, datetime.timezone.utc
        )
        if not (
            hour == last_posted_datetime.hour and minute == last_posted_datetime.minute
        ):
            await post_qotds_for_time(hour, minute)

            gap_secs = current_time - (last_posted_time or current_time)
            if gap_secs >= 60:
                # Posts may have been missed; recover them up to an hour
                self.logger.info(f"Detected gap of {gap_secs} seconds.")
                gap_minutes = min(int(gap_secs / 60), 60)
                for _ in range(gap_minutes):
                    minute -= 1
                    if minute < 0:
                        minute = 59
                        hour -= 1
                    await post_qotds_for_time(hour, minute)

        await self.config.last_posted_qotds_at.set(current_time)

    @commands.group()
    async def qotd(self, _ctx):
        pass

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def add(self, ctx, *, question: str):
        if not await self.check_and_handle_question_length(ctx, question):
            return
        async with self.config.guild(ctx.guild).questions() as questions:
            if len(questions) >= MAX_QUESTIONS_PER_GUILD:
                await ctx.reply(
                    f"Error: too many questions already added in this server! Max is {MAX_QUESTIONS_PER_GUILD}."
                )
                return
            questions.append({"question": question, "asked_by": ctx.author.id})
        await ctx.reply("Question added!")

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def list(self, ctx):
        pages = await self.paginate_questions(
            ctx, await self.config.guild(ctx.guild).questions()
        )
        if pages:
            await redbot.core.utils.menus.menu(ctx, pages)
        else:
            await ctx.reply("No questions yet.")

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def remove(self, ctx, question_id: int):
        async with self.config.guild(ctx.guild).questions() as questions:
            try:
                del questions[question_id - 1]
                await ctx.reply(f"Deleted question {question_id}.")
            except IndexError:
                await ctx.reply(f"Error: no question with id {question_id}.")

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def post_at(self, ctx, hour_after_midnight_utc: int, minute_after_hour: int):
        if (
            hour_after_midnight_utc >= 0
            and hour_after_midnight_utc < 24
            and minute_after_hour >= 0
            and minute_after_hour < 60
        ):
            async with self.config.guild(ctx.guild).post_at() as post_at:
                old_post_at = copy.copy(post_at)
                post_at["hour"] = hour_after_midnight_utc
                post_at["minute"] = minute_after_hour
                async with self.config.guild_to_post_at() as guild_to_post_at:
                    try:
                        del guild_to_post_at[
                            repr((old_post_at["hour"], old_post_at["minute"]))
                        ][repr(ctx.guild.id)]
                    except KeyError:
                        pass
                    try:
                        guild_to_post_at[(hour_after_midnight_utc, minute_after_hour)][
                            ctx.guild.id
                        ] = 1
                    except KeyError:
                        guild_to_post_at[
                            (hour_after_midnight_utc, minute_after_hour)
                        ] = {ctx.guild.id: 1}
            await ctx.reply(
                f"The bot will post the question of the day {hour_after_midnight_utc:0>2}:{minute_after_hour:0>2} hours after midnight UTC."
            )
        else:
            await ctx.reply(
                "Error: the conditions 0 ≤ hours < 24 and 0 ≤ minutes < 60 must be observed."
            )

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def post_here(self, ctx):
        await self.config.guild(ctx.guild).post_in_channel.set(ctx.channel.id)
        await ctx.reply("Questions of the day will be posted in this channel.")

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def toggle(self, ctx):
        should_be_enabled = not await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(should_be_enabled)
        post_at = await self.config.guild(ctx.guild).post_at()
        async with self.config.guild_to_post_at() as guild_to_post_at:
            try:
                guild_to_post_at[(post_at["hour"], post_at["minute"])][ctx.guild.id] = 1
            except KeyError:
                guild_to_post_at[(post_at["hour"], post_at["minute"])] = {
                    ctx.guild.id: 1
                }
        await ctx.reply(
            "QOTDs will be posted in this server (provided that the channel has been set with post_here)."
            if should_be_enabled
            else "QOTDs will no longer be posted."
        )

    @qotd.command()
    async def suggest(self, ctx, *, question: str):
        if not await self.check_and_handle_question_length(ctx, question):
            return
        async with self.config.guild(
            ctx.guild
        ).suggested_questions() as suggested_questions:
            if len(suggested_questions) >= MAX_QUESTIONS_PER_GUILD:
                await ctx.reply(
                    f"Error: too many questions already in the suggestion queue for this server! Max is {MAX_QUESTIONS_PER_GUILD}."
                )
                return
            suggested_questions.append(
                {"question": question, "asked_by": ctx.author.id}
            )
        await ctx.reply("Added question to suggestion queue!")

    @qotd.command()
    async def suggestions(self, ctx):
        pages = await self.paginate_questions(
            ctx, await self.config.guild(ctx.guild).suggested_questions()
        )
        if pages:
            await redbot.core.utils.menus.menu(ctx, pages)
        else:
            await ctx.reply("No suggested questions yet.")

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def approve(self, ctx, suggestion_id: int):
        async with self.config.guild(
            ctx.guild
        ).suggested_questions() as suggested_questions:
            try:
                suggested_question = suggested_questions[suggestion_id - 1]
            except IndexError:
                await ctx.reply(f"Error: no suggestion with id {suggestion_id}.")
                return
            async with self.config.guild(ctx.guild).questions() as questions:
                if len(questions) >= MAX_QUESTIONS_PER_GUILD:
                    await ctx.reply(
                        f"Error: there are already {MAX_QUESTIONS_PER_GUILD} questions in the main queue; can't approve suggestion."
                    )
                else:
                    questions.append(suggested_question)
                    del suggested_questions[suggestion_id - 1]
                    await ctx.reply(
                        f"Approved suggestion {suggestion_id}:\n"
                        + redbot.core.utils.chat_formatting.quote(
                            suggested_question["question"]
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )

    @qotd.command()
    @checks.admin_or_permissions(manage_server=True)
    async def deny(self, ctx, suggestion_id: int):
        async with self.config.guild(
            ctx.guild
        ).suggested_questions() as suggested_questions:
            try:
                question_text = suggested_questions[suggestion_id - 1]["question"]
                del suggested_questions[suggestion_id - 1]
                await ctx.reply(
                    f"Deleted suggestion {suggestion_id}:\n"
                    + redbot.core.utils.chat_formatting.quote(question_text),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except IndexError:
                await ctx.reply(f"Error: no suggestion with id {suggestion_id}.")

    async def paginate_questions(self, ctx, questions: list):
        return [
            x
            for x in redbot.core.utils.chat_formatting.pagify(
                redbot.core.utils.common_filters.filter_various_mentions(
                    "\n".join(
                        [
                            f"{i + 1}. {redbot.core.utils.chat_formatting.bold(question['question'])} by "
                            f"{redbot.core.utils.chat_formatting.bold(str(await ctx.guild.fetch_member(question['asked_by'])) + ' (' + str(question['asked_by']) + ')')}"
                            for i, question in enumerate(questions)
                        ]
                    )
                )
            )
        ]

    async def check_and_handle_question_length(self, ctx, question: str):
        if len(question.encode("utf-8")) > MAX_QUESTION_SIZE:
            await ctx.reply(
                f"Error: that question is too long! Maximum length is {MAX_QUESTION_SIZE} bytes."
            )
            return False
        return True
