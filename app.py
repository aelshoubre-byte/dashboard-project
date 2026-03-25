import os
from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from database import get_db, init_db
from mqtt_manager import mqtt_manager

load_dotenv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"]           = os.getenv("JWT_SECRET_KEY", "change_this_secret")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_DAYS", 7)))
CORS(app, origins=os.getenv("CORS_ORIGIN", "*"), supports_credentials=True)
jwt = JWTManager(app)


def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

def ok(data=None, message="success", status=200, **kwargs):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    body.update(kwargs)
    return jsonify(body), status

def err(message, status=400):
    return jsonify({"success": False, "message": message}), status

def get_expiry_status(exp_date):
    today = date.today()
    try:
        exp = datetime.strptime(exp_date, "%Y-%m-%d").date()
        days = (exp - today).days
        if days < 0:  return "expired"
        if days <= 3: return "soon"
        return "fresh"
    except:
        return "unknown"

def enrich_product(p):
    p = dict(p)
    try:
        days = (datetime.strptime(p["exp_date"], "%Y-%m-%d").date() - date.today()).days
        p["days_until_expiry"] = days
        p["expiry_status"]     = get_expiry_status(p["exp_date"])
    except:
        p["days_until_expiry"] = None
        p["expiry_status"]     = "unknown"
    return p


def save_sensor_to_db(temperature, humidity, connected, mode):
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE sensor_state SET temperature=?, humidity=?, connected=?, mode=?, updated_at=datetime('now') WHERE id=1",
            (temperature, humidity, 1 if connected else 0, mode)
        )
        db.execute(
            "INSERT INTO sensor_readings (temperature, humidity) VALUES (?,?)",
            (temperature, humidity)
        )
        db.commit()
        db.close()

mqtt_manager.on_data = save_sensor_to_db

with app.app_context():
    init_db()

mqtt_manager.start()


@app.get("/")
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('frontend', filename)

@app.get("/api/health")
def health():
    return ok(message="Server is running", mqtt=mqtt_manager.mode)


# ── AUTH ──────────────────────────────────────────────────

@app.post("/api/auth/register")
def register():
    data       = request.get_json() or {}
    first_name = data.get("first_name", "").strip()
    last_name  = data.get("last_name",  "").strip()
    email      = data.get("email",      "").strip().lower()
    password   = data.get("password",   "")

    if not all([first_name, last_name, email, password]):
        return err("All fields are required")
    if len(password) < 6:
        return err("Password must be at least 6 characters")

    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        db.close()
        return err("Email already registered", 409)

    hashed = generate_password_hash(password)
    cur    = db.execute(
        "INSERT INTO users (first_name, last_name, email, password) VALUES (?,?,?,?)",
        (first_name, last_name, email, hashed)
    )
    db.commit()
    user = row_to_dict(
        db.execute("SELECT id,first_name,last_name,email,avatar_url,role,created_at FROM users WHERE id=?",
                   (cur.lastrowid,)).fetchone()
    )
    db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (cur.lastrowid,))
    db.commit()
    db.close()
    token = create_access_token(identity=str(cur.lastrowid))
    return ok(message="Account created successfully", token=token, user=user, status=201)


@app.post("/api/auth/login")
def login():
    data     = request.get_json() or {}
    email    = data.get("email",    "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return err("Email and password are required")

    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    db.close()

    if not user or not check_password_hash(user["password"], password):
        return err("Invalid email or password", 401)

    safe  = {k: user[k] for k in ("id","first_name","last_name","email","avatar_url","role","created_at")}
    token = create_access_token(identity=str(user["id"]))
    return ok(message="Logged in successfully", token=token, user=safe)


@app.get("/api/auth/me")
@jwt_required()
def me():
    uid  = int(get_jwt_identity())
    db   = get_db()
    user = row_to_dict(
        db.execute("SELECT id,first_name,last_name,email,avatar_url,role,created_at FROM users WHERE id=?", (uid,)).fetchone()
    )
    db.close()
    if not user:
        return err("User not found", 404)
    return ok(user)


@app.put("/api/auth/me")
@jwt_required()
def update_profile():
    uid  = int(get_jwt_identity())
    data = request.get_json() or {}
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        db.close()
        return err("User not found", 404)
    db.execute(
        "UPDATE users SET first_name=?, last_name=?, avatar_url=? WHERE id=?",
        (
            data.get("first_name", user["first_name"]),
            data.get("last_name",  user["last_name"]),
            data.get("avatar_url", user["avatar_url"]),
            uid
        )
    )
    db.commit()
    updated = row_to_dict(
        db.execute("SELECT id,first_name,last_name,email,avatar_url,role,created_at FROM users WHERE id=?", (uid,)).fetchone()
    )
    db.close()
    return ok(updated, message="Profile updated successfully")


@app.post("/api/auth/change-password")
@jwt_required()
def change_password():
    uid  = int(get_jwt_identity())
    data = request.get_json() or {}
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")

    if not old_password or not new_password:
        return err("Both old and new passwords are required")
    if len(new_password) < 6:
        return err("New password must be at least 6 characters")

    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user or not check_password_hash(user["password"], old_password):
        db.close()
        return err("Invalid old password", 400)

    db.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new_password), uid))
    db.commit()
    db.close()
    return ok(message="Password changed successfully")


