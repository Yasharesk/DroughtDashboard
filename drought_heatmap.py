# -*- coding: utf-8 -*-
"""
Created on Tue Jul 27 13:27:37 2021

@author: Yashar
"""

import dash
from dash import dcc
from dash import html
from dash.dependencies import Input, Output
import plotly.express as px
import flask
import json
import logging
import data_collection as dc


logging.basicConfig(level=logging.DEBUG, filename='main.log', format='%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)
# gunicorn drought_heatmap:server -b :8050 --timeout 60

ZOOM_LEVELS = {'country': 5, 'province': 6.2}

# Stacked bar chart order and corresponding colors
CATEGORY_ORDER = {'category': ['Extremly dry', 'Sever dry', 'Moderate dry', 'Slight dry', 
                   'Normal', 'Slight wet', 'Moderate wet', 'Sever wet', 'Extremly wet']}

CATEGORY_COLOR = ['#610000', '#d60000', '#d65900', '#fae902', 
                  '#1bd402',
                  '#02d4cd', '#0295d4', '#022cd4', '#0f0380', '#0e0054']

COLOR_MAP = {x[0]: x[1] for x in zip(CATEGORY_ORDER['category'], CATEGORY_COLOR)}

shapes, centroids = dc.load_shapes()

""" A list of provinces for dropdown"""
province_list = [{'label': x ,'value': x} for x in centroids['province']['province_name']]
province_list.append({'label': 'همه', 'value':'country'})

"""A dict of centers for setting the center value in map by province name"""
province_centers = {x.loc['province_name']: json.dumps({'lat': x.loc['center_y'], 'lon': x.loc['center_x']}) for _, x in centroids['province'].iterrows()}
province_centers['country'] = json.dumps({'lat': 32.7089, 'lon': 53.6880})

""" A dict of counties, with each province as a key and corresponding counties as values """
all_counties = dc.load_counties()
all_counties['country'] = []

def create_slider_marks(years: list) -> dict:
    """
     Generate Marking points on the slider (each 5 years),
     based on the available years in the data
    """
    marks = [x for x in years if x % 5 == 0]
    marks_dict = dict()
    for item in marks:
        marks_dict[item] = {'label': str(item)}
    return marks_dict


""" Read Mapbox token from file """
mb_token = dc.config['mapbox']['token']

""" Load the data """
years = dc.load_years()

""" Initiate Dash App """
server = flask.Flask(__name__)
external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets, server=server)


@app.callback(
    Output('drought_graph', 'figure'),
    [Input('selected_province', 'value'),
     Input('select_year', 'value'),
     Input('selected_shape', 'value'),
     ]
    )
def update_fig(center,
               select_year=max(years),
               selected_shape='country'
               ):
    """ Create the figure """
    df_year = dc.load_data(select_year)
    if center == 'country':
        zoom_type = ZOOM_LEVELS['country']
    else:
        zoom_type = ZOOM_LEVELS['province']

    fig = px.scatter_mapbox(df_year,
                            lat='y', lon='x',
                            color='value',
                            range_color=(-3, 3),
                            hover_data={'x': False, 'y': False, 'value': ':.2f'},
                            labels={'value': 'شاخص خشکسالی'},
                            zoom=zoom_type,
                            height=800, width=1050,
                            center=json.loads(province_centers[center]),
                            color_continuous_scale=px.colors.diverging.RdYlGn,
                            color_continuous_midpoint=0,
                            )
    fig.update_layout(mapbox_style="outdoors", mapbox_accesstoken=mb_token)
    fig.update_layout(legend_font_family="Tahoma")
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    fig.update_layout(hoverlabel=dict(font_family='Tahoma'))
    if selected_shape == 'province':
        fig.update_layout(mapbox={
                                'layers': [
                                            {
                                            'source': shapes[selected_shape],
                                            'below': '',
                                            'type': 'line',
                                            'color': 'black',
                                            'line': {'width': 2}
                                            }
                                        ]
                                }
                        )
        fig2 = px.scatter_mapbox(centroids[selected_shape],
                    lat='center_y',
                    lon='center_x',
                    hover_data={
                        'center_x': False,
                        'center_y': False,
                        },
                    hover_name=f'{selected_shape}_name'
                    )
        fig2.update_traces(marker={'size': 10})
        fig.add_trace(fig2.data[0])

    elif selected_shape == 'county':
        fig.update_layout(mapbox={
                        'layers': [
                                    {
                                    'source': shapes[selected_shape],
                                    'below': '',
                                    'type': 'line',
                                    'color': 'purple',
                                    'line': {'width': 1}
                                    },
                                    {
                                    'source': shapes['province'],
                                    'below': '',
                                    'type': 'line',
                                    'color': 'black',
                                    'line': {'width': 2}
                                    },
                                ]
                        }
                )
        fig2 = px.scatter_mapbox(centroids[selected_shape],
                                 lat='center_y',
                                 lon='center_x',
                                 hover_data={
                                     'center_x': False,
                                     'center_y': False,
                                     },
                                 hover_name=f'{selected_shape}_name'
                                 )
        fig2.update_traces(marker={'size': 8})
        fig.add_trace(fig2.data[0])
    return fig


@app.callback(
    Output('selected_year', 'children'),
    Input('select_year', 'value')
    )
def updated_selected_year(value):
    """ Update the Year number showing on the subtitle according to slider """
    return f'سال {value}'


@app.callback(
    Output('selected_county', 'options'),
    Input('selected_province', 'value')
)
def update_county_list(province):
    """ Create the list of conunties to be shown on dropdown based on selected province"""
    return [{'label': name, 'value': name} for name in all_counties[province]]


