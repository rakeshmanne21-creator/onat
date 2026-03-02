from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from face_verify import register_face, verify_face
import mysql.connector
import hashlib
import uuid
import datetime
import qrcode
import os

app = Flask(__name__)
app.secret_key = "smart_attendance_secret"

# =====================================================
# DATABASE CONNECTION
# =====================================================
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Rakesh",
    database="attendance_system"
)

cursor = db.cursor(buffered=True)

# =====================================================
# PASSWORD HASH
# =====================================================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# =====================================================
# HOME ROLE PAGE
# =====================================================
@app.route("/")
def home():
    return render_template("role_select.html")


# =====================================================
# ================= STUDENT =================
# =====================================================

@app.route("/student_login", methods=["GET","POST"])
def student_login():

    if request.method == "POST":

        email = request.form.get("email")
        password = hash_password(request.form.get("password"))

        cursor.execute(
            "SELECT id,name FROM students WHERE email=%s AND password=%s",
            (email,password)
        )

        user = cursor.fetchone()

        if user:
            session["student_id"] = user[0]
            session["student_name"] = user[1]
            return redirect(url_for("scan_qr"))

        return render_template("login.html",
                               error="Invalid Login")

    return render_template("login.html")


# =====================================================
# STUDENT REGISTER + FACE CAPTURE
# =====================================================
@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        cursor.execute("""
        INSERT INTO students(name,roll_number,email,password)
        VALUES(%s,%s,%s,%s)
        """,(
            request.form.get("name"),
            request.form.get("roll"),
            request.form.get("email"),
            hash_password(request.form.get("password"))
        ))

        db.commit()

        student_id = cursor.lastrowid

        # FACE REGISTER
        register_face(student_id)

        return redirect(url_for("student_login"))

    return render_template("register.html")


@app.route("/scan_qr")
def scan_qr():

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    return render_template("scan_qr.html")


# =====================================================
# ================= FACULTY =================
# =====================================================

@app.route("/faculty_register",methods=["GET","POST"])
def faculty_register():

    if request.method=="POST":

        cursor.execute("""
        INSERT INTO faculty(name,email,password)
        VALUES(%s,%s,%s)
        """,(
            request.form.get("name"),
            request.form.get("email"),
            hash_password(request.form.get("password"))
        ))

        db.commit()
        return redirect(url_for("faculty_login"))

    return render_template("faculty_register.html")


@app.route("/faculty_login",methods=["GET","POST"])
def faculty_login():

    if request.method=="POST":

        cursor.execute("""
        SELECT id FROM faculty
        WHERE email=%s AND password=%s
        """,(
            request.form.get("email"),
            hash_password(request.form.get("password"))
        ))

        fac=cursor.fetchone()

        if fac:
            session["faculty_id"]=fac[0]
            return redirect(url_for("faculty_dashboard"))

        return render_template(
            "faculty_login.html",
            error="Invalid Login"
        )

    return render_template("faculty_login.html")


@app.route("/faculty_dashboard")
def faculty_dashboard():

    if "faculty_id" not in session:
        return redirect(url_for("faculty_login"))

    return render_template("faculty_dashboard.html")


# =====================================================
# QR GENERATION (AUTO EXPIRE)
# =====================================================
@app.route("/generate_qr")
def generate_qr():

    if "faculty_id" not in session:
        return redirect(url_for("faculty_login"))

    token=str(uuid.uuid4())
    expiry=datetime.datetime.now()+datetime.timedelta(minutes=2)

    cursor.execute("""
    INSERT INTO sessions(qr_token,expiry_time)
    VALUES(%s,%s)
    """,(token,expiry))

    db.commit()

    os.makedirs("static/qr",exist_ok=True)

    img=qrcode.make(token)
    path=f"static/qr/{token}.png"
    img.save(path)

    return jsonify({
        "qr":"/"+path,
        "expires":120
    })


# =====================================================
# LIVE ATTENDANCE COUNT
# =====================================================
@app.route("/live_count")
def live_count():

    cursor.execute("""
    SELECT COUNT(DISTINCT student_id)
    FROM attendance
    WHERE date=CURDATE()
    """)

    count=cursor.fetchone()[0]

    return jsonify({"count":count})


# =====================================================
# VERIFY QR + FACE + ATTENDANCE
# =====================================================
@app.route("/verify_qr",methods=["POST"])
def verify_qr():

    if "student_id" not in session:
        return jsonify({"status":"login_required"})

    token=request.json.get("token")

    cursor.execute(
        "SELECT expiry_time FROM sessions WHERE qr_token=%s",
        (token,)
    )

    data=cursor.fetchone()

    if not data:
        return jsonify({"status":"invalid"})

    if datetime.datetime.now()>data[0]:
        return jsonify({"status":"expired"})

    student_id=session["student_id"]

    verified_name=verify_face(student_id)

    if not verified_name:
        return jsonify({"status":"face_failed"})

    cursor.execute("""
    SELECT * FROM attendance
    WHERE student_id=%s AND date=CURDATE()
    """,(student_id,))

    if cursor.fetchone():
        return jsonify({"status":"already_marked"})

    cursor.execute("""
    INSERT INTO attendance(student_id,date,time)
    VALUES(%s,CURDATE(),CURTIME())
    """,(student_id,))

    db.commit()

    return jsonify({
        "status":"success",
        "student":verified_name
    })


# =====================================================
# ================= ADMIN =================
# =====================================================
@app.route("/admin_register",methods=["GET","POST"])
def admin_register():

    if request.method=="POST":

        cursor.execute("""
        INSERT INTO admin(username,password)
        VALUES(%s,%s)
        """,(
            request.form.get("username"),
            hash_password(request.form.get("password"))
        ))

        db.commit()
        return redirect(url_for("admin_login"))

    return render_template("admin_register.html")


@app.route("/admin_login",methods=["GET","POST"])
def admin_login():

    if request.method=="POST":

        cursor.execute("""
        SELECT id FROM admin
        WHERE username=%s AND password=%s
        """,(
            request.form.get("username"),
            hash_password(request.form.get("password"))
        ))

        admin=cursor.fetchone()

        if admin:
            session["admin"]=admin[0]
            return redirect(url_for("admin_dashboard"))

        return render_template(
            "admin_login.html",
            error="Invalid Login"
        )

    return render_template("admin_login.html")


@app.route("/admin_dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect(url_for("admin_login"))

    cursor.execute("SELECT COUNT(*) FROM students")
    students=cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM faculty")
    faculty=cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM attendance")
    attendance=cursor.fetchone()[0]

    return render_template(
        "admin_dashboard.html",
        students=students,
        faculty=faculty,
        attendance=attendance
    )


# =====================================================
# LOGOUT
# =====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# =====================================================
if __name__=="__main__":
    app.run(debug=True)