"""
for if you want to restrict imports from any possible file, not just specific
ones
"""

import sys
import errors


__all__ = []


mode = True  # True for blacklist, False for whitelist
lst = []


class Restrict:
    """
    class that handles restricting the imports
    """

    @classmethod
    def find_spec(self, name, path, target=None):
        match mode, name in lst:
            case True, True:
                raise errors.RestrictedAccessError("That module is blacklisted from import.")
            case False, False:
                raise errors.RestrictedAccessError("That module is not whitelisted for import.")
        return None


sys.meta_path.insert(0, Restrict)