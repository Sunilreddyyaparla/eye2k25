from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
from flask_mail import Mail, Message
import random
import razorpay
from flask_sqlalchemy import SQLAlchemy
import logging 
from sqlalchemy import inspect
import sys

# Enhanced logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database Configuration
DATABASE_URL = "postgresql://eye2k25_user:S4haUy7pTIEGbGCHDWt5cINm70ZvykVY@dpg-cu9pvolumphs73cfl9f0-a.oregon-postgres.render.com/eye2k25"

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'max_overflow': 10,
    'pool_timeout': 30,
    'pool_recycle': 1800,
}
app.config['SQLALCHEMY_ECHO'] = True

# Email Configuration
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USE_SSL=False,
    MAIL_USERNAME='yaparla25@gmail.com',
    MAIL_PASSWORD='hspv rseb ntvd ttda',
    MAIL_DEFAULT_SENDER='yaparla25@gmail.com'
)

mail = Mail(app)
db = SQLAlchemy(app)

# Models remain the same...
class RegData(db.Model):
    __tablename__ = 'reg_data'
    payment_id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    mobileno = db.Column(db.BigInteger, nullable=False)
    event = db.Column(db.String(100), nullable=False)
    college = db.Column(db.String(200), nullable=False)

class VisitorCount(db.Model):
    __tablename__ = 'visitor_count'
    id = db.Column(db.Integer, primary_key=True)
    count = db.Column(db.BigInteger, default=0)

    @classmethod
    def increment(cls):
        try:
            with db.session.begin_nested():
                count_record = cls.query.with_for_update().first()
                if count_record is None:
                    count_record = cls(count=1)
                    db.session.add(count_record)
                else:
                    count_record.count += 1
            db.session.commit()
            return count_record.count
        except Exception as e:
            logger.error(f"Error incrementing visitor count: {e}")
            db.session.rollback()
            return 0

# Razorpay configuration
razorpay_client = razorpay.Client(auth=("rzp_test_Aq1j1l911IgPB7", "wS97NzUTtmye6nuTBeXo3Rmm"))

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
    logger.info("Payment callback received")
    try:
        payment_data = request.get_json()
        logger.info(f"Payment data: {payment_data}")
        
        registration_data = session.get('registration_data')
        logger.info(f"Registration data from session: {registration_data}")
        
        if not registration_data:
            logger.error("No registration data in session")
            return jsonify({'status': 'error', 'message': 'No registration data found'})

        # Verify payment
        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_payment_id': payment_data['razorpay_payment_id'],
                'razorpay_order_id': payment_data['razorpay_order_id'],
                'razorpay_signature': payment_data['razorpay_signature']
            })
            logger.info("Payment verification successful")
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Payment verification failed'})

        # Save to database
        try:
            new_reg = RegData(
                payment_id=payment_data['razorpay_payment_id'],
                name=registration_data['fullname'],
                email=registration_data['email'],
                mobileno=int(registration_data['mobile']),
                event=registration_data['event_name'],
                college=registration_data['yourcollege']
            )
            logger.info(f"Attempting to save registration: {new_reg}")
            db.session.add(new_reg)
            db.session.commit()
            logger.info("Registration saved successfully")
        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            db.session.rollback()
            return jsonify({'status': 'error', 'message': 'Database error'})

        # Send email
        try:
            msg = Message(
                'EYE 2K25 Registration Confirmation',
                recipients=[registration_data['email']],
                body=f"""
Dear {registration_data['fullname']},

Thank you for registering for EYE 2K25!

Event: {registration_data['event_name']}
Payment ID: {payment_data['razorpay_payment_id']}
Amount: ₹{registration_data['event_fee']}

Best regards,
EYE 2K25 Team
                """
            )
            mail.send(msg)
            logger.info(f"Confirmation email sent to {registration_data['email']}")
        except Exception as e:
            logger.error(f"Email error: {str(e)}")
            # Continue even if email fails

        return jsonify({'status': 'success'})

    except Exception as e:
        logger.error(f"General error in payment_callback: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/test_email')
def test_email_route():
    if test_email():
        return "Test email sent successfully!"
    return "Failed to send test email"


def send_confirmation_email(registration_data, payment_id):
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
Thank you for being a part of EYE 2K25.
Have a nice day!

Best regards,
The EYE 2K25 Team
"""
        # Send email synchronously
        with app.app_context():
            mail.send(msg)
            logger.info(f"Confirmation email sent successfully to {registration_data['email']}")
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {str(e)}")
        raise


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
        try:
            # Test database connection
            db.create_all()
            logger.info("Database tables created successfully")
            
            # Test email configuration
            test_email()
            
            # Initialize visitor count if needed
            visitor = VisitorCount.query.first()
            if visitor is None:
                initial_count = VisitorCount(count=0)
                db.session.add(initial_count)
                db.session.commit()
                logger.info("Initialized visitor count to 0")
        except Exception as e:
            logger.error(f"Startup error: {str(e)}")
    
    app.run(debug=True)
