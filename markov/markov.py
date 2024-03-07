import aiosqlite
import discord
import redbot.core
from redbot.core import Config
from redbot.core import commands
import math
import random
import re
import unicodedata
from .errors import *

MAX_BLACKLISTED_STRINGS_PER_GUILD = 50
MAX_TOKEN_GENERATION_ITERATIONS = 1000
MAX_TOKEN_LENGTH = 70


class Markov(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier="551742410770612234|085c218a-e850-4b07-9fc9-535c1b0d4c73"
        )
        self.config.register_guild(use_messages=False, blacklisted_strings=[])
        self.config.register_member(use_messages=True)
        self.config.register_channel(use_messages=False)

        self.db_path = redbot.core.data_manager.cog_data_path(self) / "markov.db"

    async def cog_load(self):
        with open(
            redbot.core.data_manager.bundled_data_path(self) / "init.sql", "r"
        ) as setup_script_file:
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(setup_script_file.read())

    @commands.Cog.listener()
    async def on_message_without_command(self, message):
        if message.guild is None:
            return
        if not await self.config.guild(message.guild).use_messages():
            return
        if not await self.config.channel(message.channel).use_messages():
            return
        if not await self.config.member(message.author).use_messages():
            return
        if message.author.id == self.bot.user.id:
            return

        await self.process_message(
            message.clean_content, message.guild.id, message.author.id
        )

    async def process_message(self, clean_content: str, guild_id: int, member_id: int):
        # Normalize
        clean_content = unicodedata.normalize("NFKC", clean_content)
        clean_content = clean_content.replace("’", "'")

        # Ignore messages with blacklisted strings
        for blacklisted_string in await self.config.guild_from_id(
            guild_id
        ).blacklisted_strings():
            if blacklisted_string in clean_content:
                return

        # Strip out URL-esque patterns - a run of characters without spaces that contains '://' within it
        clean_content = re.sub(r"(?: |^)\w+:\/\/[^ ]+(?: |$)", " ", clean_content)

        # Extract words, punctuation, and custom emoji as individual
        # tokens, then add sentinel (empty string) on either end.
        # NOTE: if changing the punctuation in the regex, also change PUNCTUATION in generate()
        tokens = (
            [""]
            + [
                token
                for token in re.findall(r"[\w']+|[\.,!?\/]|<:\w+:\d+>", clean_content)
                if len(token) <= MAX_TOKEN_LENGTH
            ]
            + [""]
        )

        if len(tokens) <= 2:
            return

        async with aiosqlite.connect(self.db_path) as db:
            for i in range(len(tokens) - 1):
                first_token = tokens[i]
                second_token = tokens[i + 1]

                await db.execute(
                    "INSERT INTO guild_pairs(guild_id, first_token, second_token, frequency)"
                    " VALUES (?, ?, ?, 1)"
                    " ON CONFLICT(guild_id, first_token, second_token)"
                    " DO UPDATE SET frequency = frequency + 1;",
                    (self.uint_to_bytes(guild_id), first_token, second_token),
                )
                await db.execute(
                    "INSERT INTO guild_total_completion_count(guild_id, first_token, total_completion_count)"
                    " VALUES(?, ?, 1)"
                    " ON CONFLICT(guild_id, first_token)"
                    " DO UPDATE SET total_completion_count = total_completion_count + 1;",
                    (self.uint_to_bytes(guild_id), first_token),
                )

                await db.execute(
                    "INSERT INTO member_pairs(guild_id, member_id, first_token, second_token, frequency)"
                    " VALUES (?, ?, ?, ?, 1)"
                    " ON CONFLICT(guild_id, member_id, first_token, second_token)"
                    " DO UPDATE SET frequency = frequency + 1;",
                    (
                        self.uint_to_bytes(guild_id),
                        self.uint_to_bytes(member_id),
                        first_token,
                        second_token,
                    ),
                )
                await db.execute(
                    "INSERT INTO member_total_completion_count(guild_id, member_id, first_token, total_completion_count)"
                    " VALUES(?, ?, ?, 1)"
                    " ON CONFLICT(guild_id, member_id, first_token)"
                    " DO UPDATE SET total_completion_count = total_completion_count + 1;",
                    (
                        self.uint_to_bytes(guild_id),
                        self.uint_to_bytes(member_id),
                        first_token,
                    ),
                )

                await db.commit()

    def uint_to_bytes(self, x: int):
        if x < 0:
            raise ValueError(f"x must be non-negative (got {x})")
        return x.to_bytes(math.ceil(x.bit_length() / 8), byteorder="big", signed=False)

    @commands.group()
    async def markov(self, _ctx):
        """
        Base for all markov commands.
        """
        pass

    @markov.command()
    async def optout(self, ctx):
        """
        Opt out of processing your messages to build Markov chains.
        """
        await self.config.member(ctx.author).use_messages.set(False)
        await ctx.reply(
            "Words in your messages will no longer be processed by the markov cog.\n"
            f"You can use `{ctx.clean_prefix}markov optin` to opt back in."
        )

    @markov.command()
    async def optin(self, ctx):
        """
        Opt in to processing your messages to build Markov chains. (This is the default.)
        """
        await self.config.member(ctx.author).use_messages.set(True)
        await ctx.reply(
            "Words in your messages will now be processed by the markov cog.\n"
            f"You can use `{ctx.clean_prefix}markov optout` to opt out."
        )

    @markov.command()
    @commands.admin_or_can_manage_channel()
    async def toggle_channel(self, ctx):
        """
        Enable/disable processing in this channel (must be enabled for the guild
        using toggle_guild as well).
        """
        channel_conf = self.config.channel(ctx.channel)
        new_state = not (await channel_conf.use_messages())
        await channel_conf.use_messages.set(new_state)
        await ctx.reply(
            f"This channel will be {'processed' if new_state else 'ignored'} by the markov cog."
        )

    @markov.command()
    @commands.admin_or_permissions(manage_server=True)
    async def enable_all_channels(self, ctx):
        """
        Enable processing in all channels. You can disable the undesired ones individually.
        The default for a new channel will remain disabled.
        """
        for channel in await ctx.guild.fetch_channels():
            await self.config.channel(channel).use_messages.set(True)
        await ctx.reply("Enabled markov processing in all existing channels.")

    @markov.command()
    @commands.admin_or_permissions(manage_server=True)
    async def disable_all_channels(self, ctx):
        """
        Disable processing in all channels. You can enable the desired ones individually.
        """
        for channel in await ctx.guild.fetch_channels():
            await self.config.channel(channel).use_messages.set(False)
        await ctx.reply("Disabled markov processing in all existing channels.")

    @markov.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def toggle_guild(self, ctx):
        """
        Enable/disable the markov cog in this guild. You still need to enable processing
        of each channel with toggle_channel or enable_all_channels/disable_all_channels.
        """
        guild_conf = self.config.guild(ctx.guild)
        new_state = not (await guild_conf.use_messages())
        await guild_conf.use_messages.set(new_state)
        await ctx.reply(
            f"The markov cog is now {'enabled' if new_state else 'disabled'} in this guild."
        )

    @markov.group()
    async def blacklist_string(self, _ctx):
        pass

    @blacklist_string.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def add(self, ctx, *, blacklisted_string: str):
        """
        Exclude every message containing this string from processing.
        """
        if not blacklisted_string:
            await ctx.reply("Error: blacklisted_string must have length greater than 0")
            return
        async with self.config.guild(
            ctx.guild
        ).blacklisted_strings() as blacklisted_strings:
            if len(blacklisted_strings) >= MAX_BLACKLISTED_STRINGS_PER_GUILD:
                await ctx.reply(
                    "Error: you already have the maximum number of blacklisted strings in this guild"
                    f" ({MAX_BLACKLISTED_STRINGS_PER_GUILD})."
                )
                return
            blacklisted_strings.append(blacklisted_string)
        await ctx.reply(f"Added that to the blacklisted strings for this guild.")

    @blacklist_string.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def remove(self, ctx, num: int):
        """
        Remove blacklisted string with ID num. You can see the IDs in `markov blacklisted_string list`.
        """
        async with self.config.guild(
            ctx.guild
        ).blacklisted_strings() as blacklisted_strings:
            string = blacklisted_strings[num - 1]
            try:
                del blacklisted_strings[num - 1]
            except IndexError:
                await ctx.reply("Error: no blacklisted string with that ID exists.")
            else:
                await ctx.reply(
                    f"Removed {repr(string)} from your blacklisted strings."
                )

    @blacklist_string.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def list(self, ctx):
        text = ""
        for i, question in enumerate(
            await self.config.guild(ctx.guild).blacklisted_strings()
        ):
            text += f"{i + 1}. {repr(question)}\n"
        pages = list(redbot.core.utils.chat_formatting.pagify(text))

        if pages:
            message = await ctx.reply(".")
            await redbot.core.utils.menus.menu(ctx, pages, message=message)
        else:
            await ctx.reply("No blacklisted strings yet.")

    @markov.command()
    async def generate(self, ctx, member: discord.Member | None):
        if not await self.config.guild(ctx.guild).use_messages():
            await ctx.reply("Not enabled in this guild.")
            return
        if member is not None:
            if not await self.config.member(member).use_messages():
                await ctx.reply("That member has opted out of markov generation.")
                return

        # NOTE: if changing PUNCTUATION, also change the regex in process_message() with the corresponding note
        PUNCTUATION = ".,!?/"
        if member is None:
            result = ""
            token = ""
            async with aiosqlite.connect(self.db_path) as db:
                while True:
                    row = await (
                        await db.execute(
                            "SELECT total_completion_count FROM guild_total_completion_count"
                            " WHERE guild_id = ? AND first_token = ?;",
                            (self.uint_to_bytes(ctx.guild.id), token),
                        )
                    ).fetchone()
                    if row is None:
                        if token == "":
                            await ctx.reply("Error: no data for this guild yet!")
                            return
                        raise MarkovGenerationError(
                            "Table guild_total_completion_count had no row for token"
                            f" {repr(token)} for guild {ctx.guild.id} - this should never happen!"
                        )
                    completion_count = row[0]

                    for i in range(MAX_TOKEN_GENERATION_ITERATIONS):
                        row = await (
                            await db.execute(
                                "SELECT second_token, frequency FROM guild_pairs"
                                " WHERE guild_id = ? AND first_token = ?"
                                " ORDER BY frequency DESC LIMIT 1 OFFSET ?;",
                                (self.uint_to_bytes(ctx.guild.id), token, i),
                            )
                        ).fetchone()
                        if row is None:
                            raise MarkovGenerationError(
                                "There was no completion in guild_pairs for token"
                                f" {repr(token)} for guild {ctx.guild.id} on iteration {i}"
                                " - this should never happen!"
                            )
                        next_token, frequency = row

                        if random.randint(1, completion_count) <= frequency:
                            if next_token in PUNCTUATION:
                                result = result[:-1] + next_token + " "
                            else:
                                result += next_token + " "
                            token = next_token
                            break

                        completion_count -= frequency
                        if completion_count <= 0:
                            raise MarkovGenerationError(
                                "Sum of all frequencies in guild_pairs for token"
                                f" {repr(token)} in guild {ctx.guild.id} added up"
                                " to more than completion_count or we failed to"
                                " choose a completion despite trying all of them"
                                " This should never happen!"
                            )
                    else:
                        token = ""

                    if token == "":
                        break
            await ctx.send(result, allowed_mentions=discord.AllowedMentions.none())
        else:
            result = ""
            token = ""
            async with aiosqlite.connect(self.db_path) as db:
                while True:
                    row = await (
                        await db.execute(
                            "SELECT total_completion_count FROM member_total_completion_count"
                            " WHERE guild_id = ? AND member_id = ? AND first_token = ?;",
                            (
                                self.uint_to_bytes(ctx.guild.id),
                                self.uint_to_bytes(member.id),
                                token,
                            ),
                        )
                    ).fetchone()
                    if row is None:
                        if token == "":
                            await ctx.reply("Error: no data for this member yet!")
                            return
                        raise MarkovGenerationError(
                            "Table member_total_completion_count had no row for token"
                            f" {repr(token)} for guild {ctx.guild.id} member {member.id}"
                            " - this should never happen!"
                        )
                    completion_count = row[0]

                    next_token = None
                    for i in range(MAX_TOKEN_GENERATION_ITERATIONS):
                        row = await (
                            await db.execute(
                                "SELECT second_token, frequency FROM member_pairs"
                                " WHERE guild_id = ? AND member_id = ? AND first_token = ?"
                                " ORDER BY frequency DESC LIMIT 1 OFFSET ?;",
                                (
                                    self.uint_to_bytes(ctx.guild.id),
                                    self.uint_to_bytes(member.id),
                                    token,
                                    i,
                                ),
                            )
                        ).fetchone()
                        if row is None:
                            raise MarkovGenerationError(
                                "There was no completion in guild_pairs for token"
                                f" {repr(token)} for guild {ctx.guild.id} member {member.id}"
                                f" on iteration {i} - this should never happen!"
                            )
                        next_token, frequency = row

                        if random.randint(1, completion_count) <= frequency:
                            if next_token in PUNCTUATION:
                                result = result[:-1] + next_token + " "
                            else:
                                result += next_token + " "
                            token = next_token
                            break

                        completion_count -= frequency
                        if completion_count <= 0:
                            raise MarkovGenerationError(
                                "Sum of all frequencies in guild_pairs for token"
                                f" {repr(token)} for guild {ctx.guild.id} member"
                                f" {member.id} added up to more than completion_count"
                                " or we failed to choose a completion despite trying"
                                " all of them. This should never happen!"
                            )
                    else:
                        # If we went through MAX_TOKEN_GENERATION_ITERATIONS completions
                        # without selecting any, then just select the last one we considered
                        # (round off the probability, effectively).
                        token = next_token

                    if token == "":
                        break
            await ctx.send(result, allowed_mentions=discord.AllowedMentions.none())
