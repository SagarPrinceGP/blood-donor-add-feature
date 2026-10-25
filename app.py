import os
import random
import re
import csv
import io
import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, session, 
    flash, jsonify, Response, url_for
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "lifepulse_blood_donor_secret_2026")

DATABASE = "donors.db"

# ---------------- DATABASE CONNECTION ----------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- DATABASE INITIALIZATION & MIGRATION ----------------
def init_db():
    conn = get_db()
    c = conn.cursor()

    # 1. Donors Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS donors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        blood TEXT NOT NULL,
        phone TEXT NOT NULL,
        city TEXT NOT NULL,
        age INTEGER DEFAULT 28,
        gender TEXT DEFAULT 'Not Specified',
        status TEXT DEFAULT 'Available',
        last_donated TEXT DEFAULT '',
        total_donations INTEGER DEFAULT 1
    )
    """)

    # Check and add any missing columns in existing donors table
    c.execute("PRAGMA table_info(donors)")
    existing_donor_cols = [row["name"] for row in c.fetchall()]
    new_donor_cols = [
        ("age", "INTEGER DEFAULT 28"),
        ("gender", "TEXT DEFAULT 'Not Specified'"),
        ("status", "TEXT DEFAULT 'Available'"),
        ("last_donated", "TEXT DEFAULT ''"),
        ("total_donations", "INTEGER DEFAULT 1")
    ]
    for col_name, col_def in new_donor_cols:
        if col_name not in existing_donor_cols:
            c.execute(f"ALTER TABLE donors ADD COLUMN {col_name} {col_def}")

    # Standardize all existing blood types to uppercase
    c.execute("UPDATE donors SET blood = UPPER(TRIM(blood)) WHERE blood IS NOT NULL")

    # 2. Users Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'admin',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("PRAGMA table_info(users)")
    existing_user_cols = [row["name"] for row in c.fetchall()]
    if "role" not in existing_user_cols:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")
    if "created_at" not in existing_user_cols:
        c.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT ''")

    # 3. Emergency Blood Requests Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS blood_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT NOT NULL,
        blood_group TEXT NOT NULL,
        units INTEGER NOT NULL DEFAULT 1,
        hospital TEXT NOT NULL,
        city TEXT NOT NULL,
        contact_phone TEXT NOT NULL,
        urgency TEXT NOT NULL DEFAULT 'Urgent',
        status TEXT NOT NULL DEFAULT 'Pending',
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Seed initial emergency blood requests if none exist
    c.execute("SELECT COUNT(*) as cnt FROM blood_requests")
    req_count = c.fetchone()["cnt"]
    if req_count == 0:
        c.executemany("""
        INSERT INTO blood_requests (patient_name, blood_group, units, hospital, city, contact_phone, urgency, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("Priya Sharma", "O+", 2, "Apollo BGS Hospital", "Mysore", "9876543210", "Critical", "Pending", "ICU Emergency - Bypass Surgery"),
            ("Ramesh Gowda", "A+", 1, "Manipal Hospital", "Bangalore", "9123456780", "Urgent", "Pending", "Dengue platelet transfusion"),
            ("Ananya Hegde", "B+", 2, "District Hospital", "Chamarajanagar", "8867012001", "Standard", "Fulfilled", "Routine transfusion completed")
        ])

    conn.commit()
    conn.close()
    print("Database & Schema Ready.")

init_db()

# ---------------- BLOOD COMPATIBILITY MATRIX ----------------
# Medically validated red blood cell compatibility
COMPATIBILITY_MATRIX = {
    "O-": {
        "can_receive": ["O-"],
        "can_donate": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]
    },
    "O+": {
        "can_receive": ["O+", "O-"],
        "can_donate": ["O+", "A+", "B+", "AB+"]
    },
    "A-": {
        "can_receive": ["A-", "O-"],
        "can_donate": ["A-", "A+", "AB-", "AB+"]
    },
    "A+": {
        "can_receive": ["A+", "A-", "O+", "O-"],
        "can_donate": ["A+", "AB+"]
    },
    "B-": {
        "can_receive": ["B-", "O-"],
        "can_donate": ["B-", "B+", "AB-", "AB+"]
    },
    "B+": {
        "can_receive": ["B+", "B-", "O+", "O-"],
        "can_donate": ["B+", "AB+"]
    },
    "AB-": {
        "can_receive": ["AB-", "A-", "B-", "O-"],
        "can_donate": ["AB-", "AB+"]
    },
    "AB+": {
        "can_receive": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
        "can_donate": ["AB+"]
    }
}

