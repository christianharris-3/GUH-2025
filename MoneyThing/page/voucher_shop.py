import streamlit as st
from src.db_manager import DatabaseManager
import random, datetime

def voucher_shop_ui():
    db_manager = DatabaseManager()

    vendors = db_manager.get_all_vendor_names()
    if vendors == []:
        vendors = ["Tesco", "Lidl", "Asda"]


    st.markdown("# Voucher Shop")


    if "stored_vouchers" in st.session_state:
        vouchers = st.session_state["stored_vouchers"]
    else:
        vouchers = make_random_vouchers(random.randint(8,12), vendors)
        st.session_state["stored_vouchers"] = vouchers

    render_vouchers_prices(st, vouchers, db_manager)


def make_random_vouchers(num, vendors):
    vouchers = []
    for a in range(num):
        percentage = random.choice([5,5,5,5,10,10,10,15,15,20,25])
        company = random.choice(vendors)
        price = int(round(percentage*500*(random.random()+0.5),-2))
        vouchers.append({"vendor_name": company, "percent_off": percentage, "price": price})
    return vouchers


def render_vouchers_prices(vouchers_container, vouchers, db_manager):
    if len(vouchers) == 0:
        vouchers_container.markdown("No Vouchers Available right now, please come back later.")
    cols = vouchers_container.columns(3)
    for i, voucher in enumerate(vouchers):
        con = cols[i % 3].container(border=True)
        col1, col2 = con.columns([2, 1])
        col1.markdown(f"### {voucher['vendor_name']} Voucher")
        col2.button("Buy", key=f"buy_item_{i}", width="stretch", on_click=buy_voucher,args=(i, db_manager))
        col1, col2 = con.columns([2, 1])
        col1.markdown(f"### {voucher['percent_off']}% Off")
        col2.markdown("")
        col2.markdown(f"Price: 🪙{voucher['price']}")

def buy_voucher(i, db_manager):
    voucher = st.session_state["stored_vouchers"][i]
    current_tokens = st.session_state["current_user_tokens"]
    if current_tokens >= voucher["price"]:
        db_manager.db.execute_sql(
            f"UPDATE Users SET tokens={st.session_state["current_user_tokens"]} WHERE user_id={db_manager.db.user_id}"
        )
        st.session_state["current_user_tokens"] -= voucher["price"]
        del voucher["price"]
        voucher["expire_date"] = datetime.date.today()+datetime.timedelta(days=7)
        db_manager.db.create_row("Vouchers", voucher)
        del st.session_state["stored_vouchers"][i]