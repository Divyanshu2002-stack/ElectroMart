import os, re, sqlite3, secrets
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "shop.db"
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
PAYMENT_FOLDER = BASE_DIR / "static" / "uploads" / "payments"
PAYMENT_FOLDER.mkdir(parents=True, exist_ok=True)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "electromart_final_secret_2024")

CATEGORIES = ["Pipes & Fittings", "Wires & Cables", "Switches & Fittings", "Lights & LEDs", "Fancy & Pencil Lights",
              "Fans & Coolers", "Home Appliances", "Tools & Materials"]

ALLOWED_PINCODES = ["248001", "248002", "248003", "248005", "248006", "248007", "248009", "248171"]
FREE_DELIVERY_LIMIT = 500
DELIVERY_CHARGE = 40
UPI_ID = "9667311958@ybl"
UPI_NAME = "ElectroMart Dehradun"

def get_db():
    db = sqlite3.connect(DATABASE, timeout=15)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL DEFAULT 0, description TEXT DEFAULT '', stock INTEGER NOT NULL DEFAULT 0, image TEXT DEFAULT '', video TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner', 'customer')), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER, quantity INTEGER, total_price REAL, status TEXT DEFAULT 'Placed', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS wishlist (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER, UNIQUE(user_id, product_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS khata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            mobile TEXT DEFAULT '',
            address TEXT DEFAULT '',
            items TEXT DEFAULT '',
            total_amount REAL DEFAULT 0,
            paid_amount REAL DEFAULT 0,
            balance REAL DEFAULT 0,
            status TEXT DEFAULT 'Udhar',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        for col in ["address TEXT DEFAULT ''", "delivery_charge REAL DEFAULT 0", "pincode TEXT DEFAULT ''",
                    "payment_method TEXT DEFAULT 'COD'", "payment_screenshot TEXT DEFAULT ''",
                    "payment_status TEXT DEFAULT 'Pending'"]:
            try: db.execute(f"ALTER TABLE orders ADD COLUMN {col}")
            except: pass
        for col in ["cost_price REAL DEFAULT 0", "video TEXT DEFAULT ''"]:
            try: db.execute(f"ALTER TABLE products ADD COLUMN {col}")
            except: pass
        if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            db.executemany("INSERT INTO products (name, category, price, cost_price, description, stock, image) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("LED Bulb 9W", "Lights & LEDs", 120, 80, "Philips Energy Saving", 50, ""),
                    ("Inverter Pipe 1 inch", "Pipes & Fittings", 45, 30, "Heavy duty pipe", 100, ""),
                    ("Lenter Pipe", "Pipes & Fittings", 65, 40, "Lenter pipe strong", 3, ""),
                    ("Copper Wire Roll", "Wires & Cables", 650, 500, "1.5mm Copper Wire", 20, ""),
                    ("Ceiling Fan", "Fans & Coolers", 1850, 1500, "High Speed Fan", 10, "")
                ])
        db.commit()

def csrf_token():
    if "_csrf_token" not in session: session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]
app.jinja_env.globals["csrf_token"] = csrf_token

def validate_csrf():
    supplied = request.form.get("csrf_token", ""); expected = session.get("_csrf_token", "")
    if expected and supplied and not secrets.compare_digest(supplied, expected): abort(400)

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("user_id"): flash("Please log in first.", "error"); return redirect(url_for("login"))
        return f(*a, **k)
    return w

def owner_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("user_id") or session.get("role") != "owner": flash("Owner login required.", "error"); return redirect(url_for("owner_login"))
        return f(*a, **k)
    return w

def valid_email(e): return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) is not None

def make_login(u):
    session.clear()
    session["user_id"] = u["id"]
    session["role"] = u["role"]
    session["username"] = u["username"]
    session["email"] = u["email"]
    session["_csrf_token"] = secrets.token_urlsafe(32)

@app.route("/")
def home():
    q = request.args.get('q', '').strip(); cat = request.args.get('category', '').strip()
    with get_db() as db:
        query = "SELECT * FROM products WHERE 1=1"; params = []
        if q: query += " AND (LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?))"; params.extend([f'%{q}%', f'%{q}%'])
        if cat: query += " AND category = ?"; params.append(cat)
        query += " ORDER BY id DESC"; products = db.execute(query, params).fetchall()
    cart_count = sum(session.get('cart', {}).values())
    return render_template("index.html", products=products, categories=CATEGORIES, query=q, selected_cat=cat, cart_count=cart_count)

