from flask import Flask, render_template, request, redirect, session, flash, jsonify, make_response
from flask_mail import Mail, Message
import mysql.connector
import bcrypt
import random
import config
from email.mime.text import MIMEText
import smtplib
import os
from werkzeug.utils import secure_filename
import razorpay
import traceback
from utils.pdf_generator import generate_pdf

razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)



app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# ---------------- EMAIL CONFIGURATION ----------------
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD



mail = Mail(app)

app.config['PRODUCT_UPLOAD_FOLDER'] = 'static/uploads/product_images'
app.config['PROFILE_UPLOAD_FOLDER'] = 'static/uploads/profile_images'


# ---------------- DB CONNECTION FUNCTION --------------
def get_db_connection():
    return mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )

SUPERADMIN_EMAIL = "superadmin_email@gmail.com"
SENDER_EMAIL = "your_gmail@gmail.com"
SENDER_APP_PASSWORD = "your_gmail_app_password"




# ---------------------------------------------------------
# ROUTE 1: ADMIN SIGNUP (SEND OTP)
# ---------------------------------------------------------
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():

    # Show form
    if request.method == "GET":
        return render_template("admin/admin_signup.html", hide_admin_nav=True)

    # POST → Process signup
    name = request.form['name']
    email = request.form['email']

    # 1️⃣ Check if admin email already exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT admin_id FROM admin WHERE email=%s", (email,))
    existing_admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing_admin:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/admin-signup')

    # 2️⃣ Save user input temporarily in session
    session['signup_name'] = name
    session['signup_email'] = email

    # 3️⃣ Generate OTP and store in session
    otp = random.randint(100000, 999999)
    session['otp'] = otp

    # 4️⃣ Send OTP Email
    message = Message(
        subject="SmartCart Admin OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart Admin Registration is: {otp}"
    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')


@app.route('/verify-otp', methods=['GET'])
def verify_otp_get():
    return render_template("admin/verify_otp.html", hide_admin_nav=True)

def send_admin_approval_mail(admin_id, name, email):

    approve_link = f"http://127.0.0.1:5000/superadmin/approve-admin/{admin_id}"
    reject_link = f"http://127.0.0.1:5000/superadmin/reject-admin/{admin_id}"

    message = Message(
        subject="New Admin Approval Request",
        sender=config.MAIL_USERNAME,
        recipients=[SUPERADMIN_EMAIL]
    )

    message.body = f"""
New Admin Registration Request

Name: {name}
Email: {email}

Approve:
{approve_link}

Reject:
{reject_link}
"""

    mail.send(message)

#==============================================================
# ADMIN-VERIFY OTP Route
#==============================================================
@app.route('/verify-otp', methods=['POST'])
def verify_otp_post():
    
    user_otp = request.form['otp']
    password = request.form['password']

    if str(session.get('otp')) != str(user_otp):
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/verify-otp')

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO admin (name, email, password, status) VALUES (%s, %s, %s, %s)",
        (session['signup_name'], session['signup_email'], hashed_password, 'pending')
    )

    conn.commit()

    admin_id = cursor.lastrowid
    admin_name = session['signup_name']
    admin_email = session['signup_email']

    cursor.close()
    conn.close()

    send_admin_approval_mail(admin_id, admin_name, admin_email)

    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)

    flash("Admin Registered Successfully! Please wait for Super Admin approval.", "success")
    return redirect('/admin-login')

# =================================================================
# ROUTE 4: ADMIN LOGIN PAGE (GET + POST)
# =================================================================
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'GET':
        return render_template("admin/admin_login.html", hide_admin_nav=True)

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    if admin is None:
        flash("Email not found! Please register first.", "danger")
        return redirect('/admin-login')

    stored_hashed_password = admin['password'].encode('utf-8')

    if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
        flash("Incorrect password! Try again.", "danger")
        return redirect('/admin-login')

    if admin['status'] == 'pending':
        flash("Your account is waiting for Super Admin approval.", "warning")
        return redirect('/admin-login')

    if admin['status'] == 'rejected':
        flash("Your admin registration was rejected.", "danger")
        return redirect('/admin-login')

    session['admin_id'] = admin['admin_id']
    session['admin_name'] = admin['name']
    session['admin_email'] = admin['email']

    flash("Login Successful!", "success")
    return redirect('/admin-dashboard')



# =================================================================
# ROUTE 5: ADMIN DASHBOARD (PROTECTED ROUTE)
# =================================================================
@app.route('/admin-dashboard')
def admin_dashboard():

    # Protect dashboard → Only logged-in admin can access
    if 'admin_id' not in session:
        flash("Please login to access dashboard!", "danger")
        return redirect('/admin-login')

    # Send admin name to dashboard UI
    return render_template("admin/dashboard.html", admin_name=session['admin_name'])



# =================================================================
# ROUTE 6: ADMIN LOGOUT
# =================================================================
@app.route('/admin-logout')
def admin_logout():

    # Clear admin session
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)

    flash("Logged out successfully.", "success")
    return redirect('/admin-login')


# ------------------- IMAGE UPLOAD PATH -------------------
UPLOAD_FOLDER = 'static/uploads/product_images'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# =================================================================
# ROUTE 7: SHOW ADD PRODUCT PAGE (Protected Route)
# =================================================================
@app.route('/admin/add-item', methods=['GET'])
def add_item_page():

    # Only logged-in admin can access
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    return render_template("admin/add_item.html")


