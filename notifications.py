from database import get_db_connection
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_notification(user_id, message, type='info'):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO notifications (user_id, message, type) VALUES (%s, %s, %s)",
                (user_id, message, type)
            )
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Error creating notification: {e}")
        return False
    finally:
        conn.close()

def get_unread_notifications(user_id):
    conn = get_db_connection()
    if not conn: return []
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM notifications WHERE user_id = %s AND is_read = FALSE ORDER BY created_at DESC",
                (user_id,)
            )
            return cursor.fetchall()
    finally:
        conn.close()

def mark_notification_read(notification_id, user_id):
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cursor:
            # Ensure user owns the notification
            cursor.execute(
                "UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s",
                (notification_id, user_id)
            )
            conn.commit()
            return True
    finally:
        conn.close()
