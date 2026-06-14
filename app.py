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
        
    # Extract City from Location
    def extract_city(loc):
        parts = str(loc).split(',')
        return parts[0].strip() if len(parts) > 0 else 'Unknown'
        
    if 'City' not in df.columns and 'Location' in df.columns:
        df['City'] = df['Location'].apply(extract_city)
        
    # Calculate Age
    if 'DOB' in df.columns:
        df['Age'] = pd.to_datetime('today').year - pd.to_datetime(df['DOB'], errors='coerce').dt.year
        
    # Clean Gender
    if 'Gender' not in df.columns:
        df['Gender'] = 'Not Specified'
    
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}. Please ensure Looker_Studio_Dataset.xlsx is uploaded to GitHub!")
    st.stop()

# --- SIDEBAR FILTERS ---
st.sidebar.image("https://blue-wisdom-od.netlify.app/images/1.png", width=200)
st.sidebar.markdown("---")
st.sidebar.subheader("✨ AI Smart Search")
smart_query = st.sidebar.text_area("Describe your ideal trainer:", placeholder="e.g. female POSH trainer in ahmedabad with 5+ years experience")

st.sidebar.markdown("---")
st.sidebar.title("Manual Filters")

# State filter
if 'State' in df.columns:
    def is_valid_state(s):
        s_str = str(s).strip()
        if not s_str or s_str.lower() in ['nan', 'unknown', 'none']: return False
        if 'sent via script' in s_str.lower(): return False
        if 'am - ' in s_str.lower() or 'pm - ' in s_str.lower(): return False
        return True
    states = [s for s in df['State'].unique() if is_valid_state(s)]
    selected_state = st.sidebar.selectbox("Location (State)", ["All"] + sorted(states))
else:
    selected_state = "All"

# City filter
if 'City' in df.columns:
    cities = [c for c in df['City'].unique() if pd.notnull(c) and str(c).strip() != '' and str(c).lower() != 'nan']
    selected_city = st.sidebar.selectbox("Location (City)", ["All"] + sorted(cities))
else:
    selected_city = "All"

# Gender filter
if 'Gender' in df.columns:
    genders = [g for g in df['Gender'].unique() if pd.notnull(g) and str(g).strip() != '' and str(g).lower() != 'nan']
    selected_gender = st.sidebar.selectbox("Gender", ["All"] + sorted(genders))
else:
    selected_gender = "All"

# Age Range Filter
if 'Age' in df.columns and not df['Age'].isna().all():
    min_age = int(df['Age'].min(skipna=True))
    max_age = int(df['Age'].max(skipna=True))
    if min_age < max_age:
        selected_age = st.sidebar.slider("Age Range", min_value=min_age, max_value=max_age, value=(min_age, max_age))
    else:
        selected_age = None
else:
    selected_age = None

# Keyword Search (Topics, Skills, Name)
st.sidebar.markdown("---")
st.sidebar.subheader("Keyword & Topics")
search_kw = st.sidebar.text_input("Search (Name, Topics, Skills)")

# --- FILTER DATA ---
if smart_query:
    import re
    ai_df = df.copy()
    
    # 1. Parse Gender
    if re.search(r'\b(female|woman|women|lady)\b', smart_query, re.IGNORECASE) and 'Gender' in ai_df.columns:
        ai_df = ai_df[ai_df['Gender'].str.lower() == 'female']
    elif re.search(r'\b(male|man|men|guy)\b', smart_query, re.IGNORECASE) and 'Gender' in ai_df.columns:
        ai_df = ai_df[ai_df['Gender'].str.lower() == 'male']
        
    # 2. Parse Experience
    exp_match = re.search(r'(\d+)\s*(?:\+|years?|yrs?)', smart_query, re.IGNORECASE)
    if exp_match and 'Years of Experience' in ai_df.columns:
        min_exp = int(exp_match.group(1))
        ai_df = ai_df[ai_df['Years of Experience'] >= min_exp]
        
    # 3. Parse Location
    if 'City' in ai_df.columns:
        all_cities = ai_df['City'].dropna().unique()
        for city in all_cities:
            if str(city).lower() in smart_query.lower() and str(city).strip() != '':
                ai_df = ai_df[ai_df['City'] == city]
                break
                
    # 4. Semantic Topic Matching using scikit-learn
    if 'Core Subjects/Topics' in ai_df.columns and len(ai_df) > 0:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            
            topics = ai_df['Core Subjects/Topics'].fillna('').astype(str).tolist()
            vectorizer = TfidfVectorizer(stop_words='english')
            tfidf_matrix = vectorizer.fit_transform([smart_query] + topics)
            scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
            
            if scores.max() > 0:
                ai_df['AI Match Score'] = scores
                ai_df = ai_df[ai_df['AI Match Score'] > 0]
                ai_df = ai_df.sort_values(by='AI Match Score', ascending=False)
            
            if len(ai_df) > 20: ai_df = ai_df.head(20)
        except Exception as e:
            pass
            
    filtered_df = ai_df
else:
    filtered_df = df.copy()

    if selected_state != "All" and 'State' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['State'] == selected_state]

    if selected_city != "All" and 'City' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['City'] == selected_city]

    if selected_gender != "All" and 'Gender' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['Gender'] == selected_gender]

    if selected_age is not None and 'Age' in filtered_df.columns:
        filtered_df = filtered_df[(filtered_df['Age'].isna()) | ((filtered_df['Age'] >= selected_age[0]) & (filtered_df['Age'] <= selected_age[1]))]

    if search_kw:
        mask = pd.Series([False]*len(filtered_df), index=filtered_df.index)
        for col in ['Name', 'Core Subjects/Topics']:
            if col in filtered_df.columns:
                mask = mask | filtered_df[col].astype(str).str.contains(search_kw, case=False, na=False)
        filtered_df = filtered_df[mask]

# --- MAIN DASHBOARD HEADER ---
if smart_query:
    st.title("🤖 AI Recommended Trainers")
else:
    st.title("📊 Trainer Search & Analytics Dashboard")
st.markdown("---")

# --- KPI METRICS ---
col1, col2, col3 = st.columns(3)
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

# --- PROJECT SHORTLISTING & DATA TABLE ---
st.markdown("---")
st.subheader("📄 Project Shortlisting & Trainer Roster")
st.write("Select trainers below to export them for your project deployments.")

display_cols = [c for c in ['Trainer ID', 'Name', 'Location', 'Contact Number', 'Email ID', 'Years of Experience', 'Core Subjects/Topics', 'Status (Active/Inactive)'] if c in filtered_df.columns]
edit_df = filtered_df[display_cols].copy()
edit_df.insert(0, "Select", False)

edited_df = st.data_editor(
    edit_df,
    hide_index=True,
    column_config={"Select": st.column_config.CheckboxColumn("Select", default=False)},
    disabled=display_cols,
    use_container_width=True,
    height=400
)

selected_trainers = edited_df[edited_df["Select"]].drop(columns=["Select"])

if not selected_trainers.empty:
    st.success(f"✅ {len(selected_trainers)} trainers selected for Shortlist!")
    csv = selected_trainers.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Export Shortlist for Deployment Tracker",
        data=csv,
        file_name='project_shortlist.csv',
        mime='text/csv',
        type="primary"
    )
