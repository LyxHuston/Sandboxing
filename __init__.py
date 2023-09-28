"""
The initialization module for the sandboxing package.  Collects relevant pieces.
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

the hope is to eventually get this into a position to widely distribute it.  So
that's why this file exists.

Anyways...

restricted file access: not started

imported modules: in progress

network access: not started

globally allowed and disallowed modules for import: done (simple) (see notes in
file, not as safe as other options)
"""

from restrict_global_imports import set_allowed, set_disallowed
import sandbox_import

__all__ = ["sandbox_import", "set_allowed", "set_disallowed"]