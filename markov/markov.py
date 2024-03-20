import aiosqlite
import discord
import redbot.core
from redbot.core import Config
from redbot.core import commands
import enum
import math
import random
import re
import unicodedata
from .errors import *

MAX_EXCLUSIONS_PER_GUILD = 50
MAX_TOKEN_GENERATION_ITERATIONS = 1000
MAX_TOKEN_LENGTH = 70


class ExclusionType(enum.Enum):
    BLACKLIST = enum.auto()
    IGNORE = enum.auto()


class Markov(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier="551742410770612234|085c218a-e850-4b07-9fc9-535c1b0d4c73"
        )
        self.config.register_guild(
            use_messages=False, blacklisted_strings=[], ignored_strings=[]
        )
        self.config.register_member(use_messages=True)
        self.config.register_channel(use_messages=False)

        self.db_path = redbot.core.data_manager.cog_data_path(self) / "markov.db"

    async def cog_load(self):
        with open(
            redbot.core.data_manager.bundled_data_path(self) / "init.sql", "r"
        ) as setup_script_file:
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(setup_script_file.read())
                await db.commit()

    @commands.Cog.listener()
    async def on_message_without_command(self, message):
        if message.guild is None:
            return

        if not await self.config.guild(message.guild).use_messages():
            return

        if not await self.config.channel(
            self.get_base_channel(message.channel)
        ).use_messages():
            return

        if not await self.config.member(message.author).use_messages():
            return

        if message.author.id == self.bot.user.id:
            return

        await self.process_message(message.content, message.guild.id, message.author.id)

    async def process_message(self, content: str, guild_id: int, member_id: int):
        # Normalize
        content = unicodedata.normalize("NFKC", content)
        content = content.replace("’", "'")

        # Ignore messages with blacklisted strings
        for blacklisted_string in await self.config.guild_from_id(
            guild_id
        ).blacklisted_strings():
            if blacklisted_string in content:
                return

        # Strip out ignored strings
        for ignored_string in await self.config.guild_from_id(
            guild_id
        ).ignored_strings():
            content = content.replace(ignored_string, "")

        # Strip out URL-esque patterns - a run of characters without spaces that contains '://' within it
        content = re.sub(r"(?: |^)\w+:\/\/[^ ]+(?: |$)", " ", content)

        # Extract words, punctuation, custom emoji, and mentions as
        # individual tokens, then add a sentinel (empty string) on either end.
        # NOTE: if changing the punctuation in the regex, also change PUNCTUATION in append_token()
        tokens = (
            [""]
            + [
                token
                for token in re.findall(
                    r"[\w']+|[\.,!?\/;\(\)]|<a?:\w+:\d+>|<#\d+>|<@!?\d+>", content
                )
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
        byte_length, remainder = divmod(x.bit_length(), 8)
        if remainder:
            byte_length += 1
        return x.to_bytes(byte_length, byteorder="big", signed=False)

    def get_base_channel(self, channel_or_thread):
        if isinstance(channel_or_thread, discord.Thread):
            return channel_or_thread.parent
        return channel_or_thread

    def append_token(self, text, token):
        # NOTE: if changing PUNCTUATION, also change the regex in process_message() with the corresponding note
        PUNCTUATION = r".,!?/;()"
        if token == "/":
            text = text[:-1] + token
        elif token == "(":
            text += token
        elif token in PUNCTUATION:
            text = text[:-1] + token + " "
        else:
            text += token + " "
        return text

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
        channel_conf = self.config.channel(self.get_base_channel(ctx.channel))
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

    async def exclusion_get_config_value(self, ctx, exclusion_type: ExclusionType):
        config_value = None
        match exclusion_type:
            case ExclusionType.BLACKLIST:
                config_value = self.config.guild(ctx.guild).blacklisted_strings()
            case ExclusionType.IGNORE:
                config_value = self.config.guild(ctx.guild).ignored_strings()
            case _:
                raise ValueError(
                    "exclusion_type must be one of ExclusionType.BLACKLIST,"
                    f" ExclusionType.IGNORE (got {exclusion_type})"
                )
        return config_value

    async def exclusion_add(self, ctx, exclusion_type: ExclusionType, string: str):
        if not string:
            await ctx.reply("Error: the string must have length greater than 0.")
            return

        config_value = await self.exclusion_get_config_value(ctx, exclusion_type)

        async with config_value as exclusion_list:
            if len(exclusion_list) >= MAX_EXCLUSIONS_PER_GUILD:
                await ctx.reply(
                    "Error: the maximum number of exclusions of this type has already been reached"
                    f" ({MAX_EXCLUSIONS_PER_GUILD})."
                )
                return
            exclusion_list.append(string)
        await ctx.react_quietly("✅")

    async def exclusion_remove(self, ctx, exclusion_type: ExclusionType, num: int):
        config_value = await self.exclusion_get_config_value(ctx, exclusion_type)

        async with config_value as exclusion_list:
            try:
                string = exclusion_list[num - 1]
                del exclusion_list[num - 1]
            except IndexError:
                await ctx.reply("Error: invalid or nonexistent ID.")
            else:
                await ctx.react_quietly("✅")

    async def exclusion_list(self, ctx, exclusion_type: ExclusionType):
        config_value = await self.exclusion_get_config_value(ctx, exclusion_type)

        text = ""
        for i, string in enumerate(await config_value):
            text += f"{i + 1}. {repr(string)}\n"
        pages = list(
            redbot.core.utils.chat_formatting.pagify(
                discord.utils.escape_markdown(discord.utils.escape_mentions(text))
            )
        )

        if pages:
            await redbot.core.utils.menus.menu(ctx, pages)
        else:
            await ctx.reply("No results.")

    @markov.group()
    async def blacklist_string(self, _ctx):
        pass

    @blacklist_string.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def blacklist_string_add(self, ctx, *, blacklisted_string: str):
        """
        Exclude every message containing this string from processing.
        """
        await self.exclusion_add(ctx, ExclusionType.BLACKLIST, blacklisted_string)

    @blacklist_string.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def blacklist_string_remove(self, ctx, num: int):
        """
        Remove blacklisted string with ID num. You can see the IDs in `markov blacklisted_string list`.
        """
        await self.exclusion_remove(ctx, ExclusionType.BLACKLIST, num)

    @blacklist_string.command(name="list")
    @commands.admin_or_permissions(manage_guild=True)
    async def blacklist_string_list(self, ctx):
        """
        List all blacklisted strings.
        """
        await self.exclusion_list(ctx, ExclusionType.BLACKLIST)

    @markov.group()
    async def ignore_string(self, _ctx):
        pass

    @ignore_string.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def ignore_string_add(self, ctx, *, ignored_string: str):
        """
        Strip out ignored_string from message content before processing.
        Improper use of this can mess up your tokenization. Breaking your
        exclusion at word boundaries is recommended.
        """
        await self.exclusion_add(ctx, ExclusionType.IGNORE, ignored_string)

    @ignore_string.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def ignore_string_remove(self, ctx, num: int):
        """
        Remove ignored string with ID num. You can see the IDs in `markov ignored_string list`.
        """
        await self.exclusion_remove(ctx, ExclusionType.IGNORE, num)

    @ignore_string.command(name="list")
    @commands.admin_or_permissions(manage_guild=True)
    async def ignore_string_list(self, ctx):
        """
        List all ignored strings.
        """
        await self.exclusion_list(ctx, ExclusionType.IGNORE)

    @markov.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def delete_guild_data(self, ctx, confirmation: str | None):
        if confirmation != "YES_DELETE_IT_ALL":
            await ctx.reply(
                "This will delete **all** markov data for this Discord server."
                " Rerun this as `markov delete_guild_data YES_DELETE_IT_ALL`"
                " if you are sure."
            )
            return
        guild_id_bytes = self.uint_to_bytes(ctx.guild.id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM guild_total_completion_count WHERE guild_id = ?;",
                (guild_id_bytes,),
            )
            await db.execute(
                "DELETE FROM guild_pairs WHERE guild_id = ?;",
                (guild_id_bytes,),
            )
            await db.execute(
                "DELETE FROM member_total_completion_count WHERE guild_id = ?;",
                (guild_id_bytes,),
            )
            await db.execute(
                "DELETE FROM member_pairs WHERE guild_id = ?;",
                (guild_id_bytes,),
            )
            await db.commit()
        await ctx.reply("All markov data for this guild has been deleted.")

    @markov.command()
    async def generate(self, ctx, member: discord.Member | None):
        if not await self.config.guild(ctx.guild).use_messages():
            await ctx.reply("Not enabled in this guild.")
            return
        if member is not None:
            if not await self.config.member(member).use_messages():
                await ctx.reply("That member has opted out of markov generation.")
                return

        async def get_total_completion_count(
            db: aiosqlite.Connection,
            guild_id: int,
            member_id: int | None,
            first_token: str,
        ):
            if not member_id:
                row = await (
                    await db.execute(
                        "SELECT total_completion_count FROM guild_total_completion_count"
                        " WHERE guild_id = ? AND first_token = ?;",
                        (self.uint_to_bytes(guild_id), first_token),
                    )
                ).fetchone()
            else:
                row = await (
                    await db.execute(
                        "SELECT total_completion_count FROM member_total_completion_count"
                        " WHERE guild_id = ? AND member_id = ? AND first_token = ?;",
                        (
                            self.uint_to_bytes(guild_id),
                            self.uint_to_bytes(member_id),
                            first_token,
                        ),
                    )
                ).fetchone()
            return row[0] if row else None

        async def get_possible_next_token(
            db: aiosqlite.Connection,
            guild_id: int,
            member_id: int | None,
            first_token: str,
            offset: int,
        ):
            if not member_id:
                row = await (
                    await db.execute(
                        "SELECT second_token, frequency FROM guild_pairs"
                        " WHERE guild_id = ? AND first_token = ?"
                        " ORDER BY frequency DESC LIMIT 1 OFFSET ?;",
                        (self.uint_to_bytes(guild_id), first_token, offset),
                    )
                ).fetchone()
            else:
                row = await (
                    await db.execute(
                        "SELECT second_token, frequency FROM member_pairs"
                        " WHERE guild_id = ? AND member_id = ? AND first_token = ?"
                        " ORDER BY frequency DESC LIMIT 1 OFFSET ?;",
                        (
                            self.uint_to_bytes(guild_id),
                            self.uint_to_bytes(member_id),
                            first_token,
                            offset,
                        ),
                    )
                ).fetchone()
            if not row:
                return None, None
            next_token, frequency = row
            return next_token, frequency

        member_id = member.id if member else None
        result = ""
        token = ""
        async with aiosqlite.connect(self.db_path) as db:
            while True:
                completion_count = await get_total_completion_count(
                    db, ctx.guild.id, member_id, token
                )
                if completion_count is None:
                    if token == "":
                        await ctx.reply(
                            f"Error: no data for this {'member' if member else 'guild'} yet!"
                        )
                        return
                    raise NoTotalCompletionCountError(ctx.guild.id, member_id, token)
                next_token = None
                for i in range(MAX_TOKEN_GENERATION_ITERATIONS):
                    next_token, frequency = await get_possible_next_token(
                        db, ctx.guild.id, member_id, token, i
                    )
                    if next_token is None:
                        raise NoNextTokenError(ctx.guild.id, member_id, token, i)
                    if random.randint(1, completion_count) <= frequency:
                        result = self.append_token(result, next_token)
                        token = next_token
                        break

                    completion_count -= frequency
                    if completion_count <= 0:
                        raise InvalidCompletionCountError(
                            ctx.guild.id, member_id, token, i
                        )
                else:
                    # If we went through MAX_TOKEN_GENERATION_ITERATIONS completions
                    # without selecting any, then just select the last one we considered
                    # (round off the probability, effectively)
                    token = next_token
                if token == "":
                    break
        await ctx.send(result, allowed_mentions=discord.AllowedMentions.none())
