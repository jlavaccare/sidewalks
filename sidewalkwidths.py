from numpy import percentile
import os
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import LineString, Point
from shapely.validation import make_valid

os.chdir("C:/Users/John.LaVaccare/OneDrive - City of Philadelphia/Documents/Sidewalks/Data Analysis/sidewalkwidth_am")

# Read data
centerline_lines = gpd.read_file("data/Street_Centerline/Street_Centerline.shp")
parcel = gpd.read_file("data/DOR_Parcel/DOR_Parcel.shp")
parcel_mod = parcel[['geometry']].copy()
parcel_mod['geometry'] = parcel_mod.geometry.make_valid()
parcel_mod = parcel_mod[parcel_mod.geometry.notnull()]
parcel_mod['geometry'] = parcel_mod.geometry.simplify(0.1, preserve_topology=True)
curbs = gpd.read_file("data/Curbs_No_Cartways/Curbs_No_Cartways.shp")
pdd = gpd.read_file("data/Planning_Districts/Planning_Districts.shp").to_crs(epsg=4326)
pdd.columns = pdd.columns.str.lower().str.replace(' ', '_')


dist_list = []

def filter_sf(sf_obj, district):
    sf_mod = sf_obj.to_crs(epsg=4326)
    sf_mod['geometry'] = sf_mod['geometry'].apply(make_valid)
    sf_mod = gpd.clip(sf_mod, district)
    return sf_mod


