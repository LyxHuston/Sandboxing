"""
attempting to create an import statement that will alter the imported module to
restrict access to files, imported modules, network access, and recursively alter any imported modules to be the same

restricted files: Not started

imported modules: starting

network access: not started

globally allowed and disallowed modules for import: done (simple)
"""

# TODO implement use of _setup() (https://happytest-apidoc.readthedocs.io/en/latest/_modules/_frozen_importlib_external/)

import _warnings
import _weakref
import builtins
import os
import sys
import _io
import marshal

import frozendict
import time
from importlib._bootstrap import _builtin_from_name
_imp = _builtin_from_name("_imp")


try:
    import _thread
except:
    _thread = None

from copy import deepcopy, copy

from typing import NewType, Any


_module_type = type(sys)
module = NewType('module', _module_type)

"""
typehint for a module
"""

"""
need to change in _builtins:
for importing:
loader
__import__
__loader__
__spec__.loader
for file editing:
input (temporarily removed)
open (temporarily removed)
print (temporarily removed)
for object editing:
memoryview (temporarily removed)
"""


_NEEDS_LOADING = object()
_ERR_MSG_PREFIX = 'No module named '
_ERR_MSG = _ERR_MSG_PREFIX + '{!r}'


class RestrictedImport:
    """
    a class for restricted import objects which are used to overwrite import and loading methods and keep track of modules loaded through this
    """

    __track = -1

    @property
    @classmethod
    def __counter(cls):
        cls.__track += 1
        return cls.__track

    @property
    def _sys(self):
        return self._local_module_cache['sys']

    @property
    def _builtins(self):
        return self._local_module_cache['builtins']

    def __init__(self, allowed_imports_by_path: dict[str: list[str]] = frozendict.frozendict(), disallowed_imports_by_path: dict[str: list[str]] = frozendict.frozendict(), use_deepcopy: bool = False, stdin = None, stdout = None):
        """
        create a restricted importer object
        :param allowed_imports_by_path:
        :param disallowed_imports_by_path:
        :param use_deepcopy:
        :param stdin:
        :param stdout:
        """

        self._use_deepcopy = use_deepcopy

        self.__path_decisions = {}
        all_keys = set(allowed_imports_by_path).union(set(disallowed_imports_by_path))
        for key in all_keys:
            self.__path_decisions[key] = (
                allowed_imports_by_path[key] if key in allowed_imports_by_path else [],
                disallowed_imports_by_path[key] if key in disallowed_imports_by_path else []
            )

        self.__sandbox_number = RestrictedImport.__counter.fget

        # make the required 'modules' with modified behavior
        self._local_module_cache: dict[str: module] = dict()
        _sys: module = self._module_copy(sys)  # TODO make better recursive searcher
        self.meta_path = []
        set_multiple_attrs(_sys, [
            ("modules", self._local_module_cache),
            ("stdin", stdin),
            ("__stdin__", stdin),
            ("stdout", stdout),
            ("__stdout__", stdout)
        ])
        self._local_module_cache[_sys.__name__] = _sys
        _builtins: module = self._module_copy(builtins)
        set_multiple_attrs(_builtins, [
            ("open", None),
            ("input", None),
            ("print", None),
            ("memoryview", None),
            ("__import__", self.make_import()),  # TODO this might be safe?
            ("__doc__", "Worked!")
        ])
        self._local_module_cache[_builtins.__name__] = _builtins

        self._sys.path_importer_cache = dict()
        self._sys.path_hooks = []  # not technically necessary, should be getting overwritten in __make_local_classes anyways

        self.__make_local_classes()

    def _module_copy(self, mod: module) -> module:
        """
        copies a module and any imported module that module has, replacing relevant parameters
        :param mod:
        :return:
        """
        cop = type(mod)(mod.__name__)
        # self._copy_between_dicts(cop.__dict__, mod.__dict__)
        for key in mod.__dict__:
            if isinstance(mod.__dict__[key], type(mod)):
                cop.__dict__[key] = self._module_copy(mod.__dict__[key])
            elif isinstance(mod.__dict__[key], dict) and key == "__builtins__":
                cop.__dict__[key] = {}
                self._copy_between_dicts(cop.__dict__[key], mod.__dict__[key])
            elif self._use_deepcopy:
                cop.__dict__[key] = deepcopy(mod.__dict__[key])
            else:
                cop.__dict__[key] = mod.__dict__[key]
        cop.__import__ = None
        cop.__loader__ = None
        cop.__spec__ = copy(mod.__spec__)
        cop.__spec__.loader = None
        return cop

    def _copy_between_dicts(self, cop: dict, mod: dict):
        for key in mod:
            if isinstance(mod[key], type(sys)):
                cop[key] = self._module_copy(mod[key])
            elif isinstance(mod[key], dict) and key == "__builtins__":
                cop[key] = {}
                self._copy_between_dicts(cop[key], mod[key])
            elif self._use_deepcopy:
                cop[key] = deepcopy(mod[key])
            else:
                cop[key] = mod[key]
        cop["__import__"] = None
        cop["__loader__"] = None
        cop["__spec__"] = copy(mod["__spec__"])
        cop["__spec__"].loader = None
        return cop

    def __call__(self, name, globals=None, locals=None, fromlist=(), level=0):  # TODO potential safety concern in globals or locals
        """Import a module.

        The 'globals' argument is used to infer where the import is occurring from
        to handle relative imports. The 'locals' argument is ignored. The
        'fromlist' argument specifies what should exist as attributes on the module
        being imported (e.g. ``from module import <fromlist>``).  The 'level'
        argument represents the package location to import from in a relative
        import (e.g. ``from ..pkg import mod`` would have a 'level' of 2).

        """
        if level == 0:
            mod = self._gcd_import(name)
        else:
            globals_ = globals if globals is not None else {}
            package = _calc___package__(globals_)
            mod = self._gcd_import(name, package, level)
        if not fromlist:
            # Return up to the first dot in 'name'. This is complicated by the fact
            # that 'name' may be relative.
            if level == 0:
                return self._gcd_import(name.partition('.')[0])
            elif not name:
                return mod
            else:
                # Figure out where to slice the module's name up to the first dot
                # in 'name'.
                cut_off = len(name) - len(name.partition('.')[0])
                # Slice end needs to be positive to alleviate need to special-case
                # when ``'.' not in name``.
                return self._sys.modules[mod.__name__[:len(mod.__name__)-cut_off]]
        elif hasattr(mod, '__path__'):
            return self._handle_fromlist(mod, fromlist, self._gcd_import)
        else:
            return mod

    def make_import(self):

        def __import__(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0:
                mod = self._safe_gcd_import(name)
            else:
                globals_ = globals if globals is not None else {}
                package = _calc___package__(globals_)
                mod = self._gcd_import(name, package, level)
            if not fromlist:
                # Return up to the first dot in 'name'. This is complicated by the fact
                # that 'name' may be relative.
                if level == 0:
                    return self._safe_gcd_import(name.partition('.')[0])
                elif not name:
                    return mod
                else:
                    # Figure out where to slice the module's name up to the first dot
                    # in 'name'.
                    cut_off = len(name) - len(name.partition('.')[0])
                    # Slice end needs to be positive to alleviate need to special-case
                    # when ``'.' not in name``.
                    return self._sys.modules[mod.__name__[:len(mod.__name__) - cut_off]]
            elif hasattr(mod, '__path__'):
                return self._handle_fromlist(mod, fromlist, self._gcd_import)
            else:
                return mod

        return __import__

    def _safe_gcd_import(self, name, package=None, level=0):
        _sanity_check(name, package, level)
        if level > 0:
            name = _resolve_name(name, package, level)
        return self._safe_find_and_load(name, self._safe_gcd_import)

    def _gcd_import(self, name, package=None, level=0):  # TODO check for safety concerns (called in _handle_from_list)
        """Import and return the module based on its name, the package the call is
        being made from, and the level adjustment.

        This function represents the greatest common denominator of functionality
        between import_module and __import__. This includes setting __package__ if
        the loader did not.

        """
        _sanity_check(name, package, level)
        if level > 0:
            name = _resolve_name(name, package, level)
        return self._find_and_load(name, self._gcd_import)

    def _safe_find_and_load(self, name, import_):
        """Find and load the module."""
        with self._ModuleLockManager(name):
            mod = self._sys.modules.get(name, _NEEDS_LOADING)
            if mod is _NEEDS_LOADING:
                return self._safe_find_and_load_unlocked(name, import_)

        if mod is None:
            message = ('import of {} halted; '
                       'None in sys.modules'.format(name))
            raise ModuleNotFoundError(message, name=name)

        self._lock_unlock_module(name)
        return mod

    def _find_and_load(self, name, import_):
        """Find and load the module."""
        with self._ModuleLockManager(name):
            mod = self._sys.modules.get(name, _NEEDS_LOADING)
            if mod is _NEEDS_LOADING:
                return self._find_and_load_unlocked(name, import_)

        if mod is None:
            message = ('import of {} halted; '
                       'None in sys.modules'.format(name))
            raise ModuleNotFoundError(message, name=name)

        self._lock_unlock_module(name)
        return mod

    def _safe_find_and_load_unlocked(self, name, import_):
        path = None
        parent = name.rpartition('.')[0]
        if parent:
            if parent not in self._sys.modules:
                _call_with_frames_removed(import_, parent)
            # Crazy side-effects!
            if name in self._sys.modules:
                return self._sys.modules[name]
            parent_module = self._sys.modules[parent]
            try:
                path = parent_module.__path__
            except AttributeError:
                msg = (_ERR_MSG + '; {!r} is not a package').format(name, parent)
                raise ModuleNotFoundError(msg, name=name) from None
        spec = self._safe_find_spec(name, path)  # getting spec

        if spec is None:
            raise ModuleNotFoundError(_ERR_MSG.format(name), name=name)
        else:
            mod = self._load_unlocked(spec)  # loading
        if parent:
            # Set the module as an attribute on its parent.
            parent_module = self._sys.modules[parent]
            child = name.rpartition('.')[2]
            try:
                setattr(parent_module, child, mod)
            except AttributeError:
                msg = f"Cannot set an attribute on {parent!r} for child module {child!r}"
                _warnings.warn(msg, ImportWarning)
        return mod

    def _find_and_load_unlocked(self, name, import_):  # TODO potential safety thing (sys.modules)
        path = None
        parent = name.rpartition('.')[0]
        if parent:
            if parent not in self._sys.modules:
                _call_with_frames_removed(import_, parent)
            # Crazy side-effects!
            if name in self._sys.modules:
                return self._sys.modules[name]
            parent_module = self._sys.modules[parent]
            try:
                path = parent_module.__path__
            except AttributeError:
                msg = (_ERR_MSG + '; {!r} is not a package').format(name, parent)
                raise ModuleNotFoundError(msg, name=name) from None
        spec = self._find_spec(name, path)  # getting spec

        # pth = spec.origin
        # nme = spec.name
        # if '.' in pth:
        #     pth = pth[:pth.rindex('.')]
        # if pth.endswith(os.sep + nme):
        #     pth = pth[:-1 - len(nme)]

        if spec is None:
            raise ModuleNotFoundError(_ERR_MSG.format(name), name=name)
        else:
            mod = self._load_unlocked(spec)  # loading
        if parent:
            # Set the module as an attribute on its parent.
            parent_module = self._sys.modules[parent]
            child = name.rpartition('.')[2]
            try:
                setattr(parent_module, child, mod)
            except AttributeError:
                msg = f"Cannot set an attribute on {parent!r} for child module {child!r}"
                _warnings.warn(msg, ImportWarning)
        return mod

    def _handle_fromlist(self, module, fromlist, import_, *, recursive=False):
        """Figure out what __import__ should return.

        The import_ parameter is a callable which takes the name of module to
        import. It is required to decouple the function from assuming importlib's
        import implementation is desired.

        """
        # The hell that is fromlist ...
        # If a package was imported, try to import stuff from fromlist.
        for x in fromlist:
            if not isinstance(x, str):
                if recursive:
                    where = module.__name__ + '.__all__'
                else:
                    where = "``from list''"
                raise TypeError(f"Item in {where} must be str, "
                                f"not {type(x).__name__}")
            elif x == '*':
                if not recursive and hasattr(module, '__all__'):
                    self._handle_fromlist(module, module.__all__, import_, recursive=True)
            elif not hasattr(module, x):
                from_name = '{}.{}'.format(module.__name__, x)
                try:
                    _call_with_frames_removed(import_, from_name)
                except ModuleNotFoundError as exc:
                    # Backwards-compatibility dictates we ignore failed
                    # imports triggered by fromlist for modules that don't
                    # exist.
                    if (exc.name == from_name and
                            self._sys.modules.get(from_name, _NEEDS_LOADING) is not None):
                        continue
                    raise
        return module

    def _determine_allowed(self, spec):
        if spec is None:
            return None
        if spec.name == self._ImportLockContext.name:
            return spec
        pth = spec.origin
        nme = spec.name
        if '.' in pth:
            pth = pth[:pth.rindex('.')]
        if pth.endswith(os.sep + nme):
            pth = pth[:-1 - len(nme)]

        # always prefer not allowing, prefer specific path over general path
        allowed = False
        nme_splits = nme.split('.')
        if '*' in self.__path_decisions:
            if self.__path_decisions['*'][0] == '*':
                allowed = True
            else:
                allowed = False
                for i in range(len(nme_splits)):
                    if '.'.join(nme_splits[0:i + 1]) + '.*' in self.__path_decisions['*'][0]:
                        allowed = True
                        break
                else:
                    if nme in self.__path_decisions['*'][0]:
                        allowed = True
            if allowed:
                if self.__path_decisions['*'][1] == '*':
                    allowed = False
                else:
                    for i in range(len(nme_splits)):
                        if '.'.join(nme_splits[0:i + 1]) + '.*' in self.__path_decisions['*'][1]:
                            allowed = False
                            break
                    else:
                        if nme in self.__path_decisions['*'][1]:
                            allowed = False
        accuracy = 0
        rec_pth = ""
        for try_pth in self.__path_decisions:
            if len(try_pth) > accuracy and pth.startswith(try_pth):
                accuracy = len(try_pth)
                rec_pth = try_pth
        if accuracy > 0:
            if self.__path_decisions[rec_pth][0] == '*':
                allowed = True
            else:
                allowed = False
                for i in range(len(nme_splits)):
                    if '.'.join(nme_splits[0:i + 1]) + '.*' in self.__path_decisions[rec_pth][0]:
                        allowed = True
                        break
                else:
                    if nme in self.__path_decisions[rec_pth][0]:
                        allowed = True
            if allowed:
                if self.__path_decisions[rec_pth][1] == '*':
                    allowed = False
                    for i in range(len(nme_splits)):
                        if '.'.join(nme_splits[0:i + 1]) + '.*' in self.__path_decisions[rec_pth][1]:
                            allowed = False
                            break
                    else:
                        if nme in self.__path_decisions[rec_pth][1]:
                            allowed = False

        # if not allowed, sucks to suck, whatever the finder found
        return spec if allowed else None

    def _safe_find_spec(self, name, path, target=None):
        """Find a module's spec, trying to ignore modules that aren't allowed by filter"""
        meta_path = self._sys.meta_path
        if meta_path is None:
            # PyImport_Cleanup() is running or has been called.
            raise ImportError("sys.meta_path is None, Python is likely "
                              "shutting down")

        if not meta_path:
            _warnings.warn('sys.meta_path is empty', ImportWarning)

        # We check sys.modules here for the reload case.  While a passed-in
        # target will usually indicate a reload there is no guarantee, whereas
        # sys.modules provides one.
        is_reload = name in self._sys.modules
        for finder in meta_path:
            with self._ImportLockContext(None):
                try:
                    find_spec = finder.find_spec
                except AttributeError:
                    # raise ImportError(f"{_object_name(finder)}.find_spec() not found.")
                    spec = self._find_spec_legacy(finder, name,
                                                  path)  # deprecated implementation, deciding to remove for now
                    if spec is None:
                        continue
                else:
                    spec = find_spec(name, path, target)

            if spec is not None:

                # The parent import may have already imported this module.
                if not is_reload and name in self._sys.modules:
                    mod = self._local_module_cache[name]
                    try:
                        __spec__ = mod.__spec__
                    except AttributeError:
                        # We use the found spec since that is the one that
                        # we would have used if the parent module hadn't
                        # beaten us to the punch.
                        return spec
                    else:
                        if __spec__ is None:
                            return spec
                        else:
                            return __spec__
                else:
                    return spec
        else:
            return None

    def _find_spec(self, name, path, target=None):  # TODO this is important to look into, because it's using the loaders.  loaders will need to be customly defined
        """Find a module's spec."""
        # traceback.print_stack()
        meta_path = self._sys.meta_path
        # meta_path = sys.meta_path
        if meta_path is None:
            # PyImport_Cleanup() is running or has been called.
            raise ImportError("sys.meta_path is None, Python is likely "
                              "shutting down")

        if not meta_path:
            _warnings.warn('sys.meta_path is empty', ImportWarning)

        # We check sys.modules here for the reload case.  While a passed-in
        # target will usually indicate a reload there is no guarantee, whereas
        # sys.modules provides one.
        is_reload = name in self._sys.modules
        for finder in meta_path:
            with self._ImportLockContext(name):
                try:
                    find_spec = finder.find_spec
                except AttributeError:
                    # raise ImportError(f"{_object_name(finder)}.find_spec() not found.")
                    spec = self._find_spec_legacy(finder, name, path)  # deprecated implementation, deciding to remove for now
                    if spec is None:
                        continue
                else:
                    spec = find_spec(name, path, target)
            if spec is not None:
                # The parent import may have already imported this module.
                if not is_reload and name in self._sys.modules:
                    mod = self._local_module_cache[name]
                    try:
                        __spec__ = mod.__spec__
                    except AttributeError:
                        # We use the found spec since that is the one that
                        # we would have used if the parent module hadn't
                        # beaten us to the punch.
                        return spec
                    else:
                        if __spec__ is None:
                            return spec
                        else:
                            return __spec__
                else:
                    return spec
        else:
            return None

    def _find_spec_legacy(self, finder, name, path):  # deprecated implementation, deciding to remove for now
        msg = (f"{_object_name(finder)}.find_spec() not found; "
               "falling back to find_module()")
        _warnings.warn(msg, ImportWarning)
        loader = finder.find_module(name, path)
        if loader is None:
            return None
        return self.spec_from_loader(name, loader)

    def _load_unlocked(self, spec):
        # A helper for direct use by the import system.
        if spec.loader is not None:
            # Not a namespace package.
            if not hasattr(spec.loader, 'exec_module'):
                # raise ImportError(f"{_object_name(spec.loader)}.exec_module() not found.")
                msg = f"{_object_name(spec.loader)}.exec_module() not found; falling back to load_module()"
                _warnings.warn(msg, ImportWarning)
                return self._load_backward_compatible(spec)

        mod = self.module_from_spec(spec)

        # This must be done before putting the module in sys.modules
        # (otherwise an optimization shortcut in import.c becomes
        # wrong).
        spec._initializing = True
        try:
            self._sys.modules[spec.name] = mod
            try:
                if spec.loader is None:
                    if spec.submodule_search_locations is None:
                        raise ImportError('missing loader', name=spec.name)
                    # A namespace package so do nothing.
                else:
                    spec.loader.exec_module(mod)
            except:
                try:
                    del self._sys.modules[spec.name]
                except KeyError:
                    pass
                raise
            # Move the module to the end of sys.modules.
            # We don't ensure that the import-related module attributes get
            # set in the sys.modules replacement case.  Such modules are on
            # their own.
            mod = self._sys.modules.pop(spec.name)
            self._sys.modules[spec.name] = mod
            _verbose_message('import {!r} # {!r}', spec.name, spec.loader)
        finally:
            spec._initializing = False

        return mod

    def _load_backward_compatible(self, spec):
        # It is assumed that all callers have been warned about using load_module()
        # appropriately before calling this function.
        try:
            spec.loader.load_module(spec.name)
        except:
            if spec.name in self._sys.modules:
                mod = self._sys.modules.pop(spec.name)
                self._sys.modules[spec.name] = mod
            raise
        # The module must be in sys.modules at this point!
        # Move it to the end of sys.modules.
        mod = self._sys.modules.pop(spec.name)
        self._sys.modules[spec.name] = mod
        if getattr(mod, '__loader__', None) is None:
            try:
                mod.__loader__ = spec.loader
            except AttributeError:
                pass
        if getattr(mod, '__package__', None) is None:
            try:
                # Since module.__path__ may not line up with
                # spec.submodule_search_paths, we can't necessarily rely
                # on spec.parent here.
                mod.__package__ = mod.__name__
                if not hasattr(mod, '__path__'):
                    mod.__package__ = spec.name.rpartition('.')[0]
            except AttributeError:
                pass
        if getattr(mod, '__spec__', None) is None:
            try:
                mod.__spec__ = spec
            except AttributeError:
                pass
        return mod

    def replace_builtins(self, mod):
        # if hasattr(mod, '__builtins__'):
        setattr(mod, '__builtins__', self._builtins)
        return mod

    def __make_local_classes(outer):

        # ModuleSpec ##################################################################

        class ModuleSpec:
            """The specification for a module, used for loading.

            A module's spec is the source for information about the module.  For
            data associated with the module, including source, use the spec's
            loader.

            `name` is the absolute name of the module.  `loader` is the loader
            to use when loading the module.  `parent` is the name of the
            package the module is in.  The parent is derived from the name.

            `is_package` determines if the module is considered a package or
            not.  On modules this is reflected by the `__path__` attribute.

            `origin` is the specific location used by the loader from which to
            load the module, if that information is available.  When filename is
            set, origin will match.

            `has_location` indicates that a spec's "origin" reflects a location.
            When this is True, `__file__` attribute of the module is set.

            `cached` is the location of the cached bytecode file, if any.  It
            corresponds to the `__cached__` attribute.

            `submodule_search_locations` is the sequence of path entries to
            search when importing submodules.  If set, is_package should be
            True--and False otherwise.

            Packages are simply modules that (may) have submodules.  If a spec
            has a non-None value in `submodule_search_locations`, the import
            system will consider modules loaded from the spec as packages.

            Only finders (see importlib.abc.MetaPathFinder and
            importlib.abc.PathEntryFinder) should modify ModuleSpec instances.

            """

            def __init__(self, name, loader, *, origin=None, loader_state=None,
                         is_package=None):
                self.name = name
                self.loader = loader
                self.origin = origin
                self.loader_state = loader_state
                self.submodule_search_locations = [] if is_package else None

                # file-location attributes
                self._set_fileattr = False
                self._cached = None

            def __repr__(self):
                args = ['name={!r}'.format(self.name),
                        'loader={!r}'.format(self.loader)]
                if self.origin is not None:
                    args.append('origin={!r}'.format(self.origin))
                if self.submodule_search_locations is not None:
                    args.append('submodule_search_locations={}'
                                .format(self.submodule_search_locations))
                return '{}({})'.format(self.__class__.__name__, ', '.join(args))

            def __eq__(self, other):
                smsl = self.submodule_search_locations
                try:
                    return (self.name == other.name and
                            self.loader == other.loader and
                            self.origin == other.origin and
                            smsl == other.submodule_search_locations and
                            self.cached == other.cached and
                            self.has_location == other.has_location)
                except AttributeError:
                    return NotImplemented

            @property
            def cached(self):
                if self._cached is None:
                    if self.origin is not None and self._set_fileattr:
                        self._cached = _get_cached(self.origin)
                return self._cached

            @cached.setter
            def cached(self, cached):
                self._cached = cached

            @property
            def parent(self):
                """The name of the module's parent."""
                if self.submodule_search_locations is None:
                    return self.name.rpartition('.')[0]
                else:
                    return self.name

            @property
            def has_location(self):
                return self._set_fileattr

            @has_location.setter
            def has_location(self, value):
                self._set_fileattr = bool(value)

        outer.ModuleSpec = ModuleSpec

        def _get_supported_file_loaders():
            """Returns a list of file-based module loaders.

            Each item is a tuple (loader, suffixes).
            """
            extensions = ExtensionFileLoader, _imp.extension_suffixes()
            source = SourceFileLoader, SOURCE_SUFFIXES
            bytecode = SourcelessFileLoader, BYTECODE_SUFFIXES
            return [extensions, source, bytecode]

        outer._get_supported_file_loader = _get_supported_file_loaders

        def _load_module_shim(self, fullname):
            """Load the specified module into sys.modules and return it.

            This method is deprecated.  Use loader.exec_module() instead.

            """
            msg = ("the load_module() method is deprecated and slated for removal in "
                   "Python 3.12; use exec_module() instead")
            _warnings.warn(msg, DeprecationWarning)
            spec = outer.spec_from_loader(fullname, self)
            if fullname in outer._sys.modules:
                mod = outer._sys.modules[fullname]
                _exec(spec, mod)
                return outer._sys.modules[fullname]
            else:
                return _load(spec)

        def _load(spec):
            """Return a new module object, loaded by the spec's loader.

            The module is not added to its parent.

            If a module is already in sys.modules, that existing module gets
            clobbered.

            """
            with _ModuleLockManager(spec.name):
                return outer._load_unlocked(spec)

        def _exec(spec, module):
            """Execute the spec's specified module in an existing module's namespace."""
            name = spec.name
            with _ModuleLockManager(name):
                if outer._sys.modules.get(name) is not module:
                    msg = 'module {!r} not in sys.modules'.format(name)
                    raise ImportError(msg, name=name)
                try:
                    if spec.loader is None:
                        if spec.submodule_search_locations is None:
                            raise ImportError('missing loader', name=spec.name)
                        # Namespace package.
                        _init_module_attrs(spec, module, override=True)
                    else:
                        _init_module_attrs(spec, module, override=True)
                        if not hasattr(spec.loader, 'exec_module'):
                            msg = (f"{_object_name(spec.loader)}.exec_module() not found; "
                                   "falling back to load_module()")
                            _warnings.warn(msg, ImportWarning)
                            spec.loader.load_module(name)
                        else:
                            spec.loader.exec_module(module)
                finally:
                    # Update the order of insertion into sys.modules for module
                    # clean-up at shutdown.
                    module = outer._sys.modules.pop(spec.name)
                    outer._sys.modules[spec.name] = module
            return module

        def _requires_builtin(fxn):
            """Decorator to verify the named module is built-in."""

            def _requires_builtin_wrapper(self, fullname):
                if fullname not in outer._sys.builtin_module_names:
                    raise ImportError('{!r} is not a built-in module'.format(fullname),
                                      name=fullname)
                return fxn(self, fullname)

            _wrap(_requires_builtin_wrapper, fxn)
            return _requires_builtin_wrapper

        class BuiltinImporter:

            """Meta path import for built-in modules.

            All methods are either class or static methods to avoid the need to
            instantiate the class.

            """

            _ORIGIN = "built-in"

            @staticmethod
            def module_repr(module):
                """Return repr for the module.

                The method is deprecated.  The import machinery does the job itself.

                """
                _warnings.warn("BuiltinImporter.module_repr() is deprecated and "
                               "slated for removal in Python 3.12", DeprecationWarning)
                return f'<module {module.__name__!r} ({BuiltinImporter._ORIGIN})>'

            @classmethod
            def find_spec(cls, fullname, path=None, target=None):
                if path is not None:
                    return None
                if _imp.is_builtin(fullname):
                    return outer._determine_allowed(outer.spec_from_loader(fullname, cls, origin=cls._ORIGIN))
                else:
                    return None

            @classmethod
            def find_module(cls, fullname, path=None):
                """Find the built-in module.

                If 'path' is ever specified then the search is considered a failure.

                This method is deprecated.  Use find_spec() instead.

                """
                _warnings.warn("BuiltinImporter.find_module() is deprecated and "
                               "slated for removal in Python 3.12; use find_spec() instead",
                               DeprecationWarning)
                spec = cls.find_spec(fullname, path)
                return spec.loader if spec is not None else None

            @staticmethod
            def create_module(spec):
                """Create a built-in module"""
                if spec.name not in outer._sys.builtin_module_names:
                    raise ImportError('{!r} is not a built-in module'.format(spec.name),
                                      name=spec.name)
                return outer.replace_builtins(_call_with_frames_removed(_imp.create_builtin, spec))

            @staticmethod
            def exec_module(module):
                """Exec a built-in module"""
                _call_with_frames_removed(_imp.exec_builtin, module)

            @classmethod
            @_requires_builtin
            def get_code(cls, fullname):
                """Return None as built-in modules do not have code objects."""
                return None

            @classmethod
            @_requires_builtin
            def get_source(cls, fullname):
                """Return None as built-in modules do not have source code."""
                return None

            @classmethod
            @_requires_builtin
            def is_package(cls, fullname):
                """Return False as built-in modules are never packages."""
                return False

            load_module = classmethod(_load_module_shim)

        outer.BuiltinImporter = BuiltinImporter

        class _LoaderBasics:

            """Base class of common code needed by both SourceLoader and
            SourcelessFileLoader."""

            def is_package(self, fullname):
                """Concrete implementation of InspectLoader.is_package by checking if
                the path returned by get_filename has a filename of '__init__.py'."""
                filename = _path_split(self.get_filename(fullname))[1]
                filename_base = filename.rsplit('.', 1)[0]
                tail_name = fullname.rpartition('.')[2]
                return filename_base == '__init__' and tail_name != '__init__'

            def create_module(self, spec):
                """Use default semantics for module creation."""

            def exec_module(self, module):
                """Execute the module."""
                code = self.get_code(module.__name__)
                if code is None:
                    raise ImportError('cannot load module {!r} when get_code() '
                                      'returns None'.format(module.__name__))
                _call_with_frames_removed(exec, code, module.__dict__)

            def load_module(self, fullname):
                """This module is deprecated."""
                return _load_module_shim(self, fullname)

        outer._LoaderBasics = _LoaderBasics

        class SourceLoader(_LoaderBasics):

            def path_mtime(self, path):
                """Optional method that returns the modification time (an int) for the
                specified path (a str).

                Raises OSError when the path cannot be handled.
                """
                raise OSError

            def path_stats(self, path):
                """Optional method returning a metadata dict for the specified
                path (a str).

                Possible keys:
                - 'mtime' (mandatory) is the numeric timestamp of last source
                  code modification;
                - 'size' (optional) is the size in bytes of the source code.

                Implementing this method allows the loader to read bytecode files.
                Raises OSError when the path cannot be handled.
                """
                return {'mtime': self.path_mtime(path)}

            def _cache_bytecode(self, source_path, cache_path, data):
                """Optional method which writes data (bytes) to a file path (a str).

                Implementing this method allows for the writing of bytecode files.

                The source path is needed in order to correctly transfer permissions
                """
                # For backwards compatibility, we delegate to set_data()
                return self.set_data(cache_path, data)

            def set_data(self, path, data):
                """Optional method which writes data (bytes) to a file path (a str).

                Implementing this method allows for the writing of bytecode files.
                """

            def get_source(self, fullname):
                """Concrete implementation of InspectLoader.get_source."""
                path = self.get_filename(fullname)
                try:
                    source_bytes = self.get_data(path)
                except OSError as exc:
                    raise ImportError('source not available through get_data()',
                                      name=fullname) from exc
                return decode_source(source_bytes)

            def source_to_code(self, data, path, *, _optimize=-1):
                """Return the code object compiled from source.

                The 'data' argument can be any object type that compile() supports.
                """
                return _call_with_frames_removed(compile, data, path, 'exec', dont_inherit=True, optimize=_optimize)

            def get_code(self, fullname):
                """Concrete implementation of InspectLoader.get_code.

                Reading of bytecode requires path_stats to be implemented. To write
                bytecode, set_data must also be implemented.

                """
                source_path = self.get_filename(fullname)
                source_mtime = None
                source_bytes = None
                source_hash = None
                hash_based = False
                check_source = True
                try:
                    bytecode_path = cache_from_source(source_path)
                except NotImplementedError:
                    bytecode_path = None
                else:
                    try:
                        st = self.path_stats(source_path)
                    except OSError:
                        pass
                    else:
                        source_mtime = int(st['mtime'])
                        try:
                            data = self.get_data(bytecode_path)
                        except OSError:
                            pass
                        else:
                            exc_details = {
                                'name': fullname,
                                'path': bytecode_path,
                            }
                            try:
                                flags = _classify_pyc(data, fullname, exc_details)
                                bytes_data = memoryview(data)[16:]
                                hash_based = flags & 0b1 != 0
                                if hash_based:
                                    check_source = flags & 0b10 != 0
                                    if (_imp.check_hash_based_pycs != 'never' and
                                            (check_source or
                                             _imp.check_hash_based_pycs == 'always')):
                                        source_bytes = self.get_data(source_path)
                                        source_hash = _imp.source_hash(
                                            _RAW_MAGIC_NUMBER,
                                            source_bytes,
                                        )
                                        _validate_hash_pyc(data, source_hash, fullname,
                                                           exc_details)
                                else:
                                    _validate_timestamp_pyc(
                                        data,
                                        source_mtime,
                                        st['size'],
                                        fullname,
                                        exc_details,
                                    )
                            except (ImportError, EOFError):
                                pass
                            else:
                                _verbose_message('{} matches {}', bytecode_path, source_path)
                                return _compile_bytecode(bytes_data, name=fullname,
                                                         bytecode_path=bytecode_path,
                                                         source_path=source_path)
                if source_bytes is None:
                    source_bytes = self.get_data(source_path)
                code_object = self.source_to_code(source_bytes, source_path)
                _verbose_message('code object from {}', source_path)
                if (not outer._sys.dont_write_bytecode and bytecode_path is not None and
                        source_mtime is not None):
                    if hash_based:
                        if source_hash is None:
                            source_hash = _imp.source_hash(source_bytes)
                        data = _code_to_hash_pyc(code_object, source_hash, check_source)
                    else:
                        data = _code_to_timestamp_pyc(code_object, source_mtime,
                                                      len(source_bytes))
                    try:
                        self._cache_bytecode(source_path, bytecode_path, data)
                    except NotImplementedError:
                        pass
                return code_object

        outer.SourceLoader = SourceLoader

        class FileLoader:

            """Base file loader class which implements the loader protocol methods that
            require file system usage."""

            def __init__(self, fullname, path):
                """Cache the module name and the path to the file found by the
                finder."""
                self.name = fullname
                self.path = path

            def __eq__(self, other):
                return (self.__class__ == other.__class__ and
                        self.__dict__ == other.__dict__)

            def __hash__(self):
                return hash(self.name) ^ hash(self.path)

            @_check_name
            def load_module(self, fullname):
                """Load a module from a file.

                This method is deprecated.  Use exec_module() instead.

                """
                # The only reason for this method is for the name check.
                # Issue #14857: Avoid the zero-argument form of super so the implementation
                # of that form can be updated without breaking the frozen module
                return super(FileLoader, self).load_module(fullname)

            @_check_name
            def get_filename(self, fullname):
                """Return the path to the source file as found by the finder."""
                return self.path

            def get_data(self, path):
                """Return the data from path as raw bytes."""
                if isinstance(self, (SourceLoader, ExtensionFileLoader)):
                    with _io.open_code(str(path)) as file:
                        return file.read()
                else:
                    with _io.FileIO(path, 'r') as file:
                        return file.read()

            # ResourceReader ABC API.

            @_check_name
            def get_resource_reader(self, module):
                if self.is_package(module):
                    return self
                return None

            def open_resource(self, resource):
                path = _path_join(_path_split(self.path)[0], resource)
                return _io.FileIO(path, 'r')

            def resource_path(self, resource):
                if not self.is_resource(resource):
                    raise FileNotFoundError
                path = _path_join(_path_split(self.path)[0], resource)
                return path

            def is_resource(self, name):
                if path_sep in name:
                    return False
                path = _path_join(_path_split(self.path)[0], name)
                return _path_isfile(path)

            def contents(self):
                return iter(os.listdir(_path_split(self.path)[0]))

        outer.FileLoader = FileLoader

        class SourceFileLoader(FileLoader, SourceLoader):

            """Concrete implementation of SourceLoader using the file system."""

            def path_stats(self, path):
                """Return the metadata for the path."""
                st = _path_stat(path)
                return {'mtime': st.st_mtime, 'size': st.st_size}

            def _cache_bytecode(self, source_path, bytecode_path, data):
                # Adapt between the two APIs
                mode = _calc_mode(source_path)
                return self.set_data(bytecode_path, data, _mode=mode)

            def set_data(self, path, data, *, _mode=0o666):
                """Write bytes data to a file."""
                parent, filename = _path_split(path)
                path_parts = []
                # Figure out what directories are missing.
                while parent and not _path_isdir(parent):
                    parent, part = _path_split(parent)
                    path_parts.append(part)
                # Create needed directories.
                for part in reversed(path_parts):
                    parent = _path_join(parent, part)
                    try:
                        os.mkdir(parent)
                    except FileExistsError:
                        # Probably another Python process already created the dir.
                        continue
                    except OSError as exc:
                        # Could be a permission error, read-only filesystem: just forget
                        # about writing the data.
                        _verbose_message('could not create {!r}: {!r}',
                                                    parent, exc)
                        return
                try:
                    _write_atomic(path, data, _mode)
                    _verbose_message('created {!r}', path)
                except OSError as exc:
                    # Same as above: just don't write the bytecode.
                    _verbose_message('could not create {!r}: {!r}', path,
                                                exc)

        outer.SourceFileLoader = SourceFileLoader

        class SourcelessFileLoader(FileLoader, _LoaderBasics):

            """Loader which handles sourceless file imports."""

            def get_code(self, fullname):
                path = self.get_filename(fullname)
                data = self.get_data(path)
                # Call _classify_pyc to do basic validation of the pyc but ignore the
                # result. There's no source to check against.
                exc_details = {
                    'name': fullname,
                    'path': path,
                }
                _classify_pyc(data, fullname, exc_details)
                return _compile_bytecode(
                    memoryview(data)[16:],
                    name=fullname,
                    bytecode_path=path,
                )

            def get_source(self, fullname):
                """Return None as there is no source code."""
                return None

        outer.SourcelessFileLoader = SourcelessFileLoader

        # Filled in by _setup().
        EXTENSION_SUFFIXES = []
        SOURCE_SUFFIXES = ['.py']
        BYTECODE_SUFFIXES = ['.pyc']

        class ExtensionFileLoader(FileLoader, _LoaderBasics):

            """Loader for extension modules.

            The constructor is designed to work with FileFinder.

            """

            def __init__(self, name, path):
                self.name = name
                self.path = path

            def __eq__(self, other):
                return (self.__class__ == other.__class__ and
                        self.__dict__ == other.__dict__)

            def __hash__(self):
                return hash(self.name) ^ hash(self.path)

            def create_module(self, spec):
                """Create an unitialized extension module"""
                mod = outer.replace_builtins(_call_with_frames_removed(
                    _imp.create_dynamic, spec))
                _verbose_message('extension module {!r} loaded from {!r}', spec.name, self.path)
                return mod

            def exec_module(self, module):
                """Initialize an extension module"""
                _call_with_frames_removed(_imp.exec_dynamic, module)
                _verbose_message('extension module {!r} executed from {!r}',
                                            self.name, self.path)

            def is_package(self, fullname):
                """Return True if the extension module is a package."""
                file_name = _path_split(self.path)[1]
                return any(file_name == '__init__' + suffix
                           for suffix in EXTENSION_SUFFIXES)

            def get_code(self, fullname):
                """Return None as an extension module cannot create a code object."""
                return None

            def get_source(self, fullname):
                """Return None as extension modules have no source code."""
                return None

            @_check_name
            def get_filename(self, fullname):
                """Return the path to the source file as found by the finder."""
                return self.path

        outer.ExtensionFileLoader = ExtensionFileLoader

        class _NamespaceLoader:
            def __init__(self, name, path, path_finder):
                self._path = _NamespacePath(name, path, path_finder)

            @classmethod
            def module_repr(cls, module):
                """Return repr for the module.

                The method is deprecated.  The import machinery does the job itself.

                """
                return '<module {!r} (namespace)>'.format(module.__name__)

            def is_package(self, fullname):
                return True

            def get_source(self, fullname):
                return ''

            def get_code(self, fullname):
                return compile('', '<string>', 'exec', dont_inherit=True)

            def create_module(self, spec):
                """Use default semantics for module creation."""

            def exec_module(self, module):
                pass

            def load_module(self, fullname):
                """Load a namespace module.

                This method is deprecated.  Use exec_module() instead.

                """
                # The import system never calls this method.
                _verbose_message('namespace module loaded with path {!r}',
                                 self._path)
                return _load_module_shim(self, fullname)

        def module_from_spec(spec):
            """Create a module based on the provided spec."""
            # Typically loaders will not implement create_module().
            mod = None
            if hasattr(spec.loader, 'create_module'):
                # If create_module() returns `None` then it means default
                # module creation should be used.
                mod = spec.loader.create_module(spec)
            elif hasattr(spec.loader, 'exec_module'):
                raise ImportError('loaders that define exec_module() '
                                  'must also define create_module()')
            if mod is None:
                mod = _new_module(spec.name)
            outer.replace_builtins(mod)
            _init_module_attrs(spec, mod)
            return mod

        outer.module_from_spec = module_from_spec

        def _init_module_attrs(spec, module, *, override=False):  # TODO look here to shunt the new import and builtins
            # The passed-in module may be not support attribute assignment,
            # in which case we simply don't set the attributes.
            # __name__
            if override or getattr(module, '__name__', None) is None:
                try:
                    module.__name__ = spec.name
                except AttributeError:
                    pass
            # __loader__
            if override or getattr(module, '__loader__', None) is None:
                loader = spec.loader
                if loader is None:
                    # A backward compatibility hack.
                    if spec.submodule_search_locations is not None:
                        loader = _NamespaceLoader.__new__(_NamespaceLoader)
                        loader._path = spec.submodule_search_locations
                        spec.loader = loader
                        # While the docs say that module.__file__ is not set for
                        # built-in modules, and the code below will avoid setting it if
                        # spec.has_location is false, this is incorrect for namespace
                        # packages.  Namespace packages have no location, but their
                        # __spec__.origin is None, and thus their module.__file__
                        # should also be None for consistency.  While a bit of a hack,
                        # this is the best place to ensure this consistency.
                        #
                        # See # https://docs.python.org/3/library/importlib.html#importlib.abc.Loader.load_module
                        # and bpo-32305
                        module.__file__ = None
                try:
                    module.__loader__ = loader
                except AttributeError:
                    pass
            # __package__
            if override or getattr(module, '__package__', None) is None:
                try:
                    module.__package__ = spec.parent
                except AttributeError:
                    pass
            # __spec__
            try:
                module.__spec__ = spec
            except AttributeError:
                pass
            # __path__
            if override or getattr(module, '__path__', None) is None:
                if spec.submodule_search_locations is not None:
                    try:
                        module.__path__ = spec.submodule_search_locations
                    except AttributeError:
                        pass
            # __file__/__cached__
            if spec.has_location:
                if override or getattr(module, '__file__', None) is None:
                    try:
                        module.__file__ = spec.origin
                    except AttributeError:
                        pass

                if override or getattr(module, '__cached__', None) is None:
                    if spec.cached is not None:
                        try:
                            module.__cached__ = spec.cached
                        except AttributeError:
                            pass
            return module

        # cache stuff

        def _get_cached(filename):
            if filename.endswith(tuple(SOURCE_SUFFIXES)):
                try:
                    return cache_from_source(filename)
                except NotImplementedError:
                    pass
            elif filename.endswith(tuple(BYTECODE_SUFFIXES)):
                return filename
            else:
                return None

        _PYCACHE = f'__pycache__\\sandbox_{outer.__sandbox_number}'
        _OPT = 'opt-'

        def cache_from_source(path, debug_override=None, *, optimization=None):
            """Given the path to a .py file, return the path to its .pyc file.

            The .py file does not need to exist; this simply returns the path to the
            .pyc file calculated as if the .py file were imported.

            The 'optimization' parameter controls the presumed optimization level of
            the bytecode file. If 'optimization' is not None, the string representation
            of the argument is taken and verified to be alphanumeric (else ValueError
            is raised).

            The debug_override parameter is deprecated. If debug_override is not None,
            a True value is the same as setting 'optimization' to the empty string
            while a False value is equivalent to setting 'optimization' to '1'.

            If sys.implementation.cache_tag is None then NotImplementedError is raised.

            """
            if debug_override is not None:
                _warnings.warn('the debug_override parameter is deprecated; use '
                               "'optimization' instead", DeprecationWarning)
                if optimization is not None:
                    message = 'debug_override or optimization must be set to None'
                    raise TypeError(message)
                optimization = '' if debug_override else 1
            path = os.fspath(path)
            head, tail = _path_split(path)
            base, sep, rest = tail.rpartition('.')
            tag = outer._sys.implementation.cache_tag
            if tag is None:
                raise NotImplementedError('sys.implementation.cache_tag is None')
            almost_filename = ''.join([(base if base else rest), sep, tag])
            if optimization is None:
                if sys.flags.optimize == 0:
                    optimization = ''
                else:
                    optimization = sys.flags.optimize
            optimization = str(optimization)
            if optimization != '':
                if not optimization.isalnum():
                    raise ValueError('{!r} is not alphanumeric'.format(optimization))
                almost_filename = '{}.{}{}'.format(almost_filename, _OPT, optimization)
            filename = almost_filename + BYTECODE_SUFFIXES[0]
            if sys.pycache_prefix is not None:
                # We need an absolute path to the py file to avoid the possibility of
                # collisions within sys.pycache_prefix, if someone has two different
                # `foo/bar.py` on their system and they import both of them using the
                # same sys.pycache_prefix. Let's say sys.pycache_prefix is
                # `C:\Bytecode`; the idea here is that if we get `Foo\Bar`, we first
                # make it absolute (`C:\Somewhere\Foo\Bar`), then make it root-relative
                # (`Somewhere\Foo\Bar`), so we end up placing the bytecode file in an
                # unambiguous `C:\Bytecode\Somewhere\Foo\Bar\`.
                if not _path_isabs(head):
                    head = _path_join(os.getcwd(), head)

                # Strip initial drive from a Windows path. We know we have an absolute
                # path here, so the second part of the check rules out a POSIX path that
                # happens to contain a colon at the second character.
                if head[1] == ':' and head[0] not in path_separators:
                    head = head[2:]

                # Strip initial path separator from `head` to complete the conversion
                # back to a root-relative path before joining.
                return _path_join(
                    sys.pycache_prefix,
                    head.lstrip(path_separators),
                    filename,
                )
            return _path_join(head, _PYCACHE, filename)

        def _builtin_from_name(name):
            spec = BuiltinImporter.find_spec(name)
            if spec is None:
                raise ImportError('no built-in module named ' + name)
            return outer._load_unlocked(spec)

        # move this up here to work with importing os
        # locking so that no two imports have issues interrupting each other
        class _ImportLockContext:

            """Context manager for the import lock."""

            name = None

            def __init__(self, importing_name = None):
                self.importing_name = importing_name

            def __enter__(self):
                """Acquire the import lock."""
                _imp.acquire_lock()
                _ImportLockContext.name = self.importing_name

            def __exit__(self, exc_type, exc_value, exc_traceback):
                """Release the import lock regardless of any raised exceptions."""
                _ImportLockContext.name = None
                _imp.release_lock()

        outer._ImportLockContext = _ImportLockContext

        # path bullshit

        os_details = ('posix', ['/']), ('nt', ['\\', '/'])
        for builtin_os, path_separators in os_details:
            # Assumption made in _path_join()
            assert all(len(sep) == 1 for sep in path_separators)
            path_sep = path_separators[0]
            if builtin_os in outer._sys.modules:
                os_module = outer._sys.modules[builtin_os]
                break
            else:
                try:
                    with outer._ImportLockContext(builtin_os):
                        os_module = _builtin_from_name(builtin_os)
                    break
                except ImportError:
                    continue
        else:
            raise ImportError('sandbox_import requires posix or nt')

        path_separators = "".join(path_separators)
        _pathseps_with_colon = {f':{s}' for s in path_separators}

        def _path_split(path):
            """Replacement for os.path.split()."""
            if len(path_separators) == 1:
                front, _, tail = path.rpartition(path_sep)
                return front, tail
            for x in reversed(path):
                if x in path_separators:
                    front, tail = path.rsplit(x, maxsplit=1)
                    return front, tail
            return '', path

        outer._path_split = _path_split

        def _path_join(*path_parts):
            """Replacement for os.path.join()."""
            return path_sep.join([part.rstrip(path_separators) for part in path_parts if part])

        def _path_is_mode_type(path, mode):
            """Test whether the path is the specified mode type."""
            try:
                stat_info = _path_stat(path)
            except OSError:
                return False
            return (stat_info.st_mode & 0o170000) == mode

        def _path_isfile(path):
            """Replacement for os.path.isfile."""
            return _path_is_mode_type(path, 0o100000)

        def _path_isdir(path):
            """Replacement for os.path.isdir."""
            if not path:
                path = os.getcwd()
            return _path_is_mode_type(path, 0o040000)

        def _path_isabs(path):
            """Replacement for os.path.isabs.

            Considers a Windows drive-relative path (no drive, but starts with slash) to
            still be "absolute".
            """
            return path.startswith(path_separators) or path[1:3] in _pathseps_with_colon

        # Module-level locking ########################################################

        # A dict mapping module names to weakrefs of _ModuleLock instances
        # Dictionary protected by the global import lock
        _module_locks = {}
        # A dict mapping thread ids to _ModuleLock instances
        _blocking_on = {}

        def _lock_unlock_module(name):
            """Acquires then releases the module lock for a given module name.

            This is used to ensure a module is completely initialized, in the
            event it is being imported by another thread.
            """
            lock = _get_module_lock(name)
            try:
                lock.acquire()
            except _DeadlockError:
                # Concurrent circular import, we'll accept a partially initialized
                # module object.
                pass
            else:
                lock.release()

        outer._lock_unlock_module = _lock_unlock_module

        class _ModuleLockManager:

            def __init__(self, name):
                self._name = name
                self._lock = None

            def __enter__(self):
                self._lock = _get_module_lock(self._name)
                self._lock.acquire()

            def __exit__(self, *args, **kwargs):
                self._lock.release()

        outer._ModuleLockManager = _ModuleLockManager

        def _get_module_lock(name):
            """Get or create the module lock for a given module name.

            Acquire/release internally the global import lock to protect
            _module_locks."""

            _imp.acquire_lock()
            try:
                try:
                    lock = _module_locks[name]()
                except KeyError:
                    lock = None

                if lock is None:
                    if _thread is None:
                        lock = _DummyModuleLock(name)
                    else:
                        lock = _ModuleLock(name)

                    def cb(ref, name=name):
                        _imp.acquire_lock()
                        try:
                            # bpo-31070: Check if another thread created a new lock
                            # after the previous lock was destroyed
                            # but before the weakref callback was called.
                            if _module_locks.get(name) is ref:
                                del _module_locks[name]
                        finally:
                            _imp.release_lock()

                    _module_locks[name] = _weakref.ref(lock, cb)
            finally:
                _imp.release_lock()

            return lock

        class _ModuleLock:
            """A recursive lock implementation which is able to detect deadlocks
            (e.g. thread 1 trying to take locks A then B, and thread 2 trying to
            take locks B then A).
            """

            def __init__(self, name):
                self.lock = _thread.allocate_lock()
                self.wakeup = _thread.allocate_lock()
                self.name = name
                self.owner = None
                self.count = 0
                self.waiters = 0

            def has_deadlock(self):
                # Deadlock avoidance for concurrent circular imports.
                me = _thread.get_ident()
                tid = self.owner
                seen = set()
                while True:
                    lock = _blocking_on.get(tid)
                    if lock is None:
                        return False
                    tid = lock.owner
                    if tid == me:
                        return True
                    if tid in seen:
                        # bpo 38091: the chain of tid's we encounter here
                        # eventually leads to a fixpoint or a cycle, but
                        # does not reach 'me'.  This means we would not
                        # actually deadlock.  This can happen if other
                        # threads are at the beginning of acquire() below.
                        return False
                    seen.add(tid)

            def acquire(self):
                """
                Acquire the module lock.  If a potential deadlock is detected,
                a _DeadlockError is raised.
                Otherwise, the lock is always acquired and True is returned.
                """
                tid = _thread.get_ident()
                _blocking_on[tid] = self
                try:
                    while True:
                        with self.lock:
                            if self.count == 0 or self.owner == tid:
                                self.owner = tid
                                self.count += 1
                                return True
                            if self.has_deadlock():
                                raise _DeadlockError('deadlock detected by %r' % self)
                            if self.wakeup.acquire(False):
                                self.waiters += 1
                        # Wait for a release() call
                        self.wakeup.acquire()
                        self.wakeup.release()
                finally:
                    del _blocking_on[tid]

            def release(self):
                tid = _thread.get_ident()
                with self.lock:
                    if self.owner != tid:
                        raise RuntimeError('cannot release un-acquired lock')
                    assert self.count > 0
                    self.count -= 1
                    if self.count == 0:
                        self.owner = None
                        if self.waiters:
                            self.waiters -= 1
                            self.wakeup.release()

            def __repr__(self):
                return '_ModuleLock({!r}) at {}'.format(self.name, id(self))

        class _DummyModuleLock:
            """A simple _ModuleLock equivalent for Python builds without
            multi-threading support."""

            def __init__(self, name):
                self.name = name
                self.count = 0

            def acquire(self):
                self.count += 1
                return True

            def release(self):
                if self.count == 0:
                    raise RuntimeError('cannot release un-acquired lock')
                self.count -= 1

            def __repr__(self):
                return '_DummyModuleLock({!r}) at {}'.format(self.name, id(self))

        class DistutilsMetaFinder:
            def find_spec(self, fullname, path, target=None):
                # optimization: only consider top level modules and those
                # found in the CPython test suite.
                if path is not None and not fullname.startswith('test.'):
                    return

                method_name = 'spec_for_{fullname}'.format(**locals())
                method = getattr(self, method_name, lambda: None)
                return outer._determine_allowed(method())

            def spec_for_distutils(self):
                if self.is_cpython():
                    return

                # import importlib
                importlib_abc = outer.import_module('importlib.abc')
                importlib_util = outer.import_module('importlib.util')

                try:
                    mod = outer.import_module('setuptools._distutils')
                except Exception:
                    # There are a couple of cases where setuptools._distutils
                    # may not be present:
                    # - An older Setuptools without a local distutils is
                    #   taking precedence. Ref #2957.
                    # - Path manipulation during sitecustomize removes
                    #   setuptools from the path but only after the hook
                    #   has been loaded. Ref #2980.
                    # In either case, fall back to stdlib behavior.
                    return

                class DistutilsLoader(importlib_abc.Loader):
                    def create_module(self, spec):
                        mod.__name__ = 'distutils'
                        return mod

                    def exec_module(self, module):
                        pass

                return outer.spec_from_loader(
                    'distutils', DistutilsLoader(), origin=mod.__file__
                )

            @staticmethod
            def is_cpython():
                """
                Suppress supplying distutils for CPython (build and tests).
                Ref #2965 and #3007.
                """
                return os.path.isfile('pybuilddir.txt')

            def spec_for_pip(self):
                """
                Ensure stdlib distutils when running under pip.
                See pypa/pip#8761 for rationale.
                """
                if self.pip_imported_during_build():
                    return
                # clear_distutils()
                self.spec_for_distutils = lambda: None

            @classmethod
            def pip_imported_during_build(cls):
                """
                Detect if pip is being imported in a build script. Ref #2355.
                """
                import traceback

                return any(
                    cls.frame_file_is_setup(frame) for frame, line in traceback.walk_stack(None)
                )

            @staticmethod
            def frame_file_is_setup(frame):
                """
                Return True if the indicated frame suggests a setup.py file.
                """
                # some frames may not have __file__ (#2940)
                return frame.f_globals.get('__file__', '').endswith('setup.py')

            def spec_for_sensitive_tests(self):
                """
                Ensure stdlib distutils when running select tests under CPython.

                python/cpython#91169
                """
                # clear_distutils()
                self.spec_for_distutils = lambda: None

            sensitive_tests = (
                [
                    'test.test_distutils',
                    'test.test_peg_generator',
                    'test.test_importlib',
                ]
                if sys.version_info < (3, 10)
                else [
                    'test.test_distutils',
                ]
            )

        def _requires_frozen(fxn):
            """Decorator to verify the named module is frozen."""

            def _requires_frozen_wrapper(self, fullname):
                if not _imp.is_frozen(fullname):
                    raise ImportError('{!r} is not a frozen module'.format(fullname),
                                      name=fullname)
                return fxn(self, fullname)

            _wrap(_requires_frozen_wrapper, fxn)
            return _requires_frozen_wrapper

        class FrozenImporter:

            """Meta path import for frozen modules.

            All methods are either class or static methods to avoid the need to
            instantiate the class.

            """

            _ORIGIN = "frozen"

            @staticmethod
            def module_repr(m):
                """Return repr for the module.

                The method is deprecated.  The import machinery does the job itself.

                """
                _warnings.warn("FrozenImporter.module_repr() is deprecated and "
                               "slated for removal in Python 3.12", DeprecationWarning)
                return '<module {!r} ({})>'.format(m.__name__, FrozenImporter._ORIGIN)

            @classmethod
            def find_spec(cls, fullname, path=None, target=None):
                if _imp.is_frozen(fullname):
                    return outer._determine_allowed(outer.spec_from_loader(fullname, cls, origin=cls._ORIGIN))
                else:
                    return None

            @classmethod
            def find_module(cls, fullname, path=None):
                """Find a frozen module.

                This method is deprecated.  Use find_spec() instead.

                """
                _warnings.warn("FrozenImporter.find_module() is deprecated and "
                               "slated for removal in Python 3.12; use find_spec() instead",
                               DeprecationWarning)
                return cls if _imp.is_frozen(fullname) else None

            @staticmethod
            def create_module(spec):
                """Use default semantics for module creation."""

            @staticmethod
            def exec_module(module):
                name = module.__spec__.name
                if not _imp.is_frozen(name):
                    raise ImportError('{!r} is not a frozen module'.format(name),
                                      name=name)
                code = _call_with_frames_removed(_imp.get_frozen_object, name)
                if hasattr(module, '__builtin__'):
                    print("replacing builtins")
                    setattr(module, '__builtin__', outer._builtins)
                exec(code, module.__dict__)

            @classmethod
            def load_module(cls, fullname):
                """Load a frozen module.

                This method is deprecated.  Use exec_module() instead.

                """
                # Warning about deprecation implemented in _load_module_shim().
                return _load_module_shim(cls, fullname)

            @classmethod
            @_requires_frozen
            def get_code(cls, fullname):
                """Return the code object for the frozen module."""
                return _imp.get_frozen_object(fullname)

            @classmethod
            @_requires_frozen
            def get_source(cls, fullname):
                """Return None as frozen modules do not have source code."""
                return None

            @classmethod
            @_requires_frozen
            def is_package(cls, fullname):
                """Return True if the frozen module is a package."""
                return _imp.is_frozen_package(fullname)

        class PathFinder:

            """Meta path finder for sys.path and package __path__ attributes."""

            @staticmethod
            def invalidate_caches():
                """Call the invalidate_caches() method on all path entry finders
                stored in sys.path_importer_caches (where implemented)."""
                for name, finder in list(outer._sys.path_importer_cache.items()):
                    if finder is None:
                        del outer._sys.path_importer_cache[name]
                    elif hasattr(finder, 'invalidate_caches'):
                        finder.invalidate_caches()

            @staticmethod
            def _path_hooks(path):
                """Search sys.path_hooks for a finder for 'path'."""
                if outer._sys.path_hooks is not None and not outer._sys.path_hooks:
                    _warnings.warn('sys.path_hooks is empty', ImportWarning)
                for hook in outer._sys.path_hooks:
                    try:
                        return hook(path)
                    except ImportError:
                        continue
                else:
                    return None

            @classmethod
            def _path_importer_cache(cls, path):
                """Get the finder for the path entry from sys.path_importer_cache.

                If the path entry is not in the cache, find the appropriate finder
                and cache it. If no finder is available, store None.

                """
                if path == '':
                    try:
                        path = os.getcwd()
                    except FileNotFoundError:
                        # Don't cache the failure as the cwd can easily change to
                        # a valid directory later on.
                        return None
                try:
                    finder = outer._sys.path_importer_cache[path]
                except KeyError:
                    finder = cls._path_hooks(path)
                    outer._sys.path_importer_cache[path] = finder
                return finder

            @classmethod
            def _legacy_get_spec(cls, fullname, finder):
                # This would be a good place for a DeprecationWarning if
                # we ended up going that route.
                if hasattr(finder, 'find_loader'):
                    msg = (f"{_object_name(finder)}.find_spec() not found; "
                           "falling back to find_loader()")
                    _warnings.warn(msg, ImportWarning)
                    loader, portions = finder.find_loader(fullname)
                else:
                    msg = (f"{_object_name(finder)}.find_spec() not found; "
                           "falling back to find_module()")
                    _warnings.warn(msg, ImportWarning)
                    loader = finder.find_module(fullname)
                    portions = []
                if loader is not None:
                    return outer.spec_from_loader(fullname, loader)
                spec = ModuleSpec(fullname, None)
                spec.submodule_search_locations = portions
                return spec

            @classmethod
            def _get_spec(cls, fullname, path, target=None):
                """Find the loader or namespace_path for this module/package name."""
                # If this ends up being a namespace package, namespace_path is
                #  the list of paths that will become its __path__
                namespace_path = []
                for entry in path:
                    if not isinstance(entry, (str, bytes)):
                        continue
                    finder = cls._path_importer_cache(entry)
                    if finder is not None:
                        if hasattr(finder, 'find_spec'):
                            spec = finder.find_spec(fullname, target)
                        else:
                            spec = cls._legacy_get_spec(fullname, finder)
                        if spec is None:
                            continue
                        if spec.loader is not None:
                            return spec
                        portions = spec.submodule_search_locations
                        if portions is None:
                            raise ImportError('spec missing loader')
                        # This is possibly part of a namespace package.
                        #  Remember these path entries (if any) for when we
                        #  create a namespace package, and continue iterating
                        #  on path.
                        namespace_path.extend(portions)
                else:
                    spec = ModuleSpec(fullname, None)
                    spec.submodule_search_locations = namespace_path
                    return spec

            @classmethod
            def find_spec(cls, fullname, path=None, target=None):
                """Try to find a spec for 'fullname' on sys.path or 'path'.

                The search is based on sys.path_hooks and sys.path_importer_cache.
                """
                if path is None:
                    path = outer._sys.path
                spec = cls._get_spec(fullname, path, target)
                if spec is None:
                    return None
                elif spec.loader is None:
                    namespace_path = spec.submodule_search_locations
                    if namespace_path:
                        # We found at least one namespace path.  Return a spec which
                        # can create the namespace package.
                        spec.origin = None
                        spec.submodule_search_locations = _NamespacePath(fullname, namespace_path, cls._get_spec)
                        return outer._determine_allowed(spec)
                    else:
                        return None
                else:
                    return outer._determine_allowed(spec)

            @classmethod
            def find_module(cls, fullname, path=None):
                """find the module on sys.path or 'path' based on sys.path_hooks and
                sys.path_importer_cache.

                This method is deprecated.  Use find_spec() instead.

                """
                _warnings.warn("PathFinder.find_module() is deprecated and "
                               "slated for removal in Python 3.12; use find_spec() instead",
                               DeprecationWarning)
                spec = cls.find_spec(fullname, path)
                if spec is None:
                    return None
                return spec.loader

            @staticmethod
            def find_distributions(*args, **kwargs):
                """
                Find distributions.

                Return an iterable of all Distribution instances capable of
                loading the metadata for packages matching ``context.name``
                (or all names if ``None`` indicated) along the paths in the list
                of directories ``context.path``.
                """
                from importlib.metadata import MetadataPathFinder
                return MetadataPathFinder.find_distributions(*args, **kwargs)

        class _NamespacePath:
            """Represents a namespace package's path.  It uses the module name
            to find its parent module, and from there it looks up the parent's
            __path__.  When this changes, the module's own path is recomputed,
            using path_finder.  For top-level modules, the parent module's path
            is sys.path."""

            def __init__(self, name, path, path_finder):
                self._name = name
                self._path = path
                self._last_parent_path = tuple(self._get_parent_path())
                self._path_finder = path_finder

            def _find_parent_path_names(self):
                """Returns a tuple of (parent-module-name, parent-path-attr-name)"""
                parent, dot, me = self._name.rpartition('.')
                if dot == '':
                    # This is a top-level module. sys.path contains the parent path.
                    return 'sys', 'path'
                # Not a top-level module. parent-module.__path__ contains the
                #  parent path.
                return parent, '__path__'

            def _get_parent_path(self):
                parent_module_name, path_attr_name = self._find_parent_path_names()
                return getattr(outer._sys.modules[parent_module_name], path_attr_name)

            def _recalculate(self):
                # If the parent's path has changed, recalculate _path
                parent_path = tuple(self._get_parent_path())  # Make a copy
                if parent_path != self._last_parent_path:
                    spec = self._path_finder(self._name, parent_path)
                    # Note that no changes are made if a loader is returned, but we
                    #  do remember the new parent path
                    if spec is not None and spec.loader is None:
                        if spec.submodule_search_locations:
                            self._path = spec.submodule_search_locations
                    self._last_parent_path = parent_path  # Save the copy
                return self._path

            def __iter__(self):
                return iter(self._recalculate())

            def __getitem__(self, index):
                return self._recalculate()[index]

            def __setitem__(self, index, path):
                self._path[index] = path

            def __len__(self):
                return len(self._recalculate())

            def __repr__(self):
                return '_NamespacePath({!r})'.format(self._path)

            def __contains__(self, item):
                return item in self._recalculate()

            def append(self, item):
                self._path.append(item)

        # Bootstrap-related code ######################################################
        _CASE_INSENSITIVE_PLATFORMS_STR_KEY = 'win',
        _CASE_INSENSITIVE_PLATFORMS_BYTES_KEY = 'cygwin', 'darwin'
        _CASE_INSENSITIVE_PLATFORMS = (_CASE_INSENSITIVE_PLATFORMS_BYTES_KEY
                                       + _CASE_INSENSITIVE_PLATFORMS_STR_KEY)

        def _make_relax_case():
            if outer._sys.platform.startswith(_CASE_INSENSITIVE_PLATFORMS):
                if outer._sys.platform.startswith(_CASE_INSENSITIVE_PLATFORMS_STR_KEY):
                    key = 'PYTHONCASEOK'
                else:
                    key = b'PYTHONCASEOK'

                def _relax_case():
                    """True if filenames must be checked case-insensitively and ignore environment flags are not set."""
                    return not outer._sys.flags.ignore_environment and key in os.environ
            else:
                def _relax_case():
                    """True if filenames must be checked case-insensitively."""
                    return False
            return _relax_case

        _relax_case = _make_relax_case()



        class FileFinder:

            """File-based finder.

            Interactions with the file system are cached for performance, being
            refreshed when the directory the finder is handling has been modified.

            """

            def __init__(self, path, *loader_details):
                """Initialize with the path to search on and a variable number of
                2-tuples containing the loader and the file suffixes the loader
                recognizes."""
                loaders = []
                for loader, suffixes in loader_details:
                    loaders.extend((suffix, loader) for suffix in suffixes)
                self._loaders = loaders
                # Base (directory) path
                self.path = path or '.'
                if not _path_isabs(self.path):
                    self.path = _path_join(os.getcwd(), self.path)
                self._path_mtime = -1
                self._path_cache = set()
                self._relaxed_path_cache = set()

            def invalidate_caches(self):
                """Invalidate the directory mtime."""
                self._path_mtime = -1

            find_module = _find_module_shim

            def find_loader(self, fullname):
                """Try to find a loader for the specified module, or the namespace
                package portions. Returns (loader, list-of-portions).

                This method is deprecated.  Use find_spec() instead.

                """
                _warnings.warn("FileFinder.find_loader() is deprecated and "
                               "slated for removal in Python 3.12; use find_spec() instead",
                               DeprecationWarning)
                spec = self.find_spec(fullname)
                if spec is None:
                    return None, []
                return spec.loader, spec.submodule_search_locations or []

            def _get_spec(self, loader_class, fullname, path, smsl, target):
                loader = loader_class(fullname, path)
                return outer.spec_from_file_location(fullname, path, loader=loader, submodule_search_locations=smsl)

            def find_spec(self, fullname, target=None):
                """Try to find a spec for the specified module.

                Returns the matching spec, or None if not found.
                """
                is_namespace = False
                tail_module = fullname.rpartition('.')[2]
                try:
                    mtime = _path_stat(self.path or os.getcwd()).st_mtime
                except OSError:
                    mtime = -1
                if mtime != self._path_mtime:
                    self._fill_cache()
                    self._path_mtime = mtime
                # tail_module keeps the original casing, for __file__ and friends
                if _relax_case():
                    cache = self._relaxed_path_cache
                    cache_module = tail_module.lower()
                else:
                    cache = self._path_cache
                    cache_module = tail_module
                # Check if the module is the name of a directory (and thus a package).
                if cache_module in cache:
                    base_path = _path_join(self.path, tail_module)
                    for suffix, loader_class in self._loaders:
                        init_filename = '__init__' + suffix
                        full_path = _path_join(base_path, init_filename)
                        if _path_isfile(full_path):
                            return outer._determine_allowed(self._get_spec(loader_class, fullname, full_path,
                                                                           [base_path], target))
                    else:
                        # If a namespace package, return the path if we don't
                        #  find a module in the next section.
                        is_namespace = _path_isdir(base_path)
                # Check for a file w/ a proper suffix exists.
                for suffix, loader_class in self._loaders:
                    try:
                        full_path = _path_join(self.path, tail_module + suffix)
                    except ValueError:
                        return None
                    _verbose_message('trying {}', full_path, verbosity=2)
                    if cache_module + suffix in cache:
                        if _path_isfile(full_path):
                            return outer._determine_allowed(self._get_spec(loader_class, fullname, full_path, None,
                                                                           target))
                if is_namespace:
                    _verbose_message('possible namespace for {}', base_path)
                    spec = ModuleSpec(fullname, None)
                    spec.submodule_search_locations = [base_path]
                    return outer._determine_allowed(spec)
                return None

            def _fill_cache(self):
                """Fill the cache of potential modules and packages for this directory."""
                path = self.path
                try:
                    contents = os.listdir(path or os.getcwd())
                except (FileNotFoundError, PermissionError, NotADirectoryError):
                    # Directory has either been removed, turned into a file, or made
                    # unreadable.
                    contents = []
                # We store two cached versions, to handle runtime changes of the
                # PYTHONCASEOK environment variable.
                if not sys.platform.startswith('win'):
                    self._path_cache = set(contents)
                else:
                    # Windows users can import modules with case-insensitive file
                    # suffixes (for legacy reasons). Make the suffix lowercase here
                    # so it's done once instead of for every import. This is safe as
                    # the specified suffixes to check against are always specified in a
                    # case-sensitive manner.
                    lower_suffix_contents = set()
                    for item in contents:
                        name, dot, suffix = item.partition('.')
                        if dot:
                            new_name = '{}.{}'.format(name, suffix.lower())
                        else:
                            new_name = name
                        lower_suffix_contents.add(new_name)
                    self._path_cache = lower_suffix_contents
                if sys.platform.startswith(_CASE_INSENSITIVE_PLATFORMS):
                    self._relaxed_path_cache = {fn.lower() for fn in contents}

            @classmethod
            def path_hook(cls, *loader_details):
                """A class method which returns a closure to use on sys.path_hook
                which will return an instance using the specified loaders and the path
                called on the closure.

                If the path called on the closure is not a directory, ImportError is
                raised.

                """

                def path_hook_for_FileFinder(path):
                    """Path hook for importlib.machinery.FileFinder."""
                    if not _path_isdir(path):
                        raise ImportError('only directories are supported', path=path)
                    return cls(path, *loader_details)

                return path_hook_for_FileFinder

            def __repr__(self):
                return 'FileFinder({!r})'.format(self.path)

        def _get_supported_file_loaders():
            """Returns a list of file-based module loaders.

            Each item is a tuple (loader, suffixes).
            """
            extensions = ExtensionFileLoader, _imp.extension_suffixes()
            source = SourceFileLoader, SOURCE_SUFFIXES
            bytecode = SourcelessFileLoader, BYTECODE_SUFFIXES
            return [extensions, source, bytecode]

        outer._get_supported_file_loaders = _get_supported_file_loaders

        alt_path_sep = path_separators[1:]

        _zip_directory_cache = {}

        END_CENTRAL_DIR_SIZE = 22
        STRING_END_ARCHIVE = b'PK\x05\x06'
        MAX_COMMENT_LEN = (1 << 16) - 1

        def _read_directory(archive):
            try:
                fp = _io.open_code(archive)
            except OSError:
                raise ZipImportError(f"can't open Zip file: {archive!r}", path=archive)

            with fp:
                try:
                    fp.seek(-END_CENTRAL_DIR_SIZE, 2)
                    header_position = fp.tell()
                    buffer = fp.read(END_CENTRAL_DIR_SIZE)
                except OSError:
                    raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                if len(buffer) != END_CENTRAL_DIR_SIZE:
                    raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                if buffer[:4] != STRING_END_ARCHIVE:
                    # Bad: End of Central Dir signature
                    # Check if there's a comment.
                    try:
                        fp.seek(0, 2)
                        file_size = fp.tell()
                    except OSError:
                        raise ZipImportError(f"can't read Zip file: {archive!r}",
                                             path=archive)
                    max_comment_start = max(file_size - MAX_COMMENT_LEN -
                                            END_CENTRAL_DIR_SIZE, 0)
                    try:
                        fp.seek(max_comment_start)
                        data = fp.read()
                    except OSError:
                        raise ZipImportError(f"can't read Zip file: {archive!r}",
                                             path=archive)
                    pos = data.rfind(STRING_END_ARCHIVE)
                    if pos < 0:
                        raise ZipImportError(f'not a Zip file: {archive!r}',
                                             path=archive)
                    buffer = data[pos:pos + END_CENTRAL_DIR_SIZE]
                    if len(buffer) != END_CENTRAL_DIR_SIZE:
                        raise ZipImportError(f"corrupt Zip file: {archive!r}",
                                             path=archive)
                    header_position = file_size - len(data) + pos

                header_size = _unpack_uint32(buffer[12:16])
                header_offset = _unpack_uint32(buffer[16:20])
                if header_position < header_size:
                    raise ZipImportError(f'bad central directory size: {archive!r}', path=archive)
                if header_position < header_offset:
                    raise ZipImportError(f'bad central directory offset: {archive!r}', path=archive)
                header_position -= header_size
                arc_offset = header_position - header_offset
                if arc_offset < 0:
                    raise ZipImportError(f'bad central directory size or offset: {archive!r}', path=archive)

                files = {}
                # Start of Central Directory
                count = 0
                try:
                    fp.seek(header_position)
                except OSError:
                    raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                while True:
                    buffer = fp.read(46)
                    if len(buffer) < 4:
                        raise EOFError('EOF read where not expected')
                    # Start of file header
                    if buffer[:4] != b'PK\x01\x02':
                        break  # Bad: Central Dir File Header
                    if len(buffer) != 46:
                        raise EOFError('EOF read where not expected')
                    flags = _unpack_uint16(buffer[8:10])
                    compress = _unpack_uint16(buffer[10:12])
                    time = _unpack_uint16(buffer[12:14])
                    date = _unpack_uint16(buffer[14:16])
                    crc = _unpack_uint32(buffer[16:20])
                    data_size = _unpack_uint32(buffer[20:24])
                    file_size = _unpack_uint32(buffer[24:28])
                    name_size = _unpack_uint16(buffer[28:30])
                    extra_size = _unpack_uint16(buffer[30:32])
                    comment_size = _unpack_uint16(buffer[32:34])
                    file_offset = _unpack_uint32(buffer[42:46])
                    header_size = name_size + extra_size + comment_size
                    if file_offset > header_offset:
                        raise ZipImportError(f'bad local header offset: {archive!r}', path=archive)
                    file_offset += arc_offset

                    try:
                        name = fp.read(name_size)
                    except OSError:
                        raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                    if len(name) != name_size:
                        raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                    # On Windows, calling fseek to skip over the fields we don't use is
                    # slower than reading the data because fseek flushes stdio's
                    # internal buffers.    See issue #8745.
                    try:
                        if len(fp.read(header_size - name_size)) != header_size - name_size:
                            raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                    except OSError:
                        raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)

                    if flags & 0x800:
                        # UTF-8 file names extension
                        name = name.decode()
                    else:
                        # Historical ZIP filename encoding
                        try:
                            name = name.decode('ascii')
                        except UnicodeDecodeError:
                            name = name.decode('latin1').translate(cp437_table)

                    name = name.replace('/', path_sep)
                    path = _path_join(archive, name)
                    t = (path, compress, data_size, file_size, file_offset, time, date, crc)
                    files[name] = t
                    count += 1
            _verbose_message('zipimport: found {} names in {!r}', count, archive)
            return files

        class ZipImportError(ImportError):
            pass

        class zipimporter(_LoaderBasics):
            """zipimporter(archivepath) -> zipimporter object

            Create a new zipimporter instance. 'archivepath' must be a path to
            a zipfile, or to a specific path inside a zipfile. For example, it can be
            '/tmp/myimport.zip', or '/tmp/myimport.zip/mydirectory', if mydirectory is a
            valid directory inside the archive.

            'ZipImportError is raised if 'archivepath' doesn't point to a valid Zip
            archive.

            The 'archive' attribute of zipimporter objects contains the name of the
            zipfile targeted.
            """

            # Split the "subdirectory" from the Zip archive path, lookup a matching
            # entry in sys.path_importer_cache, fetch the file directory from there
            # if found, or else read it from the archive.
            def __init__(self, path):
                if not isinstance(path, str):
                    import os
                    path = os.fsdecode(path)
                if not path:
                    raise ZipImportError('archive path is empty', path=path)
                if alt_path_sep:
                    path = path.replace(alt_path_sep, path_sep)

                prefix = []
                while True:
                    try:
                        st = _path_stat(path)
                    except (OSError, ValueError):
                        # On Windows a ValueError is raised for too long paths.
                        # Back up one path element.
                        dirname, basename = _path_split(path)
                        if dirname == path:
                            raise ZipImportError('not a Zip file', path=path)
                        path = dirname
                        prefix.append(basename)
                    else:
                        # it exists
                        if (st.st_mode & 0o170000) != 0o100000:  # stat.S_ISREG
                            # it's a not file
                            raise ZipImportError('not a Zip file', path=path)
                        break

                try:
                    files = _zip_directory_cache[path]
                except KeyError:
                    files = _read_directory(path)
                    _zip_directory_cache[path] = files
                self._files = files
                self.archive = path
                # a prefix directory following the ZIP file path.
                self.prefix = _path_join(*prefix[::-1])
                if self.prefix:
                    self.prefix += path_sep

            # Check whether we can satisfy the import of the module named by
            # 'fullname', or whether it could be a portion of a namespace
            # package. Return self if we can load it, a string containing the
            # full path if it's a possible namespace portion, None if we
            # can't load it.
            def find_loader(self, fullname, path=None):
                """find_loader(fullname, path=None) -> self, str or None.

                Search for a module specified by 'fullname'. 'fullname' must be the
                fully qualified (dotted) module name. It returns the zipimporter
                instance itself if the module was found, a string containing the
                full path name if it's possibly a portion of a namespace package,
                or None otherwise. The optional 'path' argument is ignored -- it's
                there for compatibility with the importer protocol.

                Deprecated since Python 3.10. Use find_spec() instead.
                """
                _warnings.warn("zipimporter.find_loader() is deprecated and slated for "
                               "removal in Python 3.12; use find_spec() instead",
                               DeprecationWarning)
                mi = _get_module_info(self, fullname)
                if mi is not None:
                    # This is a module or package.
                    return self, []

                # Not a module or regular package. See if this is a directory, and
                # therefore possibly a portion of a namespace package.

                # We're only interested in the last path component of fullname
                # earlier components are recorded in self.prefix.
                modpath = _get_module_path(self, fullname)
                if _is_dir(self, modpath):
                    # This is possibly a portion of a namespace
                    # package. Return the string representing its path,
                    # without a trailing separator.
                    return None, [f'{self.archive}{path_sep}{modpath}']

                return None, []

            # Check whether we can satisfy the import of the module named by
            # 'fullname'. Return self if we can, None if we can't.
            def find_module(self, fullname, path=None):
                """find_module(fullname, path=None) -> self or None.

                Search for a module specified by 'fullname'. 'fullname' must be the
                fully qualified (dotted) module name. It returns the zipimporter
                instance itself if the module was found, or None if it wasn't.
                The optional 'path' argument is ignored -- it's there for compatibility
                with the importer protocol.

                Deprecated since Python 3.10. Use find_spec() instead.
                """
                _warnings.warn("zipimporter.find_module() is deprecated and slated for "
                               "removal in Python 3.12; use find_spec() instead",
                               DeprecationWarning)
                return self.find_loader(fullname, path)[0]

            def find_spec(self, fullname, target=None):
                """Create a ModuleSpec for the specified module.

                Returns None if the module cannot be found.
                """
                module_info = _get_module_info(self, fullname)
                if module_info is not None:
                    return outer._determine_allowed((outer.spec_from_loader(fullname, self, is_package=module_info)))
                else:
                    # Not a module or regular package. See if this is a directory, and
                    # therefore possibly a portion of a namespace package.

                    # We're only interested in the last path component of fullname
                    # earlier components are recorded in self.prefix.
                    modpath = _get_module_path(self, fullname)
                    if _is_dir(self, modpath):
                        # This is possibly a portion of a namespace
                        # package. Return the string representing its path,
                        # without a trailing separator.
                        path = f'{self.archive}{path_sep}{modpath}'
                        spec = ModuleSpec(name=fullname, loader=None,
                                                     is_package=True)
                        spec.submodule_search_locations.append(path)
                        return outer._determine_allowed(spec)
                    else:
                        return None

            def get_code(self, fullname):
                """get_code(fullname) -> code object.

                Return the code object for the specified module. Raise ZipImportError
                if the module couldn't be imported.
                """
                code, ispackage, modpath = _get_module_code(self, fullname)
                return code

            def get_data(self, pathname):
                """get_data(pathname) -> string with file data.

                Return the data associated with 'pathname'. Raise OSError if
                the file wasn't found.
                """
                if alt_path_sep:
                    pathname = pathname.replace(alt_path_sep, path_sep)

                key = pathname
                if pathname.startswith(self.archive + path_sep):
                    key = pathname[len(self.archive + path_sep):]

                try:
                    toc_entry = self._files[key]
                except KeyError:
                    raise OSError(0, '', key)
                return _get_data(self.archive, toc_entry)

            # Return a string matching __file__ for the named module
            def get_filename(self, fullname):
                """get_filename(fullname) -> filename string.

                Return the filename for the specified module or raise ZipImportError
                if it couldn't be imported.
                """
                # Deciding the filename requires working out where the code
                # would come from if the module was actually loaded
                code, ispackage, modpath = _get_module_code(self, fullname)
                return modpath

            def get_source(self, fullname):
                """get_source(fullname) -> source string.

                Return the source code for the specified module. Raise ZipImportError
                if the module couldn't be found, return None if the archive does
                contain the module, but has no source for it.
                """
                mi = _get_module_info(self, fullname)
                if mi is None:
                    raise ZipImportError(f"can't find module {fullname!r}", name=fullname)

                path = _get_module_path(self, fullname)
                if mi:
                    fullpath = _path_join(path, '__init__.py')
                else:
                    fullpath = f'{path}.py'

                try:
                    toc_entry = self._files[fullpath]
                except KeyError:
                    # we have the module, but no source
                    return None
                return _get_data(self.archive, toc_entry).decode()

            # Return a bool signifying whether the module is a package or not.
            def is_package(self, fullname):
                """is_package(fullname) -> bool.

                Return True if the module specified by fullname is a package.
                Raise ZipImportError if the module couldn't be found.
                """
                mi = _get_module_info(self, fullname)
                if mi is None:
                    raise ZipImportError(f"can't find module {fullname!r}", name=fullname)
                return mi

            # Load and return the module named by 'fullname'.
            def load_module(self, fullname):
                """load_module(fullname) -> module.

                Load the module specified by 'fullname'. 'fullname' must be the
                fully qualified (dotted) module name. It returns the imported
                module, or raises ZipImportError if it could not be imported.

                Deprecated since Python 3.10. Use exec_module() instead.
                """
                msg = ("zipimport.zipimporter.load_module() is deprecated and slated for "
                       "removal in Python 3.12; use exec_module() instead")
                _warnings.warn(msg, DeprecationWarning)
                code, ispackage, modpath = _get_module_code(self, fullname)
                mod = sys.modules.get(fullname)
                if mod is None or not isinstance(mod, _module_type):
                    mod = _module_type(fullname)
                    sys.modules[fullname] = mod
                mod.__loader__ = self

                try:
                    if ispackage:
                        # add __path__ to the module *before* the code gets
                        # executed
                        path = _get_module_path(self, fullname)
                        fullpath = _path_join(self.archive, path)
                        mod.__path__ = [fullpath]

                    if not hasattr(mod, '__builtins__'):
                        mod.__builtins__ = __builtins__
                    _fix_up_module(mod.__dict__, fullname, modpath)
                    exec(code, mod.__dict__)
                except:
                    del sys.modules[fullname]
                    raise

                try:
                    mod = outer._sys.modules[fullname]
                except KeyError:
                    raise ImportError(f'Loaded module {fullname!r} not found in sys.modules')
                _verbose_message('import {} # loaded from Zip {}', fullname, modpath)
                return mod

            def get_resource_reader(self, fullname):
                """Return the ResourceReader for a package in a zip file.

                If 'fullname' is a package within the zip file, return the
                'ResourceReader' object for the package.  Otherwise return None.
                """
                try:
                    if not self.is_package(fullname):
                        return None
                except ZipImportError:
                    return None
                from importlib.readers import ZipReader
                return ZipReader(self, fullname)

            def invalidate_caches(self):
                """Reload the file data of the archive path."""
                try:
                    self._files = _read_directory(self.archive)
                    _zip_directory_cache[self.archive] = self._files
                except ZipImportError:
                    _zip_directory_cache.pop(self.archive, None)
                    self._files = {}

            def __repr__(self):
                return f'<zipimporter object "{self.archive}{path_sep}{self.prefix}">'

        _zip_searchorder = (
            (path_sep + '__init__.pyc', True, True),
            (path_sep + '__init__.py', False, True),
            ('.pyc', True, False),
            ('.py', False, False),
        )

        def _get_module_path(self, fullname):
            return self.prefix + fullname.rpartition('.')[2]

        def _get_module_code(self, fullname):
            path = _get_module_path(self, fullname)
            import_error = None
            for suffix, isbytecode, ispackage in _zip_searchorder:
                fullpath = path + suffix
                _verbose_message('trying {}{}{}', self.archive, path_sep, fullpath, verbosity=2)
                try:
                    toc_entry = self._files[fullpath]
                except KeyError:
                    pass
                else:
                    modpath = toc_entry[0]
                    data = _get_data(self.archive, toc_entry)
                    code = None
                    if isbytecode:
                        try:
                            code = _unmarshal_code(self, modpath, fullpath, fullname, data)
                        except ImportError as exc:
                            import_error = exc
                    else:
                        code = _compile_source(modpath, data)
                    if code is None:
                        # bad magic number or non-matching mtime
                        # in byte code, try next
                        continue
                    modpath = toc_entry[0]
                    return code, ispackage, modpath
            else:
                if import_error:
                    msg = f"module load failed: {import_error}"
                    raise ZipImportError(msg, name=fullname) from import_error
                else:
                    raise ZipImportError(f"can't find module {fullname!r}", name=fullname)

        def _compile_source(pathname, source):
            source = _normalize_line_endings(source)
            return compile(source, pathname, 'exec', dont_inherit=True)

        def _normalize_line_endings(source):
            source = source.replace(b'\r\n', b'\n')
            source = source.replace(b'\r', b'\n')
            return source

        def _unmarshal_code(self, pathname, fullpath, fullname, data):
            exc_details = {
                'name': fullname,
                'path': fullpath,
            }

            flags = _classify_pyc(data, fullname, exc_details)

            hash_based = flags & 0b1 != 0
            if hash_based:
                check_source = flags & 0b10 != 0
                if (_imp.check_hash_based_pycs != 'never' and
                        (check_source or _imp.check_hash_based_pycs == 'always')):
                    source_bytes = _get_pyc_source(self, fullpath)
                    if source_bytes is not None:
                        source_hash = _imp.source_hash(
                            _RAW_MAGIC_NUMBER,
                            source_bytes,
                        )

                        _validate_hash_pyc(
                            data, source_hash, fullname, exc_details)
            else:
                source_mtime, source_size = \
                    _get_mtime_and_size_of_source(self, fullpath)

                if source_mtime:
                    # We don't use _bootstrap_external._validate_timestamp_pyc
                    # to allow for a more lenient timestamp check.
                    if (not _eq_mtime(_unpack_uint32(data[8:12]), source_mtime) or
                            _unpack_uint32(data[12:16]) != source_size):
                        _verbose_message(
                            f'bytecode is stale for {fullname!r}')
                        return None

            code = marshal.loads(data[16:])
            if not isinstance(code, _code_type):
                raise TypeError(f'compiled module {pathname!r} is not a code object')
            return code

        def _eq_mtime(t1, t2):
            # dostime only stores even seconds, so be lenient
            return abs(t1 - t2) <= 1

        def _get_pyc_source(self, path):
            # strip 'c' or 'o' from *.py[co]
            assert path[-1:] in ('c', 'o')
            path = path[:-1]

            try:
                toc_entry = self._files[path]
            except KeyError:
                return None
            else:
                return _get_data(self.archive, toc_entry)

        def _get_mtime_and_size_of_source(self, path):
            try:
                # strip 'c' or 'o' from *.py[co]
                assert path[-1:] in ('c', 'o')
                path = path[:-1]
                toc_entry = self._files[path]
                # fetch the time stamp of the .py file for comparison
                # with an embedded pyc time stamp
                time = toc_entry[5]
                date = toc_entry[6]
                uncompressed_size = toc_entry[3]
                return _parse_dostime(date, time), uncompressed_size
            except (KeyError, IndexError, TypeError):
                return 0, 0

        def _parse_dostime(d, t):
            return time.mktime((
                (d >> 9) + 1980,  # bits 9..15: year
                (d >> 5) & 0xF,  # bits 5..8: month
                d & 0x1F,  # bits 0..4: day
                t >> 11,  # bits 11..15: hours
                (t >> 5) & 0x3F,  # bits 8..10: minutes
                (t & 0x1F) * 2,  # bits 0..7: seconds / 2
                -1, -1, -1))

        def _get_data(archive, toc_entry):
            datapath, compress, data_size, file_size, file_offset, time, date, crc = toc_entry
            if data_size < 0:
                raise ZipImportError('negative data size')

            with _io.open_code(archive) as fp:
                # Check to make sure the local file header is correct
                try:
                    fp.seek(file_offset)
                except OSError:
                    raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                buffer = fp.read(30)
                if len(buffer) != 30:
                    raise EOFError('EOF read where not expected')

                if buffer[:4] != b'PK\x03\x04':
                    # Bad: Local File Header
                    raise ZipImportError(f'bad local file header: {archive!r}', path=archive)

                name_size = _unpack_uint16(buffer[26:28])
                extra_size = _unpack_uint16(buffer[28:30])
                header_size = 30 + name_size + extra_size
                file_offset += header_size  # Start of file data
                try:
                    fp.seek(file_offset)
                except OSError:
                    raise ZipImportError(f"can't read Zip file: {archive!r}", path=archive)
                raw_data = fp.read(data_size)
                if len(raw_data) != data_size:
                    raise OSError("zipimport: can't read data")

        def _get_module_info(self, fullname):
            path = _get_module_path(self, fullname)
            for suffix, isbytecode, ispackage in _zip_searchorder:
                fullpath = path + suffix
                if fullpath in self._files:
                    return ispackage
            return None

        def _is_dir(self, path):
            # See if this is a "directory". If so, it's eligible to be part
            # of a namespace package. We test by seeing if the name, with an
            # appended path separator, exists.
            dirpath = path + path_sep
            # If dirpath is present in self._files, we have a directory.
            return dirpath in self._files

        def _fix_up_module(ns, name, pathname, cpathname=None):
            # This function is used by PyImport_ExecCodeModuleObject().
            loader = ns.get('__loader__')
            spec = ns.get('__spec__')
            if not loader:
                if spec:
                    loader = spec.loader
                elif pathname == cpathname:
                    loader = SourcelessFileLoader(name, pathname)
                else:
                    loader = SourceFileLoader(name, pathname)
            if not spec:
                spec = outer.spec_from_file_location(name, pathname, loader=loader)
            try:
                ns['__spec__'] = spec
                ns['__loader__'] = loader
                ns['__file__'] = pathname
                ns['__cached__'] = cpathname
            except Exception:
                # Not important enough to report.
                pass

        outer._sys.path_hooks = [zipimporter, FileFinder.path_hook(*_get_supported_file_loaders())]
        outer._sys.meta_path = [DistutilsMetaFinder(), BuiltinImporter, FrozenImporter, PathFinder]

    def import_module(self, name, package=None):
        """Import a module.

        The 'package' argument is required when performing a relative import. It
        specifies the package to use as the anchor point from which to resolve the
        relative import to an absolute import.

        """
        level = 0
        if name.startswith('.'):
            if not package:
                msg = ("the 'package' argument is required to perform a relative "
                       "import for {!r}")
                raise TypeError(msg.format(name))
            for character in name:
                if character != '.':
                    break
                level += 1
        return self._safe_gcd_import(name[level:], package, level)

    def spec_from_loader(self, name, loader, *, origin=None,
                         is_package=None):  # deprecated implementation, deciding to remove for now
        """Return a module spec based on various loader methods."""
        if hasattr(loader, 'get_filename'):
            if is_package is None:
                return self.spec_from_file_location(name, loader=loader)
            search = [] if is_package else None
            return self._determine_allowed(self.spec_from_file_location(name, loader=loader, submodule_search_locations=search))

        if is_package is None:
            if hasattr(loader, 'is_package'):
                try:
                    is_package = loader.is_package(name)
                except ImportError:
                    is_package = None  # aka, undefined
            else:
                # the default
                is_package = False

        return self._determine_allowed(self.ModuleSpec(name, loader, origin=origin, is_package=is_package))

    _POPULATE = object()

    def spec_from_file_location(self, name, location=None, *, loader=None,
                                submodule_search_locations=_POPULATE):
        """Return a module spec based on a file location.

        To indicate that the module is a package, set
        submodule_search_locations to a list of directory paths.  An
        empty list is sufficient, though its not otherwise useful to the
        import system.

        The loader must take a spec as its only __init__() arg.

        """
        if location is None:
            # The caller may simply want a partially populated location-
            # oriented spec.  So we set the location to a bogus value and
            # fill in as much as we can.
            location = '<unknown>'
            if hasattr(loader, 'get_filename'):
                # ExecutionLoader
                try:
                    location = loader.get_filename(name)
                except ImportError:
                    pass
        else:
            location = os.fspath(location)

        # If the location is on the filesystem, but doesn't actually exist,
        # we could return None here, indicating that the location is not
        # valid.  However, we don't have a good way of testing since an
        # indirect location (e.g. a zip file or URL) will look like a
        # non-existent file relative to the filesystem.

        spec = self.ModuleSpec(name, loader, origin=location)
        spec._set_fileattr = True

        # Pick a loader if one wasn't provided.
        if loader is None:
            for loader_class, suffixes in self._get_supported_file_loaders():
                if location.endswith(tuple(suffixes)):
                    loader = loader_class(name, location)
                    spec.loader = loader
                    break
            else:
                return None

        # Set submodule_search_paths appropriately.
        if submodule_search_locations is RestrictedImport._POPULATE:
            # Check the loader.
            if hasattr(loader, 'is_package'):
                try:
                    is_package = loader.is_package(name)
                except ImportError:
                    pass
                else:
                    if is_package:
                        spec.submodule_search_locations = []
        else:
            spec.submodule_search_locations = submodule_search_locations
        if spec.submodule_search_locations == []:
            if location:
                dirname = self._path_split(location)[0]
                spec.submodule_search_locations.append(dirname)

        return spec


