"""Détection locale et recherche faciale AWS Rekognition 1:N."""

from functools import lru_cache

import boto3
import cv2
import numpy as np
from django.conf import settings


MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _setting(name, default):
    return getattr(settings, name, default)


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "rekognition",
        region_name=_setting("AWS_REGION", "eu-west-1"),
    )


def _decode(image_bytes):
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Image illisible ; fournissez un JPEG, PNG ou WebP valide.")
    return image


def detect_face_count(image_bytes):
    image = _decode(image_bytes)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    detected = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60),
    )
    return len(detected)


def normalize_image(image_bytes, max_dimension=1600):
    image = _decode(image_bytes)
    height, width = image.shape[:2]
    scale = min(1.0, max_dimension / max(height, width))
    if scale < 1.0:
        image = cv2.resize(
            image,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not success:
        raise ValueError("Impossible de convertir l'image pour Rekognition.")
    return encoded.tobytes()


def ensure_collection():
    client = _client()
    try:
        client.create_collection(
            CollectionId=_setting("AWS_REKOGNITION_COLLECTION", "campusconnect-auth-faces")
        )
    except client.exceptions.ResourceAlreadyExistsException:
        return


def enroll_face(user_id, reference_image_bytes):
    """Indexe une référence sous l'identifiant du compte Auth existant."""
    if not reference_image_bytes or len(reference_image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("La photo de référence doit peser au maximum 5 Mo.")
    if detect_face_count(reference_image_bytes) != 1:
        raise ValueError("La photo de référence doit contenir exactement un visage.")

    response = _client().index_faces(
        CollectionId=_setting("AWS_REKOGNITION_COLLECTION", "campusconnect-auth-faces"),
        Image={"Bytes": normalize_image(reference_image_bytes)},
        ExternalImageId=str(user_id),
        MaxFaces=1,
        QualityFilter="AUTO",
        DetectionAttributes=[],
    )
    records = response.get("FaceRecords", [])
    if not records:
        raise ValueError("Rekognition n'a pas pu indexer le visage.")
    return {
        "user_id": str(user_id),
        "face_id": records[0]["Face"]["FaceId"],
    }


def recognize_face(live_image_bytes):
    """Vérifie la présence d'un visage puis cherche le compte correspondant."""
    if not live_image_bytes or len(live_image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("L'image caméra doit peser au maximum 5 Mo.")
    count = detect_face_count(live_image_bytes)
    if count == 0:
        return {"status": "no_face", "face_count": 0}
    if count > 1:
        return {"status": "multiple_faces", "face_count": count}

    response = _client().search_faces_by_image(
        CollectionId=_setting("AWS_REKOGNITION_COLLECTION", "campusconnect-auth-faces"),
        Image={"Bytes": normalize_image(live_image_bytes)},
        MaxFaces=1,
        FaceMatchThreshold=_setting("FACE_MATCH_THRESHOLD", 80.0),
    )
    matches = response.get("FaceMatches", [])
    if not matches:
        return {"status": "unknown", "face_count": 1}

    best = max(matches, key=lambda item: item["Similarity"])
    user_id = best.get("Face", {}).get("ExternalImageId")
    if not user_id:
        return {"status": "unknown", "face_count": 1}
    return {
        "status": "recognized",
        "face_count": 1,
        "user_id": str(user_id),
        "face_id": best.get("Face", {}).get("FaceId"),
        "similarity": round(float(best["Similarity"]), 2),
    }
