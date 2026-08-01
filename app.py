from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import init_db, get_db
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'agrihub2026secretkey'

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.before_request
def setup():
    init_db()

# ── HOME ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db()
    featured = db.execute(
        'SELECT p.*, u.farm_name FROM products p JOIN users u ON p.user_id=u.id ORDER BY p.created_at DESC LIMIT 8'
    ).fetchall()
    events = db.execute('SELECT * FROM events ORDER BY event_date ASC').fetchall()
    return render_template('index.html', featured=featured, events=events)

# ── AUTH ─────────────────────────────────────────────────────────────────────
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name     = request.form['name']
        farm     = request.form['farm_name']
        email    = request.form['email']
        phone    = request.form['phone']
        county   = request.form['county']
        password = generate_password_hash(request.form['password'])
        db = get_db()
        if db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
        db.execute('INSERT INTO users (name,farm_name,email,phone,county,password) VALUES (?,?,?,?,?,?)',
                   (name,farm,email,phone,county,password))
        db.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        db   = get_db()
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id']  = user['id']
            session['user_name']= user['name']
            session['is_admin'] = user['is_admin']
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

# ── MARKETPLACE ───────────────────────────────────────────────────────────────
@app.route('/marketplace')
def marketplace():
    db       = get_db()
    category = request.args.get('category','')
    search   = request.args.get('search','')
    query    = 'SELECT p.*,u.farm_name,u.county FROM products p JOIN users u ON p.user_id=u.id WHERE p.available=1'
    params   = []
    if category:
        query += ' AND p.category=?'; params.append(category)
    if search:
        query += ' AND (p.name LIKE ? OR p.description LIKE ?)'; params.extend([f'%{search}%']*2)
    query += ' ORDER BY p.created_at DESC'
    products   = db.execute(query, params).fetchall()
    categories = db.execute('SELECT DISTINCT category FROM products').fetchall()
    return render_template('marketplace.html', products=products, categories=categories,
                           selected_category=category, search=search)

@app.route('/product/<int:pid>')
def product_detail(pid):
    db = get_db()
    product = db.execute(
        'SELECT p.*,u.farm_name,u.county,u.phone,u.name as seller_name FROM products p JOIN users u ON p.user_id=u.id WHERE p.id=?', (pid,)
    ).fetchone()
    if not product:
        flash('Product not found.', 'danger'); return redirect(url_for('marketplace'))
    return render_template('product_detail.html', product=product)

