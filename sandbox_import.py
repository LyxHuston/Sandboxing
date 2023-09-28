"""
attempting to create an import statement that will alter the imported module to
restrict access to files, imported modules, network access, and recursively alter any imported modules to be the same

restricted files: Not started

imported modules: not started

network access: not started
"""


from importlib import __import__
# __import__ = importlib.import_module
# __import__ = None
# import_stmt = None

# import errors
errors = __import__("errors")
import test

raise errors.RestrictedAccessError()