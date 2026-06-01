# ADR-055: Declarative encrypted casts + app `Encrypter`

Status: Accepted (delivered WI-arvel-018)

Eloquent-parity increment (backlog `006`, story S3). Adds an app-level encrypter and
`"encrypted[:variant]"` cast specs. Touches PII handling — recorded with a security note.

## ADR-055-01: A new app `Encrypter`, separate from column-level `EncryptedType`

Status: Accepted

`database.casts.EncryptedType` is a SQLAlchemy `TypeDecorator` configured per column with an
explicit key (wire format v1, `key_id`-tagged for rolling migrations). The declarative cast
needs an **app-wide** encrypter keyed from `APP_KEY`, so we add `arvel.encryption.Encrypter`
(AES-256-GCM) with its own wire format (v2: `b64(VERSION || IV(12) || ct+tag)`). The two never
collide on disk because the version byte differs.

The 32-byte key is HKDF-SHA256-derived from the raw `APP_KEY` bytes (any length, `base64:`
prefix accepted), with `info=b"arvel-encrypter"` — the same derivation style the cookie session
store and URL signer already use. IV is random per write, so equal plaintexts produce different
ciphertexts (not searchable by equality, by design).

## ADR-055-02: `Crypt` facade caches per `APP_KEY`

Status: Accepted

`arvel.facades.Crypt` builds the encrypter lazily from `os.environ["APP_KEY"]` and caches it in a
dict keyed by the raw key string — so a rotated or test-monkeypatched key transparently rebuilds.
`Crypt.set_encrypter(enc)` pins one for tests; `set_encrypter(None)` reverts. A missing `APP_KEY`
raises `MissingAppKeyError` rather than silently using a zero key.

## ADR-055-03: Cast variants and the read/write/serialize contract

Status: Accepted

`_make_encrypted_cast(param)` handles `encrypted` (param `""`/`string`), `encrypted:json`,
`encrypted:array`, `encrypted:object`, `encrypted:collection`. Unknown variants raise at class
definition time.

- write: `string` → `encrypt_string(str(value))`; the others JSON-encode then encrypt
  (`Crypt.encrypt`). A `SimpleNamespace` is unwrapped to its `__dict__` first; `dict`/`list`
  (including `Collection`, a `list` subclass) pass straight to `json.dumps`.
- read: `string` → `decrypt_string`; the others decrypt then decode, with `object` →
  `SimpleNamespace` and `collection` → `Collection`.
- serialize: `object` → plain `dict`, `collection` → plain `list`; the rest need none (decrypted
  string/list/dict are already JSON-friendly).

Because reads decrypt, `to_dict()` exposes the **decrypted** value — matching Eloquent's
`toArray`. Use `__hidden__` to keep secrets out of serialized output. Cast-aware dirty tracking
compares decrypted values, so re-encrypting an unchanged value (new IV → new ciphertext) is
correctly seen as not dirty.
