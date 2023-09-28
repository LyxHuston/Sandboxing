import sandbox_import
import sys
import dataclasses
import errors

# print(sys.path_importer_cache)

# for finder in sys.meta_path:
#     print(getattr(finder, '__name__', None), sys.modules[finder.__module__])
# print(sys.meta_path)
#
# # print(set({'hello': 2}).union(set({"bye": 3})))
#
# print(sys.prefix)

print("pre-init")

sandbox = sandbox_import.RestrictedImport(allowed_imports_by_path={'*': ['importlib.*', '_imp', '_io', 'marshal', 'winreg', 'warnings', 'abc', '_py_abc', '_weakrefset', 'types', 'typing', 'collections', '_collections_abc']})

print("start")
for name in ["distutils", "os", "dataclasses", "errors", "test2"]:
    res = sandbox(name)
    print(res.__dict__.get("__builtins__", None)["__import__"])
# print(sandbox("distutils").__dict__.get("__builtins__", None)["__import__"])
# print(sandbox_import("os").__dict__.get("__builtins__", None)["__import__"])
# print(sandbox_import("dataclasses").__dict__.get("__builtins__", None)["__import__"])
# print(sandbox_import("errors").__dict__.get("__builtins__", None)["__import__"])
# print(sandbox_import("test2").__dict__.get("__builtins__", None)["__import__"])
print("end")