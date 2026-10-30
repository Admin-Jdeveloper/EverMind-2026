/**
 * Derives exactly one uppercase initial for user avatars.
 * Strictly enforces single-character representation, safely handling
 * whitespace, missing profile data, empty names, and Unicode characters.
 *
 * Examples:
 *   "Arunav Gupta" -> "A"
 *   "Priya Sharma" -> "P"
 *   "  alex  " -> "A"
 *   "" (with email "john@example.com") -> "J"
 *   null -> "U"
 *   "Éléonore" -> "É"
 *   "李华" -> "李"
 */
export function getUserInitial(
  name?: string | null,
  email?: string | null,
  fallback = 'U'
): string {
  const cleanName = typeof name === 'string' ? name.trim() : '';
  if (cleanName.length > 0) {
    // Array.from handles surrogate pairs and Unicode code points correctly
    const firstChar = Array.from(cleanName)[0];
    return firstChar.toUpperCase();
  }

  const cleanEmail = typeof email === 'string' ? email.trim() : '';
  if (cleanEmail.length > 0) {
    const firstChar = Array.from(cleanEmail)[0];
    return firstChar.toUpperCase();
  }

  return (fallback || 'U').trim().slice(0, 1).toUpperCase() || 'U';
}
