# config.py
# ------------------------------------
# This file holds all configurations
# like Secret Key, Database connection
# details, Email settings, Razorpay keys etc.
# ------------------------------------

SECRET_KEY = "hello@123"   # used for sessions

# MySQL Database Configuration
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "171004"  # keep empty if no password
DB_NAME = "Smartcart_db"

# Email SMTP Settings
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = 'narendralenka553@gmail.com'
MAIL_PASSWORD = 'krmn yijr ggxn hzuk'   # Gmail App Password

RAZORPAY_KEY_ID = "rzp_test_SgserJ7uNLGmPg"
RAZORPAY_KEY_SECRET = "3fH1NzJO0gw5mZlAkIimMPe4"

