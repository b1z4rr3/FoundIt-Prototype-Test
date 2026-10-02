# app.py
import time
import streamlit as st
import datetime
import extra_streamlit_components as stx
from models import (Institution, User, Category, Tracking, Item, Post, load_database,
                    save_to_supabase, update_status_in_supabase, authenticate_user, restore_session)

st.set_page_config(page_title="FoundIt - Campus Lost & Found", page_icon="", layout="centered")

COOKIE_NAME = "foundit_refresh_token"
COOKIE_DAYS = 7

cookie_manager = stx.CookieManager()

school = Institution("Mapúa Malayan Colleges Mindanao", "Davao City")

if "categories" not in st.session_state:
    st.session_state.categories = [
        Category("Electronics", "CAT-01"),
        Category("Tumblers/Bottles", "CAT-02"),
        Category("IDs/Cards", "CAT-03"),
        Category("Others", "CAT-04")
    ]

if "posts" not in st.session_state:
    st.session_state.posts = load_database(st.session_state.categories)

if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "logged_out" not in st.session_state:
    st.session_state.logged_out = False

# --- AUTO-LOGIN FROM COOKIE (survives page refresh) ---
if not st.session_state.current_user and not st.session_state.logged_out:
    saved_token = cookie_manager.get(COOKIE_NAME)
    if saved_token:
        restored = restore_session(saved_token)
        if restored:
            st.session_state.current_user = User(
                username=restored["email"].split("@")[0],
                institutional_id=restored["email"],
                is_admin=restored["is_admin"],
            )
            cookie_manager.set(
                COOKIE_NAME,
                restored["refresh_token"],
                expires_at=datetime.datetime.now() + datetime.timedelta(days=COOKIE_DAYS),
            )
            time.sleep(0.5)  # give the browser a moment to store the new cookie
            st.rerun()

st.title("FoundIt: Campus Lost & Found Hub")
st.caption(f"{school.get_details()}")
st.markdown("---")

# --- AUTHENTICATION ---
if not st.session_state.current_user:
    st.subheader("Login")
    with st.form("login_form"):
        email = st.text_input("Institutional Email")
        password = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Login")

        if submit_login:
            auth_result = authenticate_user(email, password)
            if auth_result["success"]:
                # Create a user session object
                logged_user = User(username=email.split("@")[0], institutional_id=email, is_admin=auth_result["is_admin"])
                st.session_state.current_user = logged_user
                st.session_state.logged_out = False
                cookie_manager.set(
                    COOKIE_NAME,
                    auth_result["refresh_token"],
                    expires_at=datetime.datetime.now() + datetime.timedelta(days=COOKIE_DAYS),
                )
                time.sleep(0.5)  # give the browser a moment to store the cookie
                st.rerun()
            else:
                st.error(f"Authentication failed: {auth_result['error']}")
