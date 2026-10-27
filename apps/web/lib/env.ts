/**
 * Evermind — Centralized Web Environment Configuration & Validation.
 */

export interface WebConfig {
  environment: 'development' | 'production' | 'test';
  appUrl: string;
  djangoApiUrl: string;
  internalApiSecret: string;
  internalApiIssuer: string;
  internalApiAudience: string;
  isProduction: boolean;
}

export function getWebConfig(): WebConfig {
  const env = (process.env.ENVIRONMENT || process.env.NODE_ENV || 'development').toLowerCase();
  const isProduction = env === 'production';

  const defaultAppUrl = isProduction ? 'https://app.evermind.io' : 'http://localhost:3000';
  const defaultDjangoUrl = isProduction ? 'https://api.evermind.io' : 'http://127.0.0.1:8000';

  const appUrl = process.env.NEXT_PUBLIC_APP_URL || defaultAppUrl;
  const djangoApiUrl = process.env.DJANGO_API_URL || defaultDjangoUrl;

  const internalApiSecret =
    process.env.INTERNAL_API_SECRET ||
    'development-internal-api-secret-key-must-be-min-32-chars';

  const internalApiIssuer = process.env.INTERNAL_API_ISSUER || 'evermind-web';
  const internalApiAudience = process.env.INTERNAL_API_AUDIENCE || 'evermind-api';

  return {
    environment: isProduction ? 'production' : env === 'test' ? 'test' : 'development',
    appUrl,
    djangoApiUrl,
    internalApiSecret,
    internalApiIssuer,
    internalApiAudience,
    isProduction,
  };
}

/**
 * Validates required production settings on Next.js server startup.
 */
export function validateProductionWebConfig(): { valid: boolean; errors: string[] } {
  const config = getWebConfig();
  const errors: string[] = [];

  if (config.isProduction) {
    if (config.djangoApiUrl.includes('127.0.0.1') || config.djangoApiUrl.includes('localhost')) {
      errors.push(
        'DJANGO_API_URL in production points to localhost (127.0.0.1). Set to your backend service URL.'
      );
    }
    if (
      !config.internalApiSecret ||
      config.internalApiSecret.includes('development-internal') ||
      config.internalApiSecret.length < 32
    ) {
      errors.push(
        'INTERNAL_API_SECRET is missing or using default development secret. Must be at least 32 characters.'
      );
    }
    if (!process.env.AUTH_SECRET) {
      errors.push('AUTH_SECRET is required in production for NextAuth v5 session security.');
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
