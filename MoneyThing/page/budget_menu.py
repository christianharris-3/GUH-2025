import streamlit as st
import src.utils as utils
import datetime

from src.db_manager import DatabaseManager


def budget_menu_ui():
    db_manager = DatabaseManager()
    st.markdown("# Budgeting")

    view, create = st.columns([1,1])

    create_view_ui(view, db_manager)

    create_budget_ui(create, db_manager)


def create_view_ui(container, db_manager):
    budgets = db_manager.db.execute_sql("SELECT * FROM Budgets").fetchall()
    # [(1, 54, 40, 'Week', 1), (2, 55, 40, 'Week', 1), (3, 56, 40, 'Month', 1)]

    for budget in budgets:
        cont = container.container(border=True)
        time = budget[3]
        spending_limit = budget[2]
        category_id = budget[1]
        category = db_manager.categories.get_db_row(category_id)
        cont.markdown(f"### Budget of £{spending_limit} over a {time} in {category}")

        spent_so_far = db_manager.transactions.db_data
        spent_so_far["date_obj"] = spent_so_far["date"].apply(utils.string_to_date)

        if time == "Week":
            progress = datetime.date.today().weekday()
            period_days = 7
            cutoff_date = datetime.date.today()-datetime.timedelta(days=progress)
        elif time == "Month":
            cutoff_date = datetime.date.today()
            progress = cutoff_date.day
            period_days = 30
            cutoff_date = datetime.date(year=cutoff_date.year, month=cutoff_date.month, day=1)
        elif time == "Year":
            cutoff_date = datetime.date.today()
            progress = cutoff_date.month*30+cutoff_date.day
            period_days = 365
            cutoff_date = datetime.date(year=cutoff_date.year, month=1, day=1)
        else:
            cutoff_date = datetime.date.today()
            progress = 0
            period_days = 7

        spent_so_far = spent_so_far[spent_so_far["date_obj"] >= cutoff_date]
        spending = sum(spent_so_far["override_money"])
        time_progress = max(min(progress/period_days, 1),0)
        spending_progress = max(min(min(spending, spending_limit)/spending_limit, 1),0)

        cont.markdown(f"Money Used:   £{spending:.2f}/£{spending_limit:.2f}")
        cont.progress(spending_progress)

        cont.markdown(f"Time Progress:   {progress}/{period_days} days")
        cont.progress(time_progress)

        if spending_progress > time_progress:
            cont.markdown(f"You are behind schedule, to hit this goal you need to reduce spending!")
        else:
            cont.markdown("You are ahead of schedule, keep it up to win the reward!")

# def get_all_child_categories(db_manager, category_id):
#     data = set(category_id)
#     while 1:
#         updated_data = data.copy()
#         for item in data:
#             filtered = db_manager.categories.get_filtered_df("parent_category_id", item)
#             updated_data.update(set(filtered["category_id"]))


def create_budget_ui(con, db_manager):
    if st.session_state.get("queue_delete_budget_input", False):
        st.session_state["queue_delete_budget_input"] = False
        del st.session_state["budget_spending_limit_input"]
        del st.session_state["budget_time_period_input"]
        del st.session_state["budget_category_name_input"]

    container = con.container(border=True)
    categories = db_manager.get_all_categories()
    categories.insert(0, "All Categories")

    container.markdown("## Create Budget")
    spending_limit = container.number_input("Spending Limit", min_value=0, key="budget_spending_limit_input")
    time_period = container.selectbox("Time Period", ["Week", "Month", "Year"], key="budget_time_period_input")
    category = container.selectbox("Category", categories, key="budget_category_name_input")

    if container.button("Add Budget"):
        category_id = db_manager.categories.get_filtered_df("name", category).iloc[0]["category_id"]
        db_manager.db.create_row("Budgets", {"spending_limit": spending_limit, "time_period": time_period,
                                             "category_id": category_id})
        st.session_state["queue_delete_budget_input"] = True
