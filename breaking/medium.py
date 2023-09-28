"""
the medium level of challenge!  Importing any builtin module is allowed.
"""

a = object()  # retrieve this from the sandboxed import!

if __name__ == '__main__':
    import sandbox_import

    sandbox = sandbox_import.RestrictedImport(allowed_imports_by_path={'built-in': '*'})

    sol = sandbox("solution")

    print(a is sol.get_a())