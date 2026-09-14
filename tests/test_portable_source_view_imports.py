import ast
from app.windows_portable_inventory import HOST_FILES
from app.windows_portable_bundle import _HOST_PROBE


def test_source_view_modules_are_shipped_and_checked_by_isolated_host_probe():
    modules = {'app.windows_source_view', 'app.source_view_worker', 'app.xhs_source_navigation'}
    assert {name.replace('.', '/') + '.py' for name in modules} <= set(HOST_FILES)
    imports = {alias.name for node in ast.walk(ast.parse(_HOST_PROBE))
               if isinstance(node, ast.Import) for alias in node.names}
    assert modules <= imports
