class NoSuchSuggestionError(Exception):
    def __init__(self, suggestion_id: int):
        self.suggestion_id = suggestion_id

    def __repr__(self):
        return f"NoSuchSuggestionError({self.suggestion_id})"

    def __str__(self):
        return f"Error: no suggestion with id {self.suggestion_id} found in suggestion queue."


class QuestionLimitReachedError(Exception):
    def __init__(self, question_limit: int):
        self.question_limit = question_limit

    def __repr__(self):
        return f"QuestionLimitReachedError({self.question_limit})"

    def __str__(self):
        return f"Error: there are already {self.question_limit} questions in the main queue; can't add more."
