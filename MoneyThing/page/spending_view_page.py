import streamlit as st
import pandas as pd
import src.utils as utils
from src.db_manager import DatabaseManager
from src.logger import log
from datetime import datetime, timedelta
import plotly.express as px


def get_all_child_category_ids(db_manager, parent_category_id):
    """
    Recursively get all child category IDs for a given parent category.
    Returns a list including the parent ID and all descendant IDs.
    """
    categories_df = db_manager.categories.db_data
    category_ids = [parent_category_id]
    
    # Find direct children
    children = categories_df[categories_df['parent_category_id'] == parent_category_id]
    
    for _, child in children.iterrows():
        child_id = child['category_id']
        # Recursively get children of this child
        category_ids.extend(get_all_child_category_ids(db_manager, child_id))
    
    return category_ids


def get_root_categories(db_manager):
    """
    Get only root categories (those without parents) and exclude their children.
    Returns DataFrame of root categories.
    """
    categories_df = db_manager.categories.db_data
    
    # Get categories with no parent (root categories)
    root_categories = categories_df[categories_df['parent_category_id'].isna()].copy()
    
    return root_categories


def get_weekly_spending_by_category(db_manager, category_id, category_name):
    """
    Get weekly spending data for a specific category INCLUDING all child categories.
    Gets all transactions for this category and its descendants, then groups by week.
    Returns a DataFrame with weeks and spending amounts.
    """
    print(f"\n=== Processing Category: {category_name} (ID: {category_id}) ===")
    
    # Get this category and all its children
    all_category_ids = get_all_child_category_ids(db_manager, category_id)
    print(f"Category IDs including children: {all_category_ids}")
    
    # Get all transactions for this category and its children
    transactions_df = db_manager.transactions.db_data
    print(f"Total transactions in DB: {len(transactions_df)}")
    
    category_transactions = transactions_df[transactions_df['category_id'].isin(all_category_ids)].copy()
    print(f"Transactions for this category (including children): {len(category_transactions)}")
    
    if category_transactions.empty:
        print("No transactions found - returning empty DataFrame")
        return pd.DataFrame(columns=['week_start', 'amount', 'category'])
    
    # Convert dates
    category_transactions['date'] = pd.to_datetime(category_transactions['date'], errors='coerce')
    category_transactions = category_transactions.dropna(subset=['date'])
    print(f"Transactions after date conversion: {len(category_transactions)}")
    
    if category_transactions.empty:
        print("No valid dates - returning empty DataFrame")
        return pd.DataFrame(columns=['week_start', 'amount', 'category'])
    
    # Get spending items for these transactions
    spending_items_df = db_manager.spending_items.db_data
    print(f"Total spending items in DB: {len(spending_items_df)}")
    
    transaction_spending = spending_items_df[
        spending_items_df['transaction_id'].isin(category_transactions['transaction_id'])
    ].copy()
    print(f"Spending items for this category's transactions: {len(transaction_spending)}")
    
    # If no spending items, use transaction-level override_money
    if transaction_spending.empty:
        print("No spending items found - using transaction override_money instead")
        # Use the transaction's override_money as the amount
        merged_data = category_transactions[['transaction_id', 'date', 'override_money']].copy()
        merged_data = merged_data.dropna(subset=['override_money'])
        
        if merged_data.empty:
            print("No override_money values - returning empty DataFrame")
            return pd.DataFrame(columns=['week_start', 'amount', 'category'])
        
        merged_data['amount'] = merged_data['override_money'].abs()
        print(f"Total amount from transactions: £{merged_data['amount'].sum():.2f}")
    else:
        # Calculate the amount spent per item
        transaction_spending['amount'] = transaction_spending['display_price'] * transaction_spending['num_purchased']
        print(f"Total amount calculated from spending items: £{transaction_spending['amount'].sum():.2f}")
        
        # Merge with transaction dates
        merged_data = transaction_spending.merge(
            category_transactions[['transaction_id', 'date']],
            on='transaction_id',
            how='left'
        )
    
    print(f"Merged data rows: {len(merged_data)}")
    
    # Get week start dates (Monday)
    merged_data['week_start'] = merged_data['date'].dt.to_period('W').apply(lambda r: r.start_time)
    
    # Group by week and sum
    weekly_spending = merged_data.groupby('week_start')['amount'].sum().reset_index()
    weekly_spending['category'] = category_name
    print(f"Weeks with spending: {len(weekly_spending)}")
    print(f"Weekly spending:\n{weekly_spending}")
    
    return weekly_spending


