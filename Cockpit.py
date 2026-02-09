import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import os
import time

st.set_page_config(page_title="Iterative SAP Mapper", layout="wide")

SAP_FILE = 'T001W.txt'
CACHE_FILE = 'geocoded_cache.csv'

st.title("📍 Iterative Site Mapper")
st.markdown("Processes locations in blocks of 10 and updates the map live.")

# --- 1. INITIALIZE SESSION STATE ---
# We use session state to keep track of the data between re-runs
if 'mapped_df' not in st.session_state:
    st.session_state.mapped_df = pd.DataFrame()
if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False

# --- 2. DATA LOADING ---
@st.cache_data
def load_sap_data(file_path):
    if not os.path.exists(file_path):
        return None, "SAP file not found."
    
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
    return df, None

def load_cache():
    if os.path.exists(CACHE_FILE):
        return pd.read_csv(CACHE_FILE)
    return pd.DataFrame(columns=['Full_Address', 'lat', 'lon'])

# --- 3. THE MAPPING UI ---
sap_data, error = load_sap_data(SAP_FILE)

if error:
    st.error(error)
else:
    # Sidebar Controls
    st.sidebar.header("Controls")
    
    # Download Button
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as file:
            st.sidebar.download_button(
                label="📥 Download Geocoded Cache",
                data=file,
                file_name="geocoded_cache.csv",
                mime="text/csv"
            )
    
    if st.sidebar.button("Start Iterative Geocoding"):
        st.session_state.is_processing = True

    # Main Display Area
    status_container = st.empty()
    map_container = st.empty()

    # Logic to process data
    cache_df = load_cache()
    
    # Initial merge to see what we already have
    full_df = sap_data.merge(cache_df[['Full_Address', 'lat', 'lon']], on='Full_Address', how='left')
    
    # Update Session State with existing cached items
    st.session_state.mapped_df = full_df.dropna(subset=['lat', 'lon'])

    # --- 4. BATCH PROCESSING LOOP ---
    if st.session_state.is_processing:
        pending_df = full_df[full_df['lat'].isna()].copy()
        
        if pending_df.empty:
            status_container.success("All locations are already geocoded!")
            st.session_state.is_processing = False
        else:
            geolocator = Nominatim(user_agent="sap_batch_mapper")
            geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.2)
            
            # Process in blocks of 10
            batch_size = 10
            for i in range(0, len(pending_df), batch_size):
                batch = pending_df.iloc[i : i + batch_size].copy()
                status_container.info(f"Processing block {i//batch_size + 1}: {len(batch)} items...")
                
                new_lats, new_lons = [], []
                for row in batch.itertuples():
                    try:
                        loc = geocode(row.Full_Address)
                        new_lats.append(loc.latitude if loc else None)
                        new_lons.append(loc.longitude if loc else None)
                    except:
                        new_lats.append(None)
                        new_lons.append(None)
                
                batch['lat'] = new_lats
                batch['lon'] = new_lons
                
                # Update Cache File
                new_successes = batch.dropna(subset=['lat', 'lon'])[['Full_Address', 'lat', 'lon']]
                updated_cache = pd.concat([cache_df, new_successes]).drop_duplicates('Full_Address')
                updated_cache.to_csv(CACHE_FILE, index=False)
                cache_df = updated_cache # Update local variable for next loop iteration
                
                # Update Map Data for the current display
                st.session_state.mapped_df = pd.concat([st.session_state.mapped_df, new_successes])
                
                # Force Map Redraw
                with map_container:
                    m = folium.Map(location=[st.session_state.mapped_df['lat'].mean(), 
                                             st.session_state.mapped_df['lon'].mean()], zoom_start=3)
                    for _, r in st.session_state.mapped_df.iterrows():
                        folium.Marker([r.lat, r.lon], popup=r.Full_Address).add_to(m)
                    st_folium(m, width=900, height=500, key=f"map_batch_{i}")

            status_container.success("Processing Complete!")
            st.session_state.is_processing = False
            st.rerun()

    # --- 5. STATIC MAP DISPLAY (When not processing) ---
    if not st.session_state.is_processing and not st.session_state.mapped_df.empty:
        status_container.write(f"Displaying {len(st.session_state.mapped_df)} cached locations.")
        with map_container:
            m = folium.Map(location=[st.session_state.mapped_df['lat'].mean(), 
                                     st.session_state.mapped_df['lon'].mean()], zoom_start=3)
            for _, r in st.session_state.mapped_df.iterrows():
                folium.Marker([r.lat, r.lon], popup=r.Full_Address).add_to(m)
            st_folium(m, width=900, height=500, key="static_map")
