"""New, private Windows directories and read-only NTFS tree verification.

Security is supplied to CreateDirectoryW, never repaired after creation. Only
local drive paths are accepted. Handle-based checks reject reparse points and
hold ancestors against rename/delete while traversing. This is a point-in-time
check, not protection against concurrent writes by the same user or an admin.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


class WindowsPrivateDirectoryError(OSError):
    """Fixed error text; never include a caller path, SID, or native message."""


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p),
                ("inherit", wintypes.BOOL)]


class _FileInformation(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]


class _Acl(ctypes.Structure):
    _fields_ = [("revision", wintypes.BYTE), ("reserved", wintypes.BYTE),
                ("size", wintypes.WORD), ("count", wintypes.WORD),
                ("reserved2", wintypes.WORD)]


class _Ace(ctypes.Structure):
    _fields_ = [("type", wintypes.BYTE), ("flags", wintypes.BYTE),
                ("size", wintypes.WORD), ("mask", wintypes.DWORD),
                ("sid_start", wintypes.DWORD)]


_kernel32 = _advapi32 = None
if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _P = ctypes.c_void_p
    _PP = ctypes.POINTER(_P)
    for _name, _arguments, _result in (
        ("GetCurrentProcess", [], wintypes.HANDLE),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ("LocalFree", [_P], _P),
        ("CreateDirectoryW", [wintypes.LPCWSTR, ctypes.POINTER(_SecurityAttributes)], wintypes.BOOL),
        ("CreateFileW", [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, _P,
                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE], wintypes.HANDLE),
        ("GetFileInformationByHandle", [wintypes.HANDLE, ctypes.POINTER(_FileInformation)], wintypes.BOOL),
        ("GetFinalPathNameByHandleW", [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD], wintypes.DWORD),
    ):
        _function = getattr(_kernel32, _name)
        _function.argtypes, _function.restype = _arguments, _result
    for _name, _arguments, _result in (
        ("OpenProcessToken", [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)], wintypes.BOOL),
        ("GetTokenInformation", [wintypes.HANDLE, ctypes.c_int, _P, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        ("ConvertSidToStringSidW", [_P, _PP], wintypes.BOOL),
        ("IsValidSid", [_P], wintypes.BOOL),
        ("ConvertStringSecurityDescriptorToSecurityDescriptorW", [wintypes.LPCWSTR, wintypes.DWORD, _PP, _P], wintypes.BOOL),
        ("GetSecurityInfo", [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, _PP, _PP, _PP, _PP, _PP], wintypes.DWORD),
        ("GetSecurityDescriptorControl", [_P, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        ("IsValidAcl", [_P], wintypes.BOOL),
        ("GetAce", [_P, wintypes.DWORD, _PP], wintypes.BOOL),
    ):
        _function = getattr(_advapi32, _name)
        _function.argtypes, _function.restype = _arguments, _result


def _fail() -> None:
    raise WindowsPrivateDirectoryError("windows_private_directory_rejected")


def _validate_path(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        _fail()
    if len(path.drive) != 2 or path.drive[1] != ":" or not path.drive[0].isascii() or not path.drive[0].isalpha():
        _fail()
    if not path.name:
        _fail()
    for part in path.parts[1:]:
        if (part in (".", "..") or part.endswith((" ", "."))
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or Path(part).is_reserved()):
            _fail()
    return path


def _sid_text(sid) -> str:
    if not sid or not _advapi32.IsValidSid(sid):
        _fail()
    converted = ctypes.c_void_p()
    if not _advapi32.ConvertSidToStringSidW(sid, ctypes.byref(converted)):
        _fail()
    try:
        return ctypes.wstring_at(converted)
    finally:
        _kernel32.LocalFree(converted)


def _current_user_sid() -> str:
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(_kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        _fail()
    try:
        size = wintypes.DWORD()
        _advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not size.value or size.value > 65536:
            _fail()
        buffer = ctypes.create_string_buffer(size.value)
        if not _advapi32.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            _fail()
        return _sid_text(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
    finally:
        _kernel32.CloseHandle(token)


def _information(handle) -> _FileInformation:
    result = _FileInformation()
    if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(result)):
        _fail()
    if result.attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
        _fail()
    if not result.attributes & 0x10 and result.links != 1:
        _fail()
    return result


@contextmanager
def _open(path: Path, *, security: bool = False):
    # OPEN_REPARSE_POINT prevents following the leaf; ancestor handles pin each
    # already checked directory. Deliberately omit FILE_SHARE_DELETE.
    handle = _kernel32.CreateFileW(str(path), 0x80 | (0x20000 if security else 0),
                                  3, None, 3, 0x02200000, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        _fail()
    try:
        yield handle, _information(handle)
    finally:
        _kernel32.CloseHandle(handle)


def _actual_path(handle) -> Path:
    size = _kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0)
    if not size or size > 32768:
        _fail()
    buffer = ctypes.create_unicode_buffer(size + 1)
    written = _kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
    if not written or written >= len(buffer):
        _fail()
    text = buffer.value
    if text.startswith("\\\\?\\"):
        text = text[4:]
    result = Path(text)
    # A drive root is valid internally (but never a public creation target).
    if len(result.drive) != 2 or result.drive[1] != ":" or not result.is_absolute():
        _fail()
    return result


def _directory_chain(path: Path, stack: ExitStack) -> Path:
    current = Path(path.anchor)
    for part in (None, *path.parts[1:]):
        if part is not None:
            current /= part
        handle, info = stack.enter_context(_open(current))
        if not info.attributes & 0x10:
            _fail()
        current = _actual_path(handle)
    return current


def _verify_security(handle, *, directory: bool, root: bool, user: str) -> None:
    owner, dacl, descriptor = (ctypes.c_void_p() for _ in range(3))
    if _advapi32.GetSecurityInfo(handle, 1, 5, ctypes.byref(owner), None,
                               ctypes.byref(dacl), None, ctypes.byref(descriptor)):
        _fail()
    try:
        permitted = {user, "S-1-5-18", "S-1-5-32-544"}
        owner_text = _sid_text(owner)
        if owner_text not in permitted or (root and owner_text != user):
            _fail()
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not _advapi32.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            _fail()
        if not control.value & 0x4 or not dacl or (root and not control.value & 0x1000):
            _fail()
        if not _advapi32.IsValidAcl(dacl):
            _fail()
        acl = ctypes.cast(dacl, ctypes.POINTER(_Acl)).contents
        if acl.count != len(permitted):
            _fail()
        seen = set()
        for index in range(acl.count):
            pointer = ctypes.c_void_p()
            if not _advapi32.GetAce(dacl, index, ctypes.byref(pointer)):
                _fail()
            ace = ctypes.cast(pointer, ctypes.POINTER(_Ace)).contents
            # Only plain full-control ALLOW ACEs. No conditional/object grants,
            # deny ACEs, inherit-only, or no-propagate semantics are accepted.
            if ace.type != 0 or ace.size < ctypes.sizeof(_Ace) or ace.mask != 0x001F01FF:
                _fail()
            if ace.flags & ~0x13 or (directory and ace.flags & 3 != 3):
                _fail()
            sid = _sid_text(pointer.value + _Ace.sid_start.offset)
            if sid not in permitted or sid in seen:
                _fail()
            seen.add(sid)
        if seen != permitted:
            _fail()
    finally:
        if descriptor:
            _kernel32.LocalFree(descriptor)


def create_private_directory(path: Path) -> Path:
    """Atomically create one NEW leaf; existing parent is required and unchanged.

    The returned path is the native handle-resolved DOS path, including any MSIX
    redirected location. Failure never chmods, repairs, or removes existing data.
    A native post-create verification failure may leave the new empty directory.
    """
    if _kernel32 is None:
        raise WindowsPrivateDirectoryError("windows_private_directory_unavailable")
    try:
        path = _validate_path(path)
        user = _current_user_sid()
        with ExitStack() as stack:
            parent = _directory_chain(path.parent, stack)
            leaf = parent / path.name
            descriptor = ctypes.c_void_p()
            sddl = f"O:{user}D:P(A;OICI;FA;;;{user})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
            if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
                _fail()
            try:
                attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
                if not _kernel32.CreateDirectoryW(str(leaf), ctypes.byref(attributes)):
                    _fail()
            finally:
                _kernel32.LocalFree(descriptor)
            with _open(leaf, security=True) as (handle, info):
                if not info.attributes & 0x10:
                    _fail()
                _verify_security(handle, directory=True, root=True, user=user)
                return _actual_path(handle)
    except (OSError, ValueError, TypeError, RecursionError):
        raise WindowsPrivateDirectoryError("windows_private_directory_rejected") from None


def verify_private_tree(root: Path) -> None:
    """Read-only, fail-closed full traversal; caller must quiesce owned writers."""
    if _kernel32 is None:
        raise WindowsPrivateDirectoryError("windows_private_directory_unavailable")
    try:
        root = _validate_path(root)
        user = _current_user_sid()
        with ExitStack() as ancestors:
            parent = _directory_chain(root.parent, ancestors)

            def visit(path: Path, is_root: bool = False) -> None:
                with _open(path, security=True) as (handle, info):
                    directory = bool(info.attributes & 0x10)
                    if is_root and not directory:
                        _fail()
                    _verify_security(handle, directory=directory, root=is_root, user=user)
                    if directory:
                        with os.scandir(_actual_path(handle)) as entries:
                            for entry in entries:
                                visit(Path(entry.path))

            visit(parent / root.name, True)
    except (OSError, ValueError, TypeError, RecursionError):
        raise WindowsPrivateDirectoryError("windows_private_directory_rejected") from None