ALL_BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

# ---------------- CONTEXT PROCESSOR ----------------
@app.context_processor
def inject_global_data():
    """Injects pending requests count into all templates for navbar badge."""
    pending_count = 0
    if "user" in session:
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM blood_requests WHERE status='Pending'")
            row = c.fetchone()
            if row:
                pending_count = row["cnt"]
            conn.close()
        except:
            pass
    return dict(pending_requests_count=pending_count)

# ---------------- PASSWORD HELPERS ----------------
def is_valid_password(password):
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True

# ---------------- EMAIL / OTP ----------------
def send_otp(email, otp):
    """Sends OTP via SMTP with graceful fallback to console / flash."""
    sender_email = "sagargpprince@gmail.com"
    sender_pass = "apctkznzvruwirut"

    try:
        msg = EmailMessage()
        msg["Subject"] = "LifePulse - Password Reset OTP Code"
        msg["From"] = f"LifePulse Network <{sender_email}>"
        msg["To"] = email

        msg.set_content(f"""Hello,

Your verification code for resetting your LifePulse account password is:

{otp}

This code will expire in 10 minutes. If you did not request this, please disregard this email.

Warm regards,
LifePulse Blood Donor Network Team
""")
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=6)
        server.starttls()
        server.login(sender_email, sender_pass)
        server.send_message(msg)
        server.quit()
        return True, "OTP successfully dispatched to your email."
    except Exception as e:
        print(f"SMTP Notification: {e}")
        return False, f"Notice: Email service unreachable. Your verification OTP is: {otp}"