def _new_module(name):
    return type(sys)(name)


def _call_with_frames_removed(f, *args, **kwds):
    """remove_importlib_frames in import.c will always remove sequences
    of importlib frames that end with a call to this function

    Use it instead of a normal call in places where including the importlib
    frames introduces unwanted noise into the traceback (e.g. when executing
    module code)
    """
    return f(*args, **kwds)


def _object_name(obj):
    try:
        return obj.__qualname__
    except AttributeError:
        return type(obj).__qualname__


def _sanity_check(name, package, level):
    """Verify arguments are "sane"."""
    if not isinstance(name, str):
        raise TypeError('module name must be str, not {}'.format(type(name)))
    if level < 0:
        raise ValueError('level must be >= 0')
    if level > 0:
        if not isinstance(package, str):
            raise TypeError('__package__ not set to a string')
        elif not package:
            raise ImportError('attempted relative import with no known parent '
                              'package')
    if not name and level == 0:
        raise ValueError('Empty module name')


def _resolve_name(name, package, level):
    """Resolve a relative module name to an absolute one."""
    bits = package.rsplit('.', level - 1)
    if len(bits) < level:
        raise ImportError('attempted relative import beyond top-level package')
    base = bits[0]
    return '{}.{}'.format(base, name) if name else base


def _calc___package__(globals):
    """Calculate what __package__ should be.

    __package__ is not guaranteed to be defined or could be set to None
    to represent that its proper value is unknown.

    """
    package = globals.get('__package__')
    spec = globals.get('__spec__')
    if package is not None:
        if spec is not None and package != spec.parent:
            _warnings.warn("__package__ != __spec__.parent "
                           f"({package!r} != {spec.parent!r})",
                           ImportWarning, stacklevel=3)
        return package
    elif spec is not None:
        return spec.parent
    else:
        _warnings.warn("can't resolve package from __spec__ or __package__, "
                       "falling back on __name__ and __path__",
                       ImportWarning, stacklevel=3)
        package = globals['__name__']
        if '__path__' not in globals:
            package = package.rpartition('.')[0]
    return package


