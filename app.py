import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(page_title="BW Executive Analytics", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS FOR BEAUTIFICATION ---
st.markdown("""
<style>
    .reportview-container .main .block-container{
        max-width: 1200px;
        padding-top: 2rem;
        padding-right: 2rem;
        padding-left: 2rem;
        padding-bottom: 2rem;
    }
    .metric-card {
        background-color: #004080;
        color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
    }
    .metric-label {
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
</style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
@st.cache_data(ttl=600) # Cache for 10 minutes to prevent overwhelming Google Sheets
def load_data():
    try:
        # Try fetching LIVE data from Google Sheets first!
        url = 'https://docs.google.com/spreadsheets/d/1oJKsU2IOrw8mu4xvx0MxBJ9aHB8omewvINjBq7-HkNc/export?format=xlsx'
        df = pd.read_excel(url, sheet_name='Trainers Database')
    except Exception:
        # Fallback to local file if the Google Sheet is set to "Private"
        df = pd.read_excel('Looker_Studio_Dataset.xlsx')
        
    def extract_state(loc):
        parts = str(loc).split(',')
        return parts[-1].strip() if len(parts) > 1 else 'Unknown'
        
    if 'State' not in df.columns and 'Location' in df.columns:
        df['State'] = df['Location'].apply(extract_state)
    
    # Fill NA first to avoid float64 type mismatch on other columns
    df = df.fillna('')
    
    # Clean experience
    if 'Years of Experience' in df.columns:
        df['Years of Experience'] = pd.to_numeric(df['Years of Experience'], errors='coerce').fillna(0)
    
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}. Please ensure Looker_Studio_Dataset.xlsx is uploaded to GitHub!")
    st.stop()

# --- SIDEBAR FILTERS ---
st.sidebar.image("https://blue-wisdom-od.netlify.app/images/1.png", width=200)
st.sidebar.title("Search Filters")

# Status filter
if 'Status (Active/Inactive)' in df.columns:
    all_statuses = ["All"] + list(df['Status (Active/Inactive)'].unique())
    selected_status = st.sidebar.selectbox("Trainer Status", all_statuses)
else:
    selected_status = "All"

# State filter
if 'State' in df.columns:
    states = [s for s in df['State'].unique() if s]
    selected_state = st.sidebar.selectbox("Location (State)", ["All"] + sorted(states))
else:
    selected_state = "All"

# Keyword Search
search_kw = st.sidebar.text_input("Keyword Search (Name, Skill, Topic)")

# --- FILTER DATA ---
filtered_df = df.copy()
if selected_status != "All" and 'Status (Active/Inactive)' in filtered_df.columns:
    filtered_df = filtered_df[filtered_df['Status (Active/Inactive)'] == selected_status]
if selected_state != "All" and 'State' in filtered_df.columns:
    filtered_df = filtered_df[filtered_df['State'] == selected_state]
if search_kw:
    # Search across multiple columns safely
    mask = pd.Series([False]*len(filtered_df), index=filtered_df.index)
    for col in ['Name', 'Core Subjects/Topics', 'Location']:
        if col in filtered_df.columns:
            mask = mask | filtered_df[col].astype(str).str.contains(search_kw, case=False, na=False)
    filtered_df = filtered_df[mask]

# --- MAIN DASHBOARD HEADER ---
st.title("📊 Trainer Search & Analytics Dashboard")
st.markdown("---")

# --- KPI METRICS ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'<div class="metric-card"><div class="metric-value">{len(filtered_df)}</div><div class="metric-label">Total Trainers</div></div>', unsafe_allow_html=True)
with col2:
    if 'Years of Experience' in filtered_df.columns:
        avg_exp = filtered_df['Years of Experience'].mean()
        val = f"{avg_exp:.1f}" if pd.notnull(avg_exp) else "0.0"
    else:
        val = "0.0"
    st.markdown(f'<div class="metric-card" style="background-color: #0073e6;"><div class="metric-value">{val}</div><div class="metric-label">Avg Experience (Yrs)</div></div>', unsafe_allow_html=True)
with col3:
    if 'Status (Active/Inactive)' in filtered_df.columns:
        active = len(filtered_df[filtered_df['Status (Active/Inactive)'] == 'Active'])
    else:
        active = len(filtered_df)
    st.markdown(f'<div class="metric-card" style="background-color: #28a745;"><div class="metric-value">{active}</div><div class="metric-label">Active Trainers</div></div>', unsafe_allow_html=True)
with col4:
    if 'State' in filtered_df.columns:
        states_count = filtered_df['State'].nunique()
    else:
        states_count = 0
    st.markdown(f'<div class="metric-card" style="background-color: #6f42c1;"><div class="metric-value">{states_count}</div><div class="metric-label">States Covered</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- CHARTS SECTION ---
c1, c2 = st.columns(2)

with c1:
    st.subheader("📍 Top Trainer Locations")
    if 'State' in filtered_df.columns:
        loc_counts = filtered_df['State'].value_counts().reset_index().head(10)
        loc_counts.columns = ['State', 'Count']
        fig_loc = px.bar(loc_counts, x='Count', y='State', orientation='h', color='Count', color_continuous_scale='Blues')
        fig_loc.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_loc, use_container_width=True)

with c2:
    st.subheader("📈 Experience Distribution")
    if 'Years of Experience' in filtered_df.columns:
        fig_exp = px.histogram(filtered_df, x="Years of Experience", nbins=20, color_discrete_sequence=['#004080'])
        fig_exp.update_layout(bargap=0.1, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_exp, use_container_width=True)

# --- "WHAT-IF" SCENARIO PLANNER ---
st.markdown("---")
st.subheader("🔮 What-If Scenario Simulator & SWOT")

expander = st.expander("Click to run a 'What-If' Simulation")
with expander:
    w1, w2, w3 = st.columns(3)
    target_skill = w1.text_input("Target Skill (e.g. 'POSH')")
    target_loc = w2.text_input("Target Location (e.g. 'Mumbai')")
    min_exp = w3.number_input("Minimum Experience (Years)", min_value=0, max_value=40, value=5)
    
    if target_skill or target_loc:
        sim_df = df.copy()
        if target_skill and 'Core Subjects/Topics' in sim_df.columns:
            sim_df = sim_df[sim_df['Core Subjects/Topics'].astype(str).str.contains(target_skill, case=False, na=False)]
        if target_loc and 'Location' in sim_df.columns:
            sim_df = sim_df[sim_df['Location'].astype(str).str.contains(target_loc, case=False, na=False)]
        if 'Years of Experience' in sim_df.columns:
            sim_df = sim_df[sim_df['Years of Experience'] >= min_exp]
        
        st.success(f"**Simulation Result:** Found **{len(sim_df)}** trainers matching this strict profile.")
        if len(sim_df) > 0:
            cols_to_show = [c for c in ['Name', 'Location', 'Years of Experience', 'Contact Number'] if c in sim_df.columns]
            st.dataframe(sim_df[cols_to_show])
        else:
            st.error("SWOT THREAT: You have zero trainers in your database matching this profile! You need to recruit/source immediately.")

# --- DATA TABLE ---
st.markdown("---")
st.subheader("📄 Filtered Trainer Roster")
display_cols = [c for c in ['Name', 'Location', 'Contact Number', 'Email ID', 'Years of Experience', 'Core Subjects/Topics', 'Status (Active/Inactive)'] if c in filtered_df.columns]
st.dataframe(filtered_df[display_cols], use_container_width=True, height=400)
