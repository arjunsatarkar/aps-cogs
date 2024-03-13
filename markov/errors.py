class MarkovGenerationError(Exception):
    def __init__(self, guild_id: int, member_id: int | None):
        self.guild_id = guild_id
        self.member_id = member_id

    def __repr__(self):
        return f"MarkovGenerationError(guild_id={self.guild_id}, member_id={self.member_id})"


class NoTotalCompletionCountError(MarkovGenerationError):
    def __init__(self, guild_id: int, member_id: int | None, token: str):
        super().__init__(guild_id, member_id)
        self.token = token

    def __repr__(self):
        return (
            "NoTotalCompletionCountError(guild_id={}, member_id={}, token={})".format(
                self.guild_id, self.member_id, repr(self.token)
            )
        )


class NoNextTokenError(MarkovGenerationError):
    def __init__(self, guild_id: int, member_id: int | None, token: str, offset: int):
        super().__init__(guild_id, member_id)
        self.token = token
        self.offset = offset

    def __repr__(self):
        return (
            "NoNextTokenError(guild_id={}, member_id={}, token={}, offset={})".format(
                self.guild_id, self.member_id, repr(self.token), self.offset
            )
        )


class InvalidCompletionCountError(MarkovGenerationError):
    def __init__(self, guild_id: int, member_id: int | None, token: str, offset: int):
        super().__init__(guild_id, member_id)
        self.token = token
        self.offset = offset

    def __repr__(self):
        return "InvalidCompletionCountError(guild_id={}, member_id={}, token={}, offset={})".format(
            self.guild_id, self.member_id, repr(self.token), self.offset
        )