# =================================================================
# ROUTE 8: ADD PRODUCT INTO DATABASE
# =================================================================
@app.route('/admin/add-item', methods=['POST'])
def add_item():

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    # 🔥 GET ADMIN ID FROM SESSION
    admin_id = session['admin_id']

    # 1️⃣ Get form data
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files['image']

    # 2️⃣ Validate image upload
    if image_file.filename == "":
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')

    # 3️⃣ Secure the file name
    filename = secure_filename(image_file.filename)

    # 4️⃣ Create full path
    image_path = os.path.join(app.config['PRODUCT_UPLOAD_FOLDER'], filename)

    # 5️⃣ Save image into folder
    image_file.save(image_path)

    # 6️⃣ Insert product into database (🔥 UPDATED)
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO products (name, description, category, price, image, admin_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (name, description, category, price, filename, admin_id)
    )

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product added successfully!", "success")
    return redirect('/admin/add-item')

# =================================================================
# ROUTE 9: DISPLAY ALL PRODUCTS (Admin)
# =================================================================
@app.route('/admin/item-list')
def item_list():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Fetch category list only for this admin's products
    cursor.execute(
        "SELECT DISTINCT category FROM products WHERE admin_id = %s",
        (admin_id,)
    )
    categories = cursor.fetchall()

    # 2️⃣ Build dynamic query based on filters
    query = "SELECT * FROM products WHERE admin_id = %s"
    params = [admin_id]

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    query += " ORDER BY product_id DESC"

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories
    )




#=================================================================
# ROUTE 10: VIEW SINGLE PRODUCT DETAILS
# =================================================================
@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_item.html", product=product)

# =================================================================
# ROUTE 11: SHOW UPDATE FORM WITH EXISTING DATA
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['GET'])
def update_item_page(item_id):

    # Check login
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # Fetch product data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/update_item.html", product=product)

# =================================================================
# ROUTE-12: UPDATE PRODUCT + OPTIONAL IMAGE REPLACE
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # 1️⃣ Get updated form data
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']

    new_image = request.files['image']

    # 2️⃣ Fetch old product data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product['image']

    # 3️⃣ If admin uploaded a new image → replace it
    if new_image and new_image.filename != "":
        
        # Secure filename
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        new_image_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        new_image.save(new_image_path)

        # Delete old image file
        old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
        if os.path.exists(old_image_path):
            os.remove(old_image_path)

        final_image_name = new_filename

    else:
        # No new image uploaded → keep old one
        final_image_name = old_image_name

    # 4️⃣ Update product in the database
    cursor.execute("""
        UPDATE products
        SET name=%s, description=%s, category=%s, price=%s, image=%s
        WHERE product_id=%s
    """, (name, description, category, price, final_image_name, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')


# =================================================================
#  route-13 DELETE PRODUCT (DELETE DB ROW + DELETE IMAGE FILE)
# =================================================================
@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']   # 🔥 ADD THIS

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Fetch product ONLY if it belongs to this admin
    cursor.execute(
        "SELECT image FROM products WHERE product_id=%s AND admin_id=%s",
        (item_id, admin_id)
    )
    product = cursor.fetchone()

    if not product:
        flash("Unauthorized or product not found!", "danger")
        return redirect('/admin/item-list')

    image_name = product['image']

    # Delete image from folder
    image_path = os.path.join(app.config['PRODUCT_UPLOAD_FOLDER'], image_name)
    if os.path.exists(image_path):
        os.remove(image_path)

    # 2️⃣ Delete product ONLY for this admin
    cursor.execute(
        "DELETE FROM products WHERE product_id=%s AND admin_id=%s",
        (item_id, admin_id)
    )
    conn.commit()

    cursor.close()
    conn.close()

    flash("Product deleted successfully!", "success")
    return redirect('/admin/item-list')

ADMIN_UPLOAD_FOLDER = 'static/uploads/admin_profiles'
app.config['ADMIN_UPLOAD_FOLDER'] = ADMIN_UPLOAD_FOLDER

# =================================================================
# ROUTE 14: SHOW ADMIN PROFILE DATA
# =================================================================
@app.route('/admin/profile', methods=['GET'])
def admin_profile():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM admin WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("admin/admin_profile.html", admin=admin)

# =================================================================
# ROUTE 15: UPDATE ADMIN PROFILE (NAME, EMAIL, PASSWORD, IMAGE)
# =================================================================
@app.route('/admin/profile', methods=['POST'])
def admin_profile_update():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    # 1️⃣ Get form data
    name = request.form['name']
    email = request.form['email']
    new_password = request.form['password']
    new_image = request.files['profile_image']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 2️⃣ Fetch old admin data
    cursor.execute("SELECT * FROM admin WHERE admin_id = %s", (admin_id,))
    admin = cursor.fetchone()

    old_image_name = admin['profile_image']

    # 3️⃣ Update password only if entered
    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    else:
        hashed_password = admin['password']  # keep old password

    # 4️⃣ Process new profile image if uploaded
    if new_image and new_image.filename != "":
        
        from werkzeug.utils import secure_filename
        new_filename = secure_filename(new_image.filename)

        # Save new image
        image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], new_filename)
        new_image.save(image_path)

        # Delete old image
        if old_image_name:
            old_image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], old_image_name)
            if os.path.exists(old_image_path):
                os.remove(old_image_path)

        final_image_name = new_filename
    else:
        final_image_name = old_image_name

    # 5️⃣ Update database
    cursor.execute("""
        UPDATE admin
        SET name=%s, email=%s, password=%s, profile_image=%s
        WHERE admin_id=%s
    """, (name, email, hashed_password, final_image_name, admin_id))

    conn.commit()
    cursor.close()
    conn.close()

    # Update session name for UI consistency
    session['admin_name'] = name  
    session['admin_email'] = email

    flash("Profile updated successfully!", "success")
    return redirect('/admin/profile')

@app.route('/')
def Home():
    return render_template('user/user_login.html')

@app.route('/about')
def about():
    return render_template('admin/about.html', hide_admin_nav=True)

