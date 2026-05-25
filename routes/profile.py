import base64
import re
from flask import Blueprint, request, jsonify, g
from datetime import datetime
from extensions.mongodb import get_db
from middlewares.auth import login_required
from models.user import User

bp = Blueprint('profile', __name__, url_prefix='/api/profile')

# Max avatar size: 2 MB (base64 overhead ~33%, so raw limit ~1.5 MB)
MAX_AVATAR_BYTES = 2 * 1024 * 1024
ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}

TIMEZONES = {
    'UTC', 'Europe/Riga', 'Europe/Moscow', 'Europe/London',
    'Europe/Berlin', 'Europe/Paris', 'America/New_York',
    'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Kolkata', 'Australia/Sydney',
}


@bp.route('', methods=['GET'])
@login_required
def get_profile():
    """Получить профиль текущего пользователя"""
    return jsonify({"user": User.to_dict(g.current_user)})


@bp.route('', methods=['PATCH'])
@login_required
def update_profile():
    """
    Обновить профиль.
    Разрешённые поля: display_name, username, email, timezone
    """
    db = get_db()
    data = request.json or {}
    user_id = str(g.current_user['_id'])

    allowed = ['display_name', 'username', 'email', 'timezone']
    update = {k: v for k, v in data.items() if k in allowed}

    if not update:
        return jsonify({"error": "No valid fields provided"}), 400

    # Валидация
    if 'email' in update:
        email = update['email'].strip().lower()
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return jsonify({"error": "Invalid email format"}), 400
        existing = db.users.find_one({"email": email, "_id": {"$ne": g.current_user['_id']}})
        if existing:
            return jsonify({"error": "Email already in use"}), 409
        update['email'] = email

    if 'username' in update:
        username = update['username'].strip()
        if len(username) < 3:
            return jsonify({"error": "Username must be at least 3 characters"}), 400
        if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
            return jsonify({"error": "Username can only contain letters, numbers, _ . -"}), 400
        existing = db.users.find_one({"username": username, "_id": {"$ne": g.current_user['_id']}})
        if existing:
            return jsonify({"error": "Username already taken"}), 409
        update['username'] = username

    if 'display_name' in update:
        display_name = update['display_name'].strip()
        if len(display_name) < 1 or len(display_name) > 64:
            return jsonify({"error": "Display name must be 1–64 characters"}), 400
        update['display_name'] = display_name

    if 'timezone' in update:
        if update['timezone'] not in TIMEZONES:
            return jsonify({"error": f"Unknown timezone: {update['timezone']}"}), 400

    update['updated_at'] = datetime.utcnow()

    db.users.update_one({"_id": g.current_user['_id']}, {"$set": update})

    # Возвращаем обновлённого пользователя
    updated = User.find_by_id(user_id)
    return jsonify({"user": User.to_dict(updated)})


@bp.route('/avatar', methods=['PUT'])
@login_required
def update_avatar():
    """
    Загрузить аватар в base64.
    Тело: { "avatar": "data:image/png;base64,..." } или { "avatar": null } — удалить аватар
    """
    db = get_db()
    data = request.json or {}
    user_id = str(g.current_user['_id'])

    avatar = data.get('avatar')

    if avatar is None:
        # Удалить аватар
        db.users.update_one(
            {"_id": g.current_user['_id']},
            {"$set": {"avatar_base64": None, "updated_at": datetime.utcnow()}}
        )
        return jsonify({"message": "Avatar removed"})

    # Валидируем data URI
    if not isinstance(avatar, str):
        return jsonify({"error": "Avatar must be a base64 data URI string or null"}), 400

    # Ожидаем формат: data:<mime>;base64,<data>
    match = re.match(r'^data:([^;]+);base64,(.+)$', avatar, re.DOTALL)
    if not match:
        return jsonify({"error": "Invalid data URI format. Expected: data:<mime>;base64,<data>"}), 400

    mime_type = match.group(1).lower()
    b64_data = match.group(2)

    if mime_type not in ALLOWED_MIME:
        return jsonify({"error": f"Unsupported image type: {mime_type}. Allowed: jpeg, png, webp, gif"}), 400

    # Декодируем и проверяем размер
    try:
        raw_bytes = base64.b64decode(b64_data)
    except Exception:
        return jsonify({"error": "Invalid base64 data"}), 400

    if len(raw_bytes) > MAX_AVATAR_BYTES:
        return jsonify({"error": f"Avatar too large. Max size: 2 MB"}), 413

    db.users.update_one(
        {"_id": g.current_user['_id']},
        {"$set": {"avatar_base64": avatar, "updated_at": datetime.utcnow()}}
    )

    updated = User.find_by_id(user_id)
    return jsonify({
        "message": "Avatar updated",
        "user": User.to_dict(updated)
    })


@bp.route('/avatar', methods=['DELETE'])
@login_required
def delete_avatar():
    """Удалить аватар"""
    db = get_db()
    db.users.update_one(
        {"_id": g.current_user['_id']},
        {"$set": {"avatar_base64": None, "updated_at": datetime.utcnow()}}
    )
    return jsonify({"message": "Avatar removed"})