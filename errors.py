"""
errors for when a sandboxed module is trying to break out of the sandbox
"""


class RestrictedAccessError(Exception):
    """
    raised when something is trying to break out of the sandbox
    """
    pass