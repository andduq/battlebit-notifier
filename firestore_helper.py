from firebase_admin import firestore, credentials, initialize_app
import os

cred = credentials.Certificate("firebase-credentials.json")
initialize_app(cred)
db = firestore.client()

def get_firestore_client():
    """Returns the Firestore client instance."""
    return db