#============================================================================================
#       CONTACT PAGE
#==========================================================================================

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        message = request.form["message"]

        body = f"""
New Message

Name: {name}
Email: {email}
Phone: {phone}

Message:
{message}
"""

        msg = MIMEText(body)
        msg["Subject"] = "Contact Form"
        msg["From"] = email
        msg["To"] = "lenkanarendra536@gmail.com"

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login("narendralenka553@gmail.com", "ochp jzwg ugwi ebbz")
        server.send_message(msg)
        server.quit()

        # ✅ Flash message instead of plain text
        flash("Message sent successfully!", "success")
        return redirect("/contact")

    return render_template("/admin/contact.html", hide_admin_nav=True)

#FORGOT PASSWORD

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'GET':
        return render_template("admin/forgot_password.html", hide_admin_nav=True)

    email = request.form['email']

    # Check email exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if not admin:
        flash("Email not found!", "danger")
        return redirect('/forgot-password')

    # Generate OTP
    otp = random.randint(100000, 999999)

    # Store in session
    session['reset_email'] = email
    session['reset_otp'] = str(otp)

    # Send email
    msg = Message(
        subject="Password Reset OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = f"Your OTP is: {otp}"
    mail.send(msg)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-reset-otp')

# VERIFY OTP ROUTE
@app.route('/verify-reset-otp', methods=['GET', 'POST'])
def verify_reset_otp():

    if request.method == 'GET':
        return render_template("admin/verify_reset_otp.html", hide_admin_nav=True)

    user_otp = request.form['otp']

    if user_otp != session.get('reset_otp'):
        flash("Invalid OTP!", "danger")
        return redirect('/verify-reset-otp')

    flash("OTP Verified! Now reset your password.", "success")
    return redirect('/reset-password')

#RESET PASSWORD
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():

    if request.method == 'GET':
        return render_template("admin/reset_password.html", hide_admin_nav=True)

    new_password = request.form['password']

    # Hash password
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

    # Update DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE admin SET password=%s WHERE email=%s",
        (hashed_password, session.get('reset_email'))
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Clear session
    session.pop('reset_email', None)
    session.pop('reset_otp', None)

    flash("Password updated successfully!", "success")
    return redirect('/admin-login')

# ======================j==================================
# ADMIN: VIEW ALL ORDERS
# ======================j==================================
@app.route('/admin/orders')
def admin_orders():

    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM orders
        WHERE admin_id = %s
        ORDER BY order_id DESC
    """, (admin_id,))

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/order_list.html", orders=orders)

# ================================================================
# ADMIN: VIEW ORDER DETAILS
# ================================================================
@app.route('/admin/order/<int:order_id>')
def admin_order_details(order_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM orders WHERE order_id=%s", (order_id,))
    order = cursor.fetchone()

    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/order_details.html", order=order, items=items)


# ================================================================
# ADMIN: UPDATE ORDER STATUS
# ================================================================
@app.route("/admin/update-order-status/<int:order_id>", methods=['POST'])
def update_order_status(order_id):
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    new_status = request.form.get('status')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE orders SET order_status=%s WHERE order_id=%s",
                    (new_status, order_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Order status updated successfully!", "success")
    return redirect(f"/admin/order/{order_id}")






# ---------------------------------------- USER MODULE --------------------------------------------------------
# =================================================================
# ROUTE 01: USER REGISTRATION
# =================================================================
@app.route('/user-register', methods=['GET', 'POST'])
def user_register():

    # Show form
    if request.method == "GET":
        return render_template("user/user_register.html", hide_admin_nav=True)

    # POST → Process signup
    name = request.form['name']
    email = request.form['email']

    # 1️⃣ Check if admin email already exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
    existing_user = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing_user:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/user-register')

    # 2️⃣ Save user input temporarily in session
    session['signup_name'] = name
    session['signup_email'] = email

    # 3️⃣ Generate OTP and store in session
    otp = random.randint(100000, 999999)
    session['otp'] = otp

    # 4️⃣ Send OTP Email
    message = Message(
        subject="SmartCart User OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart User Registration is: {otp}"
    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/user-verify-otp')


@app.route('/user-verify-otp', methods=['GET'])
def user_verify_otp_get():
    return render_template("user/user_verify_otp.html")

# admin-VERIFY Route

@app.route('/user-verify-otp', methods=['POST'])
def user_verify_otp_post():
    
    # User submitted OTP + Password
    user_otp = request.form['otp']
    password = request.form['password']

    # Compare OTP
    if str(session.get('otp')) != str(user_otp):
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/user-verify-otp')

    # Hash password using bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    # Insert admin into database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
        (session['signup_name'], session['signup_email'], hashed_password)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Clear temporary session data
    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)

    flash("Admin Registered Successfully!", "success")
    return redirect('/user-login')


# =================================================================
# ROUTE 02: USER LOGIN
# =================================================================
@app.route('/user-login', methods=['GET', 'POST'])
def user_login():

    if request.method == 'GET':
        return render_template("user/user_login.html", hide_user_nav=True)

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        flash("Email not found! Please register.", "danger")
        return redirect('/user-login')

    # Verify password
    if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        flash("Incorrect password!", "danger")
        return redirect('/user-login')

    # Create user session
    session['user_id'] = user['user_id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']

    flash("Login successful!", "success")
    return redirect('/user-dashboard')

# =================================================================
# ROUTE 03: USER DASHBOARD
# =================================================================
@app.context_processor
def inject_cart_count():
    cart = session.get('cart', {})
    cart_count = sum(item['quantity'] for item in cart.values())
    return dict(cart_count=cart_count)


@app.route('/user-dashboard')
def user_dashboard():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    # Example dashboard values
    total_orders = 12
    wishlist_count = 5
    available_offers = 3
    recent_views = 8

    return render_template(
        "user/user_home.html",
        user_name=session['user_name'],
        total_orders=total_orders,
        wishlist_count=wishlist_count,
        available_offers=available_offers,
        recent_views=recent_views
    )

# =================================================================
# ROUTE 04: USER LOGOUT
# =================================================================
@app.route('/user-logout')
def user_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)

    # only remove old session cart, not database cart
    session.pop('cart', None)

    flash("Logged out successfully!", "success")
    return redirect('/user-login')
# =================================================================
# ROUTE: USER PRODUCT LISTING (SEARCH + FILTER)
# =================================================================
@app.route('/user/products')
def user_products():

    if 'user_id' not in session:
        flash("Please login to view products!", "danger")
        return redirect('/user-login')

    search = request.args.get('search', '')
    category_filter = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Categories only from active products of approved admins
    cursor.execute("""
        SELECT DISTINCT p.category
        FROM products p
        JOIN admin a ON p.admin_id = a.admin_id
        WHERE p.status = 'active'
        AND a.status = 'approved'
    """)
    categories = cursor.fetchall()

    # Show only active products from approved admins
    query = """
        SELECT p.*
        FROM products p
        JOIN admin a ON p.admin_id = a.admin_id
        WHERE p.status = 'active'
        AND a.status = 'approved'
    """
    params = []

    if search:
        query += " AND p.name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND p.category = %s"
        params.append(category_filter)

    query += " ORDER BY p.product_id DESC"

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/user_products.html",
        products=products,
        categories=categories
    )
# =================================================================
# ROUTE: USER PRODUCT DETAILS PAGE
# =================================================================
@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template("user/product_details.html", product=product)

#USER FORGOT PASSWORD

@app.route('/user-forgot-password', methods=['GET', 'POST'])
def user_forgot_password():

    if request.method == 'GET':
        return render_template("user/user_forgot_password.html", hide_user_nav=True)

    email = request.form['email']

    # Check email exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if not admin:
        flash("Email not found!", "danger")
        return redirect('/user-forgot-password')

    # Generate OTP
    otp = random.randint(100000, 999999)

    # Store in session
    session['reset_email'] = email
    session['reset_otp'] = str(otp)

    # Send email
    msg = Message(
        subject="Password Reset OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = f"Your OTP is: {otp}"
    mail.send(msg)

    flash("OTP sent to your email!", "success")
    return redirect('/user-verify-reset-otp')

# VERIFY OTP ROUTE
@app.route('/user-verify-reset-otp', methods=['GET', 'POST'])
def user_verify_reset_otp():

    if request.method == 'GET':
        return render_template("user/user_verify_reset_otp.html", hide_user_nav=True)

    user_otp = request.form['otp']

    if user_otp != session.get('reset_otp'):
        flash("Invalid OTP!", "danger")
        return redirect('/user-verify-reset-otp')

    flash("OTP Verified! Now reset your password.", "success")
    return redirect('/user-reset-password')

#RESET PASSWORD
@app.route('/user-reset-password', methods=['GET', 'POST'])
def user_reset_password():

    if request.method == 'GET':
        return render_template("user/user_reset_password.html", hide_user_nav=True)

    new_password = request.form['password']

    # Hash password
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

    # Update DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password=%s WHERE email=%s",
        (hashed_password, session.get('reset_email'))
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Clear session
    session.pop('reset_email', None)
    session.pop('reset_otp', None)

    flash("Password updated successfully!", "success")
    return redirect('/user-login')

UPLOAD_FOLDER = 'static/uploads/user_profiles'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# =================================================================
# ROUTE : SHOW USER PROFILE
# =================================================================
@app.route('/user/profile', methods=['GET'])
def user_profile():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("user/user_profile.html", user=user)


# =================================================================
# ROUTE : UPDATE USER PROFILE
# =================================================================
@app.route('/user/profile', methods=['POST'])
def user_profile_update():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    # 1️⃣ Get form data
    name = request.form['name']
    email = request.form['email']
    new_password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 2️⃣ Fetch old user data
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    # ================= IMAGE UPLOAD =================
    profile_image = user['profile_image']  # default old image

    if 'profile_image' in request.files:
        file = request.files['profile_image']

        if file and file.filename != "":
            filename = secure_filename(file.filename)

            # make unique filename
            filename = f"{user_id}_{filename}"

            # ✅ FIX: create folder if not exists
            upload_folder = app.config['PROFILE_UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)

            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)

            profile_image = filename

    # ================= PASSWORD =================
    if new_password:
        hashed_password = bcrypt.hashpw(
            new_password.encode('utf-8'),
            bcrypt.gensalt()
        )
    else:
        hashed_password = user['password']

    # ================= UPDATE DB =================
    cursor.execute("""
        UPDATE users
        SET name=%s, email=%s, password=%s, profile_image=%s
        WHERE user_id=%s
    """, (name, email, hashed_password, profile_image, user_id))

    conn.commit()
    cursor.close()
    conn.close()

    # ================= SESSION UPDATE =================
    session['user_name'] = name
    session['user_email'] = email

    flash("Profile updated successfully!", "success")
    return redirect('/user/profile')


# =================================================================
# ABOUT PAGE
# =================================================================
@app.route('/user-about')
def user_about():
    return render_template('user/user_about.html', hide_user_nav=True)



#==================================
#  ROUTE : CONTACT PAGE
#===================================

@app.route("/user-contact", methods=["GET", "POST"])
def user_contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        message = request.form["message"]

        body = f"""
New Message

Name: {name}
Email: {email}
Phone: {phone}

Message:
{message}
"""

        msg = MIMEText(body)
        msg["Subject"] = "Contact Form"
        msg["From"] = email
        msg["To"] = "lenkanarendra536@gmail.com"

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login("narendralenka553@gmail.com", "ochp jzwg ugwi ebbz")
        server.send_message(msg)
        server.quit()

        # ✅ Flash message instead of plain text
        flash("Message sent successfully!", "success")
        return redirect("/contact")

    return render_template("/user/user_contact.html", hide_user_nav=True)






# =================================================================
# CONTEXT PROCESSOR FOR CART COUNT
# =================================================================
@app.context_processor
def inject_cart_count():

    if 'user_id' not in session:
        return dict(cart_count=0)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(*) AS count
        FROM cart
        WHERE user_id = %s
    """, (session['user_id'],))

    result = cursor.fetchone()

    cursor.close()
    conn.close()

    return dict(cart_count=result['count'] if result else 0)