else:
    st.sidebar.write(f"**{st.session_state.current_user.username}**")
    st.sidebar.caption(f"Role: {'Administrator' if st.session_state.current_user.is_admin else 'Student/Faculty'}")

    if st.sidebar.button("Logout"):
        cookie_manager.delete(COOKIE_NAME)
        st.session_state.current_user = None
        st.session_state.logged_out = True
        time.sleep(0.5)  # give the browser a moment to clear the cookie
        st.rerun()

    st.sidebar.markdown("---")

    # Role-based navigation setup
    if st.session_state.current_user.is_admin:
        navigation = st.sidebar.radio("Navigation", ["View Feed", "Report Item", "Filter by Campus", "Update Tracking Status"])
    else:
        navigation = st.sidebar.radio("Navigation", ["View Feed", "Filter by Campus"])
        st.sidebar.info("You are logged in as a standard user. Only authorized administrators can report or update items.")

    # --- 1. VIEW FEED ---
    if navigation == "View Feed":
        st.header("Recent Dashboard Feed")
        search_query = st.text_input("Search feed (title, category, description):", "").strip().lower()

        posts_to_display = st.session_state.posts[::-1]

        if search_query:
            posts_to_display = [
                p for p in posts_to_display
                if search_query in p.item.item_name.lower() or
                   search_query in p.item.category.category_name.lower() or
                   search_query in p.item.description.lower()
            ]

        if not posts_to_display:
            st.info("No items match your search.")
        else:
            for post in posts_to_display:
                with st.container():
                    st.subheader(f"{post.item.item_name}")
                    if post.item.image_url:
                        st.image(post.item.image_url, width=300)
                    st.write(f"**Status:** `{post.item.tracking.current_status}`")
                    st.write(f"**Campus Location:** `{post.item.campus_location}`")
                    st.write(f"**Category:** {post.item.category.category_name}")
                    st.write(f"**Description:** {post.item.description}")
                    st.caption(f"Posted by {post.user.username} on {post.date_posted}")
                    st.markdown("---")

    # --- 2. REPORT ITEM (Admin Only) ---
    elif navigation == "Report Item":
        st.header("Report a Lost Item")
        with st.form("report_form"):
            item_name = st.text_input("Item Name")
            description = st.text_area("Description / Distinguishing Features")
            campus_location = st.selectbox("Campus Holding Office", ["RSY Building", "RG Birrey"])

            cat_names = [cat.category_name for cat in st.session_state.categories]
            selected_cat_name = st.selectbox("Category", cat_names)

            uploaded_image = st.file_uploader("Upload Item Photo", type=["jpg", "jpeg", "png"])

            submit_post = st.form_submit_button("Post Item")

            if submit_post:
                if item_name.strip():
                    selected_cat = next(cat for cat in st.session_state.categories if cat.category_name == selected_cat_name)
                    new_item = Item(item_name, description, selected_cat, campus_location=campus_location)
                    today_date = datetime.date.today().strftime("%Y-%m-%d")
                    new_post = Post(f"POST-{int(datetime.datetime.now().timestamp())}", today_date, st.session_state.current_user, new_item)

                    save_to_supabase(new_post, image_file=uploaded_image)
                    st.session_state.posts = load_database(st.session_state.categories)
                    st.success("Item posted successfully and saved to Supabase!")
                else:
                    st.warning("Please provide an item name.")

    # --- 3. FILTER BY CAMPUS ---
    elif navigation == "Filter by Campus":
        st.header("Filter Feed by Campus Location")
        campus_choice = st.selectbox("Select Campus Building", ["RSY Building", "RG Birrey"])

        filtered_posts = [p for p in st.session_state.posts if p.item.campus_location == campus_choice]

        if not filtered_posts:
            st.info(f"No items found at {campus_choice}.")
        else:
            for post in filtered_posts[::-1]:
                st.markdown(f"### {post.item.item_name}")
                if post.item.image_url:
                    st.image(post.item.image_url, width=250)
                st.write(f"**Status:** `{post.item.tracking.current_status}` | **Category:** {post.item.category.category_name}")
                st.write(f"**Description:** {post.item.description}")
                st.markdown("---")

    # --- 4. UPDATE TRACKING STATUS (Admin Only) ---
    elif navigation == "Update Tracking Status":
        st.header("Update Item Status")
        if not st.session_state.posts:
            st.info("No items available to update.")
        else:
            post_options = {f"{p.item.item_name} ({p.item.tracking.current_status}) - {p.user.username}": p for p in st.session_state.posts}
            selected_option = st.selectbox("Select Item to Update", list(post_options.keys()))

            target_post = post_options[selected_option]
            new_status = st.radio("Select New Status", ["Lost", "Pending Claim", "Claimed"])

            if st.button("Apply Status Update"):
                target_post.item.tracking.update_tracking_status(new_status)
                update_status_in_supabase(target_post.post_id, new_status)
                st.session_state.posts = load_database(st.session_state.categories)
                st.success(f"Status updated to **{new_status}** in Supabase!")
                st.rerun()
