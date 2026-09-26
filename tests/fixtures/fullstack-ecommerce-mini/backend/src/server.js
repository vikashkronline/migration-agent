const express = require('express');
const app = express();
app.use(express.json());

// In a real app, db client executes SQL against PostgreSQL or SQLite
const db = { query: async (sql, params) => [] };

app.get('/api/users', async (req, res) => {
  const result = await db.query('SELECT id, name, email FROM users');
  res.json(result);
});

app.post('/api/orders', async (req, res) => {
  const { user_id, total_amount } = req.body;
  const result = await db.query('INSERT INTO orders (user_id, total_amount) VALUES ($1, $2)', [user_id, total_amount]);
  res.status(201).json({ success: true });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
