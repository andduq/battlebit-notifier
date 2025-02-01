from firebase_admin import firestore, credentials, initialize_app, storage

import os

cred = credentials.Certificate("firebase-credentials.json")
initialize_app(cred, {
    'storageBucket': 's1k-448604.firebasestorage.app'
})
db = firestore.client()
bucket = storage.bucket()

def get_firestore_client():
    """Returns the Firestore client instance."""
    return db

def get_storage_bucket():
    """Returns the Firebase Storage bucket instance."""
    return bucket