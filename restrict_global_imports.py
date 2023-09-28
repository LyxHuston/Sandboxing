"""
for if you want to restrict imports from any possible file, not just specific
ones

NOTE: this also alters the module cache in order to prevent people from importing already imported modules that are disallowed
"""

import sys
import errors


__all__ = ["set_allowed", "set_disallowed"]


_mode = True  # True for disallowed, False for allowed
_lst = []


class _Restrict:
    """
    class that handles restricting the imports
    """

    @classmethod
    def find_spec(cls, name, path, target=None):
        match _mode, name in _lst:
            case True, True:
                raise errors.RestrictedAccessError(f"Module '{name}' is disallowed from import.")
            case False, False:
                raise errors.RestrictedAccessError(f"Module '{name}' is not allowed for import.")
        return None


def set_disallowed(dalst: list[str]):
    """
    sets a disallowed list for the restricted imports
    note: set 'sys' in here so that people can't access sys.meta_path and remove the checker
    :param dalst: disallowed modules
    :return:
    """
    global _mode
    _mode = True
    _lst.clear()
    _lst.extend(dalst)
    for module in dalst:
        if module in sys.modules:
            del sys.modules[module]


def set_allowed(alst: list[str]):
    """
    sets an allowed list for the restricted imports
    note: do not set 'sys' in here so that people can't access sys.meta_path and remove the checker
    :param alst: disallowed modules
    :return:
    """
    global _mode
    _mode = False
    _lst.clear()
    _lst.extend(alst)
    module_check = tuple(sys.modules.keys())
    for module in module_check:
        if module not in alst:
            del sys.modules[module]


sys.meta_path.insert(0, _Restrict)