def _wrap(new, old):
    """Simple substitute for functools.update_wrapper."""
    for replace in ['__module__', '__name__', '__qualname__', '__doc__']:
        if hasattr(old, replace):
            setattr(new, replace, getattr(old, replace))
    new.__dict__.update(old.__dict__)


def _check_name(method):
    """Decorator to verify that the module being requested matches the one the
    loader can handle.

    The first argument (self) must define _name which the second argument is
    compared against. If the comparison fails then ImportError is raised.

    """

    def _check_name_wrapper(self, name=None, *args, **kwargs):
        if name is None:
            name = self.name
        elif self.name != name:
            raise ImportError('loader for %s cannot handle %s' % (self.name, name), name=name)
        return method(self, name, *args, **kwargs)

    _wrap(_check_name_wrapper, method)
    return _check_name_wrapper


class _DeadlockError(RuntimeError):
    pass


def set_multiple_attrs(obj: Any, lst: list[tuple[str, Any]]) -> None:
    """
    got tired of writing multiple obj.attr = blah statements.  Ugh.
    :param lst:
    :return:
    """
    for attr, val in lst:
        setattr(obj, attr, val)


def decode_source(source_bytes):
    """Decode bytes representing source code and return the string.

    Universal newline support is used in the decoding.
    """
    import tokenize  # To avoid bootstrap issues.
    source_bytes_readline = _io.BytesIO(source_bytes).readline
    encoding = tokenize.detect_encoding(source_bytes_readline)
    newline_decoder = _io.IncrementalNewlineDecoder(None, True)
    return newline_decoder.decode(source_bytes.decode(encoding[0]))


