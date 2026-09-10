"""Native NTFS boundary tests; ACL mutations touch only each test's own tree."""

import ctypes
from ctypes import wintypes
import importlib
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires Windows file security")


def _module():
    assert importlib.util.find_spec("app.windows_private_directory") is not None, (
        "Windows private directory implementation is missing"
    )
    return importlib.import_module("app.windows_private_directory")


def _security(path, sddl=None):
    """Independent native fixture: inspect SD, or replace test-owned DACL."""
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    ptr = ctypes.c_void_p
    adv.GetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
                                        ptr, ptr, ptr, ptr, ctypes.POINTER(ptr)]
    adv.GetNamedSecurityInfoW.restype = wintypes.DWORD
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ptr, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ptr), ptr]
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ptr), ptr]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    adv.GetSecurityDescriptorDacl.argtypes = [ptr, ctypes.POINTER(wintypes.BOOL),
                                           ctypes.POINTER(ptr), ctypes.POINTER(wintypes.BOOL)]
    adv.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    adv.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
                                        ptr, ptr, ptr, ptr]
    adv.SetNamedSecurityInfoW.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = [ptr]
    kernel.LocalFree.restype = ptr
    descriptor, result = ptr(), ptr()
    try:
        if sddl is not None:
            assert adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None)
            present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), ptr()
            assert adv.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted))
            assert adv.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None) == 0
            return
        assert adv.GetNamedSecurityInfoW(str(path), 1, 5, None, None, None, None, ctypes.byref(descriptor)) == 0
        assert adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 5, ctypes.byref(result), None)
        return ctypes.wstring_at(result)
    finally:
        if result:
            kernel.LocalFree(result)
        if descriptor:
            kernel.LocalFree(descriptor)


def test_create_protected_acl_and_verify_inherited_tree(tmp_path):
    api = _module()
    parent_before = _security(tmp_path)
    actual = api.create_private_directory(tmp_path / "private-原文")
    assert isinstance(actual, Path) and actual.is_absolute() and actual.is_dir()
    assert actual == actual.resolve(strict=True)
    security = _security(actual)
    assert "D:P" in security
    assert security.count("(A;OICI;FA;;;") == 3
    assert ";;;SY)" in security and ";;;BA)" in security
    child = actual / "subdir"
    child.mkdir()
    (child / "data.txt").write_text("private data", encoding="utf-8")
    before = {p: _security(p) for p in (actual, child, child / "data.txt")}
    api.verify_private_tree(actual)
    assert before == {p: _security(p) for p in before}
    assert _security(tmp_path) == parent_before


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_existing_path_and_contents_are_untouched(tmp_path, kind):
    api = _module()
    leaf = tmp_path / "existing-sensitive-name"
    if kind == "directory":
        leaf.mkdir()
        (leaf / "sentinel").write_bytes(b"keep")
    else:
        leaf.write_bytes(b"keep")
    before = _security(leaf)
    with pytest.raises(api.WindowsPrivateDirectoryError) as caught:
        api.create_private_directory(leaf)
    assert "sensitive" not in str(caught.value)
    assert _security(leaf) == before
    assert (leaf / "sentinel" if kind == "directory" else leaf).read_bytes() == b"keep"


@pytest.mark.parametrize("path", ["relative", "C:relative", "\\\\server\\share\\leaf",
                                  "\\\\?\\C:\\leaf", "\\\\.\\C:\\leaf", "C:/a/../leaf",
                                  "C:/leaf:stream", "C:/leaf.", "C:/NUL"])
def test_invalid_paths_rejected(path):
    api = _module()
    for operation in (api.create_private_directory, api.verify_private_tree):
        with pytest.raises(api.WindowsPrivateDirectoryError):
            operation(Path(path))


def test_missing_parent_is_not_created(tmp_path):
    api = _module()
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.create_private_directory(tmp_path / "missing" / "leaf")
    assert not (tmp_path / "missing").exists()


def test_hardlink_rejected_without_changing_file(tmp_path):
    api = _module()
    root = api.create_private_directory(tmp_path / "private")
    original = root / "original"
    original.write_bytes(b"keep")
    os.link(original, root / "alias")
    before = _security(original)
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_private_tree(root)
    assert original.read_bytes() == b"keep" and _security(original) == before


