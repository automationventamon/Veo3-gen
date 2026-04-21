import bcrypt from 'bcryptjs';

const USERS = [
  { username: 'usr1', password: 'V3nt@m0n#Alpha1' },
  { username: 'usr2', password: 'V3nt@m0n#Beta2!' },
  { username: 'usr3', password: 'V3nt@m0n#Gamma3' },
  { username: 'usr4', password: 'V3nt@m0n#Delta4' },
  { username: 'usr5', password: 'V3nt@m0n#Epsilon5' },
];

export async function seedUsers(pool) {
  for (const u of USERS) {
    const [rows] = await pool.query('SELECT id FROM users WHERE username = ?', [u.username]);
    if (rows.length === 0) {
      const hash = await bcrypt.hash(u.password, 12);
      await pool.query('INSERT INTO users (username, password) VALUES (?, ?)', [u.username, hash]);
      console.log(`[seed] Created user: ${u.username}`);
    }
  }
}
