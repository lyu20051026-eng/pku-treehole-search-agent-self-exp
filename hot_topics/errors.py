"""Public diagnostics contain no authentication headers or provider response bodies."""


class HotModelError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