for i in range(len(pdd)):
    district = pdd.iloc[[i]]

    cbc = filter_sf(curbs, district).to_crs(epsg=2272)
        # Combine all curbs into one geometry for fast single intersection test

    cll = filter_sf(centerline_lines, district)
    cll = cll.reset_index(drop=True)
    cll['orig_id'] = cll.index + 1
    cll = cll.explode(index_parts=False).reset_index(drop=True)
    cll = cll.to_crs(epsg=2272)

    # Sample midpoint of each linestring
    def sample_midpoint(line):
        if line.length == 0:
            return Point(line.coords[0])
        return line.interpolate(0.5, normalized=True)

    cll_p_geom = cll.geometry.apply(sample_midpoint)
    cll_p = gpd.GeoDataFrame(geometry=cll_p_geom, crs=cll.crs)

    plc = filter_sf(parcel_mod, district).to_crs(epsg=2272)
    plc = plc[plc.is_valid]
    plc['geometry'] = plc.buffer(0)
    plc = plc[plc.geometry.notnull() & ~plc.geometry.is_empty]

    if i == 6:
        plc = plc.drop(index=482411)

    if i == 15:
        plc = plc.drop(index = 478199)

    print("Data filtered for ", district.iloc[0]['dist_name'])

    def get_direction(line_geom):
        coords = np.array(line_geom.coords)
        dx = coords[-1, 0] - coords[0, 0]
        dy = coords[-1, 1] - coords[0, 1]
        length = np.sqrt(dx**2 + dy**2)
        return np.array([dx / length, dy / length])

    ray_length = 75  # max search distance (ft)

    coords = np.array([point.coords[0] for point in cll_p.geometry])
    dirs = np.array([get_direction(line) for line in cll.geometry])

    left_dirs = np.column_stack([-dirs[:, 1], dirs[:, 0]])
    right_dirs = np.column_stack([dirs[:, 1], -dirs[:, 0]])

    print("Street directions complete for ", district.iloc[0]['dist_name'])

    def make_rays(points, dirs, length):
        start = np.array([point.coords[0] for point in points.geometry])
        end = start + dirs * length
        rays = [LineString([start[i], end[i]]) for i in range(len(start))]
        return gpd.GeoSeries(rays, crs=points.crs)

    left_rays = make_rays(cll_p, left_dirs, ray_length)
    right_rays = make_rays(cll_p, right_dirs, ray_length)

    left_rays_sf = gpd.GeoDataFrame({'row_id': range(1, len(cll_p) + 1)}, geometry=left_rays, crs=cll_p.crs)
    right_rays_sf = gpd.GeoDataFrame({'row_id': range(1, len(cll_p) + 1)}, geometry=right_rays, crs=cll_p.crs)

    print("Ray calculations complete for ", district.iloc[0]['dist_name'])

    # Intersections with curbs
    left_curb_int = gpd.overlay(left_rays_sf, cbc, how='intersection', keep_geom_type='False')
    right_curb_int = gpd.overlay(right_rays_sf, cbc, how='intersection', keep_geom_type='False')

    print("curb intersections complete for ", district.iloc[0]['dist_name'])

    def compute_min_dist(intersections, points, label):
        if intersections.empty:
            return pd.DataFrame(columns=['row_id', label])
        intersections['dist'] = intersections.apply(
            lambda row: points.loc[row['row_id'] - 1].geometry.distance(row.geometry), axis=1)
        grouped = intersections.groupby('row_id')['dist'].min().reset_index()
        grouped[label] = grouped['dist']
        return grouped[['row_id', label]]

    lcd = compute_min_dist(left_curb_int, cll_p, 'left_curb_m')
    rcd = compute_min_dist(right_curb_int, cll_p, 'right_curb_m')

    print("Curb distances complete for ", district.iloc[0]['dist_name'])

    # Intersections with parcel union
    left_parcel_int = gpd.overlay(left_rays_sf, plc, how='intersection', keep_geom_type='False', make_valid='True')
    right_parcel_int = gpd.overlay(right_rays_sf, plc, how='intersection', keep_geom_type='False', make_valid='True')

    print("Parcel intersections complete for ", district.iloc[0]['dist_name'])

    lpd = compute_min_dist(left_parcel_int, cll_p, 'left_parcel_m')
    rpd = compute_min_dist(right_parcel_int, cll_p, 'right_parcel_m')

    print("Parcel distances complete for ", district.iloc[0]['dist_name'])

    cll_names = (cll.assign(row_id=range(1, len(cll) + 1))
                 .drop(columns='geometry')
                 .loc[:, ['row_id', 'objectid', 'pre_dir', 'st_name', 'st_type', 'zip_left', 'zip_right', 'l_f_add', 'l_t_add', 'r_f_add', 'r_t_add']])

    results_sf = (cll_p.assign(row_id=range(1, len(cll_p) + 1))
                  .merge(lcd, on='row_id', how='left')
                  .merge(rcd, on='row_id', how='left')
                  .merge(lpd, on='row_id', how='left')
                  .merge(rpd, on='row_id', how='left')
                  .merge(cll_names, on='row_id', how='left'))

    results_sf['curb_to_curb'] = results_sf['left_curb_m'] + results_sf['right_curb_m']
    results_sf['row_width'] = results_sf['left_parcel_m'] + results_sf['right_parcel_m']
    results_sf['sidewalk_left'] = results_sf['left_parcel_m'] - results_sf['left_curb_m']
    results_sf['sidewalk_right'] = results_sf['right_parcel_m'] - results_sf['right_curb_m']
    results_sf['diff_bw_sidewalks'] = results_sf['sidewalk_right'] - results_sf['sidewalk_left']
    results_sf['width_diff'] = np.where(results_sf['diff_bw_sidewalks'].abs() < 2, 1, 0)
    results_sf['name'] = district.iloc[0]['dist_name']

    dist_list.append(results_sf)
    print("Script complete for ", district.iloc[0]['dist_name'])

all_df = pd.concat(dist_list)
all_df_pd = pd.DataFrame(all_df.drop(columns='geometry'))

all_df_pd.to_csv('output/sidewalkwidths.csv', index=True)

all_df_pd[["sidewalk_left", "sidewalk_right"]].agg(["min", "max", "median", "mean", "skew"])
all_df_pd.groupby('name')[["sidewalk_left", "sidewalk_right"]].agg(["min", "max", "median", "mean", "skew"])