# ── PRODUCTS ──────────────────────────────────────────────

@app.get("/api/products")
@jwt_required()
def get_products():
    uid      = int(get_jwt_identity())
    category = request.args.get("category")
    status   = request.args.get("status")
    search   = request.args.get("search", "").strip()
    db       = get_db()

    query  = "SELECT * FROM products WHERE user_id=?"
    params = [uid]

    if category:
        query += " AND category=?"
        params.append(category)
    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY exp_date ASC"
    rows = db.execute(query, params).fetchall()
    db.close()

    products = [enrich_product(r) for r in rows]

    if status:
        products = [p for p in products if p["expiry_status"] == status]

    return ok(products, total=len(products))


@app.post("/api/products")
@jwt_required()
def add_product():
    uid  = int(get_jwt_identity())
    data = request.get_json() or {}

    name     = data.get("name",     "").strip()
    category = data.get("category", "").strip()
    qty      = float(data.get("qty", 1))
    unit     = data.get("unit",     "pcs").strip()
    exp_date = data.get("exp_date", "").strip()
    barcode  = data.get("barcode",  None)
    notes    = data.get("notes",    None)
    image_url= data.get("image_url",None)

    if not name or not category or not exp_date:
        return err("Name, category and expiry date are required")
    if category not in ["vegetables","meat","dairy","frozen","canned","others"]:
        return err("Invalid category")

    db  = get_db()
    cur = db.execute(
        "INSERT INTO products (user_id,name,category,qty,unit,exp_date,barcode,notes,image_url) VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, name, category, qty, unit, exp_date, barcode, notes, image_url)
    )
    db.commit()
    product = enrich_product(db.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone())
    db.close()
    return ok(product, message="Product added successfully", status=201)


@app.get("/api/products/stats")
@jwt_required()
def products_stats():
    uid   = int(get_jwt_identity())
    today = date.today().isoformat()
    db    = get_db()
    products      = rows_to_list(db.execute("SELECT * FROM products WHERE user_id=?", (uid,)).fetchall())
    removed_total = db.execute("SELECT COUNT(*) as c FROM removed_products WHERE user_id=?", (uid,)).fetchone()["c"]
    db.close()

    expired = sum(1 for p in products if p["exp_date"] < today)
    soon    = sum(1 for p in products if 0 <= (datetime.strptime(p["exp_date"], "%Y-%m-%d").date() - date.today()).days <= 3)
    return ok({
        "total_products":      len(products),
        "expired_count":       expired,
        "expiring_soon_count": soon,
        "fresh_count":         max(len(products) - expired - soon, 0),
        "removed_total":       removed_total,
    })


