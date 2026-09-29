import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="FORESIGHT",
    page_icon="📊",
    layout="wide"
)

# ---------- Load data ----------
@st.cache_data
def load_data():
    sales = pd.read_csv("sales_daily.csv")
    inventory = pd.read_csv("inventory_snapshots.csv")
    sku = pd.read_csv("sku_master.csv")
    calendar = pd.read_csv("calendar.csv")

    sales["Date"] = pd.to_datetime(sales["Date"])
    inventory["Snapshot_Date"] = pd.to_datetime(inventory["Snapshot_Date"])
    calendar["date"] = pd.to_datetime(calendar["date"])
    return sales, inventory, sku, calendar

sales, inventory, sku, calendar = load_data()

# ---------- Sidebar ----------
st.sidebar.title("FORESIGHT")
st.sidebar.caption("Demand & Inventory Intelligence")

categories = ["All"] + sorted(sku["Category"].dropna().unique().tolist())
selected_category = st.sidebar.selectbox("Category", categories)

filtered_sku_master = sku.copy()
if selected_category != "All":
    filtered_sku_master = filtered_sku_master[
        filtered_sku_master["Category"] == selected_category
    ]

sku_options = ["All"] + sorted(filtered_sku_master["SKU"].tolist())
selected_sku = st.sidebar.selectbox("SKU", sku_options)

# ---------- Filter data ----------
sales_f = sales.merge(
    sku[["SKU", "Product_Name", "Category", "Subcategory"]],
    on="SKU",
    how="left"
)

if selected_category != "All":
    sales_f = sales_f[sales_f["Category"] == selected_category]

if selected_sku != "All":
    sales_f = sales_f[sales_f["SKU"] == selected_sku]

inv_f = inventory.merge(
    sku[["SKU", "Product_Name", "Category", "Subcategory"]],
    on="SKU",
    how="left"
)

if selected_category != "All":
    inv_f = inv_f[inv_f["Category"] == selected_category]

if selected_sku != "All":
    inv_f = inv_f[inv_f["SKU"] == selected_sku]

# ---------- Header ----------
st.title("📊 FORESIGHT")
st.subheader("AI-Powered Demand & Inventory Intelligence Platform")
st.write(
    "Monitor sales, forecast demand, identify inventory risks, "
    "and prioritize inventory actions."
)

# ---------- KPIs ----------
total_sales = sales_f["Revenue"].sum()
total_units = sales_f["Units_Sold"].sum()
total_inventory = inv_f["Current_Stock"].sum()

latest_date = inv_f["Snapshot_Date"].max()
latest_inv = inv_f[inv_f["Snapshot_Date"] == latest_date].copy()

if not latest_inv.empty:
    stockout_count = (latest_inv["Current_Stock"] < latest_inv["Reorder_Point"]).sum()
    overstock_count = (
        latest_inv["Current_Stock"] > latest_inv["Reorder_Point"] * 2
    ).sum()
else:
    stockout_count = 0
    overstock_count = 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Sales", f"₹{total_sales:,.0f}")
c2.metric("Units Sold", f"{total_units:,.0f}")
c3.metric("Current Inventory", f"{total_inventory:,.0f}")
c4.metric("Stockout Risk", int(stockout_count))
c5.metric("Overstock Risk", int(overstock_count))

st.divider()

# ---------- Sales trend ----------
st.subheader("📈 Sales & Demand Trend")

daily = (
    sales_f.groupby("Date", as_index=False)
    .agg(Units_Sold=("Units_Sold", "sum"), Revenue=("Revenue", "sum"))
)

fig_sales = px.line(
    daily,
    x="Date",
    y="Units_Sold",
    title="Daily Demand / Units Sold"
)
fig_sales.update_layout(height=400)
st.plotly_chart(fig_sales, use_container_width=True)

# ---------- Actual vs baseline forecast ----------
st.subheader("🔮 Weekly Demand Forecast")

forecast_source = sales_f.copy()

# Convert daily sales into weekly demand
forecast_source["Week"] = (
    forecast_source["Date"].dt.to_period("W-SUN").dt.start_time
)

weekly = (
    forecast_source.groupby("Week", as_index=False)
    .agg(Units_Sold=("Units_Sold", "sum"))
    .sort_values("Week")
)

if weekly.empty:
    st.info("No sales data available for the selected filters.")
