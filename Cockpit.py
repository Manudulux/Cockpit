import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import os

st.set_page_config(page_title="SAP Location Map", layout="wide")

st.title("📍 Interactive Site Map")

# --- 1. ROBUST DATA LOADING ---
@st.cache_data
def load_data(file_path):
    if not os.path.exists(file_path):
        return None, "File not found."

    # First, find which row contains the actual headers
    header_idx = 0
    with open(file_path, 'r', encoding='ISO-8859-1') as f:
        for i, line in enumerate(f):
            if 'MANDT' in line and 'NAME1' in line:
                header_idx = i
                break
    
    # Load the file starting from the detected header row
    try:
        df = pd.read_csv(file_path, sep='\t', encoding='ISO-8859-1', skiprows=header_idx)
        
        # Clean column names (remove leading/trailing spaces and tabs)
        df.columns = df.columns.str.strip()
        
        # Filter out empty 'Unnamed' columns caused by leading tabs in the file
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        # Check if required columns exist
        required = ['NAME1', 'ORT01', 'STRAS', 'LAND1']
        missing = [col for col in required if col not in df.columns]
        
        if missing:
            return None, f"Missing columns in file: {missing}. Found: {list(df.columns[:5])}..."

        # Drop purely decorative rows (like lines of dashes) or empty rows
        df = df.dropna(subset=['NAME1', 'ORT01'])
        
        # Create a clean address string for geocoding
        # Handles Zip codes (PSTLZ) being read as numbers or strings
        df['Full_Address'] = (
            df['STRAS'].fillna('').astype(str).str.strip() + ', ' + 
            df['PSTLZ'].fillna('').astype(str).str.replace('.0', '', regex=False).str.strip() + ' ' + 
            df['ORT01'].astype(str).str.strip() + ', ' + 
            df['LAND1'].astype(str).str.strip()
        )
        return df, None
        
    except Exception as e:
        return None, f"Parsing error: {str(e)}"

# --- 2. CACHED GEOCODING ---
@st.cache_data
def geocode_addresses(df_subset):
    geolocator = Nominatim(user_agent="sap_map_app_v1")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.2)
    
    # To keep performance stable, we'll map the first 30 locations
    # You can increase this, but geocoding is slow (1.5s per address)
    df_to_map = df_subset.head(30).copy()
    
    lats, lons = [], []
    progress_bar = st.progress(0)
    
    for i, row in enumerate(df_to_map.itertuples()):
        try:
            location = geocode(row.Full_Address)
            if location:
                lats.append(location.latitude)
                lons.append(location.longitude)
            else:
                lats.append(None)
                lons.append(None)
        except:
            lats.append(None)
            lons.append(None)
        progress_bar.progress((i + 1) / len(df_to_map))
        
    df_to_map['lat'] = lats
    df_to_map['lon'] = lons
    return df_to_map.dropna(subset=['lat', 'lon'])

# --- MAIN APP LOGIC ---

# Attempt to load the file
data, error_msg = load_data('T001W.txt')

if error_msg:
    st.error(error_msg)
    st.info("Ensure T001W.txt is in the same folder as this script on GitHub.")
else:
    st.sidebar.success(f"Successfully loaded {len(data)} locations.")
    
    # User selects how many locations to map
    num_to_map = st.sidebar.slider("Number of sites to geocode", 5, 50, 20)
    
    if st.sidebar.button("Generate Map"):
        with st.spinner("Geocoding addresses... (This takes ~1.5s per location)"):
            mapped_df = geocode_addresses(data.head(num_to_map))
            
            if not mapped_df.empty:
                # Create the map centered at the average coordinates
                avg_lat = mapped_df['lat'].mean()
                avg_lon = mapped_df['lon'].mean()
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=4)
                
                # Add individual markers
                for _, row in mapped_df.iterrows():
                    folium.Marker(
                        location=[row['lat'], row['lon']],
                        popup=f"<b>{row['NAME1']}</b><br>{row['Full_Address']}",
                        tooltip=row['NAME1']
                    ).add_to(m)
                
                # Display the interactive map
                st_folium(m, width=1000, height=600)
                st.write(f"Showing {len(mapped_df)} successfully located sites.")
            else:
                st.error("Could not find coordinates for these addresses. Please check the address format in the file.")

    # Show raw data preview in the sidebar
    if st.sidebar.checkbox("Show Data Preview"):
        st.write(data[['NAME1', 'STRAS', 'ORT01', 'LAND1']].head(10))
