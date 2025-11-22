from flask_login import UserMixin
from database import get_db_connection

class User(UserMixin):
    def __init__(self, id, username, password, email=None, beta_active=False):
        self.id = id
        self.username = username
        self.password = password
        self.email = email
        self.beta_active = beta_active

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        if not conn:
            return None
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            if user_data:
                return User(
                    id=user_data['id'],
                    username=user_data['username'],
                    password=user_data['password'],
                    email=user_data.get('email'),
                    beta_active=bool(user_data.get('beta_active'))
                )
        return None

def init_user_db():
    conn = get_db_connection()
    if not conn:
        return
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                email VARCHAR(120) UNIQUE,
                beta_active BOOLEAN DEFAULT FALSE
            )
        """)
        # Ensure columns exist for existing installations (minimal migration check)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(120) UNIQUE")
        except: pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN beta_active BOOLEAN DEFAULT FALSE")
        except: pass

    conn.commit()
    conn.close()