def get_category_breakdown(db_manager, parent_category_id, parent_category_name):
    """
    Get weekly spending broken down by each subcategory.
    Returns a DataFrame with separate rows for parent and each child category.
    """
    categories_df = db_manager.categories.db_data
    all_breakdown_data = []
    
    # Get direct children only (not all descendants)
    children = categories_df[categories_df['parent_category_id'] == parent_category_id]
    
    if children.empty:
        # No children, just return parent data
        return get_weekly_spending_by_category(db_manager, parent_category_id, parent_category_name)
    
    # Get spending for each child category (which will include their own children)
    for _, child in children.iterrows():
        child_id = child['category_id']
        child_name = child['name']
        
        if pd.isna(child_name):
            continue
        
        child_data = get_weekly_spending_by_category(db_manager, child_id, child_name)
        if not child_data.empty:
            all_breakdown_data.append(child_data)
    
    # Get transactions that belong ONLY to the parent (not to any child)
    all_child_ids = get_all_child_category_ids(db_manager, parent_category_id)
    all_child_ids.remove(parent_category_id)  # Remove parent from the list
    
    transactions_df = db_manager.transactions.db_data
    parent_only_transactions = transactions_df[transactions_df['category_id'] == parent_category_id].copy()
    
    if not parent_only_transactions.empty:
        # Calculate parent-only spending
        parent_only_transactions['date'] = pd.to_datetime(parent_only_transactions['date'], errors='coerce')
        parent_only_transactions = parent_only_transactions.dropna(subset=['date'])
        
        if not parent_only_transactions.empty:
            spending_items_df = db_manager.spending_items.db_data
            parent_spending = spending_items_df[
                spending_items_df['transaction_id'].isin(parent_only_transactions['transaction_id'])
            ].copy()
            
            if parent_spending.empty:
                # Use override_money
                merged = parent_only_transactions[['date', 'override_money']].copy()
                merged = merged.dropna(subset=['override_money'])
                if not merged.empty:
                    merged['amount'] = merged['override_money'].abs()
                    merged['week_start'] = merged['date'].dt.to_period('W').apply(lambda r: r.start_time)
                    parent_weekly = merged.groupby('week_start')['amount'].sum().reset_index()
                    parent_weekly['category'] = f"{parent_category_name} (Direct)"
                    all_breakdown_data.append(parent_weekly)
            else:
                # Calculate from spending items
                parent_spending['amount'] = parent_spending['display_price'] * parent_spending['num_purchased']
                merged = parent_spending.merge(
                    parent_only_transactions[['transaction_id', 'date']],
                    on='transaction_id',
                    how='left'
                )
                merged['week_start'] = merged['date'].dt.to_period('W').apply(lambda r: r.start_time)
                parent_weekly = merged.groupby('week_start')['amount'].sum().reset_index()
                parent_weekly['category'] = f"{parent_category_name} (Direct)"
                all_breakdown_data.append(parent_weekly)
    
    if not all_breakdown_data:
        return pd.DataFrame(columns=['week_start', 'amount', 'category'])
    
    return pd.concat(all_breakdown_data, ignore_index=True)


def create_spending_chart(weekly_data, category_name):
    """
    Create a line chart for weekly spending.
    """
    if weekly_data.empty:
        st.info(f"No spending data available for {category_name}")
        return
    
    fig = px.line(
        weekly_data,
        x='week_start',
        y='amount',
        title=f'Weekly Spending: {category_name}',
        labels={'week_start': 'Week', 'amount': 'Amount Spent (£)'},
        markers=True
    )
    
    fig.update_layout(
        xaxis_title="Week Starting",
        yaxis_title="Amount Spent (£)",
        hovermode='x unified'
    )
    
    fig.update_traces(
        hovertemplate='<b>%{x|%Y-%m-%d}</b><br>£%{y:.2f}<extra></extra>'
    )
    
    st.plotly_chart(fig, use_container_width=True)


def create_breakdown_chart(breakdown_data, parent_category_name):
    """
    Create a line chart showing breakdown by subcategories.
    """
    if breakdown_data.empty:
        st.info(f"No spending data available for breakdown")
        return
    
    fig = px.line(
        breakdown_data,
        x='week_start',
        y='amount',
        color='category',
        title=f'Weekly Spending Breakdown: {parent_category_name}',
        labels={'week_start': 'Week', 'amount': 'Amount Spent (£)', 'category': 'Subcategory'},
        markers=True
    )
    
    fig.update_layout(
        xaxis_title="Week Starting",
        yaxis_title="Amount Spent (£)",
        hovermode='x unified',
        legend_title="Subcategory"
    )
    
    st.plotly_chart(fig, use_container_width=True)


