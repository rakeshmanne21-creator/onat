from flask import Flask, render_template, request, redirect, session, jsonify, url_for, send_file
import mysql.connector
import hashlib
import uuid
import datetime
import qrcode
import os
import base64
import numpy as np
import face_recognition
import cv2
import pandas as pd
known_face_encodings = {}

app = Flask(__name__)
app.secret_key = "smart_attendance_secret"


# =====================================================
# DATABASE CONNECTION (RAILWAY READY)
# =====================================================

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get("MYSQLHOST"),
        user=os.environ.get("MYSQLUSER"),
        password=os.environ.get("MYSQLPASSWORD"),
        database=os.environ.get("MYSQLDATABASE"),
        port=int(os.environ.get("MYSQLPORT", 3306))
        pool_size=5
    )
# INITIAL DATABASE CONNECTION
db = get_db_connection()
cursor = db.cursor(buffered=True)

# =====================================================
# AUTO RECONNECT DATABASE
# =====================================================

def reconnect_db():
    global db, cursor
    try:
        db.ping(reconnect=True)
    except:
        db = get_db_connection()
        cursor = db.cursor(buffered=True)


# =====================================================
# PASSWORD HASH
# =====================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# =====================================================
# LOAD FACE ENCODINGS (OPTIMIZATION)
# =====================================================

def load_known_faces():

    global known_face_encodings
    known_face_encodings.clear()
    folder = os.path.join(app.root_path, "static", "faces")

    if not os.path.exists(folder):
        return

    for file in os.listdir(folder):

        if file.endswith(".jpg"):

            roll = file.split("_")[0]

            path = os.path.join(folder, file)

            image = face_recognition.load_image_file(path)

            enc = face_recognition.face_encodings(image)

            if len(enc) > 0:

                if roll not in known_face_encodings:
                    known_face_encodings[roll] = []

                known_face_encodings[roll].append(enc[0])


# =====================================================
# HOME
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

        reconnect_db()

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

        return render_template("login.html",error="Invalid Login")

    return render_template("login.html")


# =====================================================
# STUDENT REGISTER
# =====================================================

@app.route("/register", methods=["GET","POST"])
def register():

    if request.method == "POST":

        reconnect_db()

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

        session["student_id"] = student_id

        return redirect("/register_face")

    return render_template("register.html")


# =====================================================
# FACE REGISTRATION PAGE
# =====================================================

@app.route("/register_face")
def register_face():

    if "student_id" not in session:
        return redirect("/student_login")

    return render_template("register_face.html")


# =====================================================
# SAVE FACE IMAGE
# =====================================================

@app.route("/save_face",methods=["POST"])
def save_face():

    if "student_id" not in session:
        return jsonify({"status":"login_required"})

    reconnect_db()

    student_id=session["student_id"]

    cursor.execute(
        "SELECT roll_number FROM students WHERE id=%s",
        (student_id,)
    )

    roll = cursor.fetchone()[0]

    data=request.get_json()

    image_data=data["image"].split(",")[1]

    image_bytes=base64.b64decode(image_data)

    folder=os.path.join(app.root_path,"static","faces")

    os.makedirs(folder,exist_ok=True)

    existing=[f for f in os.listdir(folder) if f.startswith(roll)]

    count=len(existing)+1

    path=f"{folder}/{roll}_{count}.jpg"

    with open(path,"wb") as f:
        f.write(image_bytes)

    load_known_faces()

    return jsonify({"status":"saved"})


# =====================================================
# QR SCAN PAGE
# =====================================================

@app.route("/scan_qr")
def scan_qr():

    if "student_id" not in session:
        return redirect("/student_login")

    return render_template("scan_qr.html")


# =====================================================
# ================= FACULTY =================
# =====================================================

@app.route("/faculty_register",methods=["GET","POST"])
def faculty_register():

    if request.method=="POST":

        reconnect_db()

        cursor.execute("""
        INSERT INTO faculty(name,email,password)
        VALUES(%s,%s,%s)
        """,(
            request.form.get("name"),
            request.form.get("email"),
            hash_password(request.form.get("password"))
        ))

        db.commit()

        return redirect("/faculty_login")

    return render_template("faculty_register.html")


@app.route("/faculty_login",methods=["GET","POST"])
def faculty_login():

    if request.method=="POST":

        reconnect_db()

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

            return redirect("/faculty_dashboard")

        return render_template("faculty_login.html",
                               error="Invalid Login")

    return render_template("faculty_login.html")


@app.route("/faculty_dashboard")
def faculty_dashboard():

    if "faculty_id" not in session:
        return redirect("/faculty_login")

    return render_template("faculty_dashboard.html")


# =====================================================
# QR GENERATION
# =====================================================

@app.route("/generate_qr")
def generate_qr():

    if "faculty_id" not in session:
        return redirect("/faculty_login")

    reconnect_db()

    cursor.execute("DELETE FROM sessions WHERE expiry_time < NOW()")

    db.commit()

    token=str(uuid.uuid4())

    expiry=datetime.datetime.now()+datetime.timedelta(minutes=10)

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
        "expires":600
    })


# =====================================================
# QR + GPS VERIFICATION
# =====================================================

@app.route("/verify_qr",methods=["POST"])
def verify_qr():

    if "student_id" not in session:
        return jsonify({"status":"login_required"})

    reconnect_db()

    data=request.get_json()

    token=data.get("token")
    lat=data.get("latitude")
    lon=data.get("longitude")

    college_lat = 17.489651
    college_lon = 78.316076

    distance=((lat-college_lat)**2+(lon-college_lon)**2)**0.5

    if distance > 0.002:
        return jsonify({"status":"location_failed"})

    cursor.execute(
        "SELECT expiry_time FROM sessions WHERE qr_token=%s",
        (token,)
    )

    data=cursor.fetchone()

    if not data:
        return jsonify({"status":"invalid"})

    if datetime.datetime.now()>data[0]:
        return jsonify({"status":"expired"})

    return jsonify({"status":"valid"})


