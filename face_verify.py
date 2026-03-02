import cv2
import face_recognition
import os
import numpy as np


# ==========================================
# REGISTER FACE
# ==========================================
def register_face(student_id):

    os.makedirs("static/faces", exist_ok=True)

    cam = cv2.VideoCapture(0)

    if not cam.isOpened():
        print("❌ Camera not detected")
        return False

    print("✅ Camera Started - Press S to capture")

    while True:
        ret, frame = cam.read()

        if not ret:
            break

        cv2.imshow("Register Face - Press S", frame)

        key = cv2.waitKey(1)

        # SAVE FACE
        if key == ord('s'):
            path = f"static/faces/{student_id}.jpg"
            cv2.imwrite(path, frame)
            print("✅ Face Saved:", path)
            break

        # CANCEL
        if key == ord('q'):
            cam.release()
            cv2.destroyAllWindows()
            return False

    cam.release()
    cv2.destroyAllWindows()

    return True


# ==========================================
# VERIFY FACE
# ==========================================
def verify_face(student_id):

    known_path = f"static/faces/{student_id}.jpg"

    if not os.path.exists(known_path):
        print("❌ Registered face not found")
        return False

    known_image = face_recognition.load_image_file(known_path)
    known_encoding = face_recognition.face_encodings(known_image)

    if len(known_encoding) == 0:
        print("❌ No face in saved image")
        return False

    known_encoding = known_encoding[0]

    cam = cv2.VideoCapture(0)

    print("✅ Verifying Face...")

    while True:
        ret, frame = cam.read()

        if not ret:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        faces = face_recognition.face_encodings(rgb)

        for face in faces:

            distance = face_recognition.face_distance(
                [known_encoding],
                face
            )[0]

            print("Distance:", distance)

            if distance < 0.45:
                cam.release()
                cv2.destroyAllWindows()
                print("✅ FACE VERIFIED")
                return True

        cv2.imshow("Face Verification", frame)

        if cv2.waitKey(1) == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

    return False