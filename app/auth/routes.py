from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from .forms import LoginForm, RegistrationForm, ForgotPasswordForm, ResetPasswordForm, TokenForm
from .utils import create_password_reset_token, validate_token
from ..email_service import send_password_setup_email, send_password_reset_email
from ..extensions import db, login_manager
from ..models import User, ActivityLog
from ..security import rate_limit, validate_email, validate_password
from datetime import datetime
from ..utils.email_normalization import normalize_email

auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(limit=5, window=900)  # 5 attempts per 15 minutes
def login():
    if current_user.is_authenticated:
        return redirect(url_for('analyst.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        normalized_email = normalize_email(form.email.data)
        # Validate email format
        is_valid, error = validate_email(normalized_email)
        if not is_valid:
            flash('Invalid email format.', 'danger')
            return redirect(url_for('auth.login'))
        user = User.query.filter_by(email=normalized_email).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'danger')
            log_activity(user, 'login_failed', f'Failed login attempt for {form.email.data}')
            return redirect(url_for('auth.login'))
        if not user.is_active:
            flash('Your account is inactive. Please contact an administrator.', 'warning')
            return redirect(url_for('auth.login'))
        login_user(user, remember=form.remember.data)
        user.last_login = datetime.utcnow()
        db.session.commit()
        log_activity(user, 'login_success')
        flash('Logged in successfully.', 'success')
        next_page = request.args.get('next')
        # Validate redirect URL to prevent open redirect attacks
        if not next_page or not next_page.startswith('/') or next_page.startswith('//'):
            next_page = url_for('analyst.dashboard')
        return redirect(next_page)
    return render_template('login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit(limit=3, window=3600)  # 3 registrations per hour per IP
def register():
    if current_user.is_authenticated:
        return redirect(url_for('analyst.dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        # Validate email format
        is_valid, error = validate_email(form.email.data)
        if not is_valid:
            flash(error, 'danger')
            return redirect(url_for('auth.register'))
        # Normalize email (strip diacritics)
        normalized_email = normalize_email(form.email.data)
        # Check if user already exists using normalized email
        existing_user = User.query.filter_by(email=normalized_email).first()
        if existing_user:
            if existing_user.is_active:
                flash('An account with this email already exists. Please log in.', 'info')
                return redirect(url_for('auth.login'))
            else:
                # Inactive account, resend password‑setup email
                token = create_password_reset_token(existing_user, token_type='registration')
                send_password_setup_email(existing_user, token)
                flash('An activation code has been sent to your email.', 'success')
                log_activity(existing_user, 'registration_resent')
                return redirect(url_for('auth.login'))
        # Create new inactive user with normalized email
        is_admin = normalized_email == normalize_email(current_app.config['ADMIN_EMAIL'])
        new_user = User(
            email=normalized_email,
            full_name=form.full_name.data,
            is_active=False,
            email_verified=False,
            is_admin=is_admin
        )
        new_user.set_password(form.password.data)
        db.session.add(new_user)
        db.session.commit()
        token = create_password_reset_token(new_user, token_type='registration')
        send_password_setup_email(new_user, token)
        flash('An activation code has been sent to your email. Please check your inbox.', 'success')
        log_activity(new_user, 'registration_requested')
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@rate_limit(limit=3, window=3600)  # 3 requests per hour
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('analyst.dashboard'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        normalized_email = normalize_email(form.email.data)
        user = User.query.filter_by(email=normalized_email).first()
        if user and user.is_active:
            token = create_password_reset_token(user, token_type='reset')
            send_password_reset_email(user, token)
            flash('If an account exists with that email, you will receive a password‑reset link shortly.', 'info')
            log_activity(user, 'password_reset_requested')
        else:
            # Do not reveal whether the email exists
            flash('If an account exists with that email, you will receive a password‑reset link shortly.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html', form=form)

@auth_bp.route('/activate', methods=['GET', 'POST'])
def activate():
    if current_user.is_authenticated:
        return redirect(url_for('analyst.dashboard'))
    # If token provided as query parameter, try to activate directly
    token_from_url = request.args.get('token')
    if token_from_url:
        user = validate_token(token_from_url, token_type='registration')
        if user:
            user.is_active = True
            user.email_verified = True
            db.session.commit()
            login_user(user)
            log_activity(user, 'account_activated')
            flash('Your account has been activated. You are now logged in.', 'success')
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('analyst.dashboard'))
        else:
            flash('Invalid or expired activation code.', 'danger')
            # Fall through to show form with token pre‑filled?
    form = TokenForm()
    # Pre‑fill token from URL if present
    if token_from_url and not form.token.data:
        form.token.data = token_from_url
    if form.validate_on_submit():
        token = form.token.data.strip()
        user = validate_token(token, token_type='registration')
        if not user:
            flash('Invalid or expired activation code.', 'danger')
            return redirect(url_for('auth.activate'))
        # Activate the user and log them in
        user.is_active = True
        user.email_verified = True
        db.session.commit()
        login_user(user)
        log_activity(user, 'account_activated')
        flash('Your account has been activated. You are now logged in.', 'success')
        # Redirect admin to admin dashboard, regular users to analyst dashboard
        if user.is_admin:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('analyst.dashboard'))
    return render_template('activate.html', form=form)

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('analyst.dashboard'))
    
    # Determine token type without consuming it yet
    token_type = None
    user = validate_token(token, token_type='registration', consume=False)
    if user:
        token_type = 'registration'
    else:
        user = validate_token(token, token_type='reset', consume=False)
        if user:
            token_type = 'reset'
    
    if not user:
        flash('Invalid or expired token.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Now consume the token
        consumed_user = validate_token(token, token_type=token_type, consume=True)
        if not consumed_user:
            flash('Token has already been used or expired. Please request a new password reset.', 'danger')
            return redirect(url_for('auth.forgot_password'))
        # Ensure the user matches
        if consumed_user.id != user.id:
            flash('Token validation error.', 'danger')
            return redirect(url_for('auth.forgot_password'))
        
        user.set_password(form.password.data)
        user.is_active = True
        user.email_verified = True
        db.session.commit()
        login_user(user)
        log_activity(user, 'password_reset_success')
        flash('Your password has been updated. You are now logged in.', 'success')
        return redirect(url_for('analyst.dashboard'))
    return render_template('reset_password.html', form=form, token=token)

@auth_bp.route('/logout')
@login_required
def logout():
    log_activity(current_user, 'logout')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))

def log_activity(user, action, details=None):
    """Helper to log an activity."""
    log = ActivityLog(
        user_id=user.id if user else None,
        action=action,
        details=details,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()

@auth_bp.route('/toggle-user-view', methods=['POST'])
@login_required
def toggle_user_view():
    """
    Toggle admin view between admin and normal user perspective.
    Allows admin to test how the site looks to regular users.
    """
    from flask import jsonify, session
    
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Admin only'}), 403
    
    data = request.get_json()
    view_as_user = data.get('view_as_user', False)
    
    session['admin_view_as_user'] = view_as_user
    
    return jsonify({'success': True, 'view_as_user': view_as_user})
