# models.py
import os
import streamlit as st
from datetime import datetime, timedelta
from supabase import create_client, Client

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

ADMIN_EMAIL = "dncanada@mcm.edu.ph"

def _check_admin(email):
    return bool(email and ("admin" in email or email == ADMIN_EMAIL))

def authenticate_user(email, password):
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        user = response.user
        session = response.session

        return {
            "success": True,
            "email": user.email,
            "is_admin": _check_admin(user.email),
            "refresh_token": session.refresh_token,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def restore_session(refresh_token):
    """Restore a login from a saved refresh token (used after a page refresh)."""
    try:
        response = supabase.auth.refresh_session(refresh_token)
        user = response.user
        session = response.session
        if not user or not session:
            return None
        return {
            "email": user.email,
            "is_admin": _check_admin(user.email),
            "refresh_token": session.refresh_token,  # refresh tokens rotate
        }
    except Exception:
        return None

def save_to_supabase(post, image_file=None):
    image_url = None
    if image_file is not None:
        file_ext = image_file.name.split(".")[-1]
        file_path = f"{post.post_id}.{file_ext}"
        supabase.storage.from_("item-images").upload(
            path=file_path,
            file=image_file.getvalue(),
            file_options={"content-type": image_file.type, "upsert": "true"}
        )
        image_url = supabase.storage.from_("item-images").get_public_url(file_path)

    data = {
        "post_id": post.post_id,
        "date_posted": post.date_posted,
        "username": post.user.username,
        "institutional_id": post.user.institutional_id,
        "item_name": post.item.item_name,
        "description": post.item.description,
        "category_name": post.item.category.category_name,
        "campus_location": post.item.campus_location,
        "image_url": image_url,
        "status": post.item.tracking.current_status,
        "date_claimed": post.item.tracking.date_claimed
    }
    supabase.table("posts").insert(data).execute()

def load_database(categories_list):
    purge_expired_claims()
    response = supabase.table("posts").select("*").execute()
    data = response.data

    loaded_posts = []
    for d in data:
        user = User(d["username"], d["institutional_id"])
        cat = next((c for c in categories_list if c.category_name == d["category_name"]), categories_list[3])

        item = Item(d["item_name"], d["description"], cat, campus_location=d.get("campus_location", "RSY Building"))
        item.image_url = d.get("image_url")
        item.tracking.current_status = d.get("status", "Lost")
        item.tracking.date_claimed = d.get("date_claimed")

        post = Post(d["post_id"], d["date_posted"], user, item)
        loaded_posts.append(post)
    return loaded_posts

def update_status_in_supabase(post_id, new_status):
    date_claimed_val = datetime.now().isoformat() if new_status == "Claimed" else None
    supabase.table("posts").update({
        "status": new_status,
        "date_claimed": date_claimed_val
    }).eq("post_id", post_id).execute()

def purge_expired_claims():
    threshold = (datetime.now() - timedelta(days=7)).isoformat()
    supabase.table("posts") \
        .delete() \
        .eq("status", "Claimed") \
        .lt("date_claimed", threshold) \
        .execute()

# --- OOP Classes ---
class Institution:
    def __init__(self, institution_name, campus_location):
        self.institution_name = institution_name
        self.campus_location = campus_location

    def get_details(self):
        return f"{self.institution_name} - {self.campus_location}"

class User:
    def __init__(self, username, institutional_id, is_admin=False):
        self.username = username
        self.institutional_id = institutional_id
        self.is_admin = is_admin

class Category:
    def __init__(self, category_name, category_code):
        self.category_name = category_name
        self.category_code = category_code

class Tracking:
    def __init__(self, tracking_id, current_status="Lost"):
        self.tracking_id = tracking_id
        self.current_status = current_status
        self.date_claimed = None

    def update_tracking_status(self, new_status):
        self.current_status = new_status
        if new_status == "Claimed":
            self.date_claimed = datetime.now().isoformat()

class Item:
    def __init__(self, item_name, description, category, campus_location="RSY Building"):
        self.item_name = item_name
        self.description = description
        self.category = category
        self.campus_location = campus_location
        self.image_url = None
        self.tracking = Tracking(tracking_id=f"TRK-{id(self)}")

class Post:
    def __init__(self, post_id, date_posted, user, item):
        self.post_id = post_id
        self.date_posted = date_posted
        self.user = user
        self.item = item
