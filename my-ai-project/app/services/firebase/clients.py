from functools import lru_cache
from typing import Any

from app.config import settings


@lru_cache(maxsize=4)
def _firestore_client(project_id: str) -> Any:
    from google.cloud import firestore

    return firestore.Client(project=project_id)


def get_firestore_client() -> Any:
    project_id = settings.FIRESTORE_PROJECT_ID
    if not project_id:
        raise RuntimeError("Firebase Firestore project is not configured.")
    return _firestore_client(project_id)


def get_firestore_collection(collection_name: str) -> Any:
    return get_firestore_client().collection(collection_name)


def get_firestore_document(collection_name: str, document_id: str) -> Any:
    return get_firestore_collection(collection_name).document(document_id)


def get_storage_bucket() -> Any:
    project_id = settings.FIRESTORE_PROJECT_ID
    bucket_name = settings.FIREBASE_STORAGE_BUCKET
    if not project_id:
        raise RuntimeError("Firebase project ID is not configured.")
    if not bucket_name:
        raise RuntimeError(
            "Firebase Storage bucket is not configured. Set FIREBASE_STORAGE_BUCKET."
        )

    from google.cloud import storage

    return storage.Client(project=project_id).bucket(bucket_name)
