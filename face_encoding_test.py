import face_recognition

image = face_recognition.load_image_file(
    "static/faces/12.jpg"
)

encodings = face_recognition.face_encodings(image)

if encodings:
    print("✅ Face encoding successful")
else:
    print("❌ Face not detected")