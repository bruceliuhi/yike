"""Transport-only session registry double; PostgreSQL has separate real tests."""
from pilot.auth import InvalidPilotToken


class MemorySessionRegistry:
    def __init__(self, tenant_for_user):
        self.tenant_for_user = tenant_for_user
        self.revoked = set()

    def authenticate(self, claims):
        tenant = self.tenant_for_user(claims.user_id)
        if (claims.user_id, claims.revocation_key) in self.revoked:
            raise InvalidPilotToken("invalid pilot token")
        return tenant

    def revoke(self, credentials):
        for claims in credentials:
            try:
                self.tenant_for_user(claims.user_id)
            except PermissionError:
                continue
            self.revoked.add((claims.user_id, claims.revocation_key))
