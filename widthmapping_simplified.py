from numpy import percentile
import os
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import LineString, Point
from shapely.validation import make_valid
import folium
from shapely import unary_union
import streamlit as st
from streamlit_folium import folium_static
import branca.colormap as cm

# Read centerline
centerline_lines = gpd.read_file("data/Street_Centerline/Street_Centerline.shp")
# Read parcel
parcel = gpd.read_file("data/DOR_Parcel/DOR_Parcel.shp")
parcel_mod = parcel[['geometry']].copy().to_crs(epsg=2272)
parcel_mod['geometry'] = parcel_mod.geometry.make_valid()
# read curb
curbs = gpd.read_file("data/Curbs_No_Cartways/Curbs_No_Cartways.shp")
curbs_mod = curbs[['geometry']].copy().to_crs(epsg=2272)
curbs_mod['geometry'] = curbs_mod.geometry.make_valid()
# Read districts
cdd = gpd.read_file("data/Council_Districts_2024/Council_Districts_2024.shp")
cdd['temp_id'] = 0
parks = gpd.read_file("data/PPR_Properties/PPR_Properties.shp")
# parks.explore()
neighborhoods = gpd.read_file("data/philadelphia-neighborhoods/philadelphia-neighborhoods.shp")
large_parks = ['Wissahickon Valley Park', 'West Fairmount Park', 'East Fairmount Park', 'Morris Park', 'Cobbs Creek Golf Course', 'Cobbs Creek Park']
parks_lg = parks[parks['official_n'].isin(large_parks)]
# parks_lg.explore()
city_limits = cdd.dissolve(by = 'temp_id').to_crs(epsg=2272)
city_nonpark = gpd.overlay(city_limits.to_crs(epsg=4326), parks_lg.to_crs(epsg=4326), how = 'difference')
# import result of sidewalkwidths.py
all_df = pd.read_csv("output/sidewalkwidths.csv")
cl_sidewalk_all = centerline_lines.merge(all_df, on='objectid')

def filter_sf(sf_obj, district):
    sf_mod = sf_obj.to_crs(epsg=4326)
    district = district.to_crs(epsg=4326)
    sf_mod['geometry'] = sf_mod['geometry'].apply(make_valid)
    sf_mod = gpd.clip(sf_mod, district)
    return sf_mod

# add council district field to sidewalk width data
cdl = []
for i in range(len(cdd)):
    district = cdd.iloc[[i]]
    df_cd = filter_sf(cl_sidewalk_all, district)
    df_cd['cd'] = district.iloc[0]['DISTRICT']
    cdl.append(df_cd)

all_df_cd = pd.concat(cdl)
all_df_cd = all_df_cd.drop_duplicates('geometry')

# add neighborhood field to sidewalk width data
nbl = []
for i in range(len(neighborhoods)):
    nbx = neighborhoods.iloc[[i]]
    df_cd = filter_sf(cl_sidewalk_all, nbx)
    df_cd['nbr'] = nbx.iloc[0]['MAPNAME']
    nbl.append(df_cd)

all_df_cd = pd.concat(nbl)
all_df_cd = all_df_cd.drop_duplicates('geometry')

# Remove unneeded fields
all_df_simple = all_df[['sidewalk_left', 'sidewalk_right', 'row_id', 'st_name', 'name']]
all_df_simple['objectid'] = all_df_simple['row_id']

all_df_cd['sidewalk_left'] = all_df_cd['sidewalk_left'].fillna(-0.01)
all_df_cd['sidewalk_right'] = all_df_cd['sidewalk_right'].fillna(-0.01)

# generate "sidewalk conditions" categorical variable
sw_cond = [
    ((all_df_cd['sidewalk_left'] < 0) & (all_df_cd['sidewalk_right'] < 0)),
    ((all_df_cd['sidewalk_left'] < 6) & (all_df_cd['sidewalk_right'] < 6)),
    ((all_df_cd['sidewalk_left'] < 10) & (all_df_cd['sidewalk_right'] < 10)),
    ((all_df_cd['sidewalk_left'] < 10) | (all_df_cd['sidewalk_right'] < 10)),
    ((all_df_cd['sidewalk_left'] > 10) & (all_df_cd['sidewalk_right'] > 10)),
    ((all_df_cd['sidewalk_left'] > 30) & (all_df_cd['sidewalk_right'] > 30))
]


choices = ["error", "both_u", "both_n", "one_n", "both_w", "error"]

all_df_cd['risk_status_l'] = np.select(sw_cond, choices, default = 'error')


# remove any rows with blank geometry
all_df_cd = all_df_cd.dropna(subset=['geometry']).drop(columns=['update_', 'newsegdate'], errors='ignore')

# removing highways and other non-relevant streets
to_keep = [2, 3, 4, 5]
all_streets = all_df_cd[all_df_cd['class'].isin(to_keep)]

# convert CRS
if all_streets.crs != 'EPSG:4326':
    all_streets = all_streets.to_crs('EPSG:4326')

# removing streets within parsk
all_streets = all_streets.clip(city_nonpark.to_crs(epsg=4326))
all_streets = all_streets[~(all_streets['responsibl'].isin(['FAIRMOUNT PARK','AIRPORT']))]
# remove any rows with blank geometry
all_streets = all_streets[~all_streets.geometry.is_empty & all_streets.geometry.notna()]
# removing polygon and point geometries
all_streets = all_streets[all_streets.geometry.type.isin(['LineString','MultiLineString'])]

