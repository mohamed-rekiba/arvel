#!/bin/sh
set -e

KC_URL="${KC_URL:-http://keycloak:8080}"
KC_ADMIN="${KC_ADMIN:-admin}"
KC_ADMIN_PASS="${KC_ADMIN_PASS:-admin_secret}"
REALM="arvel-test"
CLIENT_ID="arvel-test-client"

echo "Waiting for Keycloak at $KC_URL..."
until curl -sf "$KC_URL/realms/master" > /dev/null 2>&1; do
  sleep 2
done
echo "Keycloak is up."

ADMIN_TOKEN=$(curl -sf -X POST "$KC_URL/realms/master/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=admin-cli" \
  -d "username=$KC_ADMIN" \
  -d "password=$KC_ADMIN_PASS" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $ADMIN_TOKEN"

# Create the custom 'groups' client scope with group-membership mapper
echo "Creating 'groups' client scope..."
curl -sf -X POST -H "$AUTH" -H "Content-Type: application/json" \
  "$KC_URL/admin/realms/$REALM/client-scopes" \
  -d '{
    "name": "groups",
    "description": "Map user groups into the token",
    "protocol": "openid-connect",
    "attributes": {"include.in.token.scope": "true", "display.on.consent.screen": "false"},
    "protocolMappers": [{
      "name": "groups",
      "protocol": "openid-connect",
      "protocolMapper": "oidc-group-membership-mapper",
      "consentRequired": false,
      "config": {
        "full.path": "false",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "claim.name": "groups",
        "userinfo.token.claim": "true"
      }
    }]
  }' || echo "  (scope may already exist)"

# Look up client UUID
CLIENT_UUID=$(curl -sf -H "$AUTH" \
  "$KC_URL/admin/realms/$REALM/clients?clientId=$CLIENT_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
echo "Client UUID: $CLIENT_UUID"

# Link all default scopes (built-in + groups) to the client
echo "Linking scopes to client..."
ALL_SCOPES=$(curl -sf -H "$AUTH" "$KC_URL/admin/realms/$REALM/client-scopes")
for SCOPE_NAME in basic email profile roles web-origins acr groups; do
  SCOPE_ID=$(echo "$ALL_SCOPES" | python3 -c "
import sys,json
scopes = json.load(sys.stdin)
matches = [s['id'] for s in scopes if s['name'] == '$SCOPE_NAME']
print(matches[0] if matches else '')
")
  if [ -n "$SCOPE_ID" ]; then
    curl -sf -X PUT -H "$AUTH" \
      "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/default-client-scopes/$SCOPE_ID" 2>/dev/null
    echo "  Linked: $SCOPE_NAME"
  else
    echo "  Not found: $SCOPE_NAME"
  fi
done

echo "Keycloak realm setup complete."
