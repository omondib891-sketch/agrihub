import sqlite3
from flask import g
import os

DATABASE = os.path.join('instance', 'agrihub.db')

def get_db():
    if 'db' not in g:
        os.makedirs('instance', exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            farm_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            county TEXT,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            description TEXT,
            image TEXT DEFAULT 'default.jpg',
            available INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total REAL NOT NULL,
            phone TEXT,
            delivery_address TEXT,
            payment_method TEXT DEFAULT 'M-Pesa',
            payment_status TEXT DEFAULT 'Unpaid',
            mpesa_code TEXT,
            paid_at TIMESTAMP,
            status TEXT DEFAULT 'Pending',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            mpesa_code TEXT,
            status TEXT DEFAULT 'Pending',
            confirmed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (buyer_id) REFERENCES users(id),
            FOREIGN KEY (seller_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            venue TEXT NOT NULL,
            description TEXT
        );
    ''')

    # Seed ASK 2026 events
    existing = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    if existing == 0:
        events = [
            ('Eldoret National Show', '2026-03-04', 'Eldoret', 'Annual national agricultural show'),
            ('Eastern Kenya Branch Show', '2026-03-12', 'Embu', 'Regional branch show'),
            ('Mt. Kenya Branch Show', '2026-05-20', 'Nanyuki', 'Regional show at the foot of Mt. Kenya'),
            ('S.E Kenya National Show', '2026-06-03', 'Machakos', 'National show for South Eastern Kenya'),
            ('Western Kenya Branch Show', '2026-06-10', 'Kakamega', 'Regional agricultural exhibition'),
            ('Meru National Show', '2026-06-17', 'Meru', 'National show featuring local agri-products'),
            ('Nakuru National Agricultural Show', '2026-07-01', 'Nakuru', "One of Kenya's premier agricultural shows"),
            ('Southern Kenya Branch Show', '2026-07-09', 'Kisii', 'Branch show for Southern Kenya'),
            ('Kisumu National Show', '2026-07-22', 'Kisumu', 'National show at the lakeside city'),
            ('Mombasa International Show', '2026-09-02', 'Mombasa', 'International agricultural & trade exhibition'),
            ('Central Kenya National Show', '2026-09-09', 'Nyeri', 'National show in the heart of Kenya'),
            ('Nairobi International Trade Fair', '2026-09-28', 'Nairobi (J/Park)', "Kenya's flagship international trade fair"),
            ('Kitale National Show', '2026-10-07', 'Kitale', 'National show in the North Rift'),
            ('National Ploughing Contest', '2026-11-20', 'Eldoret', 'Annual national ploughing competition'),
        ]
        db.executemany('INSERT INTO events (name, event_date, venue, description) VALUES (?,?,?,?)', events)
        db.commit()
