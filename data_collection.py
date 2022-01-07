import numpy as np
from shapely.geometry import Polygon, MultiPolygon
import pyodbc
import logging
import json
import pandas as pd
import geopandas as gpd
import configparser
import os


DATA_DIR = 'Data'
logger = logging.getLogger(__name__)
config = configparser.ConfigParser()
config.read(os.path.join(DATA_DIR, 'config.ini'))

DATA_CONN_STRING = f"""
                        Driver={config['default']['SQLDriver']};
                        Server={config['drought']['DroughtServer']};
                        Database={config['drought']['DroughtDatabase']};
                        uid={config['drought']['DroughtUser']};
                        pwd={config['drought']['DroughtPWD']};
                    """

SHAPES_CONN_STRING = f"""
                            Driver={config['default']['SQLDriver']};
                            Server={config['shapes']['ShapesServer']};
                            Database={config['shapes']['ShapesDatabase']};
                            uid={config['shapes']['ShapesUser']};
                            pwd={config['shapes']['ShapesPWD']};
                        """

CENTERS_QUERY = '''select
                    c.province_name,
                    c.county_name,
                    c.longitude as county_lon,
                    c.latitude as county_lat,
                    p.longitude as province_lon,
                    p.latitude as province_lat
                from
                    dbo.County c left join dbo.Province p on c.province_id = p.id
                '''
SHAPE_FILES = {'province': 'Province', 'county': 'County'}


def make_polygon(coords: str, geometry: str):
    """ Convert the string formatted polygons in data base back to Polygon"""
    if geometry == "Polygon":
        polygon_coord = []
        for i in coords.split(','):
            polygon_coord.append(tuple(np.array(i.split(), dtype=np.float64)))
        coord_poly = Polygon(polygon_coord)

    if geometry == "MultiPolygon":
        polygons = coords.split('|')
        multipolygon = []
        for polygon in polygons:
            polygon_coord = []
            for i in polygon.split(','):
                polygon_coord.append(tuple(np.array(i.split(), dtype=np.float64)))
            multipolygon.append(Polygon(polygon_coord))
        coord_poly = MultiPolygon(multipolygon)
    return coord_poly


def load_data(year: int):
    """ Read the drought index values from database for the input year"""
    conn = pyodbc.connect(DATA_CONN_STRING)
    df = pd.read_sql_query(f'SELECT x, y, year, value FROM dbo.spei WHERE year={year}', conn)
    return df


def load_years():
    """ Load a list of all the years that have drought data in spei table; Returns a list"""
    conn = pyodbc.connect(DATA_CONN_STRING)
    df = pd.read_sql_query('SELECT DISTINCT year FROM dbo.spei', conn)
    return df['year'].unique().tolist()


def load_counties():
    """ Create a dict with province_name as key and a list of all of it's counties"""
    conn = pyodbc.connect(SHAPES_CONN_STRING)
    df = pd.read_sql_query('SELECT province_name, county_name FROM dbo.County', conn)
    return df.groupby('province_name')['county_name'].apply(list).to_dict()


def load_shapes(SHAPE_FILES: dict = SHAPE_FILES):
    """ Load shapes, shape centers and province list from database.
    Output: 
    shape_files (dict): Each shape type and corresponding json formatted geometry of shapes
    centroids (dict): The X and Y coordinates for the center of each shape
    """
    conn = pyodbc.connect(SHAPES_CONN_STRING)
    shape_files = {}
    centroids = {}

    for type_name in SHAPE_FILES:
        logger.debug(f'Sending query for dbo.{SHAPE_FILES.get(type_name)}')
        df = pd.read_sql_query(f'''SELECT id, {type_name}_name, longitude, latitude, province_name as province, polygon_type, coordinates
                                FROM dbo.{SHAPE_FILES.get(type_name)}''', conn)
        logger.debug(f'Shape set is read: {type_name}')
        df['geometry'] = df.apply(lambda x: make_polygon(x.coordinates, x.polygon_type), axis=1)
        gdf = gpd.GeoDataFrame(df)

        """ Change geometries to json formatted required by scatter_mapbox"""
        shape_files[type_name] = json.loads(gdf.geometry.to_json())

    """ Create a list of all Provinces and Counties and their centers for the drop down menu and map center """
    df_county_list = pd.read_sql_query(CENTERS_QUERY, conn)
    for type_name in SHAPE_FILES:
        centroids[type_name] = df_county_list[[f'{type_name}_name', f'{type_name}_lon', f'{type_name}_lat']].rename(columns={f'{type_name}_lon': 'center_x', f'{type_name}_lat': 'center_y'}).drop_duplicates(keep='first')
    conn.close()
    return shape_files, centroids


def load_province_category(province):
    """ Return the percentage of categories for selected province """
    conn = pyodbc.connect(DATA_CONN_STRING)
    if province == 'country':
        # TODO: Change the query to country percentage when ready and remove the calculations
        df = pd.read_sql_query(f"SELECT * FROM dbo.drought_area_per_province", conn)
        total_area = df.groupby(['year'])['area'].sum().reset_index().iloc[0,1]
        df = df.groupby(['year', 'category'])['area'].sum().reset_index()
        df['total'] = total_area
        df['percentage'] = (df['area']/df['total'])*100
        df.drop(columns=['area', 'total'], inplace=True)
    else:
        df = pd.read_sql_query(f"SELECT * FROM dbo.drought_percentage_per_province WHERE province LIKE N'{province}'", conn)
    df = df[df['year'] >= df['year'].max() - 20]
    return df


def load_region_year(year, province):
    """ Return all the category percentages of the region for the selected year"""
    conn = pyodbc.connect(DATA_CONN_STRING)
    if province == 'country':
        df = pd.read_sql_query(f"SELECT * FROM dbo.drought_percentage_per_province WHERE year = {year} ORDER BY province DESC", conn)
    else:
        df = pd.read_sql_query(f"""SELECT 
                                county, percentage, category, year 
                                FROM dbo.drought_percentage_per_county 
                                WHERE year = {year} and province like N'{province}' ORDER BY county DESC""",
                                conn)
        df.rename(columns={'county': 'province'}, inplace=True)
    return df


def load_region_year_pie(year, region, level):
    """ Return category area values for a selected region (Country, Province, County) and year"""
    query_strings = {
                    0: f"SELECT * FROM dbo.drought_area_per_province WHERE YEAR={year} AND province LIKE N'تهران'", # TODO: After getting the data change to Country query
                    1: f"SELECT * FROM dbo.drought_area_per_province WHERE YEAR={year} AND province LIKE N'{region}'",
                    2: f"SELECT * FROM dbo.drought_area_per_county WHERE YEAR={year} AND county LIKE N'{region}'"
                    }
    conn = pyodbc.connect(DATA_CONN_STRING)
    df = pd.read_sql_query(query_strings[level], conn)
    return df
