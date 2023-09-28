# print("pre-init")
#
# sandbox = sandbox_import.RestrictedImport(allowed_imports_by_path={'*': ['_imp']})
#
# print("start")
# for name in ["test2"]:
#     res = sandbox(name)
#     builtin = res.__dict__.get("__builtins__", None)
#     if builtin is None:
#         print("None")
#     elif isinstance(builtin, dict):
#         print(builtin["__import__"])
#     else:
#         print(builtin.__import__)
# print("end")
import sandbox_import

sandbox = sandbox_import.RestrictedImport(allowed_imports_by_path={'*': '*'})

sandbox("test2")