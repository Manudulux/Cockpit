import pandas as pd
import folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time

# 1. Load and clean the data
# The file appears to be tab-separated with a specific header structure
df = pd.read_csv('T001W.txt', sep='\t', skipinitialspace=True)

# Filter relevant columns for address generation
# NAME1 (Name), STRAS (Street), PSTLZ (Zip), ORT01 (City), LAND1 (Country)
cols = ['NAME1', 'STRAS', 'PSTLZ', 'ORT01', 'LAND1']
df_map = df[cols].dropna(subset=['ORT01']).copy()

# Create a full address string for geocoding
df_map['Full_Address'] = (
    df_map['STRAS'].fillna('') + ', ' + 
    df_map['PSTLZ'].fillna('') + ' ' + 
    df_map['ORT01'] + ', ' + 
    df_map['LAND1']
)

# 2. Geocode the addresses (Convert to Lat/Long)
geolocator = Nominatim(user_agent="map_generator")
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

print("Geocoding locations... This may take a moment.")
# For demonstration, we'll geocode the first 10 locations to avoid API rate limits
df_sample = df_map.head(10).copy()

def get_coordinates(address):
    try:
        location = geolocator.geocode(address)
        return (location.latitude, location.longitude) if location else (None, None)
    except:
        return (None, None)

df_sample['Coords'] = df_sample['Full_Address'].apply(get_coordinates)
df_sample[['Latitude', 'Longitude']] = pd.DataFrame(df_sample['Coords'].tolist(), index=df_sample.index)

# 3. Create the interactive map
# Filter out any locations that couldn't be geocoded
df_final = df_sample.dropna(subset=['Latitude'])

# Initialize the map at the first location
m = folium.Map(location=[df_final.iloc[0]['Latitude'], df_final.iloc[0]['Longitude']], zoom_start=5)

# Add markers for each location
for _, row in df_final.iterrows():
    folium.Marker(
        location=[row['Latitude'], row['Longitude']],
        popup=f"<b>{row['NAME1']}</b><br>{row['Full_Address']}",
        tooltip=row['NAME1']
    ).add_to(m)

# Save the map to an HTML file
m.save('location_map.html')
print("Map saved as 'location_map.html'. Open this file in your browser to view.")
