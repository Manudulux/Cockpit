import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import os

st.set_page_config(page_title="SAP Site Analytics", layout="wide")

SAP_FILE = 'T001W.txt'
CACHE_FILE = 'geocoded_cache.csv'

# --- 1. SESSION STATE ---
if 'mapped_df' not in st.session_state:
    st.session_state.mapped_df = pd.DataFrame()
if 'run_all' not in st.session_state:
    st.session_state.run_all = False

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
    
    # Address Construction
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

# Merge to see existing vs pending
full_df = sap_data.merge(cache_df[['Full_Address', 'lat', 'lon']], on='Full_Address', how='left')
st.session_state.mapped_df = full_df.dropna(subset=['lat', 'lon'])

# Sidebar
st.sidebar.header("Data Management")
pending_count = len(full_df[full_df['lat'].isna()])
st.sidebar.metric("Cached Sites", len(st.session_state.mapped_df))
st.sidebar.metric("Pending Sites", pending_count)

# Download Cache
if not st.session_state.mapped_df.empty:
    csv = st.session_state.mapped_df[['Full_Address','lat','lon']].to_csv(index=False)
    st.sidebar.download_button("📥 Download geocoded_cache.csv", csv, "geocoded_cache.csv", "text/csv")

# --- 4. THE "RUN ALL" LOGIC ---
if pending_count > 0:
    if st.sidebar.button("🚀 Run All Geocoding"):
        st.session_state.run_all = True

if st.session_state.run_all:
    pending_df = full_df[full_df['lat'].isna()].copy()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    stop_button = st.sidebar.button("Stop Geocoding")

    geolocator = Nominatim(user_agent="sap_global_mapper_v2")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
    
    new_results = []
    
    for i, row in enumerate(pending_df.itertuples()):
        if stop_button:
            st.session_state.run_all = False
            break
            
        status_text.text(f"Geocoding {i+1}/{len(pending_df)}: {row.NAME1}")
        try:
            loc = geocode(row.Full_Address)
            if loc:
                new_results.append({'Full_Address': row.Full_Address, 'lat': loc.latitude, 'lon': loc.longitude})
        except:
            pass
        
        progress_bar.progress((i + 1) / len(pending_df))
        
        # Save to disk every 5 items as a safety backup
        if len(new_results) % 5 == 0 and len(new_results) > 0:
            batch_df = pd.DataFrame(new_results)
            updated_cache = pd.concat([cache_df, batch_df]).drop_duplicates('Full_Address')
            updated_cache.to_csv(CACHE_FILE, index=False)

    # Final Save
    if new_results:
        batch_df = pd.DataFrame(new_results)
        updated_cache = pd.concat([cache_df, batch_df]).drop_duplicates('Full_Address')
        updated_cache.to_csv(CACHE_FILE, index=False)
    
    st.session_state.run_all = False
    st.rerun()

# --- 5. MAP RENDERING (NO FLASH) ---
if not st.session_state.mapped_df.empty:
    # Use Container to keep layout clean
    with st.container():
        st.subheader("Interactive Site Map")
        center_lat = st.session_state.mapped_df['lat'].mean()
        center_lon = st.session_state.mapped_df['lon'].mean()
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=3, control_scale=True)
        
        # Add Markers
        for _, r in st.session_state.mapped_df.iterrows():
            folium.Marker(
                [r.lat, r.lon], 
                popup=f"<b>{r.NAME1}</b><br>{r.Full_Address}",
                tooltip=r.NAME1
            ).add_to(m)
        
        # This only renders once the script is done with geocoding
        st_folium(m, width=1200, height=600, key="main_map_static", returned_objects=[])
else:
    st.info("No data available to map. Please click 'Run All Geocoding' in the sidebar.")