@app.route("/index")
def index(): return redirect(url_for("home"))

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    with get_db() as db: p = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p: abort(404)
    with get_db() as db: related = db.execute("SELECT * FROM products WHERE category=? AND id != ? LIMIT 4", (p['category'], product_id)).fetchall()
    return render_template("product_detail.html", p=p, related=related)

app.add_url_rule('/product/<int:product_id>', endpoint='product', view_func=product_detail)

@app.route("/add_to_cart/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    validate_csrf(); qty = int(request.form.get('quantity', 1))
    with get_db() as db:
        p = db.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()
        if not p: abort(404)
        if p['stock'] <= 0: flash("❌ Out of Stock!", "error"); return redirect(url_for("product_detail", product_id=product_id))
        cart = session.get('cart', {}); current_qty = cart.get(str(product_id), 0)
        if current_qty + qty > p['stock']: flash(f"⚠️ Only {p['stock']} left!", "error"); return redirect(url_for("product_detail", product_id=product_id))
    cart = session.get('cart', {}); cart[str(product_id)] = cart.get(str(product_id), 0) + qty; session['cart'] = cart; flash("Added to cart!", "success")
    if request.args.get("buy") == "1": return redirect(url_for("checkout_page"))
    return redirect(url_for("product_detail", product_id=product_id))

@app.route("/cart")
@login_required
def cart():
    cart_data = session.get('cart', {}); products = []; total = 0
    if cart_data:
        with get_db() as db:
            for pid, qty in cart_data.items():
                p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
                if p: products.append({'product': p, 'qty': qty, 'subtotal': p['price'] * qty}); total += p['price'] * qty
    return render_template("cart.html", cart_items=products, total=total)

@app.route("/remove_from_cart/<int:product_id>", methods=["POST"])
@login_required
def remove_from_cart(product_id):
    validate_csrf(); cart = session.get('cart', {}); cart.pop(str(product_id), None); session['cart'] = cart; return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET"])
@login_required
def checkout_page():
    cart_data = session.get('cart', {})
    if not cart_data: flash("Cart empty", "error"); return redirect(url_for("cart"))
    cart_items = []; total = 0
    with get_db() as db:
        for pid, qty in cart_data.items():
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if p: cart_items.append({'product': p, 'qty': qty, 'subtotal': p['price'] * qty}); total += p['price'] * qty
    delivery_charge = 0 if total >= FREE_DELIVERY_LIMIT else DELIVERY_CHARGE; final_total = total + delivery_charge
    return render_template("checkout.html", cart_items=cart_items, total=total, delivery_charge=delivery_charge, final_total=final_total, allowed_pincodes=ALLOWED_PINCODES, upi_id=UPI_ID, upi_name=UPI_NAME)

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    validate_csrf(); address = request.form.get("address", "").strip(); pincode = request.form.get("pincode", "").strip(); payment_method = request.form.get("payment_method", "COD").strip()
    if len(address) < 10: flash("Full address likho bhai!", "error"); return redirect(url_for("checkout_page"))
    if pincode not in ALLOWED_PINCODES: flash(f"❌ {pincode} pe delivery nahi hai.", "error"); return redirect(url_for("checkout_page"))
    cart_data = session.get('cart', {})
    if not cart_data: flash("Cart empty", "error"); return redirect(url_for("cart"))
    with get_db() as db:
        total_cart = 0
        for pid, qty in cart_data.items():
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if p: total_cart += p['price'] * qty
        delivery_charge = 0 if total_cart >= FREE_DELIVERY_LIMIT else DELIVERY_CHARGE
        screenshot_filename = ""
        if payment_method == "UPI":
            file = request.files.get("payment_screenshot")
            if file and file.filename:
                ext = file.filename.rsplit(".",1)[-1].lower()
                if ext in ["jpg","jpeg","png","webp"]:
                    screenshot_filename = secrets.token_hex(8) + "." + ext
                    file.save(PAYMENT_FOLDER / screenshot_filename)
        for pid, qty in cart_data.items():
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if p and p['stock'] >= qty:
                full_address = f"{address} | Pincode: {pincode}"
                db.execute("INSERT INTO orders (user_id, product_id, quantity, total_price, address, delivery_charge, pincode, payment_method, payment_screenshot, payment_status) VALUES (?,?,?,?,?,?,?,?,?,?)", (session['user_id'], pid, qty, (p['price'] * qty) + (delivery_charge/len(cart_data)), full_address, delivery_charge, pincode, payment_method, screenshot_filename, "Pending" if payment_method=="UPI" else "COD"))
                db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, pid))
            else: flash(f"Out of stock!", "error"); return redirect(url_for("cart"))
        db.commit()
    session['cart'] = {}
    if payment_method == "UPI": flash(f"✅ UPI Screenshot Received! Bank of Baroda (9667311958@ybl) check karke bhej denge. ₹{int(total_cart+delivery_charge)}", "success")
    else: flash(f"Order Placed! COD ₹{int(total_cart+delivery_charge)}", "success")
    return redirect(url_for("my_orders"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        validate_csrf(); username = request.form.get("username", "").strip(); email = request.form.get("email", "").strip().lower(); password = request.form.get("password", "")
        try:
            if len(username) < 3: raise ValueError("Username min 3 chars")
            if not valid_email(email): raise ValueError("Valid email required")
            if len(password) < 8: raise ValueError("Password min 8 chars")
            with get_db() as db: db.execute("INSERT INTO users (username,email,password_hash,role) VALUES (?,?,?,?)", (username, email, generate_password_hash(password), 'customer'))
            flash("Account created. Login now.", "success"); return redirect(url_for("login"))
        except Exception as e: flash(str(e), "error")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        validate_csrf(); identity = request.form.get("identity", "").strip(); password = request.form.get("password", "")
        with get_db() as db: user = db.execute("SELECT * FROM users WHERE role='customer' AND (username=? OR email=?)", (identity, identity.lower())).fetchone()
        if user and check_password_hash(user["password_hash"], password): make_login(user); return redirect(url_for("home"))
        flash("Incorrect customer login.", "error")
    return render_template("login.html", owner_login=False)

@app.route("/owner/login", methods=["GET", "POST"])
def owner_login():
    if request.method == "POST":
        validate_csrf(); identity = request.form.get("identity", "").strip(); password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE role='owner' AND (username=? OR email=?)", (identity, identity.lower())).fetchone()
            if not user:
                db.execute("INSERT OR IGNORE INTO users (username,email,password_hash,role) VALUES (?,?,?,?)", ("admin", "admin@electromart.local", generate_password_hash("admin123"), "owner"))
                user = db.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        if user and check_password_hash(user["password_hash"], password): make_login(user); return redirect(url_for("admin"))
        flash("Incorrect owner login.", "error")
    return render_template("login.html", owner_login=True)

@app.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "POST":
        try: validate_csrf()
        except: pass
    session.clear()
    flash("Logged out.", "success")
    return redirect('/account')

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    with get_db() as db: user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        validate_csrf(); username = request.form.get("username", "").strip(); email = request.form.get("email", "").strip().lower()
        with get_db() as db: db.execute("UPDATE users SET username=?, email=? WHERE id=?", (username, email, user["id"]))
        session["username"] = username; session["email"] = email; flash("Profile updated!", "success"); return redirect(url_for("settings"))
    return render_template("settings.html", user=user)

@app.route("/my-orders")
@login_required
def my_orders():
    with get_db() as db: orders = db.execute("SELECT orders.id, orders.quantity, orders.total_price, orders.status, orders.created_at, orders.address, orders.payment_method, orders.payment_status, products.name as product_name, products.image FROM orders JOIN products ON orders.product_id = products.id WHERE orders.user_id = ? ORDER BY orders.id DESC", (session['user_id'],)).fetchall()
    return render_template("my_orders.html", orders=orders)

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        validate_csrf(); old = request.form.get("old_password", ""); new = request.form.get("new_password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
            if not check_password_hash(user["password_hash"], old): flash("Old password galat hai!", "error")
            elif len(new) < 8: flash("New password min 8 chars!", "error")
            else: db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), session['user_id'])); flash("Password change ho gaya!", "success"); return redirect(url_for("settings"))
    return render_template("change_password.html")

