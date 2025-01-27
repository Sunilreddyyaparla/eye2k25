from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
from flask_mail import Mail, Message
import random
import razorpay
import threading
from flask_sqlalchemy import SQLAlchemy
import logging 
from sqlalchemy import inspect

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# SQLite Configuration with absolute path
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'eye2k25_reg.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True

logger.info(f"Database path: {db_path}")

db = SQLAlchemy(app)

class RegData(db.Model):
    __tablename__ = 'reg_data'
    payment_id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    mobileno = db.Column(db.Integer, nullable=False)
    event = db.Column(db.String(100), nullable=False)
    college = db.Column(db.String(200), nullable=False)

    def __repr__(self):
        return f'<RegData {self.payment_id}>'

class VisitorCount(db.Model):
    __tablename__ = 'visitor_count'
    id = db.Column(db.Integer, primary_key=True)
    count = db.Column(db.Integer, default=0)

    @classmethod
    def get_count(cls):
        count_record = cls.query.first()
        if count_record is None:
            count_record = cls()
            count_record.count = 0
            db.session.add(count_record)
            db.session.commit()
        return count_record.count

    @classmethod
    def increment(cls):
        try:
            with db.session.begin_nested():  # Use a savepoint
                count_record = cls.query.with_for_update().first()
                if count_record is None:
                    count_record = cls(count=1)
                    db.session.add(count_record)
                else:
                    count_record.count += 1
            db.session.commit()
            return count_record.count
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error incrementing visitor count: {e}")
            return 0

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

@app.route('/', methods=['GET', 'HEAD'])
def home():
    try:
        visitor_count = VisitorCount.increment()
        return render_template('home.html', visitor_count=visitor_count)
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        # For HEAD requests, return a minimal response
        if request.method == 'HEAD':
            return '', 200
        return render_template('home.html', visitor_count=0)
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
            app.logger.error(f"Registration error: {str(e)}")
            flash("An error occurred during registration. Please try again.", "error")
            return redirect(url_for('registration'))

    return render_template('registration.html', festevents=FEST_EVENTS)

@app.route('/payment_callback', methods=['POST'])
def payment_callback():
    try:
        # Get the payment data sent from Razorpay
        payment_data = request.get_json()
        logger.debug(f"Payment data received: {payment_data}")
        
        # Fetch registration data from the session
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

        # Save the payment and registration details to the database
        payment_id = payment_data['razorpay_payment_id']
        new_registration = RegData(
            payment_id=payment_id,
            name=registration_data['fullname'],
            email=registration_data['email'],
            mobileno=int(registration_data['mobile']),
            event=registration_data['event_name'],
            college=registration_data['yourcollege']
        )
        db.session.add(new_registration)
        db.session.commit()
        logger.debug("Registration details saved to database.")

        # Send a confirmation email
        try:
            send_confirmation_email(app, registration_data, payment_id)
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
    with app.app_context():
        if not os.path.exists(db_path):
            logger.info("Database does not exist. Creating new database...")
        else:
            logger.info("Database already exists")
        
        try:
            db.create_all()
            logger.info("Database tables created successfully")
            tables = inspect(db.engine).get_table_names()
            logger.info(f"Existing tables: {tables}")

            # Initialize visitor count if not exists
            visitor = VisitorCount.query.first()
            if visitor is None:
                initial_count = VisitorCount(count=0)
                db.session.add(initial_count)
                db.session.commit()
                logger.info("Initialized visitor count to 0")

        except Exception as e:
            logger.error(f"Error creating database tables: {str(e)}")
    
    app.run(debug=True)