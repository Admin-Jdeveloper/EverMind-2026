import crypto from 'node:crypto';

export interface TokenUser {
  id: string;
  email: string;
  name?: string;
  image?: string;
}

/**
 * Generates an ephemeral (60s TTL), cryptographically signed server-to-server JWT.
 * Used exclusively by Next.js server actions and route handlers to authenticate
 * requests to Django REST Framework (Identity Bridge).
 */
export function generateInternalApiToken(user: TokenUser): string {
  const secret = process.env.INTERNAL_API_SECRET || 'development-internal-api-secret-key-must-be-min-32-chars';
  const issuer = process.env.INTERNAL_API_ISSUER || 'evermind-web';
  const audience = process.env.INTERNAL_API_AUDIENCE || 'evermind-api';

  const header = { alg: 'HS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub: user.id,
    email: user.email,
    name: user.name || '',
    image: user.image || '',
    iss: issuer,
    aud: audience,
    iat: now,
    exp: now + 60,
  };

  const encodedHeader = Buffer.from(JSON.stringify(header)).toString('base64url');
  const encodedPayload = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const signature = crypto
    .createHmac('sha256', secret)
    .update(`${encodedHeader}.${encodedPayload}`)
    .digest('base64url');

  return `${encodedHeader}.${encodedPayload}.${signature}`;
}

/**
 * Helper to execute an authenticated request from Next.js server to Django REST Framework.
 */
export async function fetchDjangoApi(
  endpoint: string,
  user: TokenUser,
  init?: RequestInit
): Promise<Response> {
  const djangoUrl = process.env.DJANGO_API_URL || 'http://127.0.0.1:8000';
  const token = generateInternalApiToken(user);

  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);
  headers.set('Content-Type', 'application/json');

  return fetch(`${djangoUrl}${endpoint}`, {
    ...init,
    headers,
  });
}
