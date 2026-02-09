import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

st.set_page_config(page_title="Location Map Cockpit", layout="wide")

st.title("📍 Site Location Map")

# 1. Load Data with correct encoding and skipping headers
@st.cache_data
def load_data(file_path):
    # Encoding 'ISO-8859-1' handles special characters like 'ß'
    # skiprows=4 starts reading at the column headers (MANDT, WERKS, etc.)
    df = pd.read_csv(file_path, sep='\t', encoding='ISO-8859-1', skiprows=4)
    
    # Drop rows that are completely empty or metadata artifacts
    df = df.dropna(subset=['NAME1', 'ORT01'])
    
    # Create a clean address string for geocoding
    df['Full_Address'] = (
        df['STRAS'].fillna('') + ', ' + 
        df['PSTLZ'].astype(str).str.replace('.0', '', regex=False) + ' ' + 
        df['ORT01'] + ', ' + 
        df['LAND1']
    )
    return df

# 2. Geocoding Function with Caching
@st.cache_data
def geocode_addresses(df):
    geolocator = Nominatim(user_agent="my_map_app")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    
    latitudes = []
    longitudes = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # We limit to first 20 for performance/API limits; remove .head(20) for full list
    subset = df.head(20).copy() 
    
    for i, row in enumerate(subset.itertuples()):
        status_text.text(f"Geocoding: {row.NAME1} ({i+1}/{len(subset)})")
        try:
            location = geocode(row.Full_Address)
            if location:
                latitudes.append(location.latitude)
                longitudes.append(location.longitude)
            else:
                latitudes.append(None)
                longitudes.append(None)
        except:
            latitudes.append(None)
            longitudes.append(None)
        
        progress_bar.progress((i + 1) / len(subset))
        
    subset['lat'] = latitudes
    subset['lon'] = longitudes
    return subset.dropna(subset=['lat', 'lon'])

# --- Main App Logic ---

try:
    data = load_data('T001W.txt')
    
    st.sidebar.info(f"Loaded {len(data)} locations from file.")
    
    if st.sidebar.button("Generate Map"):
        with st.spinner("Fetching coordinates..."):
            mapped_df = geocode_addresses(data)
            
            if not mapped_df.empty:
                # Initialize Folium Map
                m = folium.Map(
                    location=[mapped_df['lat'].mean(), mapped_df['lon'].mean()], 
                    zoom_start=4
                )
                
                # Add Markers
                for _, row in mapped_df.iterrows():
                    folium.Marker(
                        location=[row['lat'], row['lon']],
                        popup=f"<b>{row['NAME1']}</b><br>{row['Full_Address']}",
                        tooltip=row['NAME1']
                    ).add_to(m)
                
                # Display Map in Streamlit
                st_folium(m, width=1200, height=600)
                st.success(f"Mapped {len(mapped_df)} locations successfully!")
            else:
                st.error("No locations could be geocoded. Check address formats.")

except FileNotFoundError:
    st.error("File 'T001W.txt' not found. Please ensure it is in the same directory.")
except Exception as e:
    st.error(f"An error occurred: {e}")