@app.get("/api/products/<int:pid>")
@jwt_required()
def get_product(pid):
    uid = int(get_jwt_identity())
    db  = get_db()
    row = db.execute("SELECT * FROM products WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    db.close()
    if not row:
        return err("Product not found", 404)
    return ok(enrich_product(row))


@app.put("/api/products/<int:pid>")
@jwt_required()
def update_product(pid):
    uid  = int(get_jwt_identity())
    data = request.get_json() or {}
    db   = get_db()

    existing = db.execute("SELECT * FROM products WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    if not existing:
        db.close()
        return err("Product not found", 404)

    db.execute(
        "UPDATE products SET name=?,category=?,qty=?,unit=?,exp_date=?,barcode=?,notes=?,image_url=? WHERE id=? AND user_id=?",
        (
            data.get("name",      existing["name"]),
            data.get("category",  existing["category"]),
            float(data.get("qty", existing["qty"])),
            data.get("unit",      existing["unit"]),
            data.get("exp_date",  existing["exp_date"]),
            data.get("barcode",   existing["barcode"]),
            data.get("notes",     existing["notes"]),
            data.get("image_url", existing["image_url"]),
            pid, uid
        )
    )
    db.commit()
    product = enrich_product(db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone())
    db.close()
    return ok(product, message="Product updated successfully")


@app.delete("/api/products/<int:pid>")
@jwt_required()
def delete_product(pid):
    uid    = int(get_jwt_identity())
    reason = (request.get_json() or {}).get("reason", "removed")
    db     = get_db()

    product = db.execute("SELECT * FROM products WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    if not product:
        db.close()
        return err("Product not found", 404)

    db.execute(
        "INSERT INTO removed_products (user_id,name,category,qty,unit,exp_date,reason) VALUES (?,?,?,?,?,?,?)",
        (uid, product["name"], product["category"], product["qty"], product["unit"], product["exp_date"], reason)
    )
    db.execute("DELETE FROM products WHERE id=? AND user_id=?", (pid, uid))
    db.commit()
    db.close()
    return ok(message="Product deleted successfully")


@app.get("/api/products/categories/all")
def get_categories():
    categories = [
        {"id": 1, "name": "vegetables", "label": "Vegetables & Fruits", "emoji": "🥦", "color": "#10b981"},
        {"id": 2, "name": "meat",       "label": "Meat",                "emoji": "🍗", "color": "#ef4444"},
        {"id": 3, "name": "dairy",      "label": "Dairy",               "emoji": "🥛", "color": "#3b82f6"},
        {"id": 4, "name": "frozen",     "label": "Frozen",              "emoji": "🍟", "color": "#8b5cf6"},
        {"id": 5, "name": "canned",     "label": "Canned",              "emoji": "🥫", "color": "#f59e0b"},
        {"id": 6, "name": "others",     "label": "Others",              "emoji": "🍫", "color": "#6b7280"},
    ]
    return ok(categories)


@app.get("/api/products/removed/history")
@jwt_required()
def get_removed():
    uid   = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 20)), 100)
    db    = get_db()
    rows  = db.execute(
        "SELECT * FROM removed_products WHERE user_id=? ORDER BY removed_date DESC LIMIT ?",
        (uid, limit)
    ).fetchall()
    db.close()
    return ok(rows_to_list(rows))


# ── SENSOR ────────────────────────────────────────────────

@app.get("/api/sensor/summary")
@jwt_required()
def get_sensor():
    db    = get_db()
    state = row_to_dict(db.execute("SELECT * FROM sensor_state WHERE id=1").fetchone())
    rows  = db.execute("SELECT * FROM sensor_readings ORDER BY recorded_at DESC LIMIT 20").fetchall()
    db.close()
    live = mqtt_manager.get_data()
    if state:
        live["updated_at"] = state.get("updated_at", live.get("updated_at"))
    live["readings_history"] = rows_to_list(rows)
    return ok(live)


@app.get("/api/sensor/readings")
@jwt_required()
def sensor_readings():
    hours = int(request.args.get("hours", 24))
    db    = get_db()
    rows  = db.execute(
        "SELECT * FROM sensor_readings WHERE recorded_at >= datetime('now', ?) ORDER BY recorded_at DESC",
        (f"-{hours} hours",)
    ).fetchall()
    db.close()
    return ok(rows_to_list(rows))


@app.post("/api/sensor/data")
def receive_sensor_data():
    data        = request.get_json() or {}
    temperature = data.get("temperature")
    humidity    = data.get("humidity")
    if temperature is None or humidity is None:
        return err("temperature and humidity are required")
    save_sensor_to_db(temperature, humidity, True, "webhook")
    return ok(message="Data received", temperature=temperature, humidity=humidity)


# ── NOTIFICATIONS ─────────────────────────────────────────

