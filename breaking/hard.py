"""
the hard level of challenge!  No importing allowed.
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
"""

a = object()  # retrieve this from the sandboxed import!

if __name__ == '__main__':
    import sandbox_import

    sandbox = sandbox_import.RestrictedImport(allowed_imports_by_path={})

    solution = sandbox("solution")

    print(a is solution.get_a())