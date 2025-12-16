// server.js
'use strict';

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const express = require('express');
const cors = require('cors');
const { MongoClient } = require('mongodb');
const { v4: uuidv4 } = require('uuid');

// ==== ENV ====
const MONGO_URL   = process.env.MONGO_URL;                // ex: mongodb+srv://...
const DB_NAME     = process.env.DB_NAME || 'qomir';
const CORS_LIST   = (process.env.CORS_ORIGINS || '*')
  .split(',')
  .map(s => s.trim())
  .filter(Boolean);
const PORT        = Number(process.env.PORT || 5001);

// ==== App & Middlewares ====
const app = express();
app.use(express.json());
app.use(cors({
  origin: (origin, cb) => {
    // autoriser tout si '*', sinon vérifier la liste
    if (CORS_LIST.includes('*') || !origin || CORS_LIST.includes(origin)) {
      return cb(null, true);
    }
    return cb(new Error('Not allowed by CORS'));
  },
  credentials: true,
}));

// log simple
app.use((req, _res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.originalUrl}`);
  next();
});

// ==== DB ====
let client = null;
let db = null;

async function connectDB() {
  if (!MONGO_URL) {
    throw new Error('MONGO_URL manquant dans .env');
  }
  client = new MongoClient(MONGO_URL, {
    ignoreUndefined: true,
    serverSelectionTimeoutMS: 5000,
  });
  await client.connect();
  db = client.db(DB_NAME);
  console.log('MongoDB connecté');

  // Index utiles (optionnels)
  await db.collection('status_checks').createIndex({ id: 1 }, { unique: true });
  await db.collection('status_checks').createIndex({ timestamp: -1 });
}

// ==== Router /api ====
const api = express.Router();

// GET /api/
api.get('/', (_req, res) => {
  res.json({ message: 'Hello World' });
});

// POST /api/status
// body attendu: { "client_name": "..." }
api.post('/status', async (req, res) => {
  try {
    if (!db) return res.status(503).json({ detail: 'DB non connectée' });

    const { client_name } = req.body || {};
    if (typeof client_name !== 'string' || client_name.trim().length === 0) {
      return res.status(400).json({ detail: 'client_name requis (string non vide)' });
    }

    const statusObj = {
      id: uuidv4(),
      client_name: String(client_name),
      // On stocke en ISO string (comme dans ton code Python)
      timestamp: new Date().toISOString(),
    };

    await db.collection('status_checks').insertOne(statusObj);
    // On renvoie le même objet (sans _id)
    res.json(statusObj);
  } catch (e) {
    console.error('POST /api/status error:', e);
    res.status(500).json({ detail: 'Erreur serveur' });
  }
});

// GET /api/status
api.get('/status', async (_req, res) => {
  try {
    if (!db) return res.status(503).json({ detail: 'DB non connectée' });

    const list = await db
      .collection('status_checks')
      .find({}, { projection: { _id: 0 } }) // exclure _id comme en Python
      .sort({ timestamp: -1 })
      .toArray();

    // Les timestamps sont déjà en ISO string, pas besoin de re-convertir
    res.json(list);
  } catch (e) {
    console.error('GET /api/status error:', e);
    res.status(500).json({ detail: 'Erreur serveur' });
  }
});

app.use('/api', api);

// ==== Boot ====
async function start() {
  try {
    await connectDB();
  } catch (e) {
    console.error('Erreur de connexion Mongo au démarrage:', e.message);
    console.error('Le serveur démarre quand même, mais /api/* renverra 503 tant que la DB est indisponible.');
  }

  const server = app.listen(PORT, '0.0.0.0', () => {
    console.log(`API listening on http://localhost:${PORT}`);
  });

  const close = async () => {
    console.log('Arrêt en cours...');
    try { await client?.close(); } catch {}
    server.close(() => process.exit(0));
  };

  process.on('SIGINT', close);
  process.on('SIGTERM', close);
}

start();
