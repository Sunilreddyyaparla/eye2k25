from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import psycopg2
from psycopg2.extras import DictCursor
from flask_mail import Mail, Message
import random
import razorpay
import threading
import logging
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database Configuration
DATABASE_URL = "postgresql://eye2k25_user:S4haUy7pTIEGbGCHDWt5cINm70ZvykVY@dpg-cu9pvolumphs73cfl9f0-a.oregon-postgres.render.com/eye2k25"

def get_db_connection():
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode='require'  # Enable SSL mode for secure connection
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

# Initialize Database with error handling and connection timeout
def init_db():
    retries = 3
    for attempt in range(retries):
        try:
            conn = get_db_connection()
            conn.set_session(autocommit=False)  # Explicit transaction control
            cur = conn.cursor()
            
            # Create registration table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS reg_data (
                    payment_id VARCHAR(100) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) NOT NULL,
                    mobileno BIGINT NOT NULL,
                    event VARCHAR(100) NOT NULL,
                    college VARCHAR(200) NOT NULL
                );
            ''')
            
            # Create visitor count table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS visitor_count (
                    id SERIAL PRIMARY KEY,
                    count INTEGER DEFAULT 0
                );
            ''')
            
            # Initialize visitor count if not exists
            cur.execute('SELECT count FROM visitor_count LIMIT 1;')
            if cur.fetchone() is None:
                cur.execute('INSERT INTO visitor_count (count) VALUES (0);')
            
            conn.commit()
            logger.info("Database initialized successfully")
            return True
            
        except psycopg2.Error as e:
            logger.error(f"Database initialization attempt {attempt + 1} failed: {str(e)}")
            if conn:
                conn.rollback()
            if attempt == retries - 1:
                raise
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

# Razorpay client configuration
razorpay_client = razorpay.Client(auth=("rzp_test_Aq1j1l911IgPB7", "wS97NzUTtmye6nuTBeXo3Rmm"))

# Configure Flask-Mail with Gmail SMTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'yaparla25@gmail.com'
app.config['MAIL_PASSWORD'] = 'hspv rseb ntvd ttda'
mail = Mail(app)

# Fest events and their fees
FEST_EVENTS = {
    "Project Expo": {"fee": 100},
    "Paper Presentation": {"fee": 50},
    "Poster Presentation": {"fee": 75},
    "Technical Quiz": {"fee": 150},
    "Circuit Hunt": {"fee": 25},
}