# =================================================================
# ADD ITEM TO CART
# =================================================================
@app.route('/user/add-to-cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        flash("Product not found.", "danger")
        return redirect(request.referrer or '/user/products')

    cursor.execute("""
        SELECT * FROM cart
        WHERE user_id = %s AND product_id = %s
    """, (user_id, product_id))

    existing_item = cursor.fetchone()

    if existing_item:
        cursor.execute("""
            UPDATE cart
            SET quantity = quantity + 1
            WHERE user_id = %s AND product_id = %s
        """, (user_id, product_id))
    else:
        cursor.execute("""
            INSERT INTO cart (user_id, product_id, quantity)
            VALUES (%s, %s, 1)
        """, (user_id, product_id))

    conn.commit()
    cursor.close()
    conn.close()

    session.pop('cart', None)

    flash("Item added to cart!", "success")
    return redirect(request.referrer or '/user/products')
# =================================================================
# VIEW CART PAGE
# =================================================================
@app.route('/user/cart', methods=['GET', 'POST'])
def view_cart():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            cart.cart_id,
            cart.product_id,
            cart.quantity,
            products.name,
            products.price,
            products.image,
            products.category,
            (cart.quantity * products.price) AS total
        FROM cart
        JOIN products ON cart.product_id = products.product_id
        WHERE cart.user_id = %s
    """, (user_id,))

    cart_items = cursor.fetchall()

    grand_total = sum(float(item['total']) for item in cart_items)
    cart_count = len(cart_items)

    selected_products = []
    selected_total = 0

    if request.method == 'POST':
        selected_products = request.form.getlist('selected_products')

        for item in cart_items:
            if str(item['product_id']) in selected_products:
                selected_total += float(item['total'])

    cursor.close()
    conn.close()

    return render_template(
        "user/cart.html",
        cart_items=cart_items,
        grand_total=grand_total,
        cart_count=cart_count,
        selected_total=selected_total,
        selected_products=selected_products
    )


# =================================================================
# INCREASE QUANTITY
# =================================================================
@app.route('/user/cart/increase/<pid>')
def increase_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] += 1

    session['cart'] = cart
    return redirect('/user/cart')

# =================================================================
# DECREASE QUANTITY
# =================================================================
@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart[pid]['quantity'] -= 1

        # If quantity becomes 0 → remove item
        if cart[pid]['quantity'] <= 0:
            cart.pop(pid)

    session['cart'] = cart
    return redirect('/user/cart')


# =================================================================
# REMOVE ITEM
# =================================================================
@app.route('/user/cart/remove/<pid>')
def remove_from_cart(pid):

    cart = session.get('cart', {})

    if pid in cart:
        cart.pop(pid)

    session['cart'] = cart

    flash("Item removed!", "success")
    return redirect('/user/cart')

# =================================================================
# ROUTE: CREATE RAZORPAY ORDER
# =================================================================

@app.route('/user/pay')
def user_pay():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    if 'shipping_address_id' not in session:
        flash("Please select shipping address first!", "warning")
        return redirect('/user/shipping-address')

    selected_items = session.get('selected_products_checkout', {})
    selected_total = session.get('selected_products_total', 0)
    cart = session.get('cart', {})

    if selected_items:
        total_amount = float(selected_total)
    elif cart:
        total_amount = sum(float(item['price']) * int(item['quantity']) for item in cart.values())
    else:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM addresses WHERE address_id = %s AND user_id = %s",
        (session['shipping_address_id'], session['user_id'])
    )
    shipping_address = cursor.fetchone()

    cursor.close()
    conn.close()

    if not shipping_address:
        flash("Shipping address not found!", "danger")
        return redirect('/user/shipping-address')

    razorpay_amount = int(total_amount * 100)

    razorpay_order = razorpay_client.order.create({
        "amount": razorpay_amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    session['razorpay_order_id'] = razorpay_order['id']

    return render_template(
        "user/payment.html",
        amount=total_amount,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order['id'],
        shipping_address=shipping_address
    )

#-----------------------------------------
#route for selected products
#-----------------------------------------

@app.route('/user/pay-selected-products', methods=['POST'])
def pay_selected_products():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    selected_products = request.form.getlist('selected_products')

    if not selected_products:
        flash("Please select at least one product.", "warning")
        return redirect('/user/cart')

    selected_items = {}
    selected_total = 0

    for pid in selected_products:
        if pid in cart:
            selected_items[pid] = cart[pid]
            selected_total += float(cart[pid]['price']) * int(cart[pid]['quantity'])

    if not selected_items:
        flash("Invalid product selection.", "danger")
        return redirect('/user/cart')

    session['selected_products_checkout'] = selected_items
    session['selected_products_total'] = selected_total

    # go to shipping address page first
    return redirect('/user/shipping-address')



#----------------------------------------------------------------
#ROUTE: SHIPPING ADDRESS
#---------------------------------------------------------------

@app.route('/user/shipping-address', methods=['GET', 'POST'])
def shipping_address():

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ============================
    # HANDLE POST (SELECT / NEW)
    # ============================
    if request.method == 'POST':

        # If user selected existing address
        selected_address_id = request.form.get('selected_address_id')

        if selected_address_id:
            cursor.execute(
                "SELECT address_id FROM addresses WHERE address_id = %s AND user_id = %s",
                (selected_address_id, user_id)
            )
            address = cursor.fetchone()

            if not address:
                flash("Invalid address selected!", "danger")
                return redirect('/user/shipping-address')

            session['shipping_address_id'] = address['address_id']

            cursor.close()
            conn.close()

            return redirect('/user/pay')

        # ============================
        # ADD NEW ADDRESS
        # ============================
        full_name = request.form.get('full_name')
        phone = request.form.get('phone')
        address_line1 = request.form.get('address_line1')
        address_line2 = request.form.get('address_line2', '')
        city = request.form.get('city')
        state = request.form.get('state')
        pincode = request.form.get('pincode')
        country = request.form.get('country')

        if not full_name or not phone or not address_line1:
            flash("Please fill required fields!", "warning")
            return redirect('/user/shipping-address')

        insert_cursor = conn.cursor()

        insert_cursor.execute("""
            INSERT INTO addresses
            (user_id, full_name, phone, address_line1, address_line2, city, state, pincode, country)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, full_name, phone, address_line1, address_line2, city, state, pincode, country))

        conn.commit()
        address_id = insert_cursor.lastrowid

        insert_cursor.close()
        cursor.close()
        conn.close()

        session['shipping_address_id'] = address_id

        return redirect('/user/pay')

    # ============================
    # FETCH SAVED ADDRESSES (GET)
    # ============================
    cursor.execute(
        "SELECT * FROM addresses WHERE user_id = %s ORDER BY address_id DESC",
        (user_id,)
    )
    addresses = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('user/shipping_address.html', addresses=addresses)

