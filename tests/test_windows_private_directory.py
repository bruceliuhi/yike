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


def _security(path, sddl=None, *, protected=True):
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
            flags = 0x80000004 if protected else 0x20000004
            assert adv.SetNamedSecurityInfoW(str(path), 1, flags, None, None, dacl, None) == 0
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


# Fixed Chromium UNKNOWN-channel network capability; independent native fixture.
_NETWORK_SID = ('S-1-15-3-1024-1528657515-1944437972-2795272136-1227674495-'
                '293963776-353393192-4060142787-1908764039')


def _browser_tree(tmp_path, relative, *, directory=False):
    api = _module()
    root = api.create_private_directory(tmp_path / 'browser')
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if directory:
        path.mkdir()
    else:
        path.write_bytes(b'fixture, not an account')
    return api, root, path


@pytest.mark.parametrize('relative', ['Local State', 'Default/Secure Preferences'])
def test_browser_duplicate_trusted_grants_are_readonly_and_profile_only(tmp_path, relative):
    api, root, path = _browser_tree(tmp_path, relative)
    sd = _security(path)
    _security(path, sd.replace(';ID;', ';;'), protected=False)
    before = _security(path)
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_private_tree(root)
    api.verify_browser_profile_tree(root)
    assert _security(path) == before


def test_browser_deny_file_execute_is_readonly_and_profile_only(tmp_path):
    api, root, path = _browser_tree(tmp_path, 'Default/Session Storage/CURRENT')
    _security(path, _security(path).replace('(A;', '(D;;WP;;;WD)(A;', 1))
    before = _security(path)
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_private_tree(root)
    api.verify_browser_profile_tree(root)
    assert _security(path) == before


@pytest.mark.parametrize('directory_name', ['Cache', 'Network', 'Safe Browsing Network', 'Shared Dictionary'])
def test_browser_network_capability_accepts_exact_subtrees_and_inheritance(tmp_path, directory_name):
    api, root, path = _browser_tree(tmp_path, f'Default/{directory_name}', directory=True)
    _security(path, _security(path) + f'(A;;0x1301bf;;;{_NETWORK_SID})(A;OICIIO;0xe0010000;;;{_NETWORK_SID})')
    (path / 'nested').mkdir()
    (path / 'nested' / 'data').write_bytes(b'fixture')
    before = {p: _security(p) for p in (path, path / 'nested', path / 'nested/data')}
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_private_tree(root)
    api.verify_browser_profile_tree(root)
    assert before == {p: _security(p) for p in before}


@pytest.mark.parametrize('relative', ['Network', 'Default/NetworkElse', 'Default/Preferences', 'Other/Network'])
def test_browser_capability_outside_exact_network_subtrees_rejected(tmp_path, relative):
    api, root, path = _browser_tree(tmp_path, relative, directory=True)
    _security(path, _security(path) + f'(A;;0x1301bf;;;{_NETWORK_SID})(A;OICIIO;0xe0010000;;;{_NETWORK_SID})')
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_browser_profile_tree(root)


@pytest.mark.parametrize('grant', [
    '(A;;FA;;;WD)',
    f'(A;;FA;;;{_NETWORK_SID})',
    f'(A;;0x40000;;;{_NETWORK_SID})',
    f'(A;;0x80000;;;{_NETWORK_SID})',
    f'(A;;0x1301bf;;;{_NETWORK_SID[:-1]}8)',
    '(D;;0x2;;;WD)',
], ids=['everyone-allow', 'cap-full', 'cap-write-dacl', 'cap-write-owner', 'unknown-cap', 'unknown-deny'])
def test_browser_unrecognized_or_widened_ace_rejected(tmp_path, grant):
    api, root, path = _browser_tree(tmp_path, 'Default/Network/data')
    original = _security(path)
    try:
        _security(path, original + grant)
        with pytest.raises(api.WindowsPrivateDirectoryError):
            api.verify_browser_profile_tree(root)
    finally:
        _security(path, original)


def test_browser_root_remains_strict(tmp_path):
    api = _module()
    root = api.create_private_directory(tmp_path / 'browser')
    _security(root, _security(root) + f'(A;;0x1301bf;;;{_NETWORK_SID})')
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_browser_profile_tree(root)


def test_browser_capability_no_propagate_directory_rejected(tmp_path):
    api, root, path = _browser_tree(tmp_path, 'Default/Network', directory=True)
    _security(path, _security(path) + f'(A;OICINP;0x1301bf;;;{_NETWORK_SID})')
    assert 'NP' in _security(path)
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_browser_profile_tree(root)


def test_browser_missing_trusted_subject_rejected(tmp_path):
    api, root, path = _browser_tree(tmp_path, 'Local State')
    import re
    _security(path, re.sub(r'\(A;[^)]*;;;BA\)', '', _security(path)))
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_browser_profile_tree(root)


def test_browser_hardlink_remains_rejected(tmp_path):
    api, root, path = _browser_tree(tmp_path, 'Local State')
    os.link(path, root / 'alias')
    with pytest.raises(api.WindowsPrivateDirectoryError):
        api.verify_browser_profile_tree(root)