@app.callback(
    Output('selected_county', 'disabled'),
    Input('selected_province', 'value')
)
def enable_county_dropdown(province):
    """Enable the county drop down if a single province is selected"""
    return province == 'country'


@app.callback(
    Output('category_stacked', 'figure'),
    Input('selected_province', 'value')
)
def update_category_bar(province):
    df = dc.load_province_category(province)
    fig = px.bar(df, x='year', y='percentage', color='category',
                category_orders=CATEGORY_ORDER,
                color_discrete_sequence=CATEGORY_COLOR,
                labels={'percentage': 'درصد از کل', 'year': 'سال', 'category':'وضعیت'},
                height=600, width=1050)
    fig.update_layout(legend_font_family = 'Tahoma')
    fig.update_layout(font_family='Tahoma')
    fig.update_layout(hoverlabel=dict(font_family='Tahoma'))
    fig.update_layout(title=dict(text='ایران' if province=='country' else province, x=0.5, y=0.95, xanchor='center', yanchor='top'))
    fig.update_layout(font = dict(color = "#909497"))
    fig.update_traces(hovertemplate="<br>وضعیت: %{color} <br> درصد: %{percent}")
    fig.update_traces(hovertemplate='%{y:.2f}<br>')
    return fig


@app.callback(
    Output('region_stacked', 'figure'),
    [Input('select_year', 'value'),
    Input('selected_province', 'value')]
)
def update_region_bar(year, province):
    df = dc.load_region_year(year, province)
    fig = px.bar(df, x='percentage', y='province', color='category', orientation='h',
                height=800, width=1050,
                category_orders=CATEGORY_ORDER, 
                color_discrete_sequence=CATEGORY_COLOR,
                labels={'year': False, 'category':'وضعیت'})
    fig.update_layout(legend_font_family = 'Tahoma')
    fig.update_layout(font_family='Tahoma')
    fig.update_layout(hoverlabel=dict(font_family='Tahoma'))
    fig.update_layout(title=dict(text=str(year), x=0.5, y=0.95, xanchor='center', yanchor='top'))
    fig.update_layout(font = dict(color = "#909497"))
    fig.update_layout(xaxis_title=None, yaxis_title=None)
    fig.update_traces(hovertemplate="<br>وضعیت: %{color} <br> درصد: %{percent}")
    fig.update_traces(hovertemplate='%{x:.2f}<br>')
    return fig


@app.callback(
    Output('pie_chart', 'figure'),
    [
        Input('select_year', 'value'),
        Input('selected_province', 'value'),
        Input('selected_county', 'value')
    ]
)
def update_pie_chart(year, province, county):
    if province == 'country':
        level = 0
        region = 'ایران'
    elif county == 'country':
        level = 1
        region = province
    else:
        level = 2
        region = county
        
    df = dc.load_region_year_pie(year, region, level)
    fig = px.pie(df, values='area', names='category', color='category',
             color_discrete_map=COLOR_MAP, hole=0, 
             hover_data=['area'],
             custom_data=['area'],
             height=400,
             width=1050
            )
    fig.update_traces(textinfo='percent+label', hovertemplate = "<br>هکتار %{value:,.2f}")
    fig.update_layout(title=dict(text=region + ' - ' + str(year), 
                                x=0.45, 
                                y=0.95, 
                                xanchor='center', 
                                yanchor='top'))
    fig.update_layout(legend_font_family='Tahoma')
    fig.update_layout(font_family='Tahoma')
    fig.update_layout(hoverlabel=dict(font_family='Tahoma'))
    fig.update_layout(font=dict(color = "#909497"))
    return fig


app.layout = html.Div(children=[
    html.H2(children='نقشه وضعیت خشکسالی', style={'margin-left': '300px'}),
    
    html.Div(children=[
        html.Div(id='selected_year', style={'margin-left': '450px'}),
        html.Div(dcc.Slider(id='select_year',
                            min=min(years),
                            max=max(years),
                            step=1,
                            marks=create_slider_marks(years),
                            value=max(years),
                            ),
                 style={'width': '1000px'}),
                ]),
    html.Div(dcc.RadioItems(id='selected_shape',
                          options=[
                              {'label': 'شهرستان', 'value': 'county'},
                              {'label': 'استان', 'value': 'province'},
                              {'label': 'کشور', 'value': 'country'}
                              ],
                          value='country',
                          className='radiobutton-group',
                          labelStyle={'display': 'inline-block'}
                          ),
             style={'width': '200px', 'margin-left': '400px', 'align-text': 'center', 'margin-top': '10px'}
             ),

    html.Div(dcc.Dropdown(id='selected_province',
                          options=province_list,
                          value='country',
                          clearable=False
                          ),
             style={'width': '200px', 'margin-left': '400px', 'margin-top': '10px', 'direction': 'rtl'}
             ),

    html.Div(dcc.Dropdown(id='selected_county',
                            options=province_list,
                            value='country',
                            clearable=False
                            ),
            style={'width': '200px', 'margin-left': '400px', 'margin-top': '10px'}
                            ),

    html.Div(dcc.Graph(id='drought_graph'),
             style={'text-align': 'center', 'margin-left': '25px', 'margin-top': '20px'}
             ),
    
    html.Div(dcc.Graph(id='category_stacked'),
            style={'text-align': 'center', 'margin-left': '25px', 'margin-top': '20px'}
            ),
            
    html.Div(dcc.Graph(id='region_stacked'),
        style={'text-align': 'center', 'margin-left': '25px', 'margin-top': '20px'}
            ),

    html.Div(dcc.Graph(id='pie_chart'),
        style={'text-align': 'center', 'margin-left': '25px', 'margin-top': '20px'}
            )
                         ],
    style={'font-family': 'tahoma'}
    )


if __name__ == '__main__':
    app.run_server(debug=True)
    # app.run_server()