# ------------------------------
# Route: Verify Payment and Store Order
# ------------------------------
@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    if 'user_id' not in session:
        flash("Please login to complete the payment.", "danger")
        return redirect('/user-login')

    razorpay_payment_id = request.form.get('razorpay_payment_id')
    razorpay_order_id = request.form.get('razorpay_order_id')
    razorpay_signature = request.form.get('razorpay_signature')

    if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
        flash("Payment verification failed (missing data).", "danger")
        return redirect('/user/cart')

    payload = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }

    try:
        razorpay_client.utility.verify_payment_signature(payload)
    except Exception as e:
        app.logger.error("Razorpay signature verification failed: %s", str(e))
        flash("Payment verification failed. Please contact support.", "danger")
        return redirect('/user/cart')

    user_id = session['user_id']
    shipping_address_id = session.get('shipping_address_id')

    if not shipping_address_id:
        flash("Shipping address not found.", "danger")
        return redirect('/user/shipping-address')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM addresses
            WHERE address_id = %s AND user_id = %s
        """, (shipping_address_id, user_id))
        address = cursor.fetchone()

        if not address:
            flash("Invalid shipping address.", "danger")
            return redirect('/user/shipping-address')

        selected_products = session.get('selected_products_checkout', [])

        if selected_products:
            placeholders = ','.join(['%s'] * len(selected_products))
            query = f"""
                SELECT 
                    cart.product_id,
                    cart.quantity,
                    products.name,
                    products.price,
                    products.admin_id
                FROM cart
                JOIN products ON cart.product_id = products.product_id
                WHERE cart.user_id = %s
                AND cart.product_id IN ({placeholders})
            """
            cursor.execute(query, [user_id] + selected_products)
        else:
            cursor.execute("""
                SELECT 
                    cart.product_id,
                    cart.quantity,
                    products.name,
                    products.price,
                    products.admin_id
                FROM cart
                JOIN products ON cart.product_id = products.product_id
                WHERE cart.user_id = %s
            """, (user_id,))

        cart_items = cursor.fetchall()

        if not cart_items:
            flash("Cart is empty. Cannot create order.", "danger")
            return redirect('/user/cart')

        total_amount = sum(float(item['price']) * int(item['quantity']) for item in cart_items)
        admin_id = cart_items[0]['admin_id']

        cursor.execute("""
            INSERT INTO orders (
                user_id,
                razorpay_order_id,
                razorpay_payment_id,
                amount,
                payment_status,
                order_status,
                full_name,
                phone,
                address_line1,
                address_line2,
                city,
                state,
                pincode,
                country,
                admin_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            razorpay_order_id,
            razorpay_payment_id,
            total_amount,
            'paid',
            'Pending',
            address['full_name'],
            address['phone'],
            address['address_line1'],
            address['address_line2'],
            address['city'],
            address['state'],
            address['pincode'],
            address['country'],
            admin_id
        ))

        order_db_id = cursor.lastrowid

        for item in cart_items:
            quantity = int(item['quantity'])
            price = float(item['price'])
            total = quantity * price

            cursor.execute("""
                INSERT INTO order_items (
                    order_id,
                    product_id,
                    product_name,
                    quantity,
                    price,
                    total
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                order_db_id,
                item['product_id'],
                item['name'],
                quantity,
                price,
                total
            ))

        if selected_products:
            placeholders = ','.join(['%s'] * len(selected_products))
            delete_query = f"""
                DELETE FROM cart
                WHERE user_id = %s
                AND product_id IN ({placeholders})
            """
            cursor.execute(delete_query, [user_id] + selected_products)
        else:
            cursor.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))

        conn.commit()

        session.pop('cart', None)
        session.pop('razorpay_order_id', None)
        session.pop('selected_products_checkout', None)
        session.pop('selected_products_total', None)
        session.pop('shipping_address_id', None)

        flash("Payment successful and order placed!", "success")
        return redirect(f"/user/order-success/{order_db_id}")

    except Exception as e:
        conn.rollback()
        app.logger.error("Order storage failed: %s\n%s", str(e), traceback.format_exc())
        flash(f"There was an error saving your order: {str(e)}", "danger")
        return redirect('/user/cart')

    finally:
        cursor.close()
        conn.close()

#------------------------------------------------------------
# ROUTE: ORDER-SUCCESS
#-------------------------------------------------------
@app.route('/user/order-success/<int:order_db_id>')
def order_success(order_db_id):
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM orders WHERE order_id=%s AND user_id=%s", (order_db_id, session['user_id']))
    order = cursor.fetchone()

    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_db_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.", "danger")
        return redirect('/user/products')

    return render_template("user/order_success.html", order=order, items=items)

#-------------------------------------------
#    ROUTE: MY- ORDERS
#-------------------------------------------
@app.route('/user/my-orders')
def my_orders():
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            order_id,
            user_id,
            amount,
            payment_status,
            order_status,
            created_at
        FROM orders
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))

    orders = cursor.fetchall()

    print("LOGGED USER ID:", user_id)
    print("ORDERS FOUND:", orders)

    cursor.close()
    conn.close()

    return render_template("user/my_orders.html", orders=orders)
#====================================================================================================
#    CANCEL ORDER
#====================================================================================================

@app.route('/user/cancel-order/<int:order_id>')
def cancel_order(order_id):

    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM orders
        WHERE order_id = %s AND user_id = %s
    """, (order_id, user_id))

    order = cursor.fetchone()

    if not order:
        flash("Order not found!", "danger")

    elif order['order_status'] == 'Cancelled':
        flash("Order already cancelled!", "warning")

    else:
        cursor.execute("""
            UPDATE orders
            SET order_status = 'Cancelled'
            WHERE order_id = %s AND user_id = %s
        """, (order_id, user_id))

        conn.commit()
        flash("Order cancelled successfully!", "success")

    cursor.close()
    conn.close()

    return redirect('/user/my-orders')


