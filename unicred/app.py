import os
import hashlib
import uuid
import json
import qrcode
# io and base64 removed — not used in current implementation
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, send_file)
# Email verification removed — flask_mail and itsdangerous not needed for this phase
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import logging
from logging.handlers import RotatingFileHandler

from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from database import query_db, execute_db

app = Flask(__name__)
app.config.from_object(Config)

# Make jsonify handle datetime, date, and Decimal objects automatically
from datetime import date
import decimal
import json as _json

class _UCEncoder(_json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)

app.config['RESTFUL_JSON'] = {}
# mail and serializer removed — email verification disabled

# Initialize Extensions
csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[app.config['RATELIMIT_DEFAULT']],
    storage_uri=app.config['RATELIMIT_STORAGE_URI']
)

# Database is accessed via raw PyMySQL in database.py — no ORM needed

# Setup Logging
if not app.debug:
    os.makedirs('logs', exist_ok=True)
    file_handler = RotatingFileHandler('logs/unicred.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('UniCred startup')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join('static', 'qrcodes'), exist_ok=True)

# ─────────────────────────────────────────────
# DECORATORS
# ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'Admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_current_user():
    if 'user_id' not in session:
        return None
    return query_db("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)

def get_user_credits(user_id):
    return query_db("SELECT * FROM credits WHERE user_id=%s", (user_id,), one=True)

# send_verification_email() removed — email verification is disabled for this phase

def create_notification(user_id, title, message, notif_type='info', link=None):
    execute_db(
        "INSERT INTO notifications (user_id, title, message, type, link) VALUES (%s,%s,%s,%s,%s)",
        (user_id, title, message, notif_type, link)
    )

def award_badges(user_id):
    """Check and award any newly earned badges."""
    credits_row = get_user_credits(user_id)
    if not credits_row:
        return
    total_earned = float(credits_row['total_earned'])
    completed = query_db(
        "SELECT COUNT(*) AS cnt FROM transactions WHERE (borrower_id=%s OR lender_id=%s) AND status='Returned'",
        (user_id, user_id), one=True
    )
    cnt = completed['cnt'] if completed else 0
    user = query_db("SELECT trust_score FROM users WHERE id=%s", (user_id,), one=True)
    trust = float(user['trust_score']) if user else 0.0

    badges = query_db("SELECT * FROM badges")
    for badge in badges:
        already = query_db(
            "SELECT id FROM user_badges WHERE user_id=%s AND badge_id=%s",
            (user_id, badge['id']), one=True
        )
        if already:
            continue
        earned = False
        ct = badge['criteria_type']
        cv = badge['criteria_value']
        if ct == 'transactions' and cnt >= cv:
            earned = True
        elif ct == 'credits_earned' and total_earned >= cv:
            earned = True
        elif ct == 'trust_score' and trust >= 4.5 and cnt >= cv:
            earned = True
        if earned:
            execute_db("INSERT INTO user_badges (user_id, badge_id) VALUES (%s,%s)", (user_id, badge['id']))
            create_notification(user_id, f'Badge Earned: {badge["name"]}',
                                badge['description'], 'success')

# ─────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────
def compute_qr_hash(tx_id, user_id, action, secret_salt=""):
    """Compute a SHA256 hash for QR code verification to prevent tampering."""
    raw = f"{tx_id}:{user_id}:{action}:{app.config['SECRET_KEY']}:{secret_salt}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def generate_qr_code(tx_id, user_id, action='collection'):
    """Generate a secure QR code with expiry and save it to the static domain."""
    # Ensure a highly unique and hard to guess hash per generation
    salt = str(uuid.uuid4())
    qr_hash = compute_qr_hash(tx_id, user_id, action, salt)
    
    # 5 minute expiry window for QR codes
    expires_at = (datetime.now() + timedelta(minutes=5)).isoformat()
    
    payload = {
        'tx_id': tx_id,
        'user_id': user_id,
        'type': action,
        'hash': qr_hash,
        'expires': expires_at
    }
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(json.dumps(payload))
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    filename = f"qr_{tx_id}_{action}_{int(datetime.now().timestamp())}.png"
    filepath = os.path.join('static', 'qrcodes', filename)
    img.save(filepath)
    return filename, qr_hash

def apply_daily_penalties():
    """Cron-like function: apply penalties for overdue transactions."""
    with app.app_context():
        overdue = query_db(
            """SELECT t.*, r.title FROM transactions t
               JOIN resources r ON t.resource_id=r.id
               WHERE t.status='Active' AND t.due_date < CURDATE()"""
        )
        for tx in overdue:
            execute_db(
                "UPDATE transactions SET penalty_applied = penalty_applied + %s WHERE id=%s",
                (Config.PENALTY_PER_DAY, tx['id'])
            )
            execute_db(
                "UPDATE credits SET balance = balance - %s WHERE user_id=%s AND balance > 0",
                (Config.PENALTY_PER_DAY, tx['borrower_id'])
            )
            execute_db(
                """INSERT INTO penalty_log (user_id, transaction_id, penalty_amount, reason)
                   VALUES (%s,%s,%s,%s)""",
                (tx['borrower_id'], tx['id'], Config.PENALTY_PER_DAY,
                 f"Overdue return: {tx['title']}")
            )
            execute_db(
                "UPDATE users SET trust_score = GREATEST(0, trust_score - 0.1) WHERE id=%s",
                (tx['borrower_id'],)
            )
            violations = query_db(
                "SELECT COUNT(*) AS cnt FROM penalty_log WHERE user_id=%s AND applied_at > DATE_SUB(NOW(), INTERVAL 30 DAY)",
                (tx['borrower_id'],), one=True
            )
            if violations and violations['cnt'] >= Config.MAX_VIOLATIONS:
                execute_db("UPDATE users SET is_frozen=TRUE WHERE id=%s", (tx['borrower_id'],))
            create_notification(tx['borrower_id'], 'Overdue Penalty Applied',
                                f"{Config.PENALTY_PER_DAY} credits deducted for overdue item: {tx['title']}", 'danger')

def auto_transfer_deposits():
    """Cron-like function: auto transfer security deposits to lenders if not returned past due date."""
    with app.app_context():
        stuck_txs = query_db(
            """SELECT t.*, r.title FROM transactions t
               JOIN resources r ON t.resource_id=r.id
               WHERE t.status='Active' AND t.due_date < CURDATE()"""
        )
        for tx in stuck_txs:
            deposit = float(tx['security_deposit'])
            if deposit > 0:
                # Release locked credits from borrower and transfer to lender
                execute_db(
                    "UPDATE credits SET locked_credits=locked_credits-%s WHERE user_id=%s",
                    (deposit, tx['borrower_id'])
                )
                execute_db(
                    "UPDATE credits SET balance=balance+%s, total_earned=total_earned+%s WHERE user_id=%s",
                    (deposit, deposit, tx['lender_id'])
                )
                execute_db(
                    "UPDATE transactions SET security_deposit=0 WHERE id=%s",
                    (tx['id'],)
                )
                create_notification(tx['lender_id'], 'Deposit Auto-Transferred',
                                    f"Security deposit ({deposit} credits) transferred for overdue item: {tx['title']}", 'success')
                create_notification(tx['borrower_id'], 'Deposit Forfeited',
                                    f"Security deposit forfeited for overdue item: {tx['title']}", 'danger')

def remind_upcoming_dues():
    """Cron-like function: remind borrowers of items due tomorrow."""
    with app.app_context():
        due_tomorrow = query_db(
            """SELECT t.*, r.title FROM transactions t
               JOIN resources r ON t.resource_id=r.id
               WHERE t.status='Active' AND t.due_date = DATE_ADD(CURDATE(), INTERVAL 1 DAY)"""
        )
        for tx in due_tomorrow:
            create_notification(tx['borrower_id'], 'Item Due Tomorrow',
                                f'Reminder: Please return "{tx["title"]}" by tomorrow to avoid penalties.', 'warning')

# Initialize and start scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=apply_daily_penalties, trigger="cron", hour=0, minute=1)
scheduler.add_job(func=auto_transfer_deposits, trigger="cron", hour=0, minute=5)
scheduler.add_job(func=remind_upcoming_dues, trigger="cron", hour=8, minute=0)
scheduler.start()

# ─────────────────────────────────────────────
# FRAUD DETECTION ENGINE
# ─────────────────────────────────────────────
def check_transaction_frequency(user_id):
    """Detect high frequency of transactions between the same pair of users."""
    with app.app_context():
        suspicious_pairs = query_db(
            """SELECT lender_id, borrower_id, COUNT(*) AS tx_count
               FROM transactions
               WHERE (lender_id=%s OR borrower_id=%s) AND created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
               GROUP BY lender_id, borrower_id
               HAVING tx_count > 5""", (user_id, user_id)
        )
        for pair in suspicious_pairs:
            details = f"High frequency: {pair['tx_count']} transactions between user {pair['lender_id']} and {pair['borrower_id']} in 7 days."
            # Check if recently flagged
            recent = query_db("SELECT id FROM fraud_flags WHERE user_id=%s AND flag_type='Frequency' AND created_at > DATE_SUB(NOW(), INTERVAL 1 DAY)", (user_id,), one=True)
            if not recent:
                execute_db("INSERT INTO fraud_flags (user_id, flag_type, details) VALUES (%s, %s, %s)",
                           (user_id, 'Frequency', details))

def check_rapid_credit_spikes(user_id):
    """Detect abnormal rapid credit growth for a user."""
    with app.app_context():
        user_credits = query_db("SELECT total_earned FROM credits WHERE user_id=%s", (user_id,), one=True)
        if user_credits and user_credits['total_earned'] > 1000:
            details = f"Rapid credit spike detected. User {user_id} has earned {user_credits['total_earned']} credits."
            recent = query_db("SELECT id FROM fraud_flags WHERE user_id=%s AND flag_type='Credit Spike' AND created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)", (user_id,), one=True)
            if not recent:
                execute_db("INSERT INTO fraud_flags (user_id, flag_type, details) VALUES (%s, %s, %s)",
                           (user_id, 'Credit Spike', details))

def check_circular_ratings(user_id):
    """Detect circular mutual rating patterns."""
    with app.app_context():
        circular = query_db(
            """SELECT r1.ratee_id AS partner_id, COUNT(*) AS rating_count
               FROM ratings r1
               JOIN ratings r2 ON r1.rater_id = r2.ratee_id AND r1.ratee_id = r2.rater_id
               WHERE r1.rater_id=%s AND r1.created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
               GROUP BY r1.ratee_id
               HAVING rating_count > 3""", (user_id,)
        )
        for c in circular:
            details = f"Circular ratings detected: User {user_id} and User {c['partner_id']} exchanged {c['rating_count']} mutual ratings."
            recent = query_db("SELECT id FROM fraud_flags WHERE user_id=%s AND flag_type='Circular Ratings' AND created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)", (user_id,), one=True)
            if not recent:
                execute_db("INSERT INTO fraud_flags (user_id, flag_type, details) VALUES (%s, %s, %s)",
                           (user_id, 'Circular Ratings', details))

def run_fraud_checks(user_id):
    check_transaction_frequency(user_id)
    check_rapid_credit_spikes(user_id)
    check_circular_ratings(user_id)

# ─────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    stats = {
        'users': query_db("SELECT COUNT(*) AS c FROM users WHERE role != 'Admin'", one=True)['c'],
        'resources': query_db("SELECT COUNT(*) AS c FROM resources", one=True)['c'],
        'transactions': query_db("SELECT COUNT(*) AS c FROM transactions WHERE status='Returned'", one=True)['c'],
    }
    return render_template('index.html', stats=stats)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        roll = request.form.get('roll_number', '').strip().upper()
        dept = request.form.get('department', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        # Validate
        if not all([name, email, roll, dept, password]):
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('auth/register.html')

        if not name or not dept:
             flash('Name and Department cannot be empty.', 'danger')
             return render_template('auth/register.html')

        existing_email = query_db("SELECT id FROM users WHERE email=%s", (email,), one=True)
        if existing_email:
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')

        existing_roll = query_db("SELECT id FROM users WHERE roll_number=%s", (roll,), one=True)
        if existing_roll:
            flash('Roll number already registered. Please use your own roll number.', 'danger')
            return render_template('auth/register.html')

        try:
            pwd_hash = generate_password_hash(password)
            user_id = execute_db(
                "INSERT INTO users (name, email, roll_number, password_hash, department, is_verified)"
                " VALUES (%s, %s, %s, %s, %s, TRUE)",
                (name, email, roll, pwd_hash, dept), get_id=True
            )
            execute_db("INSERT INTO credits (user_id, balance, total_earned) VALUES (%s, %s, %s)",
                       (user_id, Config.CREDIT_INITIAL_BALANCE, Config.CREDIT_INITIAL_BALANCE))
        except Exception as db_err:
            app.logger.error(f"Registration DB error for {email}: {db_err}")
            flash('Registration failed due to a server error. Please try again.', 'danger')
            return render_template('auth/register.html')

        flash('Registration successful! You can now log in.', 'success')
        app.logger.info(f"New user registered: {email}")
        return redirect(url_for('login'))
    return render_template('auth/register.html')

# /verify/<token> route removed — email verification is disabled for this phase

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        # Add basic input validation
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('auth/login.html')
            
        user = query_db("SELECT * FROM users WHERE email=%s", (email,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            # is_verified check removed — all registered accounts are immediately active
            if user['is_frozen']:
                flash('Account is frozen due to violations. Contact admin.', 'danger')
                return render_template('auth/login.html')
            
            session.permanent = True
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['role'] = user['role']
            session['email'] = user['email']
            
            flash(f'Welcome back, {user["name"]}!', 'success')
            app.logger.info(f"User {user['id']} logged in")
            return redirect(url_for('dashboard'))
            
        flash('Invalid email or password.', 'danger')
        app.logger.warning(f"Failed login attempt for {email}")
        
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    user = get_current_user()
    credits = get_user_credits(uid)
    active_borrowings = query_db(
        """SELECT t.*, r.title, u.name AS lender_name FROM transactions t
           JOIN resources r ON t.resource_id=r.id
           JOIN users u ON t.lender_id=u.id
           WHERE t.borrower_id=%s AND t.status IN ('Active','Initiated','ItemCollected')""",
        (uid,)
    )
    active_lendings = query_db(
        """SELECT t.*, r.title, u.name AS borrower_name FROM transactions t
           JOIN resources r ON t.resource_id=r.id
           JOIN users u ON t.borrower_id=u.id
           WHERE t.lender_id=%s AND t.status IN ('Active','Initiated','ItemCollected')""",
        (uid,)
    )
    pending_requests = query_db(
        """SELECT rq.*, r.title, u.name AS borrower_name FROM requests rq
           JOIN resources r ON rq.resource_id=r.id
           JOIN users u ON rq.borrower_id=u.id
           WHERE rq.lender_id=%s AND rq.status='Pending'""",
        (uid,)
    )
    notifications = query_db(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 5",
        (uid,)
    )
    rank_row = query_db(
        """SELECT COUNT(*)+1 AS rnk FROM credits
           WHERE balance > (SELECT balance FROM credits WHERE user_id=%s)""",
        (uid,), one=True
    )
    badges = query_db(
        """SELECT b.* FROM badges b
           JOIN user_badges ub ON b.id=ub.badge_id
           WHERE ub.user_id=%s ORDER BY ub.earned_at DESC""",
        (uid,)
    )
    # Request System — open requests from other users (for dashboard quick-accept)
    open_resource_reqs = query_db(
        """SELECT rr.*, u.name AS requester_name
           FROM resource_requests rr
           JOIN users u ON rr.user_id = u.id
           WHERE rr.status = 'Open' AND rr.user_id != %s
           ORDER BY rr.created_at DESC LIMIT 5""",
        (uid,)
    )
    open_knowledge_reqs = query_db(
        """SELECT kr.*, u.name AS requester_name
           FROM knowledge_requests kr
           JOIN users u ON kr.user_id = u.id
           WHERE kr.status = 'Open' AND kr.user_id != %s
           ORDER BY kr.created_at DESC LIMIT 5""",
        (uid,)
    )
    return render_template('dashboard/dashboard.html',
                           user=user, credits=credits,
                           active_borrowings=active_borrowings,
                           active_lendings=active_lendings,
                           pending_requests=pending_requests,
                           notifications=notifications,
                           rank=rank_row['rnk'] if rank_row else '-',
                           badges=badges,
                           open_resource_reqs=open_resource_reqs,
                           open_knowledge_reqs=open_knowledge_reqs)


# ─────────────────────────────────────────────
# NOTIFICATIONS API
# ─────────────────────────────────────────────
@app.route('/api/notifications')
@login_required
def api_notifications():
    uid = session['user_id']
    notifs = query_db(
        "SELECT id, title, message, type, is_read, created_at, link"
        " FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 10",
        (uid,)
    )
    # Convert to plain list of dicts (datetime → string handled by UCJSONProvider)
    notif_list = [dict(n) for n in notifs] if notifs else []
    for n in notif_list:
        if 'created_at' in n and n['created_at']:
            n['created_at'] = n['created_at'].isoformat()
    return jsonify({'notifications': notif_list, 'count': sum(1 for n in notif_list if not n['is_read'])})

@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    uid = session['user_id']
    execute_db(
        "UPDATE notifications SET is_read=TRUE WHERE id=%s AND user_id=%s",
        (notif_id, uid)
    )
    return jsonify({'status': 'ok'})

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    uid = session['user_id']
    execute_db("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (uid,))
    return jsonify({'status': 'ok'})

# Legacy alias kept for backward compatibility
@app.route('/api/notifications/mark_read', methods=['POST'])
@login_required
def mark_notifications_read():
    uid = session['user_id']
    execute_db("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (uid,))
    return jsonify({'status': 'ok'})

# ─────────────────────────────────────────────
# RESOURCES
# ─────────────────────────────────────────────
@app.route('/resources')
@login_required
def browse_resources():
    uid = session['user_id']
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    rtype = request.args.get('type', 'Resource')
    sql = """SELECT r.*, u.name AS owner_name, u.trust_score
             FROM resources r JOIN users u ON r.owner_id=u.id
             WHERE r.status='Available' AND r.owner_id != %s
             AND r.resource_type=%s"""
    params = [uid, rtype]
    if category:
        sql += " AND r.category=%s"
        params.append(category)
    if search:
        sql += " AND (r.title LIKE %s OR r.description LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    sql += " ORDER BY r.created_at DESC"
    resources = query_db(sql, params)
    return render_template('resources/browse.html', resources=resources,
                           category=category, search=search, rtype=rtype)

@app.route('/resources/offer', methods=['GET', 'POST'])
@login_required
def offer_resource():
    if request.method == 'POST':
        uid = session['user_id']
        title = request.form.get('title', '').strip()
        category = request.form.get('category')
        desc = request.form.get('description', '').strip()
        
        try:
            qty = int(request.form.get('quantity', 1) or 1)
        except ValueError:
            qty = 1
            
        avail_from = request.form.get('available_from')
        if not avail_from:
            avail_from = None
            
        avail_until = request.form.get('available_until')
        if not avail_until:
            avail_until = None
            
        location = request.form.get('location', '').strip()
        
        try:
            deposit = float(request.form.get('security_deposit', 0) or 0.0)
        except ValueError:
            deposit = 0.0
            
        try:
            cpd = float(request.form.get('credits_per_day', 0) or 0.0)
        except ValueError:
            cpd = 0.0
            
        rtype = request.form.get('resource_type', 'Resource')

        if not title or not category:
            flash('Title and category are required.', 'danger')
            return render_template('resources/offer.html')

        execute_db(
            """INSERT INTO resources (owner_id, title, category, description, quantity,
               available_from, available_until, location, security_deposit, credits_per_day, resource_type)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uid, title, category, desc, qty, avail_from, avail_until,
             location, deposit, cpd, rtype)
        )
        flash(f'"{title}" listed successfully!', 'success')
        return redirect(url_for('browse_resources'))
    return render_template('resources/offer.html')

@app.route('/resources/<int:resource_id>')
@login_required
def resource_detail(resource_id):
    resource = query_db(
        """SELECT r.*, u.name AS owner_name, u.trust_score, u.id AS owner_id
           FROM resources r JOIN users u ON r.owner_id=u.id WHERE r.id=%s""",
        (resource_id,), one=True
    )
    if not resource:
        flash('Resource not found.', 'danger')
        return redirect(url_for('browse_resources'))
    return render_template('resources/detail.html', resource=resource)

@app.route('/resources/<int:resource_id>/request', methods=['POST'])
@login_required
def request_resource(resource_id):
    uid = session['user_id']
    resource = query_db("SELECT * FROM resources WHERE id=%s AND status='Available'", (resource_id,), one=True)
    if not resource:
        flash('Resource not available.', 'danger')
        return redirect(url_for('browse_resources'))
    if resource['owner_id'] == uid:
        flash('You cannot request your own resource.', 'danger')
        return redirect(url_for('resource_detail', resource_id=resource_id))

    try:
        borrow_days = int(request.form.get('borrow_days', 1) or 1)
    except ValueError:
        borrow_days = 1
        
    message = request.form.get('message', '')
    total_credits = float(resource['credits_per_day']) * borrow_days + float(resource['security_deposit'])

    # Check borrower credits
    credits = get_user_credits(uid)
    if not credits or float(credits['balance']) < total_credits:
        flash(f'Insufficient credits. You need {total_credits} credits.', 'danger')
        return redirect(url_for('resource_detail', resource_id=resource_id))

    # Check trust score
    user = get_current_user()
    if float(user['trust_score']) < Config.MIN_TRUST_SCORE:
        flash('Your trust score is too low to borrow resources.', 'danger')
        return redirect(url_for('resource_detail', resource_id=resource_id))

    # Existing active request
    existing = query_db(
        "SELECT id FROM requests WHERE resource_id=%s AND borrower_id=%s AND status='Pending'",
        (resource_id, uid), one=True
    )
    if existing:
        flash('You already have a pending request for this resource.', 'warning')
        return redirect(url_for('resource_detail', resource_id=resource_id))

    req_id = execute_db(
        """INSERT INTO requests (resource_id, borrower_id, lender_id, borrow_days, total_credits, message)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (resource_id, uid, resource['owner_id'], borrow_days, total_credits, message), get_id=True
    )
    create_notification(resource['owner_id'], 'New Borrow Request',
                        f'{user["name"]} wants to borrow "{resource["title"]}" for {borrow_days} days.',
                        'info', url_for('dashboard'))
    flash('Borrow request sent!', 'success')
    return redirect(url_for('dashboard'))

# ─────────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────────
@app.route('/requests/<int:req_id>/approve', methods=['POST'])
@login_required
def approve_request(req_id):
    uid = session['user_id']
    req = query_db("SELECT * FROM requests WHERE id=%s AND lender_id=%s AND status='Pending'", (req_id, uid), one=True)
    if not req:
        flash('Request not found.', 'danger')
        return redirect(url_for('dashboard'))
    resource = query_db("SELECT * FROM resources WHERE id=%s", (req['resource_id'],), one=True)
    deposit = float(resource['security_deposit']) if resource else 0.0

    # Lock security deposit credits from borrower
    credits = get_user_credits(req['borrower_id'])
    if float(credits['balance']) < float(req['total_credits']):
        flash('Borrower no longer has sufficient credits.', 'danger')
        execute_db("UPDATE requests SET status='Rejected' WHERE id=%s", (req_id,))
        return redirect(url_for('dashboard'))

    execute_db(
        "UPDATE credits SET balance=balance-%s, locked_credits=locked_credits+%s WHERE user_id=%s",
        (deposit, deposit, req['borrower_id'])
    )
    execute_db("UPDATE requests SET status='Approved' WHERE id=%s", (req_id,))
    execute_db("UPDATE resources SET status='Borrowed' WHERE id=%s", (req['resource_id'],))

    # Create transaction
    tx_id = str(uuid.uuid4()).replace('-', '').upper()
    due_date = (datetime.now() + timedelta(days=req['borrow_days'])).date()
    # Initial QR hash for collection, will be updated when QR is generated for display
    initial_qr_hash = compute_qr_hash(tx_id, req['borrower_id'], 'collection', str(uuid.uuid4()))

    exec_id = execute_db(
        """INSERT INTO transactions (transaction_id, request_id, borrower_id, lender_id, resource_id,
           credits_transferred, security_deposit, due_date, qr_hash)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (tx_id, req_id, req['borrower_id'], uid, req['resource_id'],
         req['total_credits'], deposit, due_date, initial_qr_hash), get_id=True
    )
    # No need to insert into qr_log here, it's done when QR is generated for display
    borrower = query_db("SELECT name FROM users WHERE id=%s", (req['borrower_id'],), one=True)
    create_notification(req['borrower_id'], 'Request Approved!',
                        f'Your request for "{resource["title"]}" was approved. Show QR to collect.',
                        'success', url_for('view_transaction', tx_db_id=exec_id))
    flash('Request approved! Transaction created.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/requests/<int:req_id>/reject', methods=['POST'])
@login_required
def reject_request(req_id):
    uid = session['user_id']
    req = query_db("SELECT * FROM requests WHERE id=%s AND lender_id=%s AND status='Pending'", (req_id, uid), one=True)
    if not req:
        flash('Request not found.', 'danger')
        return redirect(url_for('dashboard'))
    execute_db("UPDATE requests SET status='Rejected' WHERE id=%s", (req_id,))
    resource = query_db("SELECT title FROM resources WHERE id=%s", (req['resource_id'],), one=True)
    create_notification(req['borrower_id'], 'Request Rejected',
                        f'Your request for "{resource["title"]}" was rejected.', 'danger')
    flash('Request rejected.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/transaction/<int:tx_db_id>')
@login_required
def view_transaction(tx_db_id):
    uid = session['user_id']
    tx = query_db(
        """SELECT t.*, r.title, u1.name AS borrower_name, u2.name AS lender_name
           FROM transactions t
           JOIN resources r ON t.resource_id=r.id
           JOIN users u1 ON t.borrower_id=u1.id
           JOIN users u2 ON t.lender_id=u2.id
           WHERE t.id=%s AND (t.borrower_id=%s OR t.lender_id=%s)""",
        (tx_db_id, uid, uid), one=True
    )
    if not tx:
        flash('Transaction not found.', 'danger')
        return redirect(url_for('dashboard'))

    # Prepare QR data for display
    tx['qr_file'] = None
    tx['qr_action'] = None

    if tx['status'] in ('Initiated',) and tx['borrower_id'] == uid:
        filename, qr_hash = generate_qr_code(tx['transaction_id'], uid, action='collection')
        # Update the transaction with the generated QR hash for verification later
        execute_db("UPDATE transactions SET qr_hash=%s WHERE id=%s", (qr_hash, tx_db_id))
        tx['qr_file'] = filename
        tx['qr_action'] = 'Collection'
        
    if tx['status'] == 'Active' and tx['borrower_id'] == uid:
        filename, qr_hash = generate_qr_code(tx['transaction_id'], uid, action='return')
        
        # We don't save return qr_hash to tx table because it's dynamic now and verified differently 
        # (the scan route computes expected_hash on the fly using the borrower_id)
        
        tx['qr_file'] = filename
        tx['qr_action'] = 'Return'
        
    return render_template('transactions/view.html', tx=tx)

@app.route('/transaction/scan', methods=['GET', 'POST'])
@login_required
def scan_qr():
    if request.method == 'POST':
        uid = session['user_id']
        qr_payload_str = request.form.get('qr_data', '')
        try:
            payload = json.loads(qr_payload_str)
        except Exception:
            return jsonify({'success': False, 'message': 'Invalid QR data format'})

        tx_id = payload.get('tx_id')
        qr_type = payload.get('type', 'collection')
        received_hash = payload.get('hash')
        expires_str = payload.get('expires')
        
        if not tx_id or not received_hash or not expires_str:
             return jsonify({'success': False, 'message': 'Missing QR data fields'})
             
        # Expiration Check
        try:
            expires_at = datetime.fromisoformat(expires_str)
            if datetime.now() > expires_at:
                return jsonify({'success': False, 'message': 'QR Code has expired. Please generate a new one.'})
        except Exception:
            return jsonify({'success': False, 'message': 'Invalid expiry format'})

        tx = query_db("SELECT * FROM transactions WHERE transaction_id=%s", (tx_id,), one=True)
        if not tx:
            return jsonify({'success': False, 'message': 'Transaction not found'})

        # Verify scanner is the lender
        if tx['lender_id'] != uid:
            return jsonify({'success': False, 'message': 'Only the lender can scan this QR'})
            
        # Replay Attack Prevention Check using qr_log
        log_entry = query_db("SELECT id, used FROM qr_log WHERE qr_hash=%s", (received_hash,), one=True)
        if log_entry and log_entry['used']:
            return jsonify({'success': False, 'message': 'This QR code has already been used (Replay blocked).'})

        if qr_type == 'collection':
            if tx['status'] != 'Initiated':
                return jsonify({'success': False, 'message': 'Transaction is not in initiated state'})
            expected_hash = tx['qr_hash']
            if received_hash != expected_hash:
                return jsonify({'success': False, 'message': 'QR hash mismatch - invalid QR'})
            
            # Mark log as used
            execute_db("UPDATE qr_log SET used=TRUE, used_at=NOW() WHERE qr_hash=%s", (received_hash,))
            
            execute_db(
                "UPDATE transactions SET status='Active', collected_at=NOW() WHERE transaction_id=%s",
                (tx_id,)
            )
            resource = query_db("SELECT title FROM resources WHERE id=%s", (tx['resource_id'],), one=True)
            create_notification(tx['borrower_id'], 'Item Collected',
                                f'Your borrowing of "{resource["title"]}" has started. Return by {tx["due_date"]}.', 'success')
            return jsonify({'success': True, 'message': 'Item collection confirmed!'})

        elif qr_type == 'return':
            if tx['status'] != 'Active':
                return jsonify({'success': False, 'message': 'Transaction is not active'})
            # For returns, we don't store a static return hash in the tx table currently, but we can validate against the dynamic generation
            expected_hash = compute_qr_hash(tx_id, tx['borrower_id'], 'return', 'return')
            if received_hash != expected_hash:
                return jsonify({'success': False, 'message': 'Return QR invalid'})
                
            # Log the return QR usage if it doesn't exist
            if not log_entry:
                execute_db("INSERT INTO qr_log (transaction_id, qr_type, qr_hash, expires_at, used, used_at) VALUES (%s, %s, %s, %s, TRUE, NOW())",
                           (tx_id, 'Return', received_hash, expires_str))
            else:
                execute_db("UPDATE qr_log SET used=TRUE, used_at=NOW() WHERE qr_hash=%s", (received_hash,))

            deposit = float(tx['security_deposit'])
            credits_due = float(tx['credits_transferred']) - deposit

            # Release deposit, transfer credits to lender
            execute_db(
                "UPDATE credits SET locked_credits=locked_credits-%s, balance=balance+%s WHERE user_id=%s",
                (deposit, deposit, tx['borrower_id'])
            )
            execute_db(
                "UPDATE credits SET balance=balance+%s, total_earned=total_earned+%s WHERE user_id=%s",
                (credits_due, credits_due, tx['lender_id'])
            )
            execute_db(
                "UPDATE credits SET balance=balance-%s, total_spent=total_spent+%s WHERE user_id=%s",
                (credits_due, credits_due, tx['borrower_id'])
            )
            execute_db(
                "UPDATE transactions SET status='Returned', returned_at=NOW() WHERE transaction_id=%s",
                (tx_id,)
            )
            resource = query_db(
                "SELECT r.title, t.request_id FROM transactions t JOIN resources r ON t.resource_id=r.id WHERE t.transaction_id=%s",
                (tx_id,), one=True
            )
            execute_db("UPDATE resources SET status='Available' WHERE id=%s", (tx['resource_id'],))
            create_notification(tx['lender_id'], 'Item Returned',
                                f'Item returned. {credits_due} credits added to your balance!', 'success')
            create_notification(tx['borrower_id'], 'Return Confirmed',
                                'Item returned successfully. Security deposit released.', 'success')
            award_badges(tx['lender_id'])
            award_badges(tx['borrower_id'])
            
            # Fire fraud checks after transaction completes
            run_fraud_checks(tx['lender_id'])
            run_fraud_checks(tx['borrower_id'])
            
            return jsonify({'success': True, 'message': f'Return confirmed! {credits_due} credits transferred.'})

        return jsonify({'success': False, 'message': 'Unknown QR type'})

    return render_template('transactions/scan_qr.html')

@app.route('/transactions/history')
@login_required
def transaction_history():
    uid = session['user_id']
    txs = query_db(
        """SELECT t.*, r.title, u1.name AS borrower_name, u2.name AS lender_name
           FROM transactions t
           JOIN resources r ON t.resource_id=r.id
           JOIN users u1 ON t.borrower_id=u1.id
           JOIN users u2 ON t.lender_id=u2.id
           WHERE t.borrower_id=%s OR t.lender_id=%s
           ORDER BY t.created_at DESC""",
        (uid, uid)
    )
    return render_template('transactions/history.html', transactions=txs)

# ─────────────────────────────────────────────
# RATINGS
# ─────────────────────────────────────────────
@app.route('/rate/<int:tx_db_id>', methods=['GET', 'POST'])
@login_required
def rate_transaction(tx_db_id):
    uid = session['user_id']
    tx = query_db(
        """SELECT t.*, r.title FROM transactions t
           JOIN resources r ON t.resource_id=r.id
           WHERE t.id=%s AND (t.borrower_id=%s OR t.lender_id=%s) AND t.status='Returned'""",
        (tx_db_id, uid, uid), one=True
    )
    if not tx:
        flash('Cannot rate this transaction.', 'danger')
        return redirect(url_for('transaction_history'))

    ratee_id = tx['lender_id'] if uid == tx['borrower_id'] else tx['borrower_id']
    already_rated = query_db(
        "SELECT id FROM ratings WHERE transaction_id=%s AND rater_id=%s",
        (tx_db_id, uid), one=True
    )
    if already_rated:
        flash('You already rated this transaction.', 'info')
        return redirect(url_for('transaction_history'))

    if request.method == 'POST':
        comm = int(request.form.get('communication', 3))
        time_ = int(request.form.get('timeliness', 3))
        cond = int(request.form.get('condition', 3))
        comment = request.form.get('comment', '')
        overall = round((comm + time_ + cond) / 3, 2)

        execute_db(
            """INSERT INTO ratings (transaction_id, rater_id, ratee_id, communication_rating,
               timeliness_rating, condition_rating, overall_rating, comment)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (tx_db_id, uid, ratee_id, comm, time_, cond, overall, comment)
        )
        # Update trust score
        avg = query_db(
            "SELECT AVG(overall_rating) AS avg_rating FROM ratings WHERE ratee_id=%s",
            (ratee_id,), one=True
        )
        if avg and avg['avg_rating']:
            execute_db("UPDATE users SET trust_score=%s WHERE id=%s",
                       (round(float(avg['avg_rating']), 2), ratee_id))
            
        run_fraud_checks(uid)
        
        flash('Rating submitted!', 'success')
        return redirect(url_for('transaction_history'))

    return render_template('ratings/rate.html', tx=tx)

# ─────────────────────────────────────────────
# LEADERBOARD
# ─────────────────────────────────────────────
@app.route('/leaderboard')
@login_required
def leaderboard():
    users_data = query_db(
        """SELECT u.id, u.name, u.department, u.trust_score, u.role,
                  c.balance, c.total_earned,
                  (SELECT COUNT(*) FROM transactions t WHERE t.lender_id=u.id AND t.status='Returned') AS completed
           FROM users u
           JOIN credits c ON u.id=c.user_id
           WHERE u.is_active=TRUE AND u.role != 'Admin'"""
    )
    
    # Composite Score Calculation
    # Dynamic weight: 50% credits, 30% trust score, 20% completed txs
    for l in users_data:
        credits_weight = float(l['total_earned']) * 0.5
        trust_weight = float(l['trust_score']) * 10 * 0.3  # Scale trust 0-5 to 0-50 then apply weight
        tx_weight = float(l['completed']) * 5 * 0.2        # Give some flat weight per complete tx
        l['composite_score'] = credits_weight + trust_weight + tx_weight

    # Sort users by composite score DESC
    users_data.sort(key=lambda x: x['composite_score'], reverse=True)
    
    # Assign Ranks and trim to Top 50
    leaders = []
    for idx, u in enumerate(users_data[:50]):
        u['rnk'] = idx + 1
        leaders.append(u)

    badges_map = {}
    for l in leaders:
        badges = query_db(
            """SELECT b.icon FROM badges b JOIN user_badges ub ON b.id=ub.badge_id WHERE ub.user_id=%s""",
            (l['id'],)
        )
        badges_map[l['id']] = [b['icon'] for b in badges]
        
    return render_template('leaderboard/leaderboard.html', leaders=leaders, badges_map=badges_map)

# ─────────────────────────────────────────────
# KNOWLEDGE / SKILL SHARING
# ─────────────────────────────────────────────
@app.route('/knowledge')
@login_required
def knowledge_hub():
    uid = session['user_id']
    rtype = request.args.get('type', 'Knowledge')
    items = query_db(
        """SELECT r.*, u.name AS owner_name, u.trust_score
           FROM resources r JOIN users u ON r.owner_id=u.id
           WHERE r.status='Available' AND r.resource_type=%s AND r.owner_id != %s
           ORDER BY r.created_at DESC""",
        (rtype, uid)
    )
    return render_template('knowledge/knowledge.html', items=items, rtype=rtype)

# ─────────────────────────────────────────────
# REQUEST SYSTEM — RESOURCE REQUESTS
# ─────────────────────────────────────────────

@app.route('/request-resource', methods=['GET', 'POST'])
@login_required
def post_resource_request():
    """Let a user post a public 'I need X' resource request."""
    if request.method == 'POST':
        uid = session['user_id']
        title    = request.form.get('title', '').strip()
        category = request.form.get('category', 'Other')
        desc     = request.form.get('description', '').strip()
        location = request.form.get('location', '').strip()
        try:
            duration = int(request.form.get('duration_days', 1) or 1)
        except ValueError:
            duration = 1
        try:
            credits_offered = float(request.form.get('credits_offered', 0) or 0)
        except ValueError:
            credits_offered = 0.0

        if not title:
            flash('Resource name is required.', 'danger')
            return render_template('requests/request_resource.html')

        # Check requester has enough credits
        creds = get_user_credits(uid)
        if not creds or float(creds['balance']) < credits_offered:
            flash(f'Insufficient credits. You have {float(creds["balance"]) if creds else 0} credits.', 'danger')
            return render_template('requests/request_resource.html')

        execute_db(
            """INSERT INTO resource_requests
               (user_id, title, category, description, location, duration_days, credits_offered)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (uid, title, category, desc, location, duration, credits_offered)
        )

        # Broadcast notification to all other active users
        all_users = query_db(
            "SELECT id FROM users WHERE id != %s AND is_active=TRUE AND role != 'Admin'",
            (uid,)
        )
        requester = query_db("SELECT name FROM users WHERE id=%s", (uid,), one=True)
        for u in (all_users or []):
            create_notification(
                u['id'],
                'New Resource Request',
                f'{requester["name"]} is looking for "{title}". Can you help?',
                'info',
                url_for('browse_requests')
            )

        flash(f'Request for "{title}" posted successfully!', 'success')
        return redirect(url_for('browse_requests'))

    return render_template('requests/request_resource.html')


@app.route('/requests/browse')
@login_required
def browse_requests():
    """Browse all open resource and knowledge requests."""
    uid  = session['user_id']
    tab  = request.args.get('tab', 'resource')  # 'resource' or 'knowledge'

    resource_reqs = query_db(
        """SELECT rr.*, u.name AS requester_name, u.trust_score
           FROM resource_requests rr
           JOIN users u ON rr.user_id = u.id
           WHERE rr.status = 'Open' AND rr.user_id != %s
           ORDER BY rr.created_at DESC""",
        (uid,)
    )
    knowledge_reqs = query_db(
        """SELECT kr.*, u.name AS requester_name, u.trust_score
           FROM knowledge_requests kr
           JOIN users u ON kr.user_id = u.id
           WHERE kr.status = 'Open' AND kr.user_id != %s
           ORDER BY kr.created_at DESC""",
        (uid,)
    )
    return render_template('requests/browse_requests.html',
                           resource_reqs=resource_reqs,
                           knowledge_reqs=knowledge_reqs,
                           tab=tab)


@app.route('/request-resource/<int:req_id>/accept', methods=['POST'])
@login_required
def accept_resource_request(req_id):
    """Accept an open resource request (provider side)."""
    uid = session['user_id']
    req = query_db(
        "SELECT * FROM resource_requests WHERE id=%s AND status='Open'",
        (req_id,), one=True
    )
    if not req:
        flash('Request is no longer available.', 'danger')
        return redirect(url_for('browse_requests'))
    if req['user_id'] == uid:
        flash('You cannot accept your own request.', 'danger')
        return redirect(url_for('browse_requests'))

    execute_db(
        "UPDATE resource_requests SET status='Accepted', accepted_by=%s WHERE id=%s",
        (uid, req_id)
    )
    provider = query_db("SELECT name FROM users WHERE id=%s", (uid,), one=True)
    create_notification(
        req['user_id'],
        'Your Request Was Accepted!',
        f'{provider["name"]} has agreed to provide "{req["title"]}". '
        f'Head to My Requests to complete the exchange.',
        'success',
        url_for('my_requests')
    )
    flash(f'You accepted the request for "{req["title"]}"!', 'success')
    return redirect(url_for('my_requests'))


@app.route('/request-resource/<int:req_id>/complete', methods=['POST'])
@login_required
def complete_resource_request(req_id):
    """
    Requester or provider marks the request complete.
    Creates a shadow resource + standard request + transaction so
    the existing QR pipeline handles credit transfer unchanged.
    """
    uid = session['user_id']
    req = query_db(
        "SELECT * FROM resource_requests WHERE id=%s AND status='Accepted'",
        (req_id,), one=True
    )
    if not req:
        flash('Request not found or not in accepted state.', 'danger')
        return redirect(url_for('my_requests'))
    # Only requester or provider may trigger completion
    if uid not in (req['user_id'], req['accepted_by']):
        flash('Not authorized.', 'danger')
        return redirect(url_for('my_requests'))

    requester_id = req['user_id']
    provider_id  = req['accepted_by']
    credits_amt  = float(req['credits_offered'])

    # Guard: requester must have credits
    creds = get_user_credits(requester_id)
    if not creds or float(creds['balance']) < credits_amt:
        flash('Requester no longer has sufficient credits.', 'danger')
        return redirect(url_for('my_requests'))

    # ── Create shadow resource (provider is the "owner") ──
    shadow_res_id = execute_db(
        """INSERT INTO resources
           (owner_id, title, category, description, location,
            credits_per_day, security_deposit, resource_type, status)
           VALUES (%s,%s,%s,%s,%s,%s,0,'Resource','Borrowed')""",
        (provider_id, req['title'], req['category'],
         req['description'] or '', req['location'] or '',
         credits_amt / max(req['duration_days'], 1)),
        get_id=True
    )

    # ── Create standard borrow request row ──
    std_req_id = execute_db(
        """INSERT INTO requests
           (resource_id, borrower_id, lender_id, borrow_days, total_credits, status)
           VALUES (%s,%s,%s,%s,%s,'Approved')""",
        (shadow_res_id, requester_id, provider_id,
         req['duration_days'], credits_amt),
        get_id=True
    )

    # ── Lock credits from requester (deposit = 0 for simplicity) ──
    execute_db(
        "UPDATE credits SET balance=balance-%s WHERE user_id=%s",
        (credits_amt, requester_id)
    )

    # ── Create transaction ──
    tx_id    = str(uuid.uuid4()).replace('-', '').upper()
    due_date = (datetime.now() + timedelta(days=req['duration_days'])).date()
    init_hash = compute_qr_hash(tx_id, requester_id, 'collection', str(uuid.uuid4()))

    tx_db_id = execute_db(
        """INSERT INTO transactions
           (transaction_id, request_id, borrower_id, lender_id, resource_id,
            credits_transferred, security_deposit, due_date, qr_hash, status)
           VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,'Initiated')""",
        (tx_id, std_req_id, requester_id, provider_id,
         shadow_res_id, credits_amt, due_date, init_hash),
        get_id=True
    )

    # ── Link transaction back to resource_request ──
    execute_db(
        "UPDATE resource_requests SET status='Completed', transaction_id=%s WHERE id=%s",
        (tx_db_id, req_id)
    )

    create_notification(
        requester_id, 'Exchange Initiated',
        f'Your request for "{req["title"]}" is ready. Show the provider your QR code to complete.',
        'success', url_for('view_transaction', tx_db_id=tx_db_id)
    )
    create_notification(
        provider_id, 'Exchange Initiated',
        f'Ready to hand over "{req["title"]}". Ask the requester to show their QR code.',
        'info', url_for('scan_qr')
    )

    flash('Exchange initiated! Show your QR code to the provider.', 'success')
    return redirect(url_for('view_transaction', tx_db_id=tx_db_id))


# ─────────────────────────────────────────────
# REQUEST SYSTEM — KNOWLEDGE REQUESTS
# ─────────────────────────────────────────────

@app.route('/request-knowledge', methods=['GET', 'POST'])
@login_required
def post_knowledge_request():
    """Let a user post a public 'I need help with X' knowledge request."""
    if request.method == 'POST':
        uid     = session['user_id']
        subject = request.form.get('subject', '').strip()
        topic   = request.form.get('topic', '').strip()
        desc    = request.form.get('description', '').strip()
        try:
            credits_offered = float(request.form.get('credits_offered', 0) or 0)
        except ValueError:
            credits_offered = 0.0

        if not subject or not topic:
            flash('Subject and topic are required.', 'danger')
            return render_template('requests/request_knowledge.html')

        creds = get_user_credits(uid)
        if not creds or float(creds['balance']) < credits_offered:
            flash('Insufficient credits.', 'danger')
            return render_template('requests/request_knowledge.html')

        execute_db(
            """INSERT INTO knowledge_requests
               (user_id, subject, topic, description, credits_offered)
               VALUES (%s,%s,%s,%s,%s)""",
            (uid, subject, topic, desc, credits_offered)
        )

        requester = query_db("SELECT name FROM users WHERE id=%s", (uid,), one=True)
        all_users = query_db(
            "SELECT id FROM users WHERE id != %s AND is_active=TRUE AND role != 'Admin'",
            (uid,)
        )
        for u in (all_users or []):
            create_notification(
                u['id'],
                'New Knowledge Request',
                f'{requester["name"]} needs help with "{topic}" ({subject}). Can you assist?',
                'warning',
                url_for('browse_requests', tab='knowledge')
            )

        flash(f'Knowledge request for "{topic}" posted!', 'success')
        return redirect(url_for('browse_requests', tab='knowledge'))

    return render_template('requests/request_knowledge.html')


@app.route('/request-knowledge/<int:req_id>/accept', methods=['POST'])
@login_required
def accept_knowledge_request(req_id):
    """Accept an open knowledge request."""
    uid = session['user_id']
    req = query_db(
        "SELECT * FROM knowledge_requests WHERE id=%s AND status='Open'",
        (req_id,), one=True
    )
    if not req:
        flash('Knowledge request is no longer available.', 'danger')
        return redirect(url_for('browse_requests', tab='knowledge'))
    if req['user_id'] == uid:
        flash('You cannot accept your own request.', 'danger')
        return redirect(url_for('browse_requests', tab='knowledge'))

    execute_db(
        "UPDATE knowledge_requests SET status='Accepted', accepted_by=%s WHERE id=%s",
        (uid, req_id)
    )
    helper = query_db("SELECT name FROM users WHERE id=%s", (uid,), one=True)
    create_notification(
        req['user_id'],
        'Knowledge Request Accepted!',
        f'{helper["name"]} will help you with "{req["topic"]}". '
        f'Go to My Requests to complete the session.',
        'success',
        url_for('my_requests', tab='knowledge')
    )
    flash(f'You accepted the knowledge request for "{req["topic"]}"!', 'success')
    return redirect(url_for('my_requests', tab='knowledge'))


@app.route('/request-knowledge/<int:req_id>/complete', methods=['POST'])
@login_required
def complete_knowledge_request(req_id):
    """Complete a knowledge request — deduct credits from requester, add to helper."""
    uid = session['user_id']
    req = query_db(
        "SELECT * FROM knowledge_requests WHERE id=%s AND status='Accepted'",
        (req_id,), one=True
    )
    if not req:
        flash('Knowledge request not found or not accepted yet.', 'danger')
        return redirect(url_for('my_requests', tab='knowledge'))
    if uid not in (req['user_id'], req['accepted_by']):
        flash('Not authorized.', 'danger')
        return redirect(url_for('my_requests', tab='knowledge'))

    requester_id = req['user_id']
    helper_id    = req['accepted_by']
    credits_amt  = float(req['credits_offered'])

    creds = get_user_credits(requester_id)
    if not creds or float(creds['balance']) < credits_amt:
        flash('Requester no longer has sufficient credits.', 'danger')
        return redirect(url_for('my_requests', tab='knowledge'))

    # ── Shadow knowledge resource (helper is "owner") ──
    shadow_res_id = execute_db(
        """INSERT INTO resources
           (owner_id, title, category, description,
            credits_per_day, security_deposit, resource_type, status)
           VALUES (%s,%s,'Academic',%s,%s,0,'Knowledge','Borrowed')""",
        (helper_id,
         f'{req["subject"]}: {req["topic"]}',
         req['description'] or '',
         credits_amt),
        get_id=True
    )

    std_req_id = execute_db(
        """INSERT INTO requests
           (resource_id, borrower_id, lender_id, borrow_days, total_credits, status)
           VALUES (%s,%s,%s,1,%s,'Approved')""",
        (shadow_res_id, requester_id, helper_id, credits_amt),
        get_id=True
    )

    # Deduct from requester immediately (knowledge = single session, no QR needed)
    execute_db(
        "UPDATE credits SET balance=balance-%s, total_spent=total_spent+%s WHERE user_id=%s",
        (credits_amt, credits_amt, requester_id)
    )
    execute_db(
        "UPDATE credits SET balance=balance+%s, total_earned=total_earned+%s WHERE user_id=%s",
        (credits_amt, credits_amt, helper_id)
    )

    tx_id = str(uuid.uuid4()).replace('-', '').upper()
    due_date = datetime.now().date()
    tx_db_id = execute_db(
        """INSERT INTO transactions
           (transaction_id, request_id, borrower_id, lender_id, resource_id,
            credits_transferred, security_deposit, due_date,
            qr_hash, status, collected_at, returned_at)
           VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,'Returned',NOW(),NOW())""",
        (tx_id, std_req_id, requester_id, helper_id,
         shadow_res_id, credits_amt, due_date,
         compute_qr_hash(tx_id, requester_id, 'knowledge', str(uuid.uuid4()))),
        get_id=True
    )

    execute_db(
        "UPDATE knowledge_requests SET status='Completed', transaction_id=%s WHERE id=%s",
        (tx_db_id, req_id)
    )

    award_badges(helper_id)
    award_badges(requester_id)
    run_fraud_checks(helper_id)

    create_notification(
        requester_id, 'Knowledge Session Completed',
        f'{credits_amt} credits sent to your helper for "{req["topic"]}". '
        'Rate the session from your transaction history.',
        'success', url_for('transaction_history')
    )
    create_notification(
        helper_id, 'Credits Received!',
        f'{credits_amt} credits added for helping with "{req["topic"]}".',
        'success', url_for('transaction_history')
    )

    flash(f'Session completed! {credits_amt} credits transferred.', 'success')
    return redirect(url_for('transaction_history'))


# ─────────────────────────────────────────────
# REQUEST SYSTEM — MY REQUESTS VIEW
# ─────────────────────────────────────────────

@app.route('/requests/my')
@login_required
def my_requests():
    """Show the current user's posted requests and ones they've accepted."""
    uid = session['user_id']
    tab = request.args.get('tab', 'resource')

    # Resource requests —  posted by me
    my_resource_posted = query_db(
        """SELECT rr.*, u.name AS accepted_by_name
           FROM resource_requests rr
           LEFT JOIN users u ON rr.accepted_by = u.id
           WHERE rr.user_id = %s
           ORDER BY rr.created_at DESC""",
        (uid,)
    )
    # Resource requests — accepted by me (I'm the provider)
    my_resource_accepted = query_db(
        """SELECT rr.*, u.name AS requester_name
           FROM resource_requests rr
           JOIN users u ON rr.user_id = u.id
           WHERE rr.accepted_by = %s AND rr.status IN ('Accepted','Completed')
           ORDER BY rr.created_at DESC""",
        (uid,)
    )
    # Knowledge requests — posted by me
    my_knowledge_posted = query_db(
        """SELECT kr.*, u.name AS accepted_by_name
           FROM knowledge_requests kr
           LEFT JOIN users u ON kr.accepted_by = u.id
           WHERE kr.user_id = %s
           ORDER BY kr.created_at DESC""",
        (uid,)
    )
    # Knowledge requests — accepted by me (I'm the helper)
    my_knowledge_accepted = query_db(
        """SELECT kr.*, u.name AS requester_name
           FROM knowledge_requests kr
           JOIN users u ON kr.user_id = u.id
           WHERE kr.accepted_by = %s AND kr.status IN ('Accepted','Completed')
           ORDER BY kr.created_at DESC""",
        (uid,)
    )
    return render_template('requests/my_requests.html',
                           my_resource_posted=my_resource_posted,
                           my_resource_accepted=my_resource_accepted,
                           my_knowledge_posted=my_knowledge_posted,
                           my_knowledge_accepted=my_knowledge_accepted,
                           tab=tab)


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = {
        'total_users': query_db("SELECT COUNT(*) AS c FROM users WHERE role != 'Admin'", one=True)['c'],
        'active_transactions': query_db("SELECT COUNT(*) AS c FROM transactions WHERE status='Active'", one=True)['c'],
        'total_resources': query_db("SELECT COUNT(*) AS c FROM resources", one=True)['c'],
        'flagged': query_db("SELECT COUNT(*) AS c FROM fraud_flags WHERE reviewed=FALSE", one=True)['c'],
        'frozen': query_db("SELECT COUNT(*) AS c FROM users WHERE is_frozen=TRUE", one=True)['c'],
        'total_credits_in_system': query_db("SELECT SUM(balance) AS s FROM credits", one=True)['s'] or 0,
    }
    recent_txs = query_db(
        """SELECT t.*, r.title, u1.name AS borrower_name, u2.name AS lender_name
           FROM transactions t
           JOIN resources r ON t.resource_id=r.id
           JOIN users u1 ON t.borrower_id=u1.id
           JOIN users u2 ON t.lender_id=u2.id
           ORDER BY t.created_at DESC LIMIT 10"""
    )
    flags = query_db(
        """SELECT ff.*, u.name AS user_name FROM fraud_flags ff
           JOIN users u ON ff.user_id=u.id WHERE ff.reviewed=FALSE ORDER BY ff.created_at DESC LIMIT 10"""
    )
    return render_template('admin/admin_dashboard.html', stats=stats, recent_txs=recent_txs, flags=flags)

@app.route('/admin/users')
@admin_required
def admin_users():
    users = query_db(
        """SELECT u.*, c.balance, c.total_earned FROM users u
           LEFT JOIN credits c ON u.id=c.user_id ORDER BY u.created_at DESC"""
    )
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/<int:uid>/freeze', methods=['POST'])
@admin_required
def freeze_user(uid):
    action = request.form.get('action', 'freeze')
    frozen = action == 'freeze'
    execute_db("UPDATE users SET is_frozen=%s WHERE id=%s", (frozen, uid))
    flash(f'User {"frozen" if frozen else "unfrozen"} successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    dept_stats = query_db(
        """SELECT u.department, COUNT(*) AS user_count, AVG(c.balance) AS avg_credits
           FROM users u JOIN credits c ON u.id=c.user_id
           WHERE u.role != 'Admin' GROUP BY u.department ORDER BY user_count DESC"""
    )
    category_stats = query_db(
        "SELECT category, COUNT(*) AS cnt FROM resources GROUP BY category ORDER BY cnt DESC"
    )
    monthly_txs = query_db(
        """SELECT DATE_FORMAT(created_at, '%Y-%m') AS month, COUNT(*) AS cnt,
                  SUM(credits_transferred) AS total_credits
           FROM transactions GROUP BY month ORDER BY month DESC LIMIT 12"""
    )
    top_users = query_db(
        """SELECT u.name, u.department, c.total_earned, u.trust_score,
                  (SELECT COUNT(*) FROM transactions t WHERE (t.lender_id=u.id OR t.borrower_id=u.id) AND t.status='Returned') AS completed
           FROM users u JOIN credits c ON u.id=c.user_id
           WHERE u.role != 'Admin' ORDER BY c.total_earned DESC LIMIT 10"""
    )
    return render_template('admin/analytics.html',
                           dept_stats=dept_stats, category_stats=category_stats,
                           monthly_txs=monthly_txs, top_users=top_users)

@app.route('/admin/flags/<int:flag_id>/review', methods=['POST'])
@admin_required
def review_flag(flag_id):
    execute_db("UPDATE fraud_flags SET reviewed=TRUE WHERE id=%s", (flag_id,))
    flash('Flag marked as reviewed.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/api/leaderboard_data')
@login_required
def api_leaderboard_data():
    data = query_db(
        """SELECT u.name, c.balance, c.total_earned
           FROM users u JOIN credits c ON u.id=c.user_id
           WHERE u.role != 'Admin' AND u.is_active=TRUE
           ORDER BY c.balance DESC LIMIT 10"""
    )
    return jsonify({'data': data})

# ─────────────────────────────────────────────
# PROFILE
# ─────────────────────────────────────────────
@app.route('/profile')
@login_required
def profile():
    uid = session['user_id']
    user = get_current_user()
    credits = get_user_credits(uid)
    my_resources = query_db("SELECT * FROM resources WHERE owner_id=%s ORDER BY created_at DESC", (uid,))
    my_ratings = query_db(
        """SELECT r.*, u.name AS rater_name FROM ratings r
           JOIN users u ON r.rater_id=u.id WHERE r.ratee_id=%s ORDER BY r.created_at DESC""",
        (uid,)
    )
    badges = query_db(
        """SELECT b.*, ub.earned_at FROM badges b JOIN user_badges ub ON b.id=ub.badge_id
           WHERE ub.user_id=%s ORDER BY ub.earned_at DESC""",
        (uid,)
    )
    tx_count = query_db(
        "SELECT COUNT(*) AS c FROM transactions WHERE (borrower_id=%s OR lender_id=%s) AND status='Returned'",
        (uid, uid), one=True
    )
    return render_template('profile/profile.html', user=user, credits=credits,
                           my_resources=my_resources, my_ratings=my_ratings,
                           badges=badges, tx_count=tx_count['c'] if tx_count else 0)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    uid = session['user_id']
    user = get_current_user()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        dept = request.form.get('department', '').strip()
        if name:
            execute_db("UPDATE users SET name=%s, department=%s WHERE id=%s", (name, dept, uid))
            session['name'] = name
            flash('Profile updated!', 'success')
        return redirect(url_for('profile'))
    return render_template('profile/edit_profile.html', user=user)

# ─────────────────────────────────────────────
# CONTEXT PROCESSORS
# ─────────────────────────────────────────────
@app.context_processor
def inject_now():
    return {'now': datetime.now}

# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=5000)
