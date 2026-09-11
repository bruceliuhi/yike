"""Provider-only schema guidance; application validators remain authoritative."""
from copy import deepcopy


def provider_json_schema(schema: dict, *, base_url: str) -> dict:
    """Adapt only the verified Ark endpoint, never mutate the original schema.

    Ark rejects string lengths and array counts in constrained decoding. Keep
    those requirements as textual guidance and enforce them locally as before.
    Walk schema nodes, not arbitrary dictionaries (property names can coincide
    with JSON Schema keywords).
    """
    result = deepcopy(schema)
    if base_url.rstrip('/') != 'https://ark.cn-beijing.volces.com/api/v3':
        return result

    def visit(node):
        if not isinstance(node, dict):
            return
        keys = {'string': ('minLength', 'maxLength'),
                'array': ('minItems', 'maxItems')}.get(node.get('type'), ())
        requirements = [f'{key}={node.pop(key)}' for key in keys if key in node]
        if requirements:
            node['description'] = (node.get('description', '')
                + ' Application requirements (strictly validated): '
                + ', '.join(requirements)).strip()
        for key in ('properties', '$defs', 'definitions', 'patternProperties'):
            for child in node.get(key, {}).values():
                visit(child)
        for key in ('items', 'additionalProperties', 'not', 'if', 'then', 'else'):
            visit(node.get(key))
        for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
            for child in node.get(key, []):
                visit(child)

    visit(result)
    return result