# --- NEW OWNER PASSWORD CHANGE ---
@app.route("/owner/change-password", methods=["GET", "POST"])
@owner_required
def owner_change_password():
    if request.method == "POST":
        validate_csrf()
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if new != confirm:
            flash("Naya password match nahi kar raha!", "error")
            return redirect(url_for("owner_change_password"))
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE id=?", (session['user_id'],)).fetchone()
            if not check_password_hash(user["password_hash"], old):
                flash("Purana password galat hai!", "error")
            elif len(new) < 8:
                flash("Naya password min 8 chars!", "error")
            else:
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), session['user_id']))
                db.commit()
                flash("Owner Password Change Ho Gaya! ✅", "success")
                return redirect(url_for("admin"))
    return render_template("change_password.html")

@app.route("/wishlist")
@login_required
def wishlist():
    with get_db() as db: items = db.execute("SELECT products.* FROM wishlist JOIN products ON wishlist.product_id = products.id WHERE wishlist.user_id=?", (session['user_id'],)).fetchall()
    return render_template("wishlist.html", products=items)

@app.route("/wishlist/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_wishlist(product_id):
    validate_csrf()
    with get_db() as db: db.execute("INSERT OR IGNORE INTO wishlist (user_id, product_id) VALUES (?,?)", (session['user_id'], product_id))
    flash("Added to Wishlist ❤️", "success"); return redirect(url_for("product_detail", product_id=product_id))

@app.route("/forgot-password")
def forgot_password(): return render_template("forgot_password.html")

@app.route("/owner")
@owner_required
def admin():
    cat = request.args.get('category','').strip()
    with get_db() as db:
        if cat:
            products = db.execute("SELECT * FROM products WHERE category=? ORDER BY id DESC", (cat,)).fetchall()
        else:
            products = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
        orders = db.execute("SELECT orders.id, orders.quantity, orders.total_price, orders.status, orders.created_at, orders.address, orders.payment_method, orders.payment_screenshot, orders.payment_status, users.username, users.email, products.name as product_name FROM orders JOIN users ON orders.user_id = users.id JOIN products ON orders.product_id = products.id ORDER BY orders.id DESC").fetchall()
        all_products = db.execute("SELECT * FROM products").fetchall()
        all_low = [p for p in all_products if (p['stock'] is not None and p['stock'] <= 5)]
        khata_total = db.execute("SELECT SUM(balance) as t, COUNT(*) as c FROM khata WHERE status='Udhar'").fetchone()
    return render_template("admin.html", products=products, orders=orders, categories=CATEGORIES, low_stock=all_low, selected_cat=cat, khata_total=khata_total)

@app.route("/owner/add", methods=["POST"])
@owner_required
def add_product():
    validate_csrf(); name = request.form.get("name", "").strip(); cat = request.form.get("category", ""); price = float(request.form.get("price", "0")); cost_price = float(request.form.get("cost_price", "0") or 0); desc = request.form.get("description", ""); stock = int(request.form.get("stock", "0"))
    image_filename = ""; video_filename = ""
    photo = request.files.get("photo")
    if photo and photo.filename:
        ext = photo.filename.rsplit(".", 1)[-1].lower()
        if ext in ["jpg", "jpeg", "png", "webp", "avif"]:
            image_filename = secrets.token_hex(8) + "." + ext; photo.save(UPLOAD_FOLDER / image_filename)
    video = request.files.get("video")
    if video and video.filename:
        ext = video.filename.rsplit(".", 1)[-1].lower()
        if ext in ["mp4", "webm", "mov", "avi", "mkv"]:
            video_filename = secrets.token_hex(8) + "." + ext; video.save(UPLOAD_FOLDER / video_filename)
    with get_db() as db: db.execute("INSERT INTO products (name,category,price,cost_price,description,stock,image,video) VALUES (?,?,?,?,?,?,?,?)", (name, cat, price, cost_price, desc, stock, image_filename, video_filename))
    flash("Product added! 📸", "success"); return redirect(url_for("admin"))

@app.route("/owner/delete/<int:product_id>", methods=["POST"])
@owner_required
def delete_product(product_id):
    validate_csrf();
    with get_db() as db: db.execute("DELETE FROM products WHERE id=?", (product_id,))
    flash("Product deleted.", "success"); return redirect(url_for("admin"))

@app.route("/owner/order_status/<int:order_id>", methods=["POST"])
@owner_required
def update_order_status(order_id):
    validate_csrf(); new_status = request.form.get("status", ""); allowed = ["Placed", "Packed", "Shipped", "Out for Delivery", "Delivered", "Cancelled"]
    if new_status not in allowed: flash("Invalid status!", "error"); return redirect(url_for("admin"))
    with get_db() as db: db.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id)); db.commit()
    flash(f"Order #{order_id} -> {new_status} ✅", "success"); return redirect(url_for("admin"))

