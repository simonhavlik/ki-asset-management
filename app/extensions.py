from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
import os

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()

# Flask-Caching for Neon.tech optimization
# Uses in-memory cache on Render (avoiding Neon DB calls)
cache = Cache(config={
    'CACHE_TYPE': os.environ.get('CACHE_TYPE', 'SimpleCache'),
    'CACHE_DEFAULT_TIMEOUT': int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300)),  # 5 min default
    'CACHE_THRESHOLD': int(os.environ.get('CACHE_THRESHOLD', 1000)),  # Max 1000 items in memory
    # File cache as secondary/fallback
    'CACHE_DIR': os.environ.get('CACHE_DIR', None),  # Set to enable file cache
})

# Configure login manager
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from .models import User
    return User.query.get(int(user_id))