def _verbose_message(message, *args, verbosity=1):
    """Print the message to stderr if -v/PYTHONVERBOSE is turned on."""
    if sys.flags.verbose >= verbosity:
        if not message.startswith(('#', 'import ')):
            message = '# ' + message


def _unpack_uint32(data):
    """Convert 4 bytes in little-endian to an integer."""
    assert len(data) == 4
    return int.from_bytes(data, 'little')


def _unpack_uint16(data):
    """Convert 2 bytes in little-endian to an integer."""
    assert len(data) == 2
    return int.from_bytes(data, 'little')


def _pack_uint32(x):
    """Convert a 32-bit integer to little-endian."""
    return (int(x) & 0xFFFFFFFF).to_bytes(4, 'little')



MAGIC_NUMBER = (3413).to_bytes(2, 'little') + b'\r\n'
_RAW_MAGIC_NUMBER = int.from_bytes(MAGIC_NUMBER, 'little')


def _classify_pyc(data, name, exc_details):
    """Perform basic validity checking of a pyc header and return the flags field,
    which determines how the pyc should be further validated against the source.

    *data* is the contents of the pyc file. (Only the first 16 bytes are
    required, though.)

    *name* is the name of the module being imported. It is used for logging.

    *exc_details* is a dictionary passed to ImportError if it raised for
    improved debugging.

    ImportError is raised when the magic number is incorrect or when the flags
    field is invalid. EOFError is raised when the data is found to be truncated.

    """
    magic = data[:4]
    if magic != MAGIC_NUMBER:
        message = f'bad magic number in {name!r}: {magic!r}'
        _verbose_message('{}', message)
        raise ImportError(message, **exc_details)
    if len(data) < 16:
        message = f'reached EOF while reading pyc header of {name!r}'
        _verbose_message('{}', message)
        raise EOFError(message)
    flags = _unpack_uint32(data[4:8])
    # Only the first two flags are defined.
    if flags & ~0b11:
        message = f'invalid flags {flags!r} in {name!r}'
        raise ImportError(message, **exc_details)
    return flags