def get_unassigned_category_spending(db_manager):
    """
    Get spending data for transactions with no category assigned.
    """
    print(f"\n=== Processing Unassigned Category ===")
    
    # Get all transactions with NULL category_id
    transactions_df = db_manager.transactions.db_data
    unassigned_transactions = transactions_df[transactions_df['category_id'].isna()].copy()
    print(f"Unassigned transactions: {len(unassigned_transactions)}")
    
    if unassigned_transactions.empty:
        return pd.DataFrame(columns=['week_start', 'amount', 'category'])
    
    # Convert dates
    unassigned_transactions['date'] = pd.to_datetime(unassigned_transactions['date'], errors='coerce')
    unassigned_transactions = unassigned_transactions.dropna(subset=['date'])
    
    if unassigned_transactions.empty:
        return pd.DataFrame(columns=['week_start', 'amount', 'category'])
    
    # Get spending items for these transactions
    spending_items_df = db_manager.spending_items.db_data
    transaction_spending = spending_items_df[
        spending_items_df['transaction_id'].isin(unassigned_transactions['transaction_id'])
    ].copy()
    
    # If no spending items, use transaction-level override_money
    if transaction_spending.empty:
        print("No spending items - using override_money")
        merged_data = unassigned_transactions[['date', 'override_money']].copy()
        merged_data = merged_data.dropna(subset=['override_money'])
        
        if merged_data.empty:
            return pd.DataFrame(columns=['week_start', 'amount', 'category'])
        
        merged_data['amount'] = merged_data['override_money'].abs()
    else:
        # Calculate from spending items
        transaction_spending['amount'] = transaction_spending['display_price'] * transaction_spending['num_purchased']
        merged_data = transaction_spending.merge(
            unassigned_transactions[['transaction_id', 'date']],
            on='transaction_id',
            how='left'
        )
    
    # Get week start dates
    merged_data['week_start'] = merged_data['date'].dt.to_period('W').apply(lambda r: r.start_time)
    
    # Group by week and sum
    weekly_spending = merged_data.groupby('week_start')['amount'].sum().reset_index()
    weekly_spending['category'] = 'Unassigned'
    print(f"Unassigned weekly spending: {len(weekly_spending)} weeks, £{weekly_spending['amount'].sum():.2f} total")
    
    return weekly_spending


def get_all_categories_spending(db_manager):
    """
    Get spending data for all ROOT categories combined.
    Child categories are automatically included in their parents.
    Also includes unassigned transactions.
    """
    all_weekly_data = []
    
    # Only process root categories (no parent)
    root_categories = get_root_categories(db_manager)
    
    for _, category_row in root_categories.iterrows():
        category_id = category_row['category_id']
        category_name = category_row['name']
        
        if pd.isna(category_name):
            continue
            
        weekly_data = get_weekly_spending_by_category(db_manager, category_id, category_name)
        
        if not weekly_data.empty:
            all_weekly_data.append(weekly_data)
    
    # Add unassigned spending
    unassigned_data = get_unassigned_category_spending(db_manager)
    if not unassigned_data.empty:
        all_weekly_data.append(unassigned_data)
    
    if not all_weekly_data:
        return pd.DataFrame(columns=['week_start', 'amount', 'category'])
    
    return pd.concat(all_weekly_data, ignore_index=True)


def create_combined_spending_chart(all_weekly_data):
    """
    Create a combined line chart showing all categories.
    """
    if all_weekly_data.empty:
        st.info("No spending data available")
        return
    
    fig = px.line(
        all_weekly_data,
        x='week_start',
        y='amount',
        color='category',
        title='Weekly Spending by Category',
        labels={'week_start': 'Week', 'amount': 'Amount Spent (£)', 'category': 'Category'},
        markers=True
    )
    
    fig.update_layout(
        xaxis_title="Week Starting",
        yaxis_title="Amount Spent (£)",
        hovermode='x unified',
        legend_title="Category"
    )
    
    st.plotly_chart(fig, use_container_width=True)


