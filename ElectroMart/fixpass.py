import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('shop.db')
c = conn.cursor()

# pehle jo bhi purana hai usko delete karo
c.execute("DELETE FROM users WHERE username='admin' OR email='admin@electromart.local'")

new_hash = generate_password_hash('admin123')

c.execute("INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
          ('admin', 'admin@electromart.local', new_hash, 'owner'))

conn.commit()

row = c.execute("SELECT username, email, role FROM users WHERE username='admin'").fetchone()
print(f"User mil gaya: {row}")
print("SUCCESS -> admin / admin123 ready!")

conn.close()