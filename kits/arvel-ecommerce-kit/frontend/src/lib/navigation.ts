// Sanitizes a post-login `redirect` query value into a safe same-origin path.
// Without this, ?redirect=//evil.test or ?redirect=https://evil.test would let
// an attacker bounce a freshly-authenticated user to a phishing page.
export function safeInternalPath(raw: string | null | undefined, fallback = '/'): string {
  if (!raw) return fallback
  // Must be a rooted path, not a scheme (https:, javascript:) or bare reference.
  if (!raw.startsWith('/')) return fallback
  // Protocol-relative (//host) and backslash variants browsers normalize to it.
  if (raw.startsWith('//') || raw.startsWith('/\\')) return fallback
  if (raw.includes('\\')) return fallback
  return raw
}