# =====================================================
# FACE VERIFY PAGE
# =====================================================

@app.route("/verify_face")
def verify_face():

    if "student_id" not in session:
        return redirect("/student_login")

    return render_template("verify_face.html")


# =====================================================
# FACE VERIFY API
# =====================================================

@app.route("/face_verify_api",methods=["POST"])
def face_verify_api():

    if "student_id" not in session:
        return jsonify({"status":"login_required"})

    reconnect_db()

    student_id=session["student_id"]

    cursor.execute(
        "SELECT roll_number FROM students WHERE id=%s",
        (student_id,)
    )

    roll = cursor.fetchone()[0]

    data=request.get_json()

    image_data=data["image"].split(",")[1]

    image_bytes=base64.b64decode(image_data)

    np_arr=np.frombuffer(image_bytes,np.uint8)

    frame=cv2.imdecode(np_arr,cv2.IMREAD_COLOR)

    folder=os.path.join(app.root_path,"static","faces")

    known_encodings = known_face_encodings.get(roll, [])
    if len(known_encodings) == 0:
        return jsonify({"status":"no_registered_face"})

    face_locations=face_recognition.face_locations(frame)

    encodings=face_recognition.face_encodings(frame,face_locations)

    if len(encodings)==0:
        return jsonify({"status":"no_face"})

    distances=face_recognition.face_distance(
        known_encodings,encodings[0]
    )

    best_match=min(distances)

    if best_match < 0.55:

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
            "student":session["student_name"]
        })

    return jsonify({"status":"face_failed"})


# =====================================================
# LIVE ATTENDANCE COUNT
# =====================================================

@app.route("/live_count")
def live_count():

    reconnect_db()

    cursor.execute("""
    SELECT COUNT(DISTINCT student_id)
    FROM attendance
    WHERE date=CURDATE()
    """)

    count=cursor.fetchone()[0]

    return jsonify({"count":count})


# =====================================================
# LIVE ATTENDANCE LIST
# =====================================================

@app.route("/live_attendance")
def live_attendance():

    reconnect_db()

    cursor.execute("""
    SELECT s.name, s.roll_number, a.time
    FROM attendance a
    JOIN students s ON a.student_id=s.id
    WHERE a.date=CURDATE()
    ORDER BY a.time DESC
    """)

    rows=cursor.fetchall()

    students=[]

    for row in rows:
        students.append({
            "name":row[0],
            "roll":row[1],
            "time":str(row[2])
        })

    return jsonify(students)


# =====================================================
# ================= ADMIN =================
# =====================================================

@app.route("/admin_register",methods=["GET","POST"])
def admin_register():

    if request.method=="POST":

        reconnect_db()

        cursor.execute("""
        INSERT INTO admin(username,password)
        VALUES(%s,%s)
        """,(
            request.form.get("username"),
            hash_password(request.form.get("password"))
        ))

        db.commit()

        return redirect("/admin_login")

    return render_template("admin_register.html")


@app.route("/admin_login",methods=["GET","POST"])
def admin_login():

    if request.method=="POST":

        reconnect_db()

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

            return redirect("/admin_dashboard")

        return render_template("admin_login.html",
                               error="Invalid Login")

    return render_template("admin_login.html")


@app.route("/admin_dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect("/admin_login")

    reconnect_db()

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
# ADMIN ANALYTICS API
# =====================================================

@app.route("/attendance_stats")
def attendance_stats():

    reconnect_db()

    cursor.execute("""
    SELECT date, COUNT(*)
    FROM attendance
    GROUP BY date
    ORDER BY date DESC
    LIMIT 7
    """)

    rows=cursor.fetchall()

    days=[]
    counts=[]

    for r in rows:
        days.append(str(r[0]))
        counts.append(r[1])

    days.reverse()
    counts.reverse()

    return jsonify({
        "days":days,
        "counts":counts
    })


# =====================================================
# GET ALL STUDENTS (ADMIN)
# =====================================================

@app.route("/get_students")
def get_students():

    reconnect_db()

    cursor.execute("""
    SELECT name, roll_number, email
    FROM students
    """)

    rows=cursor.fetchall()

    students=[]

    for r in rows:
        students.append({
            "name":r[0],
            "roll":r[1],
            "email":r[2]
        })

    return jsonify(students)


# =====================================================
# EXPORT ATTENDANCE TO EXCEL
# =====================================================

@app.route("/export_attendance")
def export_attendance():

    if "admin" not in session:
        return redirect("/admin_login")

    reconnect_db()

    cursor.execute("""
    SELECT s.name, s.roll_number, a.date, a.time
    FROM attendance a
    JOIN students s ON a.student_id=s.id
    ORDER BY a.date DESC
    """)

    rows=cursor.fetchall()

    data=[]

    for r in rows:
        data.append({
            "Name":r[0],
            "Roll Number":r[1],
            "Date":str(r[2]),
            "Time":str(r[3])
        })

    df=pd.DataFrame(data)

    file_path="attendance_report.xlsx"

    df.to_excel(file_path,index=False)

    return send_file(file_path,as_attachment=True)


# =====================================================
# LOGOUT
# =====================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =====================================================
# RUN SERVER (RENDER READY)
# =====================================================
@app.teardown_appcontext
def close_db(error):
    global db
    try:
        if db.is_connected():
            db.close()
    except:
        pass


if __name__ == "__main__":
    load_known_faces()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)