@pytest.mark.parametrize("target", ["root", "file", "directory"])
def test_widened_acl_rejected_without_repair(tmp_path, target):
    api = _module()
    root = api.create_private_directory(tmp_path / "private")
    path = root
    if target == "file":
        path = root / "file"
        path.write_bytes(b"keep")
    elif target == "directory":
        path = root / "directory"
        path.mkdir()
    original = _security(path)
    _security(path, original + "(A;OICI;FA;;;WD)")
    widened = _security(path)
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_private_tree(root)
    assert _security(path) == widened


def test_missing_directory_inheritance_rejected(tmp_path):
    api = _module()
    root = api.create_private_directory(tmp_path / "private")
    _security(root, _security(root).replace("OICI", ""))
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_private_tree(root)


def test_reparse_ancestor_tree_and_broken_existing_leaf_rejected(tmp_path):
    api = _module()
    root = api.create_private_directory(tmp_path / "private")
    target = tmp_path / "target"
    target.mkdir()
    junction = root / "junction"
    # cmd's fixed mklink builtin is only a fixture, never a product facility.
    created = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert created.returncode == 0
    try:
        with pytest.raises(api.WindowsPrivateDirectoryError):
            api.verify_private_tree(root)
        with pytest.raises(api.WindowsPrivateDirectoryError):
            api.create_private_directory(junction / "leaf")
        assert not (target / "leaf").exists()
        target.rmdir()
        with pytest.raises(api.WindowsPrivateDirectoryError):
            api.create_private_directory(junction)
        assert junction.lstat().st_file_attributes & 0x400
    finally:
        junction.rmdir()


def test_native_backend_unavailable_is_fail_closed(tmp_path, monkeypatch):
    api = _module()
    monkeypatch.setattr(api, "_kernel32", None)
    for operation in (api.create_private_directory, api.verify_private_tree):
        with pytest.raises(api.WindowsPrivateDirectoryError, match="^windows_private_directory_unavailable$"):
            operation(tmp_path / "private")


@pytest.mark.parametrize("sddl", ["D:NO_ACCESS_CONTROL", "D:P"])
def test_null_and_empty_acl_rejected_read_only(tmp_path, sddl):
    api = _module()
    root = api.create_private_directory(tmp_path / "private")
    original = _security(root)
    try:
        _security(root, sddl)
        before = _security(root)
        with pytest.raises(api.WindowsPrivateDirectoryError):
            api.verify_private_tree(root)
        assert _security(root) == before
    finally:
        # Fixture cleanup only: empty ACL intentionally removes normal access.
        _security(root, original)


@pytest.mark.parametrize("replacement", ["CI", "OI", "OICINP", "OICIIO"])
def test_partial_or_nonpropagating_directory_grants_rejected(tmp_path, replacement):
    api = _module()
    root = api.create_private_directory(tmp_path / "private")
    original = _security(root)
    try:
        _security(root, original.replace("OICI", replacement))
        with pytest.raises(api.WindowsPrivateDirectoryError):
            api.verify_private_tree(root)
    finally:
        # Inherit-only ACEs remove current access; restore this test-owned ACL
        # so pytest can clean its temporary directory without permission errors.
        _security(root, original)
    # SetNamedSecurityInfo may add the auto-inherited control marker; owner,
    # protection, and all restored grants must still match the original.
    assert _security(root).replace("D:PAI(", "D:P(") == original.replace("D:PAI(", "D:P(")
    api.verify_private_tree(root)


def test_file_reparse_is_rejected(tmp_path):
    api = _module()
    root = api.create_private_directory(tmp_path / "private")
    original = root / "original"
    original.write_bytes(b"keep")
    link = root / "symlink"
    try:
        link.symlink_to(original)
    except OSError as error:
        if error.winerror == 1314:
            pytest.skip("Windows symlink privilege unavailable")
        raise
    try:
        with pytest.raises(api.WindowsPrivateDirectoryError):
            api.verify_private_tree(root)
        assert original.read_bytes() == b"keep"
    finally:
        link.unlink()