@app.route("/owner/verify_payment/<int:order_id>", methods=["POST"])
@owner_required
def verify_payment(order_id):
    validate_csrf(); new_status = request.form.get("payment_status", "")
    if new_status in ["Verified", "Rejected"]:
        with get_db() as db: db.execute("UPDATE orders SET payment_status=? WHERE id=?", (new_status, order_id)); db.commit()
        flash(f"Payment {new_status}!", "success")
    return redirect(url_for("admin"))

@app.route("/owner/edit/<int:product_id>", methods=["GET", "POST"])
@owner_required
def edit_product(product_id):
    with get_db() as db: p = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p: abort(404)
    if request.method == "POST":
        validate_csrf(); name = request.form.get("name", "").strip(); cat = request.form.get("category", ""); price = float(request.form.get("price", "0")); cost_price = float(request.form.get("cost_price", "0") or p['cost_price'] or 0); desc = request.form.get("description", ""); stock = int(request.form.get("stock", "0"))
        image_filename = p["image"]; video_filename = p["video"] if "video" in p.keys() else ""
        photo = request.files.get("photo")
        if photo and photo.filename:
            ext = photo.filename.rsplit(".", 1)[-1].lower()
            if ext in ["jpg", "jpeg", "png", "webp", "avif"]:
                if image_filename and (UPLOAD_FOLDER / image_filename).exists():
                    try: os.remove(UPLOAD_FOLDER / image_filename)
                    except: pass
                image_filename = secrets.token_hex(8) + "." + ext; photo.save(UPLOAD_FOLDER / image_filename)
        video = request.files.get("video")
        if video and video.filename:
            ext = video.filename.rsplit(".", 1)[-1].lower()
            if ext in ["mp4", "webm", "mov", "avi", "mkv"]:
                if video_filename and (UPLOAD_FOLDER / video_filename).exists():
                    try: os.remove(UPLOAD_FOLDER / video_filename)
                    except: pass
                video_filename = secrets.token_hex(8) + "." + ext; video.save(UPLOAD_FOLDER / video_filename)
        with get_db() as db: db.execute("UPDATE products SET name=?, category=?, price=?, cost_price=?, description=?, stock=?, image=?, video=? WHERE id=?", (name, cat, price, cost_price, desc, stock, image_filename, video_filename, product_id)); db.commit()
        flash(f"Product {name} Updated! ✏️", "success"); return redirect(url_for("admin"))
    return render_template("edit_product.html", p=p, categories=CATEGORIES)

