import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from fpdf import FPDF
import base64

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
        df = pd.read_excel('Looker_Studio_Dataset.xlsx')
        
        # Load the newly public IPF sheet for the rich data
        url = 'https://docs.google.com/spreadsheets/d/1oJKsU2IOrw8mu4xvx0MxBJ9aHB8omewvINjBq7-HkNc/export?format=xlsx'
        ipf_df = pd.read_excel(url, sheet_name='IPF')
        
        # Merge them based on Email
        ipf_df['Email_clean'] = ipf_df['Email Address'].astype(str).str.lower().str.strip()
        ipf_df = ipf_df.drop_duplicates(subset=['Email_clean'], keep='last')
        
        df['Email_Lower'] = df['Email ID'].astype(str).str.lower().str.strip()
        
        # Prevent pandas from renaming overlapping columns to _x and _y
        overlapping_cols = [c for c in ipf_df.columns if c in df.columns]
        ipf_df = ipf_df.drop(columns=overlapping_cols)
        
        df = pd.merge(df, ipf_df, left_on='Email_Lower', right_on='Email_clean', how='left')
        df.drop(columns=['Email_Lower', 'Email_clean'], inplace=True, errors='ignore')
    except Exception:
        df = pd.read_excel('Looker_Studio_Dataset.xlsx')
        
    if 'Name' in df.columns:
        df['Name'] = df['Name'].astype(str).str.replace(r'(?i)\s*not provided', '', regex=True).str.strip()
        
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
        df.loc[(df['Age'] < 18) | (df['Age'] > 100), 'Age'] = pd.NA
        
    # Clean Gender
    if 'Gender' not in df.columns:
        df['Gender'] = 'Not Specified'
        
    # --- AUTO-DEDUPLICATION ---
    # Keep the most recent entry (last row) for each trainer based on Phone or Email
    if 'Contact Number' in df.columns:
        # Clean the phone number for accurate matching (remove spaces, +91, hyphens)
        df['Clean_Phone'] = df['Contact Number'].astype(str).str.replace(r'[\s\-\+]', '', regex=True)
        df['Clean_Phone'] = df['Clean_Phone'].str.replace(r'^91', '', regex=True) # Remove leading 91
        df = df.drop_duplicates(subset=['Clean_Phone'], keep='last')
        df = df.drop(columns=['Clean_Phone'])
    elif 'Email ID' in df.columns:
        df['Clean_Email'] = df['Email ID'].astype(str).str.lower().str.strip()
        df = df.drop_duplicates(subset=['Clean_Email'], keep='last')
        df = df.drop(columns=['Clean_Email'])
    
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
    
    # Export only the exact columns needed for the Project Deployments Sheet
    export_cols = ['Trainer ID', 'Name', 'Location', 'Contact Number', 'Email ID']
    export_df = selected_trainers[export_cols] if all(c in selected_trainers.columns for c in export_cols) else selected_trainers
    
    csv = export_df.to_csv(index=False).encode('utf-8')
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 Export Shortlist (CSV)",
            data=csv,
            file_name='project_shortlist.csv',
            mime='text/csv',
            type="primary"
        )
        
    with col2:
        # PDF GENERATION LOGIC
        if st.button("📄 Generate Client Pitch Profiles (PDF)"):
            with st.spinner("Generating Branded PDFs (This may take a moment for AI summaries)..."):
                import google.generativeai as genai
                genai.configure(api_key="AIzaSyCxaNQ1PAEgW1AnH4hkswxmAs-l6w25SLg")
                
                # Fetch BW Logo
                logo_path = None
                try:
                    import requests
                    r = requests.get("https://blue-wisdom-od.netlify.app/images/1.png", timeout=5)
                    if r.status_code == 200:
                        import tempfile
                        logo_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                        logo_file.write(r.content)
                        logo_file.close()
                        logo_path = logo_file.name
                except: pass

                def get_drive_image(url, gender, name):
                    fallback_boy = "https://avatar.iran.liara.run/public/boy"
                    fallback_girl = "https://avatar.iran.liara.run/public/girl"
                    fallback_initials = f"https://ui-avatars.com/api/?name={name.replace(' ', '+')}&background=0D8ABC&color=fff&size=256"
                    
                    gender_str = str(gender).lower()
                    if 'female' in gender_str or 'woman' in gender_str:
                        fallback = fallback_girl
                    elif 'male' in gender_str or 'man' in gender_str:
                        fallback = fallback_boy
                    else:
                        fallback = fallback_initials
                        
                    def download_image(img_url):
                        try:
                            import requests
                            from PIL import Image
                            r = requests.get(img_url, timeout=10)
                            if r.status_code == 200 and 'image' in r.headers.get('content-type', '').lower():
                                import tempfile
                                from io import BytesIO
                                img = Image.open(BytesIO(r.content))
                                # Crop to square
                                width, height = img.size
                                min_dim = min(width, height)
                                left = (width - min_dim)/2
                                top = (height - min_dim)/2
                                right = (width + min_dim)/2
                                bottom = (height + min_dim)/2
                                img = img.crop((left, top, right, bottom))
                                
                                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                                img.save(temp_file.name, 'PNG')
                                return temp_file.name
                            return None
                        except:
                            return None

                    if url and isinstance(url, str) and 'drive.google.com' in url:
                        file_id = None
                        if 'id=' in url: file_id = url.split('id=')[1].split('&')[0]
                        elif '/d/' in url: file_id = url.split('/d/')[1].split('/')[0]
                        if file_id:
                            img_path = download_image(f"https://drive.google.com/uc?id={file_id}")
                            if img_path: return img_path
                    return download_image(fallback)
                    
                def generate_ai_summary(name, exp, topics):
                    if not topics or str(topics).strip().lower() in ['nan', 'n/a', 'none', '']:
                        return f"{name} is an experienced professional with {exp} years of expertise."
                    prompt = f"Write a highly professional, 3-sentence executive summary pitching a corporate trainer named {name}. They have {exp} years of experience. Their core expertise and topics are: {topics}. Do not use formatting like bold or italics. Keep it punchy, persuasive, and strictly corporate tone."
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content(prompt)
                        return response.text.replace('\n', ' ').strip()
                    except:
                        return f"{name} is a highly seasoned corporate trainer with {exp} years of specialized experience in {topics}. They bring a wealth of practical knowledge and interactive methodologies to their sessions, ensuring maximum impact for corporate clients."

                pdf = FPDF()
                pdf.set_auto_page_break(auto=True, margin=15)
                
                for index, row in selected_trainers.iterrows():
                    pdf.add_page()
                    
                    name = str(row.get('Name', 'Trainer Profile')).encode('latin-1', 'replace').decode('latin-1')
                    loc = str(row.get('Location', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                    exp = str(row.get('Years of Experience', row.get('Total Training / Consulting Experience (in years)', 'N/A'))).encode('latin-1', 'replace').decode('latin-1')
                    topics = str(row.get('Core Subjects/Topics', row.get('Core Expertise Areas', 'N/A'))).encode('latin-1', 'replace').decode('latin-1')
                    gender = str(row.get('Gender', 'Not Specified'))
                    
                    # IPF Extra Data
                    qual = str(row.get('Highest Qualification', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                    delivery = str(row.get('Preferred Training Delivery Mode', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                    edu = str(row.get('Educational Institution(s)', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                    category = str(row.get('Primary Consultant Category', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                    linkedin = row.get('LinkedIn Profile / Professional Profile Link', '')
                    industries = str(row.get('Industries Served', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                    langs = str(row.get('Languages You Can Deliver In', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                    
                    dob_val = row.get('Date of Birth', 'N/A')
                    dob = str(dob_val).split(' ')[0] if dob_val and str(dob_val) not in ['nan', 'NaT'] else 'N/A'
                    
                    photo_url = row.get('Upload profile photo', row.get('Photo', ''))
                    profile_link = row.get("Trainer's Profile / CV", row.get('Upload CV / Resume', ''))
                    
                    img_path = get_drive_image(photo_url, gender, name)
                    
                    # --- Premium Corporate Stationery Header ---
                    pdf.set_fill_color(0, 51, 102) # Dark Blue
                    pdf.rect(0, 0, 210, 4, 'F')
                    
                    if logo_path:
                        pdf.image(logo_path, x=155, y=8, w=45)
                        
                    pdf.set_y(12)
                    pdf.set_font("Arial", 'B', 22)
                    pdf.set_text_color(0, 51, 102)
                    pdf.cell(0, 8, "BLUE WISDOM", ln=1, align="L")
                    
                    pdf.set_font("Arial", 'I', 11)
                    pdf.set_text_color(120, 120, 120)
                    pdf.cell(0, 6, "EXECUTIVE TRAINER PROFILE", ln=1, align="L")
                    
                    pdf.set_y(32)
                    pdf.set_fill_color(200, 200, 200)
                    pdf.rect(10, 32, 190, 0.5, 'F')
                    
                    # --- Two-Column Layout ---
                    # Sidebar Background
                    pdf.set_fill_color(240, 245, 250) # Light Ice Blue
                    pdf.rect(0, 32.5, 75, 297, 'F')
                    
                    # ================= LEFT COLUMN =================
                    if img_path:
                        pdf.image(img_path, x=17, y=40, w=40, h=40)
                        
                    pdf.set_y(85)
                    pdf.set_x(10)
                    
                    def add_sidebar_item(title, value):
                        if str(value).lower() in ['nan', 'n/a', 'none', '']: return
                        pdf.set_x(10)
                        pdf.set_font("Arial", 'B', 10)
                        pdf.set_text_color(0, 51, 102)
                        pdf.cell(55, 6, title.upper(), ln=1, align="L")
                        pdf.set_x(10)
                        pdf.set_font("Arial", '', 10)
                        pdf.set_text_color(60, 60, 60)
                        pdf.multi_cell(55, 5, str(value))
                        pdf.ln(4)
                        
                    add_sidebar_item("Consultant Category", category)
                    add_sidebar_item("Location", loc)
                    add_sidebar_item("Experience", f"{exp} Years")
                    add_sidebar_item("Qualification", qual)
                    add_sidebar_item("Education", edu)
                    add_sidebar_item("Delivery Mode", delivery)
                    add_sidebar_item("Languages", langs)
                    if dob != 'N/A': add_sidebar_item("DOB", dob)
                    
                    if linkedin and str(linkedin).startswith('http'):
                        pdf.set_x(10)
                        pdf.set_font("Arial", 'B', 10)
                        pdf.set_text_color(0, 102, 204)
                        pdf.cell(55, 8, "LinkedIn Profile", link=linkedin, ln=1, align="L")
                    
                    # ================= RIGHT COLUMN =================
                    # Name & Title
                    pdf.set_xy(85, 40)
                    pdf.set_font("Arial", 'B', 24)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(0, 10, name.upper(), ln=1, align="L")
                    
                    pdf.set_x(85)
                    pdf.set_font("Arial", 'B', 12)
                    pdf.set_text_color(0, 102, 204)
                    pdf.cell(0, 6, "EXECUTIVE TRAINER & CONSULTANT", ln=1, align="L")
                    
                    pdf.set_y(60)
                    pdf.set_fill_color(0, 51, 102)
                    pdf.rect(85, 60, 115, 0.5, 'F')
                    pdf.set_y(65)
                    
                    # AI Executive Summary
                    pdf.set_x(85)
                    pdf.set_font("Arial", 'B', 13)
                    pdf.set_text_color(0, 51, 102)
                    pdf.cell(0, 8, "EXECUTIVE SUMMARY", ln=1)
                    
                    ai_summary = generate_ai_summary(name, exp, topics).encode('latin-1', 'replace').decode('latin-1')
                    pdf.set_x(85)
                    pdf.set_font("Arial", '', 11)
                    pdf.set_text_color(50, 50, 50)
                    pdf.multi_cell(115, 6, ai_summary)
                    pdf.ln(8)
                    
                    # Core Expertise Area
                    pdf.set_x(85)
                    pdf.set_font("Arial", 'B', 13)
                    pdf.set_text_color(0, 51, 102)
                    pdf.cell(0, 8, "CORE EXPERTISE & TRAINING TOPICS", ln=1)
                    
                    pdf.set_font("Arial", '', 11)
                    pdf.set_text_color(60, 60, 60)
                    topic_list = [t.strip() for t in topics.split(',')]
                    for t in topic_list:
                        if t and t.lower() not in ['nan', 'n/a']: 
                            pdf.set_x(85)
                            pdf.cell(0, 6, f"  *  {t}", ln=1)
                    pdf.ln(8)
                    
                    # Industries Served
                    if industries.lower() not in ['nan', 'n/a', 'none', '']:
                        pdf.set_x(85)
                        pdf.set_font("Arial", 'B', 13)
                        pdf.set_text_color(0, 51, 102)
                        pdf.cell(0, 8, "INDUSTRIES SERVED", ln=1)
                        pdf.set_font("Arial", '', 11)
                        pdf.set_text_color(60, 60, 60)
                        pdf.set_x(85)
                        pdf.multi_cell(115, 6, industries)
                    
                    # --- Footer / CV Link ---
                    if profile_link and str(profile_link).startswith('http'):
                        pdf.set_y(260)
                        pdf.set_x(85)
                        pdf.set_font("Arial", 'B', 11)
                        pdf.set_text_color(255, 255, 255)
                        pdf.set_fill_color(0, 102, 204)
                        pdf.cell(100, 10, "View Detailed Profile / CV", link=profile_link, ln=1, align="C", fill=True)
                    
                    pdf.set_y(275)
                    pdf.set_x(85)
                    pdf.set_font("Arial", 'I', 9)
                    pdf.set_text_color(150, 150, 150)
                    pdf.cell(0, 10, "To book this trainer, please contact Blue Wisdom Pvt Ltd.", ln=1, align="C")
                    
                # Output PDF to bytes
                pdf_bytes = bytes(pdf.output())
                
                # Create a download link using base64
                b64 = base64.b64encode(pdf_bytes).decode()
                href = f'<a href="data:application/pdf;base64,{b64}" download="BW_Trainer_Profiles.pdf" style="display: inline-block; padding: 10px 20px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">✅ Click Here to Download PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
