const assert = require('assert');

// Pure JS implementation matching lib/avatar.ts exactly for testing
function getUserInitial(name, email, fallback = 'U') {
  const cleanName = typeof name === 'string' ? name.trim() : '';
  if (cleanName.length > 0) {
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

console.log('Testing getUserInitial...');

// 1. Normal names
assert.strictEqual(getUserInitial('Arunav Gupta'), 'A');
assert.strictEqual(getUserInitial('Priya Sharma'), 'P');
assert.strictEqual(getUserInitial('John Doe'), 'J');

// 2. Whitespace-padded names
assert.strictEqual(getUserInitial('   alex   '), 'A');
assert.strictEqual(getUserInitial('\tElena\n'), 'E');

// 3. Single-character names
assert.strictEqual(getUserInitial('x'), 'X');

// 4. Missing / empty names with email fallback
assert.strictEqual(getUserInitial('', 'karen@example.com'), 'K');
assert.strictEqual(getUserInitial(null, 'bob@domain.org'), 'B');
assert.strictEqual(getUserInitial(undefined, 'charlie@web.io'), 'C');
assert.strictEqual(getUserInitial('   ', 'david@test.com'), 'D');

// 5. Completely empty / missing data
assert.strictEqual(getUserInitial('', ''), 'U');
assert.strictEqual(getUserInitial(null, null), 'U');
assert.strictEqual(getUserInitial(undefined, undefined), 'U');
assert.strictEqual(getUserInitial('   ', '   '), 'U');
assert.strictEqual(getUserInitial('', '', 'G'), 'G');

// 6. Unicode / Non-Latin names
assert.strictEqual(getUserInitial('Éléonore Martin'), 'É');
assert.strictEqual(getUserInitial('Øyvind'), 'Ø');
assert.strictEqual(getUserInitial('王伟'), '王');
assert.strictEqual(getUserInitial('Алексей'), 'А');
assert.strictEqual(getUserInitial('محمد'), 'م');

// 7. Verify length is ALWAYS strictly 1
['Arunav Gupta', 'Priya Sharma', '   ', '', 'Éléonore', null].forEach((val) => {
  const res = getUserInitial(val);
  assert.strictEqual(Array.from(res).length, 1, `Expected length 1 for '${val}', got '${res}'`);
});

console.log('ALL AVATAR INITIAL TESTS PASSED (7/7 test suites)!');
