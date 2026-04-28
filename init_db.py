import sqlite3

def init_db():
    conn = sqlite3.connect("smartcart.db")
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # USERS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        profile_image TEXT
    )
    """)

    # ADMIN
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        profile_image TEXT,
        status TEXT DEFAULT 'pending'
    )
    """)

    # SUPERADMINS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS superadmins (
        superadmin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # PRODUCTS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        category TEXT,
        price REAL,
        image TEXT,
        admin_id INTEGER,
        status TEXT DEFAULT 'active',
        FOREIGN KEY (admin_id) REFERENCES admin(admin_id)
    )
    """)

    # ADDRESSES
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS addresses (
        address_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,

        full_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        address TEXT NOT NULL,
        landmark TEXT NOT NULL,
        city TEXT NOT NULL,
        district TEXT NOT NULL,
        state TEXT NOT NULL,
        country TEXT NOT NULL DEFAULT 'India',
        pincode TEXT NOT NULL,

        address_type TEXT,
        is_default INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    # CART
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cart (
        cart_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    )
    """)

    # ORDERS
    # ORDERS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        razorpay_order_id TEXT,
        razorpay_payment_id TEXT,
        amount REAL,
        payment_status TEXT,
        order_status TEXT DEFAULT 'Pending',

        full_name TEXT,
        phone TEXT,
        address TEXT,
        landmark TEXT,
        city TEXT,
        district TEXT,
        state TEXT,
        country TEXT,
        pincode TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        admin_id INTEGER,

        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (admin_id) REFERENCES admin(admin_id)
    )
    """)

    # ORDER ITEMS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        price REAL NOT NULL,
        total REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(order_id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    )
    """)

    conn.commit()
    conn.close()
    print("✅ SQLite database created successfully!")

# Run directly
if __name__ == "__main__":
    init_db()