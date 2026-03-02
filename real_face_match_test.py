import face_recognition
import cv2
import os

# ---------------- LOAD ALL REGISTERED FACES ----------------

known_encodings = []
known_names = []

faces_dir = "static/faces"

for file in os.listdir(faces_dir):

    if file.endswith(".jpg"):

        path = os.path.join(faces_dir, file)

        image = face_recognition.load_image_file(path)
        encodings = face_recognition.face_encodings(image)

        if len(encodings) > 0:
            known_encodings.append(encodings[0])

            # filename without .jpg becomes name
            name = file.split(".")[0]
            known_names.append(name)

print("✅ Faces Loaded:", known_names)