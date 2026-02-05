# dashboard/app.py
"""
RFSN Learning Dashboard - Streamlit Application

A clean, modern dashboard for monitoring and analyzing the RFSN learner.

Run with: streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from upstream_learner import (
    LearningAnalytics,
    OutcomeDB,
    get_arms_for_category,
    list_categories,
)

# =============================================================================
# PAGE CONFIG & STYLING
# =============================================================================
st.set_page_config(
    page_title="RFSN Learner Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for white background and clean styling
st.markdown(
    """
<style>
    /* Main app background - clean white */
    .stApp {
        background-color: #ffffff;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e9ecef;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #1a1a2e;
        font-weight: 600;
    }
    
    /* Metric cards */
    [data-testid="stMetric"] {
        background-color: #f8f9fa;
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #e9ecef;
    }
    
    [data-testid="stMetricValue"] {
        color: #1a1a2e;
        font-weight: 700;
    }
    
    /* Cards and containers */
    .stDataFrame {
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #4361ee;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 24px;
        font-weight: 500;
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        background-color: #3730a3;
        transform: translateY(-1px);
    }
    
    /* Success/warning colors */
    .success-text { color: #059669; font-weight: 600; }
    .warning-text { color: #d97706; font-weight: 600; }
    .error-text { color: #dc2626; font-weight: 600; }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 8px 16px;
    }
    
    /* Plotly chart containers */
    .js-plotly-plot {
        border-radius: 12px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# DATABASE CONNECTION
# =============================================================================
DEFAULT_DB_PATH = "./tmp/outcomes.sqlite"


@st.cache_resource
def get_db(db_path: str) -> OutcomeDB | None:
    """Get database connection (cached)."""
    try:
        path = Path(db_path)
        if path.exists():
            return OutcomeDB(str(path))
        return None
    except Exception:
        return None


@st.cache_resource
def get_analytics(db_path: str) -> LearningAnalytics | None:
    """Get analytics engine (cached)."""
    db = get_db(db_path)
    if db:
        return LearningAnalytics(db)
    return None


# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=RFSN", width=150)
    st.title("🧠 RFSN Learner")
    st.divider()

    # Database path
    db_path = st.text_input("Database Path", value=DEFAULT_DB_PATH)

    if st.button("🔄 Refresh Data"):
        st.cache_resource.clear()
        st.rerun()

    st.divider()

    # Navigation
    page = st.radio(
        "Navigation",
        ["📊 Overview", "🎯 Arm Performance", "📈 Learning Curves", "📋 Outcomes"],
        label_visibility="collapsed",
    )

# Get analytics
analytics = get_analytics(db_path)
db = get_db(db_path)

# =============================================================================
# MAIN CONTENT
# =============================================================================

if page == "📊 Overview":
    st.title("📊 Dashboard Overview")

    if not analytics:
        st.warning("⚠️ No database found. Run some tasks first to generate data.")
        st.info(f"Looking for: `{db_path}`")
    else:
        # Get summary
        summary = analytics.experiment_summary()

        # Metrics row
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Trials", f"{summary.total_trials:,}")
        with col2:
            st.metric("Unique Arms", f"{summary.unique_arms}")
        with col3:
            st.metric("Best Arm", summary.best_arm[:20] if summary.best_arm else "N/A")
        with col4:
            st.metric("Best Mean Reward", f"{summary.best_mean:.3f}")

        st.divider()

        # Two columns: Performance chart + Top arms table
        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.subheader("Arm Performance Distribution")
            if summary.arms:
                df = pd.DataFrame(
                    [
                        {
                            "Arm": a.arm_key[:30],
                            "Count": a.count,
                            "Mean Reward": a.mean_reward,
                        }
                        for a in summary.arms[:15]
                    ]
                )

                fig = px.bar(
                    df,
                    x="Arm",
                    y="Mean Reward",
                    color="Count",
                    color_continuous_scale="Blues",
                    template="plotly_white",
                )
                fig.update_layout(
                    plot_bgcolor="white",
                    paper_bgcolor="white",
                    xaxis_tickangle=-45,
                    height=400,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No arm data available yet.")

        with col_right:
            st.subheader("Top Performers")
            if summary.arms:
                for i, arm in enumerate(summary.arms[:5], 1):
                    color = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i - 1]
                    st.markdown(f"""
                    {color} **{arm.arm_key[:25]}**  
                    Reward: `{arm.mean_reward:.3f}` | Uses: `{arm.count}`
                    """)
            else:
                st.info("No rankings yet.")

        # Categories overview
        st.divider()
        st.subheader("📂 Arms by Category")

        categories = list_categories()
        cols = st.columns(len(categories))

        for i, cat in enumerate(categories):
            with cols[i]:
                arms = get_arms_for_category(cat)
                st.metric(cat.upper(), len(arms))

elif page == "🎯 Arm Performance":
    st.title("🎯 Arm Performance Analysis")

    if not analytics:
        st.warning("⚠️ No database found.")
    else:
        # Filter by category
        categories = ["All"] + list(list_categories())
        selected_cat = st.selectbox("Filter by Category", categories)

        rankings = analytics.arm_rankings(limit=50)

        if selected_cat != "All":
            rankings = [r for r in rankings if r.arm_key.startswith(f"{selected_cat}::")]

        if rankings:
            # Performance table
            df = pd.DataFrame(
                [
                    {
                        "Arm": r.arm_key,
                        "Category": r.arm_key.split("::")[0] if "::" in r.arm_key else "unknown",
                        "Count": r.count,
                        "Mean Reward": round(r.mean_reward, 4),
                        "Min": round(r.min_reward, 4),
                        "Max": round(r.max_reward, 4),
                    }
                    for r in rankings
                ]
            )

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Mean Reward": st.column_config.ProgressColumn(
                        min_value=0,
                        max_value=1,
                        format="%.3f",
                    ),
                },
            )

            # Scatter plot
            st.subheader("Reward vs Usage")
            fig = px.scatter(
                df,
                x="Count",
                y="Mean Reward",
                color="Category",
                size="Count",
                hover_data=["Arm"],
                template="plotly_white",
            )
            fig.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No arm performance data available.")