@app.route('/owner/quick-bill')
@owner_required
def quick_bill():
    with get_db() as db:
        products = db.execute("SELECT * FROM products ORDER BY name ASC").fetchall()
    return render_template("quick_bill.html", products=products)

@app.route('/owner/quick-bill/print', methods=["POST"])
@owner_required
def quick_bill_print():
    validate_csrf()
    customer_name = request.form.get("customer_name","Cash Customer")
    product_ids = request.form.getlist("product_id")
    qtys = request.form.getlist("qty")
    items_list = []
    grand_total = 0
    with get_db() as db:
        for pid, qty in zip(product_ids, qtys):
            if pid and qty and int(qty) > 0:
                p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
                if p:
                    q = int(qty)
                    subtotal = p['price'] * q
                    grand_total += subtotal
                    items_list.append({"name": p['name'], "price": p['price'], "qty": q, "total": subtotal})
                    db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (q, pid))
        db.commit()
    return render_template("bill_print.html", type="quick", customer=customer_name, items_list=items_list, grand_total=grand_total)

@app.route('/owner/report')
@owner_required
def daily_report():
    with get_db() as db:
        today_orders = db.execute("""
            SELECT orders.*, products.name, products.cost_price, products.price 
            FROM orders 
            JOIN products ON orders.product_id = products.id 
            WHERE date(orders.created_at) = date('now','localtime')
        """).fetchall()
        all_time = db.execute("""
            SELECT SUM(total_price) as total_sale, COUNT(*) as total_orders FROM orders WHERE date(created_at) = date('now','localtime')
        """).fetchone()
        month_data = db.execute("""
            SELECT date(created_at) as date, SUM(total_price) as sale, COUNT(*) as orders 
            FROM orders GROUP BY date(created_at) ORDER BY date DESC LIMIT 7
        """).fetchall()
        profit_today = 0
        for o in today_orders:
            try:
                cost = o['cost_price'] or 0
                sell = o['price'] or 0
                profit_today += (sell - cost) * o['quantity']
            except: pass
    return render_template("daily_report.html", today_orders=today_orders, all_time=all_time, month_data=month_data, profit_today=profit_today)

