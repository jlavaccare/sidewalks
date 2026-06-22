from numpy import percentile
import os
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.validation import make_valid
import folium
import branca.colormap as cm
from folium.plugins import HeatMap

os.chdir("C:/Users/John.LaVaccare/OneDrive - City of Philadelphia/Documents/Sidewalks/Data Analysis/complaints")

sw = pd.read_csv("data/dangeroussidewalk040826.csv")
sw['year'] = sw['requested_datetime'].str[:4]
sw_compl = sw[sw['lat'].notnull()]
sw_compl = sw[sw['year'] != '2026']

sw_sf = gpd.GeoDataFrame(sw_compl, geometry=gpd.points_from_xy(sw_compl.lon, sw_compl.lat), crs="EPSG:4326")

def create_popup_html(row):
    url = row['media_url']
    if not url or url == "" or str(url) == 'nan':
        return "<em>No image available</em>"
    else:
        return f"<br><img src='{url}' width='250'/>"

sw_sf['media_popup'] = sw_sf.apply(create_popup_html, axis=1)

sw_2022 = sw_sf[sw_sf['year'] == '2022']
sw_2023 = sw_sf[sw_sf['year'] == '2023']
sw_2024 = sw_sf[sw_sf['year'] == '2024']
sw_2025 = sw_sf[sw_sf['year'] == '2025']

yrs = ['2022', '2023', '2024', '2025']
sf_2225 = sw_sf[sw_sf['year'].isin(yrs)]

sf_heat = sf_2225 = [[point.xy[1][0], point.xy[0][0]] for point in sf_2225.geometry]

sw_sf.explore()

m = folium.Map(location=[39.9533, -75.1634], zoom_start=11)

# Add Satellite
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Esri Satellite',
    overlay=False,
    control=True
).add_to(m)

folium.GeoJson(
    sw_2022,
    name = "2022 Sidewalk Complaints",
    tooltip=folium.GeoJsonTooltip(fields=['address', 'requested_datetime', 'media_popup'], aliases=['Address: ', 'Request Date: ', 'Image: ']),
    marker=folium.CircleMarker(color="orange", radius=5, fill=True),
    show = False
).add_to(m)

folium.GeoJson(
    sw_2023,
    name = "2023 Sidewalk Complaints",
        marker=folium.CircleMarker(color="purple", radius=5, fill=True),
    tooltip=folium.GeoJsonTooltip(fields=['address', 'requested_datetime', 'media_popup'], aliases=['Address: ', 'Request Date: ', 'Image: ']),
    show = False
).add_to(m)

folium.GeoJson(
    sw_2024,
    name = "2024 Sidewalk Complaints",
        marker=folium.CircleMarker(color="blue", radius=5, fill=True),

    tooltip=folium.GeoJsonTooltip(fields=['address', 'requested_datetime', 'media_popup'], aliases=['Address: ', 'Request Date: ', 'Image: ']),
    show = False
).add_to(m)

folium.GeoJson(
    sw_2025,
    name = "2025 Sidewalk Complaints",
        marker=folium.CircleMarker(color="gold", radius=5, fill=True),

    tooltip=folium.GeoJsonTooltip(fields=['address', 'requested_datetime', 'media_popup'], aliases=['Address: ', 'Request Date: ', 'Image: ']),
    show = False
).add_to(m)


HeatMap(sf_heat, name="Heatmap 2022-25 Sidewalk Complaints").add_to(m)

folium.LayerControl().add_to(m)

m.save("output/complaints.html")