elif page == "📈 Learning Curves":
    st.title("📈 Learning Curves")

    if not analytics:
        st.warning("⚠️ No database found.")
    else:
        # Get learning curve
        window = st.slider("Rolling Window Size", 5, 50, 10)
        curve = analytics.learning_curve(window=window)

        if curve.points:
            df = pd.DataFrame(curve.points, columns=["Index", "Window Mean", "Cumulative Mean"])

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=df["Index"],
                    y=df["Window Mean"],
                    mode="lines",
                    name="Rolling Mean",
                    line=dict(color="#4361ee", width=2),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=df["Index"],
                    y=df["Cumulative Mean"],
                    mode="lines",
                    name="Cumulative Mean",
                    line=dict(color="#06b6d4", width=2, dash="dash"),
                )
            )

            fig.update_layout(
                template="plotly_white",
                plot_bgcolor="white",
                paper_bgcolor="white",
                xaxis_title="Trial Number",
                yaxis_title="Reward",
                height=450,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Final Mean", f"{curve.final_mean:.4f}")
            with col2:
                st.metric("Total Trials", curve.total_count)
            with col3:
                converged = "✅ Yes" if curve.is_converged() else "❌ Not yet"
                st.metric("Converged", converged)
        else:
            st.info("No learning curve data available yet.")

elif page == "📋 Outcomes":
    st.title("📋 Recent Outcomes")

    if not db:
        st.warning("⚠️ No database found.")
    else:
        limit = st.slider("Number of outcomes", 10, 200, 50)
        outcomes = db.recent_outcomes(limit=limit)

        if outcomes:
            df = pd.DataFrame(
                [
                    {
                        "Timestamp": o.ts_utc[:19] if o.ts_utc else "",
                        "Task ID": o.task_id[:20] if o.task_id else "",
                        "Arm": o.arm_key[:30],
                        "Reward": round(o.reward, 4),
                        "Seed": o.seed,
                    }
                    for o in outcomes
                ]
            )

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Reward": st.column_config.ProgressColumn(
                        min_value=0,
                        max_value=1,
                        format="%.3f",
                    ),
                },
            )

            # Reward distribution
            st.subheader("Reward Distribution")
            rewards = [o.reward for o in outcomes]
            fig = px.histogram(
                x=rewards,
                nbins=20,
                template="plotly_white",
                color_discrete_sequence=["#4361ee"],
            )
            fig.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                xaxis_title="Reward",
                yaxis_title="Count",
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No outcomes recorded yet.")

# =============================================================================
# FOOTER
# =============================================================================
st.divider()
st.caption("RFSN Learner Dashboard • Built with Streamlit • White Theme Edition")