@app.get("/api/notifications")
@jwt_required()
def get_notifications():
    uid        = int(get_jwt_identity())
    unread     = request.args.get("unread_only", "false").lower() == "true"
    notif_type = request.args.get("type")
    limit      = min(int(request.args.get("limit", 50)), 200)
    db         = get_db()

    query  = "SELECT * FROM notifications WHERE user_id=?"
    params = [uid]
    if unread:
        query += " AND is_read=0"
    if notif_type:
        query += " AND type=?"
        params.append(notif_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    db.close()
    return ok(rows_to_list(rows))


@app.get("/api/notifications/count")
@jwt_required()
def notifications_count():
    uid = int(get_jwt_identity())
    db  = get_db()
    count = db.execute(
        "SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0", (uid,)
    ).fetchone()["c"]
    db.close()
    return ok({"unread_count": count})


@app.post("/api/notifications/mark-read")
@jwt_required()
def mark_read():
    uid  = int(get_jwt_identity())
    data = request.get_json() or {}
    ids  = data.get("notification_ids", [])
    db   = get_db()
    for nid in ids:
        db.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (nid, uid))
    db.commit()
    db.close()
    return ok({"marked_read": len(ids)})


@app.post("/api/notifications/mark-all-read")
@jwt_required()
def mark_all_read():
    uid = int(get_jwt_identity())
    db  = get_db()
    cur = db.execute("UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0", (uid,))
    db.commit()
    db.close()
    return ok({"marked_read": cur.rowcount})


@app.delete("/api/notifications/<int:nid>")
@jwt_required()
def delete_notification(nid):
    uid = int(get_jwt_identity())
    db  = get_db()
    row = db.execute("SELECT id FROM notifications WHERE id=? AND user_id=?", (nid, uid)).fetchone()
    if not row:
        db.close()
        return err("Notification not found", 404)
    db.execute("DELETE FROM notifications WHERE id=?", (nid,))
    db.commit()
    db.close()
    return ok(message="Notification deleted")


@app.post("/api/notifications/fcm-token")
@jwt_required()
def register_fcm_token():
    uid  = int(get_jwt_identity())
    data = request.get_json() or {}
    token       = data.get("token", "").strip()
    device_type = data.get("device_type", "mobile")
    if not token:
        return err("Token is required")
    db = get_db()
    db.execute(
        "INSERT INTO fcm_tokens (user_id, token, device_type) VALUES (?,?,?)",
        (uid, token, device_type)
    )
    db.commit()
    db.close()
    return ok(message="FCM token registered")


# ── USER SETTINGS ─────────────────────────────────────────

@app.get("/api/notifications/settings")
@jwt_required()
def get_settings():
    uid = int(get_jwt_identity())
    db  = get_db()
    db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (uid,))
    db.commit()
    settings = row_to_dict(db.execute("SELECT * FROM user_settings WHERE user_id=?", (uid,)).fetchone())
    db.close()
    return ok(settings)


@app.put("/api/notifications/settings")
@jwt_required()
def update_settings():
    uid  = int(get_jwt_identity())
    data = request.get_json() or {}
    db   = get_db()
    db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (uid,))
    s = row_to_dict(db.execute("SELECT * FROM user_settings WHERE user_id=?", (uid,)).fetchone())

    db.execute("""
        UPDATE user_settings SET
            expiry_warning_days=?, temp_min=?, temp_max=?,
            humidity_min=?, humidity_max=?,
            push_notifications=?, email_notifications=?, language=?
        WHERE user_id=?
    """, (
        data.get("expiry_warning_days", s["expiry_warning_days"]),
        data.get("temp_min",            s["temp_min"]),
        data.get("temp_max",            s["temp_max"]),
        data.get("humidity_min",        s["humidity_min"]),
        data.get("humidity_max",        s["humidity_max"]),
        data.get("push_notifications",  s["push_notifications"]),
        data.get("email_notifications", s["email_notifications"]),
        data.get("language",            s["language"]),
        uid
    ))
    db.commit()
    updated = row_to_dict(db.execute("SELECT * FROM user_settings WHERE user_id=?", (uid,)).fetchone())
    db.close()
    return ok(updated, message="Settings updated successfully")


# ── CONSUMPTION / STATS ───────────────────────────────────

@app.get("/api/stats/summary")
@jwt_required()
def stats_summary():
    uid   = int(get_jwt_identity())
    today = date.today().isoformat()
    db    = get_db()
    products      = rows_to_list(db.execute("SELECT * FROM products WHERE user_id=?", (uid,)).fetchall())
    removed_total = db.execute("SELECT COUNT(*) as c FROM removed_products WHERE user_id=?", (uid,)).fetchone()["c"]
    db.close()

    expired = sum(1 for p in products if p["exp_date"] < today)
    soon    = sum(1 for p in products if 0 <= (datetime.strptime(p["exp_date"], "%Y-%m-%d").date() - date.today()).days <= 3)
    return ok({
        "total": len(products), "expired": expired,
        "expiring_soon": soon, "fresh": max(len(products) - expired - soon, 0),
        "removed_total": removed_total,
    })


