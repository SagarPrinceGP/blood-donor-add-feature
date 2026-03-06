import os
print("PROJECT FOLDER:", os.getcwd())
import random
import os
print("Database Path:", os.path.abspath("donors.db"))
import smtplib
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import re

app = Flask(__name__, static_folder="static")
app.secret_key = "blood_donor_secret"


# ---------------- DATABASE ----------------
def init_db():

    conn = sqlite3.connect("donors.db")
    c = conn.cursor()

    # Create donors table
    c.execute("""
    CREATE TABLE IF NOT EXISTS donors(
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        blood TEXT NOT NULL,
        phone TEXT NOT NULL,
        city TEXT NOT NULL
    )
    """)

    # Create users table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

    print("Database & Tables Created Successfully")


init_db()


# ---------------- OTP EMAIL ----------------
import smtplib
from email.message import EmailMessage


def send_otp(email, otp):

    sender_email = "sagargpprince@gmail.com"   # YOUR Gmail
    sender_pass = "apctkznzvruwirut" # App password (no space)

    msg = EmailMessage()
    msg["Subject"] = "Password Reset OTP"
    msg["From"] = sender_email
    msg["To"] = email

    msg.set_content(f"""
Hello,

Your OTP for password reset is:

{otp}

Do not share this OTP.

Blood Donor System
""")

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()

    server.login(sender_email, sender_pass)

    server.send_message(msg)

    server.quit()



# ---------------- PASSWORD VALIDATION ----------------

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


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        email = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect("donors.db")
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE email=? AND password=?",
                  (email, password))

        user = c.fetchone()
        conn.close()

        if user:
            session["admin"] = True
            session["user"] = user[1]
            return redirect("/")
        else:
            return render_template("login.html",
                                   error="Invalid Email or Password")

    return render_template("login.html")


# ---------------- HOME ----------------

@app.route("/")
def home():

    if "user" not in session:
        return redirect("/login")

    return render_template("index.html")



# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        if not is_valid_password(password):
            return render_template("register.html",
                                   error="Password must be 8+ chars, include uppercase, number & special character!")

        conn = sqlite3.connect("donors.db")
        c = conn.cursor()

        try:
            c.execute("""
            INSERT INTO users (name, email, password)
            VALUES (?, ?, ?)
            """, (name, email, password))

            conn.commit()
            conn.close()

            return redirect("/login")

        except:
            conn.close()
            return render_template("register.html",
                                   error="Email already exists!")

    return render_template("register.html")


# ---------------- FORGOT (SEND OTP) ----------------

@app.route("/forgot", methods=["GET","POST"])
def forgot():

    if request.method == "POST":

        email = request.form.get("email")

        conn = sqlite3.connect("donors.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()
        conn.close()

        if not user:
            return render_template("forgot.html",
                                   error="Email not registered!")

        otp = random.randint(100000,999999)

        session["reset_email"] = email
        session["otp"] = otp

        send_otp(email, otp)

        return redirect("/otp")

    return render_template("forgot.html")


# ---------------- OTP PAGE ----------------

@app.route("/otp", methods=["GET","POST"])
def otp():

    if request.method == "POST":

        user_otp = request.form.get("otp")

        if int(user_otp) == session.get("otp"):
            return redirect("/reset")
        else:
            return render_template("otp.html",
                                   error="Invalid OTP!")

    return render_template("otp.html")


# ---------------- RESET PASSWORD ----------------
@app.route("/reset", methods=["GET","POST"])
def reset():

    # ✅ SECURITY CHECK (ADD THIS)
    if "reset_email" not in session:
        return redirect("/login")

    if request.method == "POST":

        new_pass = request.form.get("new_password")
        confirm = request.form.get("confirm_password")

        if new_pass != confirm:
            return render_template("reset.html",
                                   error="Passwords do not match!")

        if not is_valid_password(new_pass):
            return render_template("reset.html",
                                   error="Password must be strong!")

        email = session.get("reset_email")

        conn = sqlite3.connect("donors.db")
        c = conn.cursor()

        c.execute("""
        UPDATE users SET password=?
        WHERE email=?
        """,(new_pass,email))

        conn.commit()
        conn.close()

        # Clear session after reset
        session.clear()

        return redirect("/login")

    return render_template("reset.html")

@app.route("/add", methods=["POST"])
def add():

    # Check login (user must be logged in)
    if "user" not in session:
        return redirect("/login")

    name = request.form.get("name")
    blood = request.form.get("blood")
    phone = request.form.get("phone")
    city = request.form.get("city")

    # Validate
    if not name or not blood or not phone or not city:
        flash("All fields are required!")
        return redirect("/")

    conn = sqlite3.connect("donors.db")
    c = conn.cursor()

    c.execute("""
    INSERT INTO donors (name, blood, phone, city)
    VALUES (?, ?, ?, ?)
    """, (name, blood, phone, city))

    conn.commit()
    conn.close()

    flash("Donor added successfully!")

    return redirect("/")

@app.route("/view")
def view():

    # Only logged users
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("donors.db")
    c = conn.cursor()

    c.execute("SELECT * FROM donors")
    data = c.fetchall()

    conn.close()

    return render_template("view.html", donors=data)

@app.route("/search", methods=["POST"])
def search():

    # User must be logged in
    if "user" not in session:
        return redirect("/login")

    blood = request.form.get("blood")

    # Remove spaces and convert to uppercase
    blood = blood.strip().upper()

    conn = sqlite3.connect("donors.db")
    c = conn.cursor()

    # Case-insensitive search
    c.execute("""
    SELECT * FROM donors
    WHERE UPPER(blood)=?
    """, (blood,))

    data = c.fetchall()

    conn.close()

    return render_template("view.html", donors=data)

from flask import flash   # at top

@app.route("/delete/<int:id>")
def delete(id):

    if session.get("role") != "admin":
        flash("Only Admin can delete donors!")
        return redirect("/view")

    conn = sqlite3.connect("donors.db")
    c = conn.cursor()

    c.execute("DELETE FROM donors WHERE id=?", (id,))

    conn.commit()
    conn.close()

    flash("Donor deleted successfully!")

    return redirect("/view")

@app.route("/logout")
def logout():

    # Remove all session data
    session.clear()

    # Redirect to login page
    return redirect("/login")







# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)