def _validate_timestamp_pyc(data, source_mtime, source_size, name,
                            exc_details):
    """Validate a pyc against the source last-modified time.

    *data* is the contents of the pyc file. (Only the first 16 bytes are
    required.)

    *source_mtime* is the last modified timestamp of the source file.

    *source_size* is None or the size of the source file in bytes.

    *name* is the name of the module being imported. It is used for logging.

    *exc_details* is a dictionary passed to ImportError if it raised for
    improved debugging.

    An ImportError is raised if the bytecode is stale.

    """
    if _unpack_uint32(data[8:12]) != (source_mtime & 0xFFFFFFFF):
        message = f'bytecode is stale for {name!r}'
        _verbose_message('{}', message)
        raise ImportError(message, **exc_details)
    if (source_size is not None and
        _unpack_uint32(data[12:16]) != (source_size & 0xFFFFFFFF)):
        raise ImportError(f'bytecode is stale for {name!r}', **exc_details)


def _validate_hash_pyc(data, source_hash, name, exc_details):
    """Validate a hash-based pyc by checking the real source hash against the one in
    the pyc header.

    *data* is the contents of the pyc file. (Only the first 16 bytes are
    required.)

    *source_hash* is the importlib.util.source_hash() of the source file.

    *name* is the name of the module being imported. It is used for logging.

    *exc_details* is a dictionary passed to ImportError if it raised for
    improved debugging.

    An ImportError is raised if the bytecode is stale.

    """
    if data[8:16] != source_hash:
        raise ImportError(
            f'hash in bytecode doesn\'t match hash of source {name!r}',
            **exc_details,
        )


