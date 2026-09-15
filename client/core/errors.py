"""
Client Exception Hierarchy.
Provides clear user-facing messages and structured diagnostic error codes.
"""

class CopilotClientError(Exception):
    def __init__(self, message: str, code: str = "CLIENT_ERROR", user_hint: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.user_hint = user_hint or message


class AudioDeviceError(CopilotClientError):
    pass


class BackendConnectionError(CopilotClientError):
    pass


class PermissionDeniedError(CopilotClientError):
    pass
