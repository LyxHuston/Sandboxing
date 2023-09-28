"""
Errors that can be used by this program
Copyright (C) 2023  Lyx Huston

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or any later
versions.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

A copy of the GNU Affero General Public License is in LICENSE.txt.  If not, see
<https://www.gnu.org/licenses/>.

errors for when a sandboxed module is trying to break out of the sandbox.
Currently unused because... reasons.
"""


class RestrictedAccessError(Exception):
    """
    raised when something is trying to break out of the sandbox
    """
    pass