def _write_atomic(path, data, mode=0o666):
    """Best-effort function to write data to a path atomically.
    Be prepared to handle a FileExistsError if concurrent writing of the
    temporary file is attempted."""
    # id() is used to generate a pseudo-random filename.
    path_tmp = '{}.{}'.format(path, id(path))
    fd = os.open(path_tmp,
                  os.O_EXCL | os.O_CREAT | os.O_WRONLY, mode & 0o666)
    try:
        # We first write data to a temporary file, and then use os.replace() to
        # perform an atomic rename.
        with _io.FileIO(fd, 'wb') as file:
            file.write(data)
        os.replace(path_tmp, path)
    except OSError:
        try:
            os.unlink(path_tmp)
        except OSError:
            pass
        raise


_code_type = type(_write_atomic.__code__)  # TODO this is not the same thing as used in source file (though it should work) check/test


def _compile_bytecode(data, name=None, bytecode_path=None, source_path=None):
    """Compile bytecode as found in a pyc."""
    code = marshal.loads(data)
    if isinstance(code, _code_type):
        _verbose_message('code object from {!r}', bytecode_path)
        if source_path is not None:
            _imp._fix_co_filename(code, source_path)
        return code
    else:
        raise ImportError('Non-code object in {!r}'.format(bytecode_path),
                          name=name, path=bytecode_path)