@app.get("/api/consumption/summary")
@jwt_required()
def consumption_summary():
    uid  = int(get_jwt_identity())
    db   = get_db()

    weekly_rows = db.execute(
        """SELECT strftime('%w', removed_date) as dow, COUNT(*) as cnt
           FROM removed_products WHERE user_id=? AND removed_date >= date('now','-7 days')
           GROUP BY dow""", (uid,)
    ).fetchall()

    monthly_rows = db.execute(
        """SELECT strftime('%m', removed_date) as mon, COUNT(*) as cnt
           FROM removed_products WHERE user_id=? AND removed_date >= date('now','-12 months')
           GROUP BY mon ORDER BY mon""", (uid,)
    ).fetchall()

    total_expired  = db.execute("SELECT COUNT(*) as c FROM removed_products WHERE user_id=? AND reason='expired'",  (uid,)).fetchone()["c"]
    total_consumed = db.execute("SELECT COUNT(*) as c FROM removed_products WHERE user_id=? AND reason='consumed'", (uid,)).fetchone()["c"]
    total_removed  = db.execute("SELECT COUNT(*) as c FROM removed_products WHERE user_id=?",                       (uid,)).fetchone()["c"]
    db.close()

    days   = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    wvals  = [0] * 7
    for r in weekly_rows:
        wvals[int(r["dow"])] = r["cnt"]

    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    mvals  = [0] * 12
    for r in monthly_rows:
        mvals[int(r["mon"]) - 1] = r["cnt"]

    return ok({
        "weekly":         {"labels": days,   "data": wvals, "total": sum(wvals)},
        "monthly":        {"labels": months, "data": mvals, "total": sum(mvals)},
        "total_expired":  total_expired,
        "total_consumed": total_consumed,
        "total_removed":  total_removed,
    })


@app.get("/api/stats/weekly")
@jwt_required()
def stats_weekly():
    uid  = int(get_jwt_identity())
    db   = get_db()
    rows = db.execute(
        """SELECT strftime('%w', removed_date) as dow, COUNT(*) as cnt
           FROM removed_products WHERE user_id=? AND removed_date >= date('now','-7 days')
           GROUP BY dow""", (uid,)
    ).fetchall()
    db.close()
    days   = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    values = [0] * 7
    for r in rows:
        values[int(r["dow"])] = r["cnt"]
    return ok({"labels": days, "values": values})


@app.get("/api/stats/monthly")
@jwt_required()
def stats_monthly():
    uid  = int(get_jwt_identity())
    db   = get_db()
    rows = db.execute(
        """SELECT strftime('%m', removed_date) as mon, COUNT(*) as cnt
           FROM removed_products WHERE user_id=? AND removed_date >= date('now','-12 months')
           GROUP BY mon ORDER BY mon""", (uid,)
    ).fetchall()
    db.close()
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    values = [0] * 12
    for r in rows:
        values[int(r["mon"]) - 1] = r["cnt"]
    return ok({"labels": months, "values": values})


@app.get("/api/consumption/logs")
@jwt_required()
def consumption_logs():
    uid    = int(get_jwt_identity())
    days   = int(request.args.get("days", 30))
    action = request.args.get("action")
    db     = get_db()

    query  = "SELECT * FROM removed_products WHERE user_id=? AND removed_date >= date('now', ?)"
    params = [uid, f"-{days} days"]
    if action:
        query += " AND reason=?"
        params.append(action)
    query += " ORDER BY removed_date DESC"

    rows = db.execute(query, params).fetchall()
    db.close()
    return ok(rows_to_list(rows))


# ── ERROR HANDLERS ────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return err("Route not found", 404)

@app.errorhandler(500)
def server_error(e):
    return err("Internal server error", 500)

@jwt.invalid_token_loader
def invalid_token(r):
    return err("Invalid token", 401)

@jwt.expired_token_loader
def expired_token(h, d):
    return err("Session expired, please login again", 401)

@jwt.unauthorized_loader
def unauthorized(r):
    return err("Unauthorized", 401)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    print(f"Server running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=bool(int(os.getenv("FLASK_DEBUG", 1))))
