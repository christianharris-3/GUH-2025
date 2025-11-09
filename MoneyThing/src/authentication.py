import streamlit as st
from src.sql_database import SQLDatabase
from src.logger import log
import pandas as pd
import bcrypt
from src.backup_maker import make_backup

def st_auth_ui():
    users_df = load_users()

    if st.session_state["authenticated"]:
        logged_in_ui(users_df)
        return

    _, middle, _ = st.columns([0.3,0.4,0.3])

    if "auth_page" not in st.session_state:
        st.session_state["auth_page"] = "login"

    with middle.container(border=True):
        if st.session_state["auth_page"] == "login":
            if st.session_state["authenticated"]:
                logged_in_ui(users_df)
            else:
                login_ui(users_df)
        else:
            register_ui(users_df)

def logged_in_ui(users_df):
    user_row = users_df[users_df["user_id"] == st.session_state["current_user_id"]].iloc[0]
    st.markdown(f"# Hello {user_row['username']}!")

    vouchers_container = st.container(border=True)
    top_bar = vouchers_container.columns([3.5,1])
    top_bar[0].markdown("## Vouchers")
    top_bar[1].markdown(f"### Tokens: 🪙{st.session_state.get('current_user_tokens', '?')}")

    sql = SQLDatabase()
    vouchers = sql.execute_sql("""
    SELECT *
    FROM Vouchers
    JOIN MetaData ON Vouchers.meta_data_id = MetaData.meta_data_id
    WHERE MetaData.user_id = ? AND MetaData.row_deleted = 0;""", [sql.user_id]).fetchall()

    render_vouchers(vouchers_container, vouchers)

    st.markdown("# Recent Transactions")
    st.markdown("## details about current budgeting")

def render_vouchers(vouchers_container, vouchers):
    cols = vouchers_container.columns(3)
    for i, voucher in enumerate(vouchers):
        con = cols[i % 3].container(border=True)
        con.markdown(f"### {voucher[2]} Voucher")
        col1, col2 = con.columns([1, 1])
        col1.markdown(f"### {voucher[4]}% Off")
        col2.markdown("")
        col2.markdown(f"Expires {voucher[5]}")

@st.dialog("Change Password")
def change_password_ui(user_row):
    current = st.text_input("Current Password", type="password")
    password1 = st.text_input("New Password", type="password")
    password2 = st.text_input("Repeat New Password", type="password")
    if not (current == "" or password1 == "" or password2 == ""):
        output = None
        if not check_password(current, user_row["password_hash"]):
            output = "Current Password doesn't match!"
        if password1 != password2:
            output = "New passwords do not match!"
        if output is not None:
            st.markdown(output)
        elif st.button("Change Password"):
            st.toast("Password Changed!", icon="✔️")
            change_password(user_row["user_id"], password1)
            st.rerun()

@st.dialog("Change Username")
def change_username_ui(user_row, used_usernames):
    new_username = st.text_input("New Username")
    if new_username != "":
        if new_username.lower() in map(lambda name: name.lower(), used_usernames):
            st.markdown("Username Already Used")
        elif st.button("Change Username"):
            st.toast("Username Changed!", icon="✔️")
            change_username(user_row["user_id"], new_username)
            st.rerun()

def login_ui(users_df):
    left, right = st.columns([0.6, 0.4], vertical_alignment="center")

    left.markdown("### Login")
    if right.button("Register", use_container_width=True):
        st.session_state["auth_page"] = "register"
        st.rerun()
    username = st.text_input("Username", key="login_username_input")
    password = st.text_input("Password", type="password", key="login_password_input")
    if st.button("Login", use_container_width=True):
        user_id = login(users_df, username, password)
        if user_id is None:
            st.toast("Incorrect Username or password", icon="⛔")
        else:
            st.toast("Logged in successfully!", icon="✔️")
            log(f"Logging In with User ID: {user_id}")
            st.session_state["authenticated"] = True
            st.session_state["current_user_id"] = user_id
            st.session_state["current_user_tokens"] = users_df[users_df["user_id"]==user_id].iloc[0]["tokens"]
            st.rerun()

def register_ui(users_df):
    left, right = st.columns([0.6, 0.4], vertical_alignment="center")

    left.markdown("### Register")
    if right.button("Login", use_container_width=True, key="swap_to_login_ui_button"):
        st.session_state["auth_page"] = "login"
        st.rerun()
    username = st.text_input("Username", key="register_username_input")
    password1 = st.text_input("Password", type="password", key="register_password_1_input")
    password2 = st.text_input("Repeat Password", type="password", key="register_password_2_input")
    if st.button("Register", use_container_width=True):
        if password1 != password2:
            st.toast("Passwords must be the same", icon="⛔")
        elif username is None or username == "":
            st.toast("Username must be at least 1 character", icon="⛔")
        elif username.lower() in map(lambda string: string.lower(), users_df["username"].values):
            st.toast("Username already in use, please choose another", icon="⛔")
        else:
            register_user(username, password1)
            st.session_state["auth_page"] = "login"
            st.toast("Account Registered", icon="✔️")
            st.rerun()

def load_users():
    db = SQLDatabase()
    db.create_tables()

    cursor = db.execute_sql(
        "SELECT * FROM Users",
        do_log=False
    )
    users = cursor.fetchall()
    users_df = pd.DataFrame(
        users,
        columns=[
            "user_id",
            "username",
            "password_hash",
            "tokens"
        ]

    )

    return users_df

def register_user(username, password):
    db = SQLDatabase()
    db.add_user(
        username,
        hash_password(password)
    )

def change_password(user_id, new_password):
    db = SQLDatabase()
    db.update_row(
        "Users",
        {
            "password_hash": hash_password(new_password)
        },
        "user_id",
        user_id
    )

def change_username(user_id, new_username):
    db = SQLDatabase()
    db.update_row(
        "Users",
        {
            "username": new_username
        },
        "user_id",
        user_id
    )

def hash_password(password):
    password_hash = bcrypt.hashpw(
        password.encode(),
        bcrypt.gensalt()
    ).decode()
    return password_hash

def check_password(password, password_hash):
    return bcrypt.checkpw(
        password.encode(),
        password_hash.encode()
    )

def login(user_df, username, password):
    filtered_df = user_df[user_df["username"].str.lower() == username.lower()]
    if len(filtered_df) == 0:
        return None
    row = filtered_df.iloc[0]
    password_hash = row["password_hash"]
    if check_password(password, password_hash):
        return int(row["user_id"])
    return None

def logout():
    log("Logged Out")
    keys = list(st.session_state.keys())
    for key in keys:
        del st.session_state[key]