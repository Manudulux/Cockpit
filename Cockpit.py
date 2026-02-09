import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import os

# 1. SET PAGE TO WIDE MODE AND INJECT FULL-WIDTH CSS
st.set_page_config(page_title="SAP Global Site Monitor", layout="wide")

st.markdown("""
    <style>
        /* This removes the maximum width constraint and top padding */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
        }
        /* Optional: Hide the Streamlit header to save more vertical space */
        header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

SAP_FILE = 'T001W.txt'
CACHE_FILE = 'geocoded_cache.csv'

# --- 2. DATA HELPERS ---
@st.cache_data
def load_sap_data(file_path):
    header_idx = 0
    with open(file_path, 'r', encoding='ISO-8859-1') as f:
        for i, line in enumerate(f):
            if 'MANDT' in line and 'NAME1' in line:
                header_idx = i
                break
    df = pd.read_csv(file_path, sep='\t', encoding='ISO-8859-1', skiprows=header_idx)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df = df.dropna(subset=['NAME1', 'ORT01'])
    
    df['Full_Address'] = (
        df['STRAS'].fillna('').astype(str).str.strip() + ', ' + 
        df['PSTLZ'].fillna('').astype(str).str.replace('.0', '', regex=False).str.strip() + ' ' + 
        df['ORT01'].astype(str).str.strip() + ', ' + 
        df['LAND1'].astype(str).str.strip()
    )
    return df

def load_cache():
    if os.path.exists(CACHE_FILE):
        return pd.read_csv(CACHE_FILE)
    return pd.DataFrame(columns=['Full_Address', 'lat', 'lon'])

# --- 3. UI INITIALIZATION ---
st.title("📍 SAP Global Site Monitor")
sap_data = load_sap_data(SAP_FILE)
cache_df = load_cache()

full_df = sap_data.merge(cache_df[['Full_Address', 'lat', 'lon']], on='Full_Address', how='left')
mapped_df = full_df.dropna(subset=['lat', 'lon'])

# Sidebar
st.sidebar.header("Data Management")
pending_count = len(full_df[full_df['lat'].isna()])
st.sidebar.metric("Cached Sites", len(mapped_df))
st.sidebar.metric("Pending Sites", pending_count)

if not mapped_df.empty:
    csv = mapped_df[['Full_Address','lat','lon']].to_csv(index=False)
    st.sidebar.download_button("📥 Download Cache", csv, "geocoded_cache.csv", "text/csv")

# --- 4. THE "RUN ALL" LOGIC ---
if pending_count > 0:
    if st.sidebar.button("🚀 Run All Geocoding"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        geolocator = Nominatim(user_agent="sap_global_mapper_v3")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
        
        new_results = []
        pending_df = full_df[full_df['lat'].isna()].copy()

        for i, row in enumerate(pending_df.itertuples()):
            status_text.text(f"Geocoding {i+1}/{len(pending_df)}: {row.NAME1}")
            try:
                loc = geocode(row.Full_Address)
                if loc:
                    new_results.append({'Full_Address': row.Full_Address, 'lat': loc.latitude, 'lon': loc.longitude})
            except:
                pass
            progress_bar.progress((i + 1) / len(pending_df))
            
            # Auto-save every 5
            if len(new_results) % 5 == 0 and len(new_results) > 0:
                batch_df = pd.DataFrame(new_results)
                pd.concat([cache_df, batch_df]).drop_duplicates('Full_Address').to_csv(CACHE_FILE, index=False)
        
        # Final Save and Rerun
        if new_results:
            batch_df = pd.DataFrame(new_results)
            pd.concat([cache_df, batch_df]).drop_duplicates('Full_Address').to_csv(CACHE_FILE, index=False)
        st.rerun()

# --- 5. FULL-WIDTH MAP RENDERING ---
if not mapped_df.empty:
    center_lat = mapped_df['lat'].mean()
    center_lon = mapped_df['lon'].mean()
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=3, control_scale=True)
    
    for _, r in mapped_df.iterrows():
        folium.Marker(
            [r.lat, r.lon], 
            popup=f"<b>{r.NAME1}</b><br>{r.Full_Address}",
            tooltip=r.NAME1
        ).add_to(m)
    
    # 6. EXPANDED DIMENSIONS
    # Use use_container_width=True and a larger height (e.g., 800px)
    st_folium(
        m, 
        width=None,           # Setting width to None + use_container_width=True makes it fill horizontally
        height=800,           # Increased height from 600 to 800
        use_container_width=True, 
        key="main_map_full_screen",
        returned_objects=[]
    )
else:
    st.info("No data available. Click 'Run All' in the sidebar.")
