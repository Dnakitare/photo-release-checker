import face_recognition
import numpy as np
import cv2
from PIL import Image
import io
import os

def load_known_faces(known_faces_dir):
    known_faces = []
    known_names = []
    if not os.path.exists(known_faces_dir):
        raise FileNotFoundError(f"The directory {known_faces_dir} does not exist.")
    
    for filename in os.listdir(known_faces_dir):
        if filename.endswith(".jpg") or filename.endswith(".png"):
            image_path = os.path.join(known_faces_dir, filename)
            try:
                image = face_recognition.load_image_file(image_path)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    encoding = encodings[0]
                    known_faces.append(encoding)
                    known_names.append(os.path.splitext(filename)[0])
                else:
                    print(f"No encodings found in {image_path}")
            except Exception as e:
                print(f"Error processing file {image_path}: {e}")
    return known_faces, known_names

def resize_image(image, width=800):
    aspect_ratio = width / float(image.size[0])
    height = int(image.size[1] * aspect_ratio)
    return image.resize((width, height), Image.LANCZOS)

def scan_photo_from_memory(photo_stream, known_faces, known_names):
    try:
        image = Image.open(io.BytesIO(photo_stream))
        image = resize_image(image)
        image = image.convert("RGB")  # Ensure image is in RGB format
        image = np.array(image)
        
        face_locations = face_recognition.face_locations(image)
        face_encodings = face_recognition.face_encodings(image, face_locations)
        
        matches_found = []
        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            matches = face_recognition.compare_faces(known_faces, face_encoding)
            if True in matches:
                first_match_index = matches.index(True)
                name = known_names[first_match_index]
                matches_found.append(name)
                cv2.rectangle(image, (left, top), (right, bottom), (0, 0, 255), 2)
                cv2.putText(image, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        _, buffer = cv2.imencode('.jpg', cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        return matches_found, buffer.tobytes()
    except Exception as e:
        print(f"Error in scan_photo_from_memory: {e}")
        raise