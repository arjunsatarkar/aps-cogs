class MarkovGenerationError(Exception):
    pass


class NoTotalCompletionCountError(MarkovGenerationError):
    pass


class NoNextTokenError(MarkovGenerationError):
    pass


class InvalidCompletionCountError(MarkovGenerationError):
    pass