# ----------------------------
# GENERATE INVOICE PDF
# ----------------------------
@app.route("/user/download-invoice/<int:order_id>")
def download_invoice(order_id):

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    # Fetch order
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM orders WHERE order_id=%s AND user_id=%s",
                   (order_id, session['user_id']))
    order = cursor.fetchone()

    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_id,))
    items = cursor.fetchall()

    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.", "danger")
        return redirect('/user/my-orders')

    # Render invoice HTML
    html = render_template("user/invoice.html", order=order, items=items)

    pdf = generate_pdf(html)
    if not pdf:
        flash("Error generating PDF", "danger")
        return redirect('/user/my-orders')

    # Prepare response
    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"attachment; filename=invoice_{order_id}.pdf"

    return response

#======================================== SUPER ADMIN MODULE ======================================================#
# ============================================================
# SUPER ADMIN REGISTER
# ============================================================
@app.route('/superadmin-register', methods=['GET', 'POST'])
def superadmin_register():

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM superadmins WHERE email = %s", (email,))
        existing_superadmin = cursor.fetchone()

        if existing_superadmin:
            flash("Super Admin already exists with this email!", "danger")
            cursor.close()
            conn.close()
            return redirect('/superadmin-register')

        # Hash password before saving
        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        cursor.execute(
            "INSERT INTO superadmins (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed_password)
        )

        conn.commit()
        cursor.close()
        conn.close()

        flash("Super Admin registered successfully! Please login.", "success")
        return redirect('/superadmin-login')

    return render_template('superadmin/register.html', hide_superadmin_nav=True)

