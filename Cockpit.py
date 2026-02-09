import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import os

st.set_page_config(page_title="Persistent SAP Map", layout="wide")

# File paths
SAP_FILE = 'T001W.txt'
CACHE_FILE = 'geocoded_cache.csv'

st.title("📍 Site Map with Persistent Cache")

# --- 1. DATA LOADING & CLEANING ---
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
    
    # Create the unique address string (used as our lookup key)
    df['Full_Address'] = (
        df['STRAS'].fillna('').astype(str).str.strip() + ', ' + 
        df['PSTLZ'].fillna('').astype(str).str.replace('.0', '', regex=False).str.strip() + ' ' + 
        df['ORT01'].astype(str).str.strip() + ', ' + 
        df['LAND1'].astype(str).str.strip()
    )
    return df, None

# --- 2. PERSISTENT CACHE LOGIC ---
def get_geocoded_data(df):
    # Load existing cache if it exists
    if os.path.exists(CACHE_FILE):
        cache_df = pd.read_csv(CACHE_FILE)
        # Keep only the unique address and its coordinates
        cache_df = cache_df[['Full_Address', 'lat', 'lon']].drop_duplicates('Full_Address')
    else:
        cache_df = pd.DataFrame(columns=['Full_Address', 'lat', 'lon'])

    # Merge SAP data with cache
    merged_df = df.merge(cache_df, on='Full_Address', how='left')
    
    # Identify rows that still need geocoding (lat/lon are NaN)
    to_geocode = merged_df[merged_df['lat'].isna()].copy()
    already_geocoded = merged_df[merged_df['lat'].notna()].copy()

    if not to_geocode.empty:
        st.info(f"Geocoding {len(to_geocode)} new addresses...")
        geolocator = Nominatim(user_agent="sap_persistent_map")
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.2)
        
        lats, lons = [], []
        progress_bar = st.progress(0)
        
        for i, row in enumerate(to_geocode.itertuples()):
            try:
                location = geocode(row.Full_Address)
                lats.append(location.latitude if location else None)
                lons.append(location.longitude if location else None)
            except:
                lats.append(None)
                lons.append(None)
            progress_bar.progress((i + 1) / len(to_geocode))
        
        to_geocode['lat'] = lats
        to_geocode['lon'] = lons
        
        # Combine old and new findings
        updated_full_df = pd.concat([already_geocoded, to_geocode])
        
        # Save ONLY the geocoding results to the cache file for next time
        # We drop rows where geocoding failed so we can try them again later if needed
        save_df = updated_full_df.dropna(subset=['lat', 'lon'])[['Full_Address', 'lat', 'lon']]
        save_df.to_csv(CACHE_FILE, index=False)
        
        return updated_full_df
    
    return already_geocoded

# --- MAIN APP ---
data, error = load_sap_data(SAP_FILE)

if error:
    st.error(error)
else:
    # Always display stats
    st.sidebar.write(f"Total sites in file: {len(data)}")
    
    if st.sidebar.button("Update & View Map"):
        final_df = get_geocoded_data(data)
        map_ready_df = final_df.dropna(subset=['lat', 'lon'])
        
        if not map_ready_df.empty:
            st.success(f"Displaying {len(map_ready_df)} sites ({len(final_df)-len(map_ready_df)} failed to locate).")
            
            # Map generation
            m = folium.Map(location=[map_ready_df['lat'].mean(), map_ready_df['lon'].mean()], zoom_start=4)
            for _, row in map_ready_df.iterrows():
                folium.Marker(
                    location=[row['lat'], row['lon']],
                    popup=f"<b>{row['NAME1']}</b><br>{row['Full_Address']}",
                    tooltip=row['NAME1']
                ).add_to(m)
            
            st_folium(m, width=1000, height=600)
        else:
            st.warning("No coordinates found. Try clicking 'Update' to search.")

    if os.path.exists(CACHE_FILE):
        if st.sidebar.button("Clear Cache"):
            os.remove(CACHE_FILE)
            st.sidebar.warning("Cache deleted. Next run will re-search everything.")