# removing very short and very long street segments
all_streets = all_streets[all_streets['Shape__Len'] > 30]
all_streets = all_streets[all_streets['Shape__Len'] < 2000]

# summary table by council district
# risk_l = pd.DataFrame(all_streets.groupby(['cd', 'risk_status_l'], as_index = False).agg({'Shape__Len': 'size'})).pivot(index = 'risk_status_l', columns= 'cd', values= 'Shape__Len').to_csv("by_dist.csv")
# summary table by neighborhood
risk_l_2 = pd.DataFrame(all_streets.groupby(['nbr', 'risk_status_l'], as_index = False).agg({'Shape__Len': 'size'})).pivot(columns = 'risk_status_l', index= 'nbr', values= 'Shape__Len').reset_index()
# merge with neighborhood shapefile for mapping
nbr_map = neighborhoods.merge(risk_l_2, left_on='MAPNAME', right_on = 'nbr')
nbr_map['total'] = nbr_map.iloc[:, 7:].sum(axis=1).fillna(0)
nbr_map['pct_both_u'] = (nbr_map['both_u']/nbr_map['total']).fillna(0)
nbr_map['pct_both_uf'] = nbr_map['pct_both_u'].map(lambda x: '{:.1f}%'.format(x * 100))
nbr_map['pct_both_n'] = (nbr_map['both_n']/nbr_map['total']).fillna(0)
nbr_map['pct_both_nf'] = nbr_map['pct_both_n'].map(lambda x: '{:.1f}%'.format(x * 100))
nbr_map['pct_one_n'] = (nbr_map['one_n']/(nbr_map['total'])).fillna(0)
nbr_map['pct_one_nf'] = nbr_map['pct_one_n'].map(lambda x: '{:.1f}%'.format(x * 100))
nbr_map['pct_both_w'] = (nbr_map['both_w']/(nbr_map['total'])).fillna(0)
nbr_map['pct_both_wf'] = nbr_map['pct_both_w'].map(lambda x: '{:.1f}%'.format(x * 100))
nbr_map['pct_error'] = ( ((nbr_map['error']).fillna(0))/(nbr_map['total'])).fillna(0)
nbr_map['pct_errorf'] = nbr_map['pct_error'].map(lambda x: '{:.1f}%'.format(x * 100))

#.to_csv("by_nbr.csv")


# colormap
linear = cm.LinearColormap(["blue", "red"], vmin=0, vmax = max(nbr_map['pct_both_n']))
mm = folium.Map(location=[39.9533, -75.1634], zoom_start=11)

# Add Satellite
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Esri Satellite',
    overlay=False,
    control=True
).add_to(mm)

# Add GeoJSON to map
folium.GeoJson(
    nbr_map,
    name="Sidewalk Width",
    style_function= lambda feature: {
        "fillColor": linear(feature['properties']['pct_both_n']),
        "fillOpacity": 0.9,
        "color": "black",
        "weight": 1
    },
    tooltip=folium.GeoJsonTooltip(fields=['nbr', 'pct_both_uf', 'pct_both_nf', 'pct_one_nf', 'pct_both_wf', 'pct_errorf'], aliases=['Neighborhood: ', 'Both Sides Ultra-Narrow (under 6ft): ', 'Both Sides Narrow (under 10ft): ', 'One Side Narrow: ', 'Both Sides Wide (over 10 ft): ', 'Error: '])
).add_to(mm)

folium.GeoJson(
    cdd,
    name="Council Districts",
    show = False,
    style_function= lambda feature: {
        "fillColor": 'transparent',
        "fillOpacity": 0,
        "color": "black",
        "weight": 4
    },
).add_to(mm)

linear.caption = "Pct. of Streets with Narrow Sidewalks** on Both Sides"
mm.add_child(linear)

folium.LayerControl().add_to(mm)


mm.save("output/curb_parcel_narrow.html")



# Color map of every street
# Create color map based on category
categories = all_streets['risk_status_l'].unique()
colors = ['#424242', '#9a6fe3' , '#420d09','#0218de', '#de0202' ] #['error', 'one_n' 'both_u', 'both_w', 'both_n']
color_map = {cat: colors[i % len(colors)] for i, cat in enumerate(categories)}

m = folium.Map(location=[39.9533, -75.1634], zoom_start=11)

# Add Satellite
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Esri Satellite',
    overlay=False,
    control=True
).add_to(m)

def style_function(feature):
    category = feature['properties']['risk_status_l']
    line_color = color_map.get(category, '#424242')
    
    style = {
        'color': line_color,
        'weight': 3,
        'opacity': 0.7
    }

    if feature['geometry']['type'] in ['Polygon', 'MultiPolygon']:
        style['fillColor'] = line_color
        style['fillOpacity'] = 0.5
        
    return style

# Add GeoJSON to map
folium.GeoJson(
    all_streets,
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(fields=['st_name_x', 'sidewalk_left', 'sidewalk_right', 'risk_status_l'], aliases=['Street Name: ', 'Distance_Left: ', 'Distance_Right: ', 'Status: '])
).add_to(m)

folium.LayerControl().add_to(m)

m.save("output/curb_parcel_allstreets.html")

#st.title("Curb-Property Line Distances in Philadelphia Neighborhoods (Sidewalk Proxy)")
#folium_static(mm)