@app.route('/owner/khata')
@owner_required
def khata_book():
    search = request.args.get('q','').strip()
    filter_status = request.args.get('status','').strip()
    with get_db() as db:
        query = "SELECT * FROM khata WHERE 1=1"
        params = []
        if search:
            query += " AND (LOWER(customer_name) LIKE LOWER(?) OR mobile LIKE ?)"
            params.extend([f'%{search}%', f'%{search}%'])
        if filter_status:
            query += " AND status = ?"
            params.append(filter_status)
        query += " ORDER BY CASE WHEN status='Udhar' THEN 0 ELSE 1 END, updated_at DESC"
        khata_list = db.execute(query, params).fetchall()
        total_udhar = db.execute("SELECT SUM(balance) as total FROM khata WHERE status='Udhar'").fetchone()
        total_customers = db.execute("SELECT COUNT(*) as c FROM khata WHERE status='Udhar'").fetchone()
    return render_template("khata.html", khata_list=khata_list, total_udhar=total_udhar['total'] or 0, total_customers=total_customers['c'] or 0)

@app.route('/owner/khata/add', methods=["POST"])
@owner_required
def khata_add():
    validate_csrf()
    name = request.form.get("customer_name","").strip()
    mobile = request.form.get("mobile","").strip()
    address = request.form.get("address","").strip()
    items = request.form.get("items","").strip()
    total = float(request.form.get("total_amount","0") or 0)
    paid = float(request.form.get("paid_amount","0") or 0)
    balance = total - paid
    status = "Paid" if balance <= 0 else "Udhar"
    with get_db() as db:
        db.execute("INSERT INTO khata (customer_name, mobile, address, items, total_amount, paid_amount, balance, status) VALUES (?,?,?,?,?,?,?,?)",
                   (name, mobile, address, items, total, paid, balance, status))
        db.commit()
    flash(f"Khata Add: {name} - Baaki ₹{int(balance)}", "success")
    return redirect(url_for("khata_book"))

@app.route('/owner/khata/pay/<int:khata_id>', methods=["POST"])
@owner_required
def khata_pay(khata_id):
    validate_csrf()
    pay_amount = float(request.form.get("pay_amount","0") or 0)
    with get_db() as db:
        k = db.execute("SELECT * FROM khata WHERE id=?", (khata_id,)).fetchone()
        if k:
            new_paid = k['paid_amount'] + pay_amount
            new_balance = k['total_amount'] - new_paid
            new_status = "Paid" if new_balance <= 0 else "Udhar"
            if new_balance < 0: new_balance = 0
            db.execute("UPDATE khata SET paid_amount=?, balance=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (new_paid, new_balance, new_status, khata_id))
            db.commit()
            flash(f"₹{int(pay_amount)} Jama - {k['customer_name']} ka baaki ₹{int(new_balance)}", "success")
    return redirect(url_for("khata_book"))

@app.route('/owner/khata/delete/<int:khata_id>', methods=["POST"])
@owner_required
def khata_delete(khata_id):
    validate_csrf()
    with get_db() as db:
        db.execute("DELETE FROM khata WHERE id=?", (khata_id,))
        db.commit()
    flash("Khata Entry Delete", "success")
    return redirect(url_for("khata_book"))

@app.route('/owner/khata/bill/<int:khata_id>')
@owner_required
def khata_print_bill(khata_id):
    with get_db() as db:
        k = db.execute("SELECT * FROM khata WHERE id=?", (khata_id,)).fetchone()
    if not k: abort(404)
    return render_template("bill_print.html", k=k, type="khata")

@app.route('/account')
def account_choice():
    return render_template('account_choice.html')

@app.route('/set-theme/<theme>')
def set_theme(theme):
    session['theme'] = theme
    flash(f"Theme changed to {theme}!", "success")
    return redirect(request.referrer or url_for('home'))

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)