# ===================================================================
# AUTHENTICATION ROUTES
# ===================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect("/")

    if request.method == "POST":
        email = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()

        if user:
            stored_pass = user["password"]
            password_matches = False

            # Check if hashed or legacy plain-text
            if stored_pass.startswith("scrypt:") or stored_pass.startswith("pbkdf2:"):
                password_matches = check_password_hash(stored_pass, password)
            else:
                if stored_pass == password:
                    password_matches = True
                    # Auto-upgrade plain-text password to hashed
                    new_hash = generate_password_hash(password)
                    c.execute("UPDATE users SET password=? WHERE id=?", (new_hash, user["id"]))
                    conn.commit()

            if password_matches:
                session["user"] = user["name"]
                session["user_email"] = user["email"]
                session["admin"] = True
                session["role"] = user["role"] if "role" in user.keys() and user["role"] else "admin"
                conn.close()
                flash(f"Welcome back, {user['name']}!", "success")
                return redirect("/")

        conn.close()
        return render_template("login.html", error="Invalid email address or password.")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user" in session:
        return redirect("/")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return render_template("register.html", error="All fields are mandatory.")

        if not is_valid_password(password):
            return render_template("register.html", 
                error="Password must be 8+ chars and contain an uppercase letter, a number, and a special character.")

        conn = get_db()
        c = conn.cursor()
        try:
            hashed_pass = generate_password_hash(password)
            c.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, 'admin')
            """, (name, email, hashed_pass))
            conn.commit()
            conn.close()

            flash("Account registered successfully! Please sign in.", "success")
            return redirect("/login")
        except sqlite3.IntegrityError:
            conn.close()
            return render_template("register.html", error="An account with this email already exists.")
        except Exception as e:
            conn.close()
            return render_template("register.html", error=f"Registration error: {str(e)}")

    return render_template("register.html")

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()
        conn.close()

        if not user:
            return render_template("forgot.html", error="No account found with this email address.")

        otp = random.randint(100000, 999999)
        session["reset_email"] = email
        session["otp"] = otp

        success, msg = send_otp(email, otp)
        if not success:
            flash(msg, "warning")
        else:
            flash("Verification OTP sent to your email.", "info")

        return redirect("/otp")

    return render_template("forgot.html")

@app.route("/otp", methods=["GET", "POST"])
def otp():
    if "reset_email" not in session or "otp" not in session:
        return redirect("/forgot")

    if request.method == "POST":
        user_otp = request.form.get("otp", "").strip()

        try:
            if int(user_otp) == session.get("otp"):
                session["otp_verified"] = True
                return redirect("/reset")
            else:
                return render_template("otp.html", error="Incorrect 6-digit OTP code. Please try again.")
        except ValueError:
            return render_template("otp.html", error="Please enter valid 6 digits.")

    return render_template("otp.html")

@app.route("/reset", methods=["GET", "POST"])
def reset():
    if "reset_email" not in session or not session.get("otp_verified"):
        return redirect("/login")

    if request.method == "POST":
        new_pass = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if new_pass != confirm:
            return render_template("reset.html", error="Passwords do not match!")

        if not is_valid_password(new_pass):
            return render_template("reset.html", error="Password does not satisfy complexity requirements.")

        email = session.get("reset_email")
        hashed_pass = generate_password_hash(new_pass)

        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE email=?", (hashed_pass, email))
        conn.commit()
        conn.close()

        session.clear()
        flash("Password updated successfully! Please sign in with your new password.", "success")
        return redirect("/login")

    return render_template("reset.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out securely.", "info")
    return redirect("/login")

# ===================================================================
# DASHBOARD
# ===================================================================

@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()

    # Total donors
    c.execute("SELECT COUNT(*) as total FROM donors")
    total_donors = c.fetchone()["total"]

    # Available donors
    c.execute("SELECT COUNT(*) as avail FROM donors WHERE status='Available'")
    available_donors = c.fetchone()["avail"]

    # Pending urgent requests
    c.execute("SELECT COUNT(*) as req_cnt FROM blood_requests WHERE status='Pending'")
    pending_requests = c.fetchone()["req_cnt"]

    # Distinct cities
    c.execute("SELECT COUNT(DISTINCT LOWER(TRIM(city))) as city_cnt FROM donors")
    total_cities = c.fetchone()["city_cnt"]

    # Blood group breakdown
    c.execute("SELECT UPPER(TRIM(blood)) as grp, COUNT(*) as cnt FROM donors GROUP BY grp")
    rows = c.fetchall()
    blood_counts = {g: 0 for g in ALL_BLOOD_GROUPS}
    for r in rows:
        grp = r["grp"]
        if grp in blood_counts:
            blood_counts[grp] = r["cnt"]

    # Recent 5 donors
    c.execute("SELECT * FROM donors ORDER BY id DESC LIMIT 5")
    recent_donors = c.fetchall()

    # Recent 3 urgent requests
    c.execute("""
    SELECT * FROM blood_requests 
    ORDER BY CASE WHEN urgency='Critical' THEN 1 WHEN urgency='Urgent' THEN 2 ELSE 3 END, id DESC 
    LIMIT 3
    """)
    urgent_requests = c.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        total_donors=total_donors,
        available_donors=available_donors,
        pending_requests=pending_requests,
        total_cities=total_cities,
        blood_counts=blood_counts,
        recent_donors=recent_donors,
        urgent_requests=urgent_requests
    )

# ===================================================================
# DONORS DIRECTORY & SEARCH
# ===================================================================

@app.route("/donors")
def donors_directory():
    if "user" not in session:
        return redirect("/login")

    blood_filter = request.args.get("blood", "").strip().upper()
    city_filter = request.args.get("city", "").strip()
    status_filter = request.args.get("status", "").strip()
    search_q = request.args.get("q", "").strip()

    conn = get_db()
    c = conn.cursor()

    # Fetch unique cities for filter dropdown
    c.execute("SELECT DISTINCT city FROM donors WHERE city IS NOT NULL AND city != '' ORDER BY city ASC")
    cities = [r["city"] for r in c.fetchall()]

    # Build dynamic query
    query = "SELECT * FROM donors WHERE 1=1"
    params = []

    if blood_filter:
        query += " AND UPPER(blood) = ?"
        params.append(blood_filter)

    if city_filter:
        query += " AND LOWER(city) = ?"
        params.append(city_filter.lower())

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    if search_q:
        query += " AND (name LIKE ? OR phone LIKE ? OR city LIKE ?)"
        wildcard = f"%{search_q}%"
        params.extend([wildcard, wildcard, wildcard])

    query += " ORDER BY id DESC"

    c.execute(query, params)
    donors = c.fetchall()
    conn.close()

    return render_template(
        "view.html",
        donors=donors,
        cities=cities,
        selected_blood=blood_filter,
        selected_city=city_filter,
        selected_status=status_filter,
        query_q=search_q
    )

# Backward compatibility routes
@app.route("/view")
def view():
    return redirect("/donors")

@app.route("/search", methods=["POST"])
def search():
    blood = request.form.get("blood", "").strip().upper()
    return redirect(url_for("donors_directory", blood=blood))

# ===================================================================
# ADD / EDIT / DELETE DONORS
# ===================================================================

@app.route("/add_donor", methods=["GET"])
def add_donor_page():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html")

@app.route("/add", methods=["POST"])
def add():
    if "user" not in session:
        return redirect("/login")

    name = request.form.get("name", "").strip()
    blood = request.form.get("blood", "").strip().upper()
    phone = request.form.get("phone", "").strip()
    city = request.form.get("city", "").strip()
    age = request.form.get("age", 25)
    gender = request.form.get("gender", "Not Specified")
    status = request.form.get("status", "Available")
    last_donated = request.form.get("last_donated", "")

    if not name or not blood or not phone or not city:
        flash("Name, Blood Group, Phone, and City are required!", "danger")
        return redirect("/add_donor")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO donors (name, blood, phone, city, age, gender, status, last_donated, total_donations)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (name, blood, phone, city, age, gender, status, last_donated))
    conn.commit()
    conn.close()

    flash(f"Donor '{name}' ({blood}) registered successfully!", "success")
    return redirect("/donors")

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_donor(id):
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        blood = request.form.get("blood", "").strip().upper()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        age = request.form.get("age", 25)
        gender = request.form.get("gender", "Not Specified")
        status = request.form.get("status", "Available")
        last_donated = request.form.get("last_donated", "")
        total_donations = request.form.get("total_donations", 1)

        c.execute("""
        UPDATE donors 
        SET name=?, blood=?, phone=?, city=?, age=?, gender=?, status=?, last_donated=?, total_donations=?
        WHERE id=?
        """, (name, blood, phone, city, age, gender, status, last_donated, total_donations, id))
        conn.commit()
        conn.close()

        flash("Donor record updated successfully!", "success")
        return redirect("/donors")

    c.execute("SELECT * FROM donors WHERE id=?", (id,))
    donor = c.fetchone()
    conn.close()

    if not donor:
        flash("Donor not found.", "danger")
        return redirect("/donors")

    return render_template("edit_donor.html", donor=donor)

@app.route("/delete/<int:id>")
def delete(id):
    if "user" not in session:
        flash("Please log in to manage donors.", "danger")
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM donors WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("Donor deleted successfully.", "success")
    return redirect("/donors")

# ===================================================================
# URGENT BLOOD REQUESTS
# ===================================================================

@app.route("/requests")
def view_requests():
    if "user" not in session:
        return redirect("/login")

    status_filter = request.args.get("status", "").strip()
    conn = get_db()
    c = conn.cursor()

    if status_filter:
        c.execute("""
        SELECT * FROM blood_requests 
        WHERE status=? 
        ORDER BY CASE WHEN urgency='Critical' THEN 1 WHEN urgency='Urgent' THEN 2 ELSE 3 END, id DESC
        """, (status_filter,))
    else:
        c.execute("""
        SELECT * FROM blood_requests 
        ORDER BY CASE WHEN status='Pending' THEN 1 ELSE 2 END, 
                 CASE WHEN urgency='Critical' THEN 1 WHEN urgency='Urgent' THEN 2 ELSE 3 END, 
                 id DESC
        """)

    blood_reqs = c.fetchall()
    conn.close()

    return render_template("requests.html", requests=blood_reqs, filter_status=status_filter)

@app.route("/requests/add", methods=["POST"])
def add_request():
    if "user" not in session:
        return redirect("/login")

    patient_name = request.form.get("patient_name", "").strip()
    blood_group = request.form.get("blood_group", "").strip().upper()
    units = request.form.get("units", 1)
    hospital = request.form.get("hospital", "").strip()
    city = request.form.get("city", "").strip()
    contact_phone = request.form.get("contact_phone", "").strip()
    urgency = request.form.get("urgency", "Urgent")
    notes = request.form.get("notes", "").strip()

    if not patient_name or not blood_group or not hospital or not contact_phone:
        flash("All mandatory request fields must be filled.", "danger")
        return redirect("/requests")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO blood_requests (patient_name, blood_group, units, hospital, city, contact_phone, urgency, status, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?)
    """, (patient_name, blood_group, units, hospital, city, contact_phone, urgency, notes))
    conn.commit()
    conn.close()

    flash("Emergency blood request broadcasted successfully!", "success")
    return redirect("/requests")