def _code_to_timestamp_pyc(code, mtime=0, source_size=0):
    "Produce the data for a timestamp-based pyc."
    data = bytearray(MAGIC_NUMBER)
    data.extend(_pack_uint32(0))
    data.extend(_pack_uint32(mtime))
    data.extend(_pack_uint32(source_size))
    data.extend(marshal.dumps(code))
    return data


def _code_to_hash_pyc(code, source_hash, checked=True):
    "Produce the data for a hash-based pyc."
    data = bytearray(MAGIC_NUMBER)
    flags = 0b1 | checked << 1
    data.extend(_pack_uint32(flags))
    assert len(source_hash) == 8
    data.extend(source_hash)
    data.extend(marshal.dumps(code))
    return data


def _calc_mode(path):
    """Calculate the mode permissions for a bytecode file."""
    try:
        mode = _path_stat(path).st_mode
    except OSError:
        mode = 0o666
    # We always ensure write access so we can update cached files
    # later even when the source files are read-only on Windows (#6074)
    mode |= 0o200
    return mode


def _path_stat(path):
    """Stat the path.

    Made a separate function to make it easier to override in experiments
    (e.g. cache stat results).

    """
    return os.stat(path)


def _find_module_shim(self, fullname):
    """Try to find a loader for the specified module by delegating to
    self.find_loader().

    This method is deprecated in favor of finder.find_spec().

    """
    _warnings.warn("find_module() is deprecated and "
                   "slated for removal in Python 3.12; use find_spec() instead",
                   DeprecationWarning)
    # Call find_loader(). If it returns a string (indicating this
    # is a namespace package portion), generate a warning and
    # return None.
    loader, portions = self.find_loader(fullname)
    if loader is None and len(portions):
        msg = 'Not importing directory {}: missing __init__'
        _warnings.warn(msg.format(portions[0]), ImportWarning)
    return loader


