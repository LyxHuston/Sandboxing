"""
the easy level of challenge!  Importing any module is allowed.
"""

a = object()  # retrieve this from the sandboxed import!

if __name__ == '__main__':
    import sandbox_import

    sandbox = sandbox_import.RestrictedImport(allowed_imports_by_path={'*': '*'})

    sol = sandbox("solution")

    print(a is sol.get_a())