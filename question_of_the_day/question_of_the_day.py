import discord
from discord.ext import tasks
from redbot.core import Config
from redbot.core import commands
import redbot.core
import copy
import datetime
import logging
import pathlib
import random
import time
import typing
from .errors import *

MAX_QUESTIONS_PER_GUILD = 1000
MAX_QUESTION_SIZE = 500
ICON_PATH = pathlib.Path("abstract_swirl/abstract_swirl_160x160.png")


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
            latest_qotd_message_info={"channel_id": None, "message_id": None},
        )
        self.config.register_global(last_posted_qotds_at=None, guild_to_post_at={})
        self.post_qotds_loop.start()

    async def cog_unload(self):
        self.post_qotds_loop.cancel()

    @tasks.loop(seconds=30)
    async def post_qotds_loop(self):
        async def post_qotds_for_time(hour, minute):
            try:
                guilds_due = (await self.config.guild_to_post_at())[
                    repr((hour, minute))
                ].keys()
            except KeyError:
                guilds_due = []

            for guild_id in guilds_due:
                guild = await self.bot.fetch_guild(int(guild_id))
                if await self.config.guild(guild).enabled():
                    channel_id = await self.config.guild(guild).post_in_channel()
                    if not channel_id:
                        self.logger.info(
                            f"QOTD was due for guild {guild.name} ({guild_id}) but no channel was set, so it was not posted."
                        )
                    channel = await guild.fetch_channel(channel_id)
                    await self.send_question_to_channel(channel)

        current_time = time.time()

        current_datetime = datetime.datetime.fromtimestamp(
            current_time, datetime.timezone.utc
        )
        hour = current_datetime.hour
        minute = current_datetime.minute

        last_posted_time = await self.config.last_posted_qotds_at()
        last_posted_datetime = (
            datetime.datetime.fromtimestamp(last_posted_time, datetime.timezone.utc)
            if last_posted_time
            else None
        )
        if not last_posted_datetime or not (
            hour == last_posted_datetime.hour and minute == last_posted_datetime.minute
        ):
            await post_qotds_for_time(hour, minute)

            gap_secs = current_time - (
                last_posted_time if last_posted_time is not None else current_time
            )
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
    @commands.guild_only()
    async def qotd(self, _ctx: commands.GuildContext):
        """
        Base for all question of the day commands.
        """
        pass

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def add(self, ctx: commands.GuildContext, *, question: str):
        """
        Add a question directly to the main queue (requires elevated permissions).
        """
        if not await self.check_and_handle_question_length(ctx, question):
            return
        async with self.config.guild(ctx.guild).questions() as questions:
            if len(questions) >= MAX_QUESTIONS_PER_GUILD:
                await ctx.reply(
                    f"Error: too many questions already added in this server! Max is {MAX_QUESTIONS_PER_GUILD}."
                )
                return
            questions.append({"question": question, "asked_by": ctx.author.id})
        await ctx.tick()

    @qotd.command()
    async def list(self, ctx: commands.GuildContext):
        """
        Show questions in the main queue.
        """
        pages = await self.paginate_questions(
            ctx, await self.config.guild(ctx.guild).questions()
        )
        if pages:
            await redbot.core.utils.menus.menu(ctx, pages)
        else:
            await ctx.reply("No questions yet.")

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def remove(self, ctx: commands.GuildContext, question_id: int):
        """
        Remove a question from the queue using its id (see `qotd list`).
        """
        async with self.config.guild(ctx.guild).questions() as questions:
            try:
                del questions[question_id - 1]
                await ctx.reply(f"Deleted question {question_id}.")
            except IndexError:
                await ctx.reply(f"Error: no question with id {question_id}.")

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def post(self, ctx: commands.GuildContext):
        """
        Post a question immediately.

        A question will still be sent at the scheduled time if automatic posting is enabled.
        """
        channel_id = await self.config.guild(ctx.guild).post_in_channel()
        if channel_id:
            await self.send_question_to_channel(
                await ctx.guild.fetch_channel(channel_id)
            )
        else:
            await ctx.reply(
                "Error: no channel set! Use `qotd post_here` in the intended channel first."
            )

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def post_at(
        self,
        ctx: commands.GuildContext,
        hour_after_midnight_utc: int,
        minute_after_hour: int,
    ):
        """Set the time to post a QOTD every day in this server."""
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
                f"The bot will post the question of the day at {hour_after_midnight_utc:0>2}:{minute_after_hour:0>2} UTC."
            )
        else:
            await ctx.reply(
                "Error: the conditions 0 ≤ hours < 24 and 0 ≤ minutes < 60 must be observed."
            )

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def post_here(self, ctx: commands.GuildContext):
        """
        Set the current channel as where QOTDs should be posted.
        """
        if isinstance(ctx.channel, discord.TextChannel):
            await self.config.guild(ctx.guild).post_in_channel.set(ctx.channel.id)
            await ctx.reply("Questions of the day will be posted in this channel.")
        else:
            await ctx.reply("Error: must use a text channel.")

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def toggle(self, ctx: commands.GuildContext):
        """
        Turn on or off automatic posting of questions of the day in this server.
        """
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
    async def suggest(self, ctx: commands.GuildContext, *, question: str):
        """
        Add a question to the suggestion queue (it can be approved or denied by moderators).
        """
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
        await ctx.tick()

    @qotd.command()
    async def suggestions(self, ctx: commands.GuildContext):
        """
        View all questions in the suggestion queue.
        """
        pages = await self.paginate_questions(
            ctx, await self.config.guild(ctx.guild).suggested_questions()
        )
        if pages:
            await redbot.core.utils.menus.menu(ctx, pages)
        else:
            await ctx.reply("No suggested questions yet.")

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def approve(
        self, ctx: commands.GuildContext, suggestion_id: int | typing.Literal["all"]
    ):
        """
        Approve a suggestion using its id (see `qotd suggestions`).

        This adds the suggestion to the main queue.
        """

        async def approve_suggestion(
            suggested_questions: list[dict], suggestion_id: int
        ) -> str:
            try:
                suggested_question = suggested_questions[suggestion_id - 1]
            except IndexError:
                raise NoSuchSuggestionError(suggestion_id)
            approved_suggestion_text = suggested_question["question"]
            async with self.config.guild(ctx.guild).questions() as questions:
                if len(questions) >= MAX_QUESTIONS_PER_GUILD:
                    raise QuestionLimitReachedError
                else:
                    questions.append(suggested_question)
                    del suggested_questions[suggestion_id - 1]
            return approved_suggestion_text

        async with self.config.guild(
            ctx.guild
        ).suggested_questions() as suggested_questions:
            if suggestion_id == "all":
                for _ in range(len(suggested_questions)):
                    try:
                        await approve_suggestion(suggested_questions, 1)
                    except (NoSuchSuggestionError, QuestionLimitReachedError) as e:
                        await ctx.reply(str(e))
                        return
                await ctx.reply("Approved all suggestions!")
            else:
                try:
                    approved_suggestion_text = await approve_suggestion(
                        suggested_questions, suggestion_id
                    )
                except (NoSuchSuggestionError, QuestionLimitReachedError) as e:
                    await ctx.reply(str(e))
                    return
                await ctx.reply(
                    f"Approved suggestion {suggestion_id}:\n"
                    + redbot.core.utils.chat_formatting.quote(approved_suggestion_text),
                    allowed_mentions=discord.AllowedMentions.none(),
                )

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def deny(self, ctx: commands.GuildContext, suggestion_id: int):
        """
        Decline a suggestion and remove it from the suggestion queue.

        For the suggestion's id, see `qotd suggestions`.
        """
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

    async def send_question_to_channel(self, channel):
        guild = channel.guild
        async with self.config.guild(guild).questions() as questions:
            questions_len = len(questions)
            if not questions_len:
                await channel.send("**Question of the day: no questions left!**")
            else:
                question_index = random.randrange(0, questions_len)
                question = questions[question_index]

                embed = discord.Embed(
                    description=question["question"]
                    + "\n"
                    + redbot.core.utils.chat_formatting.italics(
                        "asked by "
                        + (await guild.fetch_member(question["asked_by"])).mention
                    )
                )
                embed.set_author(
                    name="Question of the Day",
                    icon_url=f"attachment://{ICON_PATH.name}",
                )
                questions_left = questions_len - 1
                footer = f"{questions_left} question{'' if questions_left == 1 else 's'} left | "
                suggestions_count = len(
                    await self.config.guild(guild).suggested_questions()
                )
                footer += (
                    f"{suggestions_count} suggestion{'s' if suggestions_count > 1 else ''}"
                    if suggestions_count
                    else "no suggestions yet! use qotd suggest"
                )
                embed.set_footer(text=footer)

                message = await channel.send(
                    embed=embed,
                    file=discord.File(
                        redbot.core.data_manager.bundled_data_path(self) / ICON_PATH,
                        ICON_PATH.name,
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )

                del questions[question_index]
                await self.manage_qotd_pins(message)
                self.logger.info(f"Posted QOTD for guild {guild.name} ({guild.id}).")

    async def manage_qotd_pins(self, new_message):
        guild = new_message.guild
        async with self.config.guild(
            guild
        ).latest_qotd_message_info() as latest_qotd_message_info:
            if (
                latest_qotd_message_info["channel_id"] is not None
                and latest_qotd_message_info["message_id"] is not None
            ):
                channel = await guild.fetch_channel(
                    latest_qotd_message_info["channel_id"]
                )
                try:
                    old_message = await channel.fetch_message(
                        latest_qotd_message_info["message_id"]
                    )
                    await old_message.unpin(reason="Unpinning old question of the day.")
                except (discord.Forbidden, discord.NotFound):
                    pass
            try:
                await new_message.pin(reason="Pinning new question of the day.")
            except (discord.Forbidden, discord.NotFound):
                pass
            latest_qotd_message_info["channel_id"] = new_message.channel.id
            latest_qotd_message_info["message_id"] = new_message.id

    async def paginate_questions(self, ctx: commands.GuildContext, questions: list):
        return [
            *redbot.core.utils.chat_formatting.pagify(
                discord.utils.escape_mentions(
                    "\n".join(
                        [
                            f"{i + 1}. {redbot.core.utils.chat_formatting.bold(question['question'])} by "
                            + (ctx.guild.get_member(question["asked_by"])).name
                            + f" ({question['asked_by']})"
                            for i, question in enumerate(questions)
                        ]
                    )
                )
            )
        ]

    async def check_and_handle_question_length(
        self, ctx: commands.GuildContext, question: str
    ):
        if len(question.encode("utf-8")) > MAX_QUESTION_SIZE:
            await ctx.reply(
                f"Error: that question is too long! Maximum length is {MAX_QUESTION_SIZE} bytes."
            )
            return False
        return True