@app.route("/requests/status/<int:id>/<new_status>")
def toggle_request_status(id, new_status):
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE blood_requests SET status=? WHERE id=?", (new_status, id))
    conn.commit()
    conn.close()

    flash(f"Request status updated to '{new_status}'.", "info")
    return redirect("/requests")

@app.route("/requests/delete/<int:id>")
def delete_request(id):
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM blood_requests WHERE id=?", (id,))
    conn.commit()
    conn.close()

    flash("Blood request deleted.", "info")
    return redirect("/requests")

# ===================================================================
# BLOOD COMPATIBILITY & SMART MATCHER
# ===================================================================

@app.route("/compatibility")
def compatibility():
    if "user" not in session:
        return redirect("/login")

    selected_group = request.args.get("blood", "O+").strip().upper()
    if selected_group not in COMPATIBILITY_MATRIX:
        selected_group = "O+"

    comp_data = COMPATIBILITY_MATRIX[selected_group]
    compatible_donors_groups = comp_data["can_receive"]

    conn = get_db()
    c = conn.cursor()

    placeholders = ",".join(["?"] * len(compatible_donors_groups))
    query = f"""
    SELECT * FROM donors 
    WHERE UPPER(blood) IN ({placeholders})
    ORDER BY CASE WHEN status='Available' THEN 1 ELSE 2 END, id DESC
    """
    c.execute(query, compatible_donors_groups)
    matching_donors = c.fetchall()
    conn.close()

    return render_template(
        "compatibility.html",
        selected_group=selected_group,
        comp_data=comp_data,
        matching_donors=matching_donors
    )

@app.route("/api/compatibility/<blood_group>")
def api_compatibility(blood_group):
    bg = blood_group.strip().upper()
    if bg in COMPATIBILITY_MATRIX:
        return jsonify({"success": True, "blood_group": bg, "data": COMPATIBILITY_MATRIX[bg]})
    return jsonify({"success": False, "error": "Invalid blood group"}), 400

# ===================================================================
# CSV EXPORT
# ===================================================================

@app.route("/export_csv")
def export_csv():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, blood, phone, city, age, gender, status, last_donated, total_donations FROM donors ORDER BY id ASC")
    donors = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Donor ID", "Full Name", "Blood Group", "Contact Phone", 
        "City", "Age", "Gender", "Availability Status", "Last Donated Date", "Total Donations"
    ])

    for d in donors:
        writer.writerow([
            d["id"], d["name"], d["blood"], d["phone"], d["city"],
            d["age"], d["gender"], d["status"], d["last_donated"], d["total_donations"]
        ])

    csv_data = output.getvalue()
    filename = f"blood_donors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

# ===================================================================
# APPLICATION LAUNCH
# ===================================================================

if __name__ == "__main__":
    app.run(debug=True, port=5000)