conditions_l = [
    (all_df_pd['sidewalk_left'] < 2),
    (all_df_pd['sidewalk_left'] < 6),
    (all_df_pd['sidewalk_left'] < 9)
]

conditions_r = [
    (all_df_pd['sidewalk_right'] < 2),
    (all_df_pd['sidewalk_right'] < 6),
    (all_df_pd['sidewalk_right'] < 9)
]

choices = ["none_error", "too_narrow", "high_risk"]

all_df_pd['risk_status_l'] = np.select(conditions_l, choices, default = 'wide_error')
all_df_pd['risk_status_r'] = np.select(conditions_r, choices, default = 'wide_error')
all_df_pd['risk_status'] = np.select([(all_df_pd['risk_status_l'] == "high_risk") | (all_df_pd['risk_status_r'] == "high_risk")], ["true"], default = "false")

high_risk_pct = pd.DataFrame(all_df_pd.groupby('name').agg(
    n = ('risk_status', 'size'),
    count_risk = ('risk_status', lambda x: (x == "true").sum())
).assign(ratio=lambda x: x['count_risk']/x['n']))

risk_rate = pd.DataFrame(all_df_pd.groupby('name').agg(
    n = ('risk_status', 'size'),
    none_l = ('risk_status_l', lambda x: (x == "none_error").sum()),
    narrow_l = ('risk_status_l', lambda x: (x == "too_narrow").sum()),
    risk_l = ('risk_status_l', lambda x: (x == "high_risk").sum()),
    wide_l = ('risk_status_l', lambda x: (x == "wide_error").sum()),
    none_r = ('risk_status_r', lambda x: (x == "none_error").sum()),
    narrow_r = ('risk_status_r', lambda x: (x == "too_narrow").sum()),
    risk_r = ('risk_status_r', lambda x: (x == "high_risk").sum()),
    wide_r = ('risk_status_r', lambda x: (x == "wide_error").sum())
)
)

risk_rate.to_csv('output/sidewalk_tree_risk.csv', index=True)

""" 
#error check
print(plc.geometry.apply(lambda x: len(getattr(x, 'interiors', []))).sum()) 
for i, row in plc.iterrows():
    try:
         left_rays_sf.intersection(row.geometry)
    except Exception as e:
         print(f"Crash at index {i}: {e}")
"""

import folium
import branca.colormap as cm

m = folium.Map(location=[39.9533, -75.1634], zoom_start=11)

# Add Satellite
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Esri Satellite',
    overlay=False,
    control=True
).add_to(m)

folium.GeoJson(left_rays_sf.to_crs(epsg=4326), name='Rays(L)', style_function=lambda x: {"color": "#FF004F"}).add_to(m)
folium.GeoJson(right_rays_sf.to_crs(epsg=4326), name = 'Rays(R)', style_function=lambda x: {"color": "#FF004F"}).add_to(m)
folium.GeoJson(cll.select_dtypes(exclude=['datetime', 'datetime64']).to_crs(epsg=4326), name='Centerlines', style_function=lambda x: {"color": '#00ac46' }).add_to(m)
folium.GeoJson(cll_p.select_dtypes(exclude=['datetime', 'datetime64']).to_crs(epsg=4326), name='Centerline Centerpoints', style_function=lambda x: {"color": '#FFA500' }).add_to(m)
folium.GeoJson(plc.select_dtypes(exclude=['datetime', 'datetime64']).to_crs(epsg=4326), name='Parcels', style_function=lambda x: {"color": '#fd8c00' }).add_to(m)
folium.GeoJson(cbc.select_dtypes(exclude=['datetime', 'datetime64']).to_crs(epsg=4326), name='Curbs', style_function=lambda x: {"color": '#780000'}).add_to(m)

folium.LayerControl().add_to(m)

m