else:
    # Weekly demand lookup for the seasonal-naive baseline
    weekly_lookup = dict(zip(weekly["Week"], weekly["Units_Sold"]))

    last_week = weekly["Week"].max()
    recent_average = weekly.tail(4)["Units_Sold"].mean()

    # Forecast the next 8 weeks
    future_rows = []

    for i in range(1, 9):
        future_week = last_week + pd.Timedelta(weeks=i)

        # Use demand from the corresponding week 52 weeks earlier
        comparison_week = future_week - pd.Timedelta(weeks=52)

        if comparison_week in weekly_lookup:
            predicted_demand = weekly_lookup[comparison_week]
        else:
            predicted_demand = recent_average

        future_rows.append({
            "Date": future_week,
            "Units_Sold": float("nan"),
            "Forecast": max(0, predicted_demand)
        })

    # Show the last 26 weeks of actual demand
    history = weekly.tail(26).rename(
        columns={"Week": "Date"}
    ).copy()

    history["Forecast"] = float("nan")

    # Combine historical actuals and future forecasts
    future_df = pd.DataFrame(future_rows)

    chart_df = pd.concat(
        [
            history[["Date", "Units_Sold", "Forecast"]],
            future_df[["Date", "Units_Sold", "Forecast"]]
        ],
        ignore_index=True
    ).sort_values("Date")

    fig_forecast = px.line(
        chart_df,
        x="Date",
        y=["Units_Sold", "Forecast"],
        title="Weekly Actual Demand and Next 8 Weeks Forecast",
        labels={
            "Date": "Week",
            "value": "Units",
            "variable": "Series"
        }
    )

    fig_forecast.update_layout(height=450)

    st.plotly_chart(
        fig_forecast,
        use_container_width=True
    )

    st.caption(
        "Baseline method: seasonal-naive forecast using demand "
        "from 52 weeks earlier. If unavailable, the last 4-week "
        "average is used. This is a baseline, not an advanced ML model."
    )

    st.subheader("📅 Next 8 Weeks Forecast")

    st.dataframe(
        future_df.rename(
            columns={
                "Date": "Forecast Week",
                "Forecast": "Predicted Units"
            }
        )[["Forecast Week", "Predicted Units"]].assign(
            **{"Predicted Units": lambda df: df["Predicted Units"].round(0)}
        ),
        use_container_width=True,
        hide_index=True
    )

# ---------- Inventory risk ----------
st.subheader("⚠️ Inventory Risk")

if not latest_inv.empty:
    risk = latest_inv.copy()

    def classify(row):
        if row["Current_Stock"] < row["Reorder_Point"]:
            return "Reorder Now"
        elif row["Current_Stock"] > row["Reorder_Point"] * 2:
            return "Markdown / Clear"
        elif row["Current_Stock"] <= row["Reorder_Point"] * 1.25:
            return "Watch / Volatile"
        return "Healthy"

    risk["Risk_Status"] = risk.apply(classify, axis=1)

    display_cols = [
        "SKU", "Product_Name", "Category", "Current_Stock",
        "On_Order", "Reorder_Point", "Safety_Stock", "Risk_Status"
    ]
    st.dataframe(
        risk[display_cols].sort_values("Current_Stock"),
        use_container_width=True,
        hide_index=True
    )

    risk_counts = (
        risk["Risk_Status"].value_counts()
        .rename_axis("Risk_Status")
        .reset_index(name="Count")
    )
    fig_risk = px.bar(
        risk_counts,
        x="Risk_Status",
        y="Count",
        title="Inventory Risk Summary"
    )
    st.plotly_chart(fig_risk, use_container_width=True)

# ---------- Recommendations ----------
st.subheader("💡 Prioritized Recommendations")

if not latest_inv.empty:
    recommendations = latest_inv.copy()

    recommendations["Action"] = "Healthy"
    recommendations.loc[
        recommendations["Current_Stock"] < recommendations["Reorder_Point"],
        "Action"
    ] = "Reorder Now"

    recommendations.loc[
        recommendations["Current_Stock"] > recommendations["Reorder_Point"] * 2,
        "Action"
    ] = "Markdown / Clear"

    recommendations.loc[
        (recommendations["Current_Stock"] >= recommendations["Reorder_Point"]) &
        (recommendations["Current_Stock"] <= recommendations["Reorder_Point"] * 1.25),
        "Action"
    ] = "Watch / Volatile"

    recommendations["Suggested_Reorder_Qty"] = (
        recommendations["Reorder_Point"] - recommendations["Current_Stock"]
    ).clip(lower=0)

    rec_cols = [
        "SKU", "Product_Name", "Category", "Current_Stock",
        "Reorder_Point", "Suggested_Reorder_Qty", "Action"
    ]

    st.dataframe(
        recommendations[rec_cols]
        .sort_values("Suggested_Reorder_Qty", ascending=False)
        .head(20),
        use_container_width=True,
        hide_index=True
    )

# ---------- Footer ----------
st.divider()
st.caption(
    "FORESIGHT | Demand & Inventory Intelligence | "
    "Built with Python, Pandas, Plotly and Streamlit"
)
