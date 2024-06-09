import face_recognition
import os
import cv2

def load_known_faces(known_faces_dir):
    known_faces = []
    known_names = []
    for filename in os.listdir(known_faces_dir):
        image = face_recognition.load_image_file(os.path.join(known_faces_dir, filename))
        encodings = face_recognition.face_encodings(image)
        if encodings:
            encoding = encodings[0]
            known_faces.append(encoding)
            known_names.append(os.path.splittext(filename)[0])
    return known_faces, known_names

def scan_photo(photo_path, known_faces, known_names):
    image = face_recognition.load_image_file(photo_path)
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
        
    output_path = F"static/results/{os.path.basename(photo_path)}"
    cv2.imwrite(output_path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    return matches_found, output_path