# ── CART ──────────────────────────────────────────────────────────────────────
@app.route('/add_to_cart/<int:pid>')
def add_to_cart(pid):
    if 'user_id' not in session:
        flash('Please log in first.', 'warning'); return redirect(url_for('login'))
    cart = session.get('cart', {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session['cart'] = cart
    flash('Item added to cart!', 'success')
    return redirect(url_for('marketplace'))

@app.route('/cart')
def cart():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('cart.html', **_cart_data())

@app.route('/remove_from_cart/<int:pid>')
def remove_from_cart(pid):
    cart = session.get('cart', {})
    cart.pop(str(pid), None)
    session['cart'] = cart
    return redirect(url_for('cart'))

def _cart_data():
    db    = get_db()
    cart  = session.get('cart', {})
    items = []
    total = 0
    for pid, qty in cart.items():
        p = db.execute('SELECT * FROM products WHERE id=?', (int(pid),)).fetchone()
        if p:
            sub = p['price'] * qty
            total += sub
            items.append({'product': p, 'qty': qty, 'subtotal': sub})
    return {'items': items, 'total': total}

# ── CHECKOUT & PAYMENT ────────────────────────────────────────────────────────
@app.route('/checkout', methods=['GET','POST'])
def checkout():
    if 'user_id' not in session: return redirect(url_for('login'))
    data = _cart_data()
    if request.method == 'POST':
        if not data['items']:
            flash('Cart is empty.', 'warning'); return redirect(url_for('marketplace'))
        phone   = request.form['phone']
        address = request.form['delivery_address']
        method  = request.form['payment_method']
        db = get_db()
        order_id = db.execute(
            'INSERT INTO orders (user_id,total,phone,delivery_address,payment_method,payment_status,status) VALUES (?,?,?,?,?,?,?)',
            (session['user_id'], data['total'], phone, address, method, 'Unpaid', 'Pending')
        ).lastrowid
        # Determine seller from first item
        first_pid = list(session.get('cart',{}).keys())[0]
        seller = db.execute('SELECT user_id FROM products WHERE id=?', (int(first_pid),)).fetchone()
        seller_id = seller['user_id'] if seller else 1
        for item in data['items']:
            db.execute('INSERT INTO order_items (order_id,product_id,qty,price) VALUES (?,?,?,?)',
                       (order_id, item['product']['id'], item['qty'], item['product']['price']))
        # Create payment record
        db.execute(
            'INSERT INTO payments (order_id,buyer_id,seller_id,amount,payment_method,status) VALUES (?,?,?,?,?,?)',
            (order_id, session['user_id'], seller_id, data['total'], method, 'Pending')
        )
        db.commit()
        session['cart'] = {}
        flash(f'Order #{order_id} placed! Now complete your payment.', 'success')
        return redirect(url_for('pay', order_id=order_id))
    return render_template('checkout.html', **data)

@app.route('/pay/<int:order_id>', methods=['GET','POST'])
def pay(order_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    db    = get_db()
    order = db.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (order_id, session['user_id'])).fetchone()
    if not order:
        flash('Order not found.', 'danger'); return redirect(url_for('my_orders'))
    items = db.execute(
        'SELECT oi.*,p.name,p.image,p.unit FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?', (order_id,)
    ).fetchall()
    if request.method == 'POST':
        mpesa_code = request.form.get('mpesa_code','').strip().upper()
        if not mpesa_code:
            flash('Please enter your M-Pesa confirmation code.', 'danger')
            return render_template('pay.html', order=order, items=items)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute('UPDATE orders SET mpesa_code=?,payment_status=?,paid_at=?,status=? WHERE id=?',
                   (mpesa_code, 'Paid', now, 'Confirmed', order_id))
        db.execute('UPDATE payments SET mpesa_code=?,status=?,confirmed_at=? WHERE order_id=?',
                   (mpesa_code, 'Confirmed', now, order_id))
        db.commit()
        flash(f'Payment confirmed! M-Pesa code {mpesa_code} recorded.', 'success')
        return redirect(url_for('order_receipt', order_id=order_id))
    return render_template('pay.html', order=order, items=items)

@app.route('/order_receipt/<int:order_id>')
def order_receipt(order_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    db    = get_db()
    order = db.execute(
        'SELECT o.*,u.name as buyer_name,u.farm_name,u.email FROM orders o JOIN users u ON o.user_id=u.id WHERE o.id=?', (order_id,)
    ).fetchone()
    items = db.execute(
        'SELECT oi.*,p.name,p.image,p.unit FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?', (order_id,)
    ).fetchall()
    payment = db.execute('SELECT * FROM payments WHERE order_id=?', (order_id,)).fetchone()
    return render_template('order_receipt.html', order=order, items=items, payment=payment)

# ── MY ORDERS ─────────────────────────────────────────────────────────────────
@app.route('/my_orders')
def my_orders():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db()
    orders = db.execute(
        'SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC', (session['user_id'],)
    ).fetchall()
    return render_template('my_orders.html', orders=orders)

# ── FARMER DASHBOARD ──────────────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    db   = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    products = db.execute('SELECT * FROM products WHERE user_id=? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    # Sales = orders containing my products with full buyer info
    sales = db.execute('''
        SELECT o.id, o.total, o.status, o.payment_status, o.mpesa_code,
               o.phone, o.delivery_address, o.created_at, o.paid_at,
               u.name as buyer_name, u.email as buyer_email,
               GROUP_CONCAT(p.name||' x'||oi.qty, ', ') as items_summary
        FROM orders o
        JOIN order_items oi ON o.id=oi.order_id
        JOIN products p ON oi.product_id=p.id
        JOIN users u ON o.user_id=u.id
        WHERE p.user_id=?
        GROUP BY o.id
        ORDER BY o.created_at DESC
    ''', (session['user_id'],)).fetchall()
    total_revenue = sum(s['total'] for s in sales if s['payment_status']=='Paid')
    return render_template('dashboard.html', user=user, products=products, sales=sales, total_revenue=total_revenue)

@app.route('/add_product', methods=['GET','POST'])
def add_product():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        name     = request.form['name']
        category = request.form['category']
        price    = float(request.form['price'])
        unit     = request.form['unit']
        quantity = int(request.form['quantity'])
        desc     = request.form['description']
        img_name = 'default.jpg'
        if 'image' in request.files:
            f = request.files['image']
            if f and allowed_file(f.filename):
                img_name = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], img_name))
        db = get_db()
        db.execute('INSERT INTO products (user_id,name,category,price,unit,quantity,description,image,available) VALUES (?,?,?,?,?,?,?,?,1)',
                   (session['user_id'],name,category,price,unit,quantity,desc,img_name))
        db.commit()
        flash('Product listed!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_product.html')