cp437_table = (
    # ASCII part, 8 rows x 16 chars
    '\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f'
    '\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f'
    ' !"#$%&\'()*+,-./'
    '0123456789:;<=>?'
    '@ABCDEFGHIJKLMNO'
    'PQRSTUVWXYZ[\\]^_'
    '`abcdefghijklmno'
    'pqrstuvwxyz{|}~\x7f'
    # non-ASCII part, 16 rows x 8 chars
    '\xc7\xfc\xe9\xe2\xe4\xe0\xe5\xe7'
    '\xea\xeb\xe8\xef\xee\xec\xc4\xc5'
    '\xc9\xe6\xc6\xf4\xf6\xf2\xfb\xf9'
    '\xff\xd6\xdc\xa2\xa3\xa5\u20a7\u0192'
    '\xe1\xed\xf3\xfa\xf1\xd1\xaa\xba'
    '\xbf\u2310\xac\xbd\xbc\xa1\xab\xbb'
    '\u2591\u2592\u2593\u2502\u2524\u2561\u2562\u2556'
    '\u2555\u2563\u2551\u2557\u255d\u255c\u255b\u2510'
    '\u2514\u2534\u252c\u251c\u2500\u253c\u255e\u255f'
    '\u255a\u2554\u2569\u2566\u2560\u2550\u256c\u2567'
    '\u2568\u2564\u2565\u2559\u2558\u2552\u2553\u256b'
    '\u256a\u2518\u250c\u2588\u2584\u258c\u2590\u2580'
    '\u03b1\xdf\u0393\u03c0\u03a3\u03c3\xb5\u03c4'
    '\u03a6\u0398\u03a9\u03b4\u221e\u03c6\u03b5\u2229'
    '\u2261\xb1\u2265\u2264\u2320\u2321\xf7\u2248'
    '\xb0\u2219\xb7\u221a\u207f\xb2\u25a0\xa0'
)


class OuterImportCall:

    def __enter__(self, name):
        self.name = name

    def __exit__(self):
        self.name = None


class ModCall(type(sys)):
    def __call__(self, name, allowed_imports_by_path: dict[str: list[str]] = frozendict.frozendict(), disallowed_imports_by_path: dict[str: list[str]] = frozendict.frozendict(), use_deepcopy: bool = False, stdin = None, stdout = None):
        """
        calls restricted import from module level, initializing a RestrictedImport object then using it
        :param name: name of file to import
        :param allowed_imports_by_path:
        :param disallowed_imports_by_path:
        :param use_deepcopy: whether to use copy or deepcopy on already loaded modules on outer scope
        :return: a module
        """
        RI = RestrictedImport(allowed_imports_by_path, disallowed_imports_by_path, use_deepcopy, stdin, stdout)
        return RI(name)

    RestrictedImport = RestrictedImport


sys.modules[__name__] = ModCall(__name__)