def spending_view_page_ui():
    """
    Main UI for the spending view page.
    """
    utils.block_if_no_auth()
    st.set_page_config(page_title="Spending View - Money Thing", page_icon="💳", layout="wide")
    log("Loading Spending View page")
    
    st.markdown("# Spending View")
    
    db_manager = DatabaseManager()
    categories_df = db_manager.categories.db_data
    
    # Filter out categories with no name
    valid_categories = categories_df[categories_df['name'].notna()].copy()
    
    if valid_categories.empty:
        st.warning("No categories found. Please add categories first.")
        return
    
    # View options
    view_mode = st.radio(
        "View Mode",
        ["Combined View", "Individual Categories"],
        horizontal=True
    )
    
    st.divider()
    
    if view_mode == "Combined View":
        st.markdown("### All Categories Combined")
        with st.spinner("Loading spending data for all categories..."):
            all_weekly_data = get_all_categories_spending(db_manager)
            create_combined_spending_chart(all_weekly_data)
            
            # Show summary statistics
            if not all_weekly_data.empty:
                col1, col2, col3 = st.columns(3)
                
                total_spending = all_weekly_data['amount'].sum()
                avg_weekly = all_weekly_data.groupby('week_start')['amount'].sum().mean()
                num_weeks = all_weekly_data['week_start'].nunique()
                
                col1.metric("Total Spending", f"£{total_spending:.2f}")
                col2.metric("Average Weekly Spending", f"£{avg_weekly:.2f}")
                col3.metric("Weeks Tracked", num_weeks)
    
    else:  # Individual Categories
        st.markdown("### Individual Category Spending")
        st.info("💡 Tip: Child categories are automatically included in their parent category totals")
        
        # Only show root categories for selection
        root_categories = get_root_categories(db_manager)
        category_names = sorted(root_categories['name'].tolist())
        
        # Add Unassigned as an option
        category_names_with_unassigned = category_names + ['Unassigned']
        
        # Option to show all or select specific
        show_all = st.checkbox("Show all categories", value=False)
        
        if show_all:
            selected_categories = category_names_with_unassigned
        else:
            selected_categories = st.multiselect(
                "Select categories to view",
                category_names_with_unassigned,
                default=category_names
            )
        
        if not selected_categories:
            st.info("Please select at least one category to view")
            return
        
        # Display charts for each selected category
        for category_name in selected_categories:
            # Handle Unassigned category separately
            if category_name == 'Unassigned':
                with st.container(border=True):
                    st.markdown(f"#### {category_name}")
                    
                    with st.spinner(f"Loading data for {category_name}..."):
                        weekly_data = get_unassigned_category_spending(db_manager)
                        
                        if not weekly_data.empty:
                            # Show metrics
                            col1, col2, col3 = st.columns(3)
                            total = weekly_data['amount'].sum()
                            avg = weekly_data['amount'].mean()
                            weeks = len(weekly_data)
                            
                            col1.metric("Total", f"£{total:.2f}")
                            col2.metric("Avg/Week", f"£{avg:.2f}")
                            col3.metric("Weeks", weeks)
                            
                            # Show chart
                            create_spending_chart(weekly_data, category_name)
                        else:
                            st.info(f"No unassigned spending found")
                continue
            
            category_row = root_categories[root_categories['name'] == category_name].iloc[0]
            category_id = category_row['category_id']
            
            with st.container(border=True):
                # Header with breakdown toggle
                header_col, button_col = st.columns([0.7, 0.3])
                header_col.markdown(f"#### {category_name}")
                
                # Check if this category has children
                categories_df = db_manager.categories.db_data
                has_children = len(categories_df[categories_df['parent_category_id'] == category_id]) > 0
                
                show_breakdown = False
                if has_children:
                    show_breakdown = button_col.checkbox(
                        "🔍 Breakdown by subcategories",
                        key=f"breakdown_{category_id}",
                        value=False
                    )
                
                with st.spinner(f"Loading data for {category_name}..."):
                    if show_breakdown:
                        # Show breakdown by subcategories
                        breakdown_data = get_category_breakdown(
                            db_manager,
                            category_id,
                            category_name
                        )
                        
                        if not breakdown_data.empty:
                            # Show metrics for total
                            col1, col2, col3 = st.columns(3)
                            total = breakdown_data['amount'].sum()
                            avg_weekly = breakdown_data.groupby('week_start')['amount'].sum().mean()
                            weeks = breakdown_data['week_start'].nunique()
                            
                            col1.metric("Total", f"£{total:.2f}")
                            col2.metric("Avg/Week", f"£{avg_weekly:.2f}")
                            col3.metric("Weeks", weeks)
                            
                            # Show breakdown chart
                            create_breakdown_chart(breakdown_data, category_name)
                            
                            # Show subcategory totals
                            with st.expander("📊 Subcategory Totals"):
                                subcategory_totals = breakdown_data.groupby('category')['amount'].sum().reset_index()
                                subcategory_totals = subcategory_totals.sort_values('amount', ascending=False)
                                subcategory_totals.columns = ['Subcategory', 'Total Spent (£)']
                                st.dataframe(
                                    subcategory_totals,
                                    use_container_width=True,
                                    hide_index=True
                                )
                        else:
                            st.info(f"No spending data found for {category_name}")
                    else:
                        # Show aggregated view (default)
                        weekly_data = get_weekly_spending_by_category(
                            db_manager, 
                            category_id, 
                            category_name
                        )
                        
                        if not weekly_data.empty:
                            # Show metrics
                            col1, col2, col3 = st.columns(3)
                            total = weekly_data['amount'].sum()
                            avg = weekly_data['amount'].mean()
                            weeks = len(weekly_data)
                            
                            col1.metric("Total", f"£{total:.2f}")
                            col2.metric("Avg/Week", f"£{avg:.2f}")
                            col3.metric("Weeks", weeks)
                            
                            # Show chart
                            create_spending_chart(weekly_data, category_name)
                        else:
                            st.info(f"No spending data found for {category_name}")


if __name__ == "__main__":
    spending_view_page_ui()