@app.route('/delete_product/<int:pid>')
def delete_product(pid):
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db()
    db.execute('DELETE FROM products WHERE id=? AND user_id=?', (pid, session['user_id']))
    db.commit()
    flash('Product removed.', 'info')
    return redirect(url_for('dashboard'))

# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.route('/profile/<int:uid>')
def profile(uid):
    db = get_db()
    user     = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    products = db.execute('SELECT * FROM products WHERE user_id=? AND available=1', (uid,)).fetchall()
    return render_template('profile.html', user=user, products=products)

# ── EVENTS ────────────────────────────────────────────────────────────────────
@app.route('/events')
def events():
    db = get_db()
    events = db.execute('SELECT * FROM events ORDER BY event_date ASC').fetchall()
    return render_template('events.html', events=events)

# ── PAYMENTS LEDGER (farmer) ──────────────────────────────────────────────────
@app.route('/payments')
def payments():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db()
    records = db.execute('''
        SELECT py.*, 
               o.total, o.delivery_address, o.created_at as order_date,
               buyer.name as buyer_name, buyer.phone as buyer_phone, buyer.email as buyer_email,
               buyer.county as buyer_county,
               GROUP_CONCAT(p.name||' x'||oi.qty, ', ') as items
        FROM payments py
        JOIN orders o ON py.order_id=o.id
        JOIN users buyer ON py.buyer_id=buyer.id
        JOIN order_items oi ON oi.order_id=o.id
        JOIN products p ON oi.product_id=p.id
        WHERE py.seller_id=?
        GROUP BY py.id
        ORDER BY py.created_at DESC
    ''', (session['user_id'],)).fetchall()
    total_confirmed = sum(r['amount'] for r in records if r['status']=='Confirmed')
    total_pending   = sum(r['amount'] for r in records if r['status']=='Pending')
    return render_template('payments.html', records=records,
                           total_confirmed=total_confirmed, total_pending=total_pending)

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        flash('Admin access only.', 'danger'); return redirect(url_for('index'))
    db = get_db()
    users    = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    products = db.execute('SELECT p.*,u.farm_name FROM products p JOIN users u ON p.user_id=u.id ORDER BY p.created_at DESC').fetchall()
    orders   = db.execute('''
        SELECT o.*,u.name as buyer_name,u.phone as buyer_phone
        FROM orders o JOIN users u ON o.user_id=u.id ORDER BY o.created_at DESC
    ''').fetchall()
    payments = db.execute('''
        SELECT py.*,
               buyer.name as buyer_name, buyer.phone as buyer_phone,
               seller.name as seller_name, seller.farm_name,
               o.delivery_address
        FROM payments py
        JOIN users buyer ON py.buyer_id=buyer.id
        JOIN users seller ON py.seller_id=seller.id
        JOIN orders o ON py.order_id=o.id
        ORDER BY py.created_at DESC
    ''').fetchall()
    total_sales = sum(p['amount'] for p in payments if p['status']=='Confirmed')
    return render_template('admin.html', users=users, products=products,
                           orders=orders, payments=payments, total_sales=total_sales)

@app.route('/admin/update_order/<int:oid>', methods=['POST'])
def admin_update_order(oid):
    if not session.get('is_admin'): return redirect(url_for('index'))
    status = request.form['status']
    get_db().execute('UPDATE orders SET status=? WHERE id=?', (status, oid))
    get_db().commit()
    flash('Order updated.', 'success')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