# ============================================================
# SUPER ADMIN LOGIN
# ============================================================
@app.route('/superadmin-login', methods=['GET', 'POST'])
def superadmin_login():

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM superadmins WHERE email = %s",
            (email,)
        )

        superadmin = cursor.fetchone()

        cursor.close()
        conn.close()

        if superadmin and bcrypt.checkpw(
            password.encode('utf-8'),
            superadmin['password'].encode('utf-8')
        ):
            session['superadmin_id'] = superadmin['superadmin_id']
            session['superadmin_name'] = superadmin['name']

            flash("Super Admin login successful!", "success")
            return redirect('/superadmin/dashboard')

        else:
            flash("Invalid Super Admin email or password!", "danger")
            return redirect('/superadmin-login')

    return render_template('superadmin/login.html', hide_superadmin_nav=True)
# ============================================================
# SUPER ADMIN LOGIN CHECK DECORATOR
# ============================================================
def superadmin_required():
    if 'superadmin_id' not in session:
        flash("Please login as Super Admin!", "danger")
        return False
    return True


# ============================================================
# SUPER ADMIN DASHBOARD
# ============================================================
@app.route('/superadmin/dashboard')
def superadmin_dashboard():

    if not superadmin_required():
        return redirect('/superadmin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total_admins FROM admin")
    total_admins = cursor.fetchone()['total_admins']

    cursor.execute("SELECT COUNT(*) AS total_products FROM products")
    total_products = cursor.fetchone()['total_products']

    cursor.execute("SELECT COUNT(*) AS total_orders FROM orders")
    total_orders = cursor.fetchone()['total_orders']

    cursor.execute("SELECT IFNULL(SUM(amount), 0) AS total_revenue FROM orders")
    total_revenue = cursor.fetchone()['total_revenue']

    cursor.close()
    conn.close()

    return render_template(
        'superadmin/dashboard.html',
        total_admins=total_admins,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue
    )


# ============================================================
# VIEW ALL ADMINS
# ============================================================
@app.route('/superadmin/admins')
def superadmin_admins():

    if not superadmin_required():
        return redirect('/superadmin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM admin ORDER BY admin_id DESC")
    admins = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('superadmin/admins.html', admins=admins)

# ============================================================
# APPROVE ADMIN
# ============================================================
@app.route('/superadmin/approve-admin/<int:admin_id>')
def approve_admin(admin_id):

    if 'superadmin_id' not in session:
        flash("Please login as Super Admin!", "danger")
        return redirect('/superadmin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1️⃣ Approve admin
    cursor.execute("""
        UPDATE admin
        SET status = 'approved'
        WHERE admin_id = %s
    """, (admin_id,))

    # 2️⃣ Reactivate all products of this admin
    cursor.execute("""
        UPDATE products
        SET status = 'active'
        WHERE admin_id = %s
    """, (admin_id,))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Admin approved and products restored!", "success")
    return redirect('/superadmin/admins')


# ============================================================
# REJECT ADMIN
# ============================================================
@app.route('/superadmin/reject-admin/<int:admin_id>')
def reject_admin(admin_id):

    if 'superadmin_id' not in session:
        flash("Please login as Super Admin!", "danger")
        return redirect('/superadmin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1️⃣ Reject admin
    cursor.execute("""
        UPDATE admin
        SET status = 'rejected'
        WHERE admin_id = %s
    """, (admin_id,))

    # 2️⃣ Deactivate all products of this admin
    cursor.execute("""
        UPDATE products
        SET status = 'inactive'
        WHERE admin_id = %s
    """, (admin_id,))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Admin rejected and their products removed from user view!", "warning")
    return redirect('/superadmin/admins')

# ============================================================
# VIEW ALL PRODUCTS
# ============================================================
@app.route('/superadmin/products')
def superadmin_products():

    if not superadmin_required():
        return redirect('/superadmin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT products.*, admin.name AS admin_name
        FROM products
        LEFT JOIN admin ON products.admin_id = admin.admin_id
        ORDER BY products.product_id DESC
    """)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('superadmin/products.html', products=products)


# ============================================================
# VIEW ALL ORDERS
# ============================================================
@app.route('/superadmin/orders')
def superadmin_orders():

    if not superadmin_required():
        return redirect('/superadmin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            orders.order_id,
            orders.user_id,
            users.name AS username,
            orders.amount,
            orders.payment_status,
            orders.order_status,
            orders.created_at
        FROM orders
        LEFT JOIN users ON orders.user_id = users.user_id
        ORDER BY orders.order_id DESC
    """)

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('superadmin/orders.html', orders=orders)


# ============================================================
# VIEW REVENUE
# ============================================================
@app.route('/superadmin/revenue')
def superadmin_revenue():

    if not superadmin_required():
        return redirect('/superadmin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT IFNULL(SUM(amount), 0) AS total_revenue FROM orders")
    total_revenue = cursor.fetchone()['total_revenue']

    cursor.execute("""
        SELECT 
            admin.name AS admin_name,
            IFNULL(SUM(orders.amount), 0) AS revenue
        FROM admin
        LEFT JOIN products ON admin.admin_id = products.admin_id
        LEFT JOIN orders ON products.product_id = orders.order_id
        GROUP BY admin.admin_id
    """)
    admin_revenue = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'superadmin/revenue.html',
        total_revenue=total_revenue,
        admin_revenue=admin_revenue
    )

#=========================================================
#      SUPER ADMIN FORGOT PASSWORD
#=====================================================

@app.route('/sa-forgot-password', methods=['GET', 'POST'])
def sa_forgot_password():

    if request.method == 'GET':
        return render_template("superadmin/sa_forgot_password.html", hide_superadmin_nav=True)

    email = request.form['email']

    # Check email exists
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM superadmins WHERE email=%s", (email,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if not admin:
        flash("Email not found!", "danger")
        return redirect('/sa-forgot-password')

    # Generate OTP
    otp = random.randint(100000, 999999)

    # Store in session
    session['reset_email'] = email
    session['reset_otp'] = str(otp)

    # Send email
    msg = Message(
        subject="Password Reset OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    msg.body = f"Your OTP is: {otp}"
    mail.send(msg)

    flash("OTP sent to your email!", "success")
    return redirect('/sa-verify-reset-otp')

# VERIFY RESET OTP
@app.route('/sa-verify-reset-otp', methods=['GET', 'POST'])
def sa_verify_reset_otp():

    # Check forgot password step completed
    if 'reset_email' not in session:
        flash("Please enter your email first!", "warning")
        return redirect('/sa-forgot-password')

    if request.method == 'GET':
        return render_template(
            "superadmin/sa_verify_reset_otp.html",
            hide_superadmin_nav=True
        )

    user_otp = request.form['otp']

    # Check OTP
    if user_otp != session.get('reset_otp'):
        flash("Invalid OTP!", "danger")
        return redirect('/sa-verify-reset-otp')

    # Mark OTP as verified
    session['otp_verified'] = True

    flash("OTP Verified! Now reset your password.", "success")
    return redirect('/sa-reset-password')


# RESET PASSWORD
@app.route('/sa-reset-password', methods=['GET', 'POST'])
def sa_reset_password():

    # 🔒 Step 1: Check email exists in session
    if 'reset_email' not in session:
        flash("Please start from forgot password!", "warning")
        return redirect('/sa-forgot-password')

    # 🔒 Step 2: Check OTP verified
    if not session.get('otp_verified'):
        flash("Please verify OTP first!", "warning")
        return redirect('/sa-verify-reset-otp')

    if request.method == 'GET':
        return render_template(
            "superadmin/sa_reset_password.html",
            hide_superadmin_nav=True
        )

    new_password = request.form['password']

    # ✅ Hash password (IMPORTANT FIX)
    hashed_password = bcrypt.hashpw(
        new_password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    # Update DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE superadmins SET password=%s WHERE email=%s",
        (hashed_password, session.get('reset_email'))
    )
    conn.commit()
    cursor.close()
    conn.close()

    # 🧹 Clear session
    session.pop('reset_email', None)
    session.pop('reset_otp', None)
    session.pop('otp_verified', None)

    flash("Password updated successfully!", "success")
    return redirect('/superadmin-login')

# ============================================================
# SUPER ADMIN LOGOUT
# ============================================================
@app.route('/superadmin/logout')
def superadmin_logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect('/superadmin-login')


















if __name__=="__main__":
    app.run(debug=True)