def increment_visitor_count():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            UPDATE visitor_count 
            SET count = count + 1 
            RETURNING count;
        ''')
        new_count = cur.fetchone()[0]
        conn.commit()
        return new_count
    except Exception as e:
        conn.rollback()
        logger.error(f"Error incrementing visitor count: {e}")
        return 0
    finally:
        cur.close()
        conn.close()

@app.route('/', methods=['GET', 'HEAD'])
def home():
    try:
        visitor_count = increment_visitor_count()
        return render_template('home.html', visitor_count=visitor_count)
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        if request.method == 'HEAD':
            return '', 200
        return render_template('home.html', visitor_count=0)

@app.route('/registration', methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        try:
            registration_data = {
                'fullname': request.form['fullname'],
                'email': request.form['email'],
                'mobile': request.form['mobile'],
                'yourcollege': request.form['yourcollege'],
                'event_name': request.form['event'],
            }

            if registration_data['event_name'] not in FEST_EVENTS:
                flash("Invalid event selected.", "error")
                return redirect(url_for('registration'))

            registration_data['event_fee'] = FEST_EVENTS[registration_data['event_name']]['fee']
            session['registration_data'] = registration_data

            order_data = {
                'amount': registration_data['event_fee'] * 100,
                'currency': 'INR',
                'receipt': f"order_rcpt_{random.randint(1000, 9999)}",
                'payment_capture': 1
            }
            order = razorpay_client.order.create(order_data)
            session['razorpay_order_id'] = order['id']

            return render_template(
                'razorpay_payment.html',
                order_id=order['id'],
                registration_data=registration_data,
                razorpay_key="rzp_test_Aq1j1l911IgPB7"
            )
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            flash("An error occurred during registration. Please try again.", "error")
            return redirect(url_for('registration'))

    return render_template('registration.html', festevents=FEST_EVENTS)

@app.route('/payment_callback', methods=['POST'])
def payment_callback():
    try:
        payment_data = request.get_json()
        logger.debug(f"Payment data received: {payment_data}")
        
        registration_data = session.get('registration_data')
        if not registration_data:
            logger.error("Session expired or registration data not found.")
            return jsonify({'status': 'error', 'message': 'Session expired or data missing.'})

        # Verify Razorpay payment signature
        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_payment_id': payment_data['razorpay_payment_id'],
                'razorpay_order_id': payment_data['razorpay_order_id'],
                'razorpay_signature': payment_data['razorpay_signature']
            })
            logger.debug("Payment signature verified successfully.")
        except Exception as e:
            logger.error(f"Payment signature verification failed: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Payment signature verification failed.'})

        # Save registration details to database
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('''
                INSERT INTO reg_data (payment_id, name, email, mobileno, event, college)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                payment_data['razorpay_payment_id'],
                registration_data['fullname'],
                registration_data['email'],
                int(registration_data['mobile']),
                registration_data['event_name'],
                registration_data['yourcollege']
            ))
            conn.commit()
            logger.debug("Registration details saved to database.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Database error occurred.'})
        finally:
            cur.close()
            conn.close()

        # Send confirmation email
        try:
            send_confirmation_email(app, registration_data, payment_data['razorpay_payment_id'])
            logger.debug("Confirmation email sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

        # Clear session data
        session.pop('registration_data', None)
        session.pop('razorpay_order_id', None)

        return jsonify({'status': 'success'})

    except Exception as e:
        logger.error(f"Payment callback error: {str(e)}")
        return jsonify({'status': 'error', 'message': f'An error occurred: {str(e)}'})

def send_confirmation_email(app, registration_data, payment_id):
    with app.app_context():
        try:
            msg = Message(
                'EYE 2K25 Registration Confirmation',
                sender=app.config['MAIL_USERNAME'],
                recipients=[registration_data['email']]
            )
            msg.body = f"""
Dear {registration_data['fullname']},

Thank you for registering for the EYE 2K25 Tech Fest! We're thrilled to have you join us for this exciting event.

Here are your registration details:
--------------------------------------------------
🎉 Event: {registration_data['event_name']}
💰 Amount Paid: ₹{registration_data['event_fee']}
🆔 Payment ID: {payment_id}
🏫 College: {registration_data['yourcollege']}
--------------------------------------------------

Please save this email for your records. Your participation is confirmed, and we can't wait to welcome you to EYE 2K25. Be ready for a fantastic experience filled with learning, networking, and fun!

**Important Information:**
- Make sure to bring a valid ID for verification at the event.
- Stay tuned for event updates and announcements via email or our official website.

If you have any questions or require assistance, feel free to reach out.
Thank you for being a part of EYE 2K25.\nHave a nice day !

Best regards,  
**The EYE 2K25 Team**    
"""
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Failed to send email: {str(e)}")

# Other routes remain the same
@app.route('/events')
def events():
    return render_template('events.html')

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

@app.route('/portfolio')
def portfolio():
    return render_template('portfolio.html')

@app.route('/aboutus')
def aboutus():
    return render_template('aboutus.html')

@app.route('/contactus')
def contactus():
    return render_template('contactus.html')

@app.route('/terms_and_conditions')
def terms_and_conditions():
    return render_template('terms_and_conditions.html')

@app.route('/pay_success')
def payment_success():
    return render_template('pay_success.html')

@app.route('/payment_failure')
def payment_failure():
    return render_template('payment_fail.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
