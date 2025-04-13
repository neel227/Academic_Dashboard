# Import relevant libraries
from dash import Dash, html, dcc, Output, Input, State, callback_context
from dash_extensions.javascript import assign
from plotly.basedatatypes import BaseFigure
import pandas as pd
import plotly.express as px
import dash_bootstrap_components as dbc
import mysql_utils
import mongodb_utils
import neo4j_utils
import time

#Relevant Username/Password info. Users should fill this in themselves
sqlhost = 'localhost'
sqluser = 'root'
sqlpassword = 'Sameer 627'
sqldb = 'academicworld'
mongoconnect = "mongodb://localhost:27017"
mongodatabase = "academicworld"
neo4jurl = "bolt://localhost:7687"
neo4juser = "neo4j"
neo4jpassword = "Aleen@isacat411"
neo4jdb = "academicworld"

#Setting up connections to the backend databases
mysql_connect = mysql_utils.create_connection(sqlhost, sqluser, sqlpassword, sqldb)
mongo_db = mongodb_utils.connect_to_mongodb(mongoconnect, mongodatabase)
neo4j_conn = neo4j_utils.Neo4jConnection(neo4jurl, neo4juser, neo4jpassword, neo4jdb)

faculty_collection = mongo_db["faculty"]
publications_collection = mongo_db['publications']

#Data Pre-processing
def reset_hiding():
    for table in ['faculty', 'faculty_keyword', 'faculty_publication', 'keyword', 'publication', 'publication_keyword', 'university']:
        if mysql_utils.column_exists(mysql_connect, table, 'is_hidden'):
            drop_query = f'ALTER TABLE {table} DROP COLUMN is_hidden'
            mysql_utils.execute_write_query(mysql_connect, drop_query)  
        query = f'ALTER TABLE {table} ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE'
        mysql_utils.execute_write_query(mysql_connect, query)
reset_hiding()

#Creating indexes to make our view easier to query
indexes = [
    "CREATE INDEX idx_faculty_keyword_keyword_id ON faculty_keyword(keyword_id)",
    "CREATE INDEX idx_faculty_keyword_faculty_id ON faculty_keyword(faculty_id)",
    "CREATE INDEX idx_faculty_university_id ON faculty(university_id)"]

for index_query in indexes:
    mysql_utils.execute_write_query(mysql_connect, index_query)


#Creating a view for use by our dashboard
def create_u_view(name):
    mysql_utils.drop_view_if_exists(mysql_connect, name)
    mysql_utils.create_view(mysql_connect, name,"""SELECT K.name as Keyword, FK.score as Score, F.name as Professor, U.name as University, U.is_hidden as Hide
                                                            FROM keyword as K, faculty_keyword as FK, FACULTY AS F, university as U 
                                                            WHERE K.id = FK.keyword_id AND F.id = FK.faculty_id AND F.university_id = U.id AND U.is_hidden = 0 AND F.is_hidden = 0 AND FK.is_hidden = 0
                                                            ORDER BY Score desc""")
    return name
univ_keyword_view = create_u_view("University_Keywords")




#Creating stored procedures for our dashboard
create_procedure_query_1 = """
    CREATE PROCEDURE GetProfessorID(IN professor_name VARCHAR(255), OUT professor_id INT)
    BEGIN
        SELECT id INTO professor_id FROM faculty WHERE name = professor_name;
    END;
    """
mysql_utils.execute_write_query(mysql_connect, "DROP PROCEDURE IF EXISTS GetProfessorID;")
mysql_utils.execute_write_query(mysql_connect, create_procedure_query_1)

#Creating a trigger for our dashboard
trigger_query_fac = """
    CREATE TRIGGER after_faculty_delete
        AFTER DELETE ON faculty
        FOR EACH ROW
        BEGIN
            DELETE FROM faculty_keyword WHERE faculty_id = OLD.id;
            DELETE FROM faculty_publication WHERE faculty_id = OLD.id;
        END;
    """
mysql_utils.execute_write_query(mysql_connect, trigger_query_fac)

#Hiding values
create_procedure_query_2 = """
    CREATE PROCEDURE HideUniversityData(IN university_name VARCHAR(255))
    BEGIN
        DECLARE uni_id INT;

        SELECT id INTO uni_id FROM university WHERE name = university_name;
        UPDATE university SET is_hidden = TRUE WHERE id = uni_id;

        UPDATE faculty SET is_hidden = TRUE WHERE university_id = uni_id;
        UPDATE faculty_keyword SET is_hidden = TRUE WHERE faculty_id IN (SELECT id FROM faculty WHERE university_id = uni_id);

        UPDATE faculty_publication SET is_hidden = TRUE WHERE faculty_id IN (SELECT id FROM faculty WHERE university_id = uni_id);
        UPDATE publication SET is_hidden = TRUE WHERE id IN (SELECT publication_id FROM faculty_publication WHERE faculty_id IN (SELECT id FROM faculty WHERE university_id = uni_id));

        UPDATE publication_keyword SET is_hidden = TRUE WHERE publication_id IN (SELECT publication_id FROM faculty_publication WHERE faculty_id IN (SELECT id FROM faculty WHERE university_id = uni_id));

    END;
    """
mysql_utils.execute_write_query(mysql_connect, "DROP PROCEDURE IF EXISTS HideUniversityData;")
mysql_utils.execute_write_query(mysql_connect, create_procedure_query_2)


def hide_university_data_mongo(db1, db2, university_name):
    # Update faculty collection
    faculty_filter = {"affiliation.name": university_name}
    updated_faculty = mongodb_utils.update_hidden_status(db1, "faculty", faculty_filter, True)

    # Get the faculty IDs
    faculty_ids = db1["faculty"].find(faculty_filter, {"_id": 1})
    faculty_ids = [faculty["_id"] for faculty in faculty_ids]

    if not faculty_ids:
        return

    # Update publications collection
    publication_filter = {"authors.faculty_id": {"$in": faculty_ids}}
    updated_publications = mongodb_utils.update_hidden_status(db2, "publications", publication_filter, True)



def hide_university_data_neo4j(conn, university_names):
    queries = [
            """
            MATCH (u:University {name: $university_name})
            SET u.is_hidden = True
            """,
            """
            MATCH (f:Faculty)-[:AFFILIATED_WITH]->(u:University {name: $university_name})
            SET f.is_hidden = True
            """,
            """
            MATCH (f:Faculty)-[:PUBLISHES]->(p:Publication)
            WHERE f.is_hidden = True
            SET p.is_hidden = True
            """,
            """
            MATCH (f:Faculty)-[:RESEARCHES]->(k:Keyword)
            WHERE f.is_hidden = True
            SET k.is_hidden = True
            """,
            """
            MATCH (p:Publication)-[:HAS_KEYWORD]->(k:Keyword)
            WHERE p.is_hidden = True
            SET k.is_hidden = True
            """
        ]
    for university_name in university_names:
        for query in queries:
            conn.query(query, parameters={"university_name": university_name})



# Setting up app and database connections
app: Dash = Dash(__name__, suppress_callback_exceptions=True,
                 external_stylesheets=[dbc.themes.QUARTZ])

keyword_list = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, "SELECT name FROM keyword"))[0].tolist()
university_list = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, "SELECT name FROM university"))[0].tolist()


# Setting up basic app components
app.title = "Investigating University and Faculty Information for Popular Research Topics"
background_color: str = "rgb(128,128,128,.8)"
widget_list: list = [title.upper() for title in ["Top Professors per Keyword", "Faculty Page",
                                                 "Leading Universities by Keyword", "Top 10 Keywords for a University", 
                                                 "Similar Keywords", "University Blacklist", 'Temp']]
widget_title_color = ["white", "white", "white","white", "white", "black", 'white']

#Auxiliary data structures
table1 = pd.DataFrame()

# Building the aesthetic of the widgets
widgets = [
    [
        html.Button(
            html.H4(widget_list[0], style={"textAlign": "center", "color": widget_title_color[0],
                                           "fontFamily": "Arial", "fontWeight": "bold", "margin": "0"}),
            widget_list[0], 
            0, 
            style={"margin": "auto", "display": "block", "border": "none", "backgroundColor": "transparent", 
                   "marginTop": "1%", "marginBottom": "0"}
        ),
        dcc.Slider(0, 1, 1, value=1, id="num_professors_slider"),  
        html.Div(id="table1_div", style={"margin": "2%", "textAlign": "center"})
    ],
    [
        html.Button(
            html.H4(widget_list[1], style={"textAlign": "center", "fontFamily": "Arial", "fontWeight": "bold", 
                                           "margin": "0", "color": widget_title_color[5]}), 
            widget_list[1], 
            0, 
            style={"margin": "auto", "display": "block", "border": "none", "backgroundColor": "transparent"}
        ),
        html.Table(
            html.Tbody([
                html.Tr([
                    html.Td(
                        dcc.Dropdown(clearable=False, id="faculty_name_dropdown"), 
                        style={"width": "100%", "paddingLeft": "10px", "color": "black"}
                    ),
                    html.Td(
                        html.Button(
                            html.Img(src="https://static.thenounproject.com/png/101790-200.png", height=35, width=35),
                            id="delete_faculty_button", 
                            style={"background": background_color, "borderRadius": "5px", "padding": "1%"}
                        ), 
                    ),
                ], style={"width": "400px"})
            ]), 
            style={"marginTop": "2%", "marginBottom": "2%", "textAlign": "center"}
        ),
        html.Table(
            html.Tbody([
                html.Tr([
                    html.Td(html.Div(id="faculty_picture_div", style={"display": "flex", "flexDirection": "row"})),
                    html.Td( html.Div(id="faculty_info_div", style={"display": "flex", "flexDirection": "row"})),
                ])
            ]), 
            style={"marginTop": "2%", "marginBottom": "2%", "textAlign": "left"}
        ),
    ],
    [
        html.Button(
            html.H4(widget_list[2], style={"textAlign": "center", "color": widget_title_color[2], 
                                           "fontFamily": "Arial", "fontWeight": "bold", "margin": "0"}), 
            widget_list[2], 
            style={"margin": "auto", "display": "block", "border": "none", "backgroundColor": "transparent", "marginBottom": "1%"}
        ), 
        html.Div(id="graph3_div")
    ],
    [
        html.Button(
            html.H4(widget_list[3], style={"textAlign": "center", "color": widget_title_color[3], 
                                           "fontFamily": "Arial", "fontWeight": "bold", "margin": "0"}), 
            widget_list[3], 
            0, 
            style={"margin": "auto", "display": "block", "border": "none", "backgroundColor": "transparent"}
        ), 
        html.Div([
                dcc.Dropdown(id="university_name_dropdown", style={"width": "90%", "textAlign": "center", "color": "black", "marginTop": "2%"}), 
                html.Div( html.Div(id="univ_picture_div"))], 
            style={'display': 'flex', 'justify-content': 'space-between'}
        ),
        html.Div(id="graph4_div", style = {"marginTop": "1%"})
    ],
    [
        html.Button(
            html.H4(widget_list[4], style={"textAlign": "center", "color": widget_title_color[4], 
                                           "fontFamily": "Arial", "fontWeight": "bold", "margin": "0"}), 
            widget_list[4], 0,  style={"margin": "auto", "display": "block", "border": "none", "backgroundColor": "transparent"}), 
        html.Div(
                [dcc.Dropdown(
                        keyword_list,  "", False, True, id="similar_keywords_dropdown", 
                        style={"textAlign": "center", "color": "black", "margin": "auto", "width": "100%"}
                    ),
                dcc.Dropdown(
                        ["Number of Shared Citations", "Similarity Scores"], "", False, False, id="similar_keywords_dropdown_2", 
                        style={"textAlign": "center", "color": "black", "margin": "auto", "width":"70%"}
                    )], style={'display': 'flex','flexDirection': 'row','justifyContent': 'space-between','width': '95%','margin': 'auto'}),
        html.Div(id="table5_div", style={"margin": "2%", "textAlign": "center"})
    ],
    [
        html.Button(
            html.H4(widget_list[5], style={"textAlign": "center", "color": widget_title_color[5], 
                                           "fontFamily": "Arial", "fontWeight": "bold", "margin": "0"}), 
            widget_list[5], 
            0, 
            style={"margin": "auto", "display": "block", "border": "none", "backgroundColor": "transparent", "marginTop": "1%"}
        ),
        html.Div(
            [
                dcc.Dropdown(university_list, "", False, True, id="university_blacklist_dropdown", 
                    style={"textAlign": "center", "color": "black", "margin": "auto", "paddingLeft": "5%"})
            ],style={"margin": "auto", "flex": 4}), 
        html.Div(id="image6_div", style={"padding": "1%"})
    ]
]

app.layout = html.Div([
    html.Div(
        [
            html.Div(
                [
                    dcc.Dropdown(keyword_list, "", True, False, id="keyword_name_dropdown", 
                        style={"textAlign": "center", "color": "black", "margin": "auto", "paddingLeft": "5%"}),
                    html.Div(id="keyword_trigger", children = [''])
                ],
                style={"margin": "auto", "flex": 4}
            ),
            html.Div(
                [dcc.Store(id='trigger_store', data={'trigger': False}),
                html.Button(
                    html.Img(
                        src="https://static.thenounproject.com/png/3648091-200.png", id="clear_button", height=40, width=40,
                        style={"display": "block", "margin": "auto", "background": "white", "border": "2px solid grey", "borderRadius": "20px"}
                    ),
                    "",
                    n_clicks = 0,
                    style={"border": "none", "backgroundColor": "transparent", "marginRight": "30%"}
                )],
                style={"flex": 1, "paddingRight": "1%"}
            ),
            html.Div(
                html.Button(
                    html.Img(
                        src="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQQOlu1sma0lhKMZibsFzkAFWtAlTs_MQSnhw&s",
                        id="affiliation_photo_img",
                        height=95,
                        width=150,
                        style={"display": "block", "margin": "auto", "background": "white", "border": "2px solid grey", "borderRadius": "20px"}
                    ),
                    "",
                    style={"border": "none", "backgroundColor": "transparent", "marginLeft": "30%"}
                ),
                style={"flex": 1, "paddingLeft": "1%"}
            )
        ],
        style={"display": "flex", "flexDirection": "row", "margin": "auto", "paddingTop": "5px", "paddingBottom": "5px"}
    ),


    # Add the table to input each widget and do formatting  
    html.Table(
        html.Tbody([
            html.Tr([
                html.Td(
                    html.Div(widgets[0], style={"border": "3px solid rgb(0, 58, 111)", "margin": "auto", 
                                                "background": background_color, "height": "500px"}), 
                    style={"padding": "5px"}
                ),
                html.Td(
                    html.Div(widgets[1], style={"border": "3px solid rgb(0, 58, 111)", "margin": "auto", 
                                                "background": background_color, "height": "500px"}), 
                    style={"padding": "5px"}
                )
            ]),
            html.Tr([
                html.Td(
                    html.Div(widgets[2], style={"border": "3px solid rgb(0, 58, 111)", "margin": "auto", 
                                                "background": background_color, "height": "500px"}), 
                    style={"padding": "5px"}
                ),
                html.Td(
                    html.Div(widgets[3], style={"border": "3px solid rgb(0, 58, 111)", "margin": "auto", 
                                                "background": background_color, "height": "500px"}), 
                    style={"padding": "5px"}
                )
            ]),
            html.Tr([
                html.Td(
                    html.Div(widgets[4], style={"border": "3px solid rgb(0, 58, 111)", "margin": "auto", 
                                                "background": background_color, "height": "500px"}), 
                    style={"padding": "5px"}
                ),
                html.Td(
                    html.Div(widgets[5], style={"border": "3px solid rgb(0, 58, 111)", "margin": "auto", 
                                                "background": background_color, "height": "500px"}), 
                    style={"padding": "5px"}
                )
            ])
        ]), 
        style={"tableLayout": "fixed", "width": "100%", "height": "100%"}
    ),
    html.H6(
        id="faculty_info_widget_trigger", 
        style={"visibility": "hidden"}
    ),
    html.Div(children = 3, id='dummy_div', style={'display': 'none'})
], 
style={"margin": 0, "padding": 0, "width": "100%", "height": "100%", "top": "0px", "left": "0px", "zIndex": "1000"})

# CALLBACKS


@app.callback(
     [Output("num_professors_slider", "value"),
     Output("num_professors_slider", "max"),
     Output("num_professors_slider", "min"),
     Output("graph3_div", "children"),
     Output("faculty_name_dropdown", "options"),
     Output("faculty_name_dropdown", "value"),
     Output("university_name_dropdown", "options"),
     Output("university_name_dropdown", "value"),
     Output("faculty_info_widget_trigger", "children")],
     [Input("keyword_name_dropdown", "value"),
      Input('keyword_trigger', 'children')]
     )
def update_view(keywords, extra):
    global table1
    if keywords is None or keywords == "" or len(keywords) == 0:
        return (0,1,0, [], [], "", [], "","")
    
    keywords = [keywords] if isinstance(keywords, str) else keywords

    df = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect,f"SELECT Keyword, Professor, University FROM {univ_keyword_view}"))
    df.columns =['Keyword', 'Professor', 'University']
    df = df[df["Keyword"].isin(keywords)]

    table1 = df.head(100)
    
    faculty_keywords = sorted(list(set(df['Professor'])))
    university_keywords = sorted(list(set(df['University'])))
    df2 = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, f"""SELECT Keyword, University, count(*) as count 
                                                      FROM  {univ_keyword_view} GROUP BY University, Keyword ORDER BY count desc"""))
    df2.columns = ['Keyword', 'University', 'Number of Publication(s)']
    df2 = df2[df2["Keyword"].isin(keywords)]



    fig3: BaseFigure = px.bar(
        df2.head(10),
        x="University",
        y="Number of Publication(s)",
        height=370,
        template="plotly_dark",
        color="Keyword",
        barmode="group"
    )
    fig3.update_layout(
        plot_bgcolor="#23252F",
        font={"family": "courier"},
        legend=dict(yanchor="top", y=-0.7, xanchor="left", x=0.01)
   )

    fig3.update_layout(
        plot_bgcolor="#23252F",
        font={"family": "Arial"},
        title={
            'text': f"Leading Universities by Keyword",
            'x':0.5,
            'xanchor': 'center',
            'font': {'size': 16, 'color': 'white', 'family': 'Arial', 'weight': 'bold'}
        },
        xaxis_title={
            'text': 'University',
            'font': {'size': 12, 'color': 'white', 'family': 'Arial', 'weight': 'bold'}
        },
        yaxis_title={
            'text': 'Number of Publication(s)',
            'font': {'size': 12, 'color': 'white', 'family': 'Arial', 'weight': 'bold'}
        })
    return (5,8,3,dcc.Graph(figure=fig3) if len(df2) > 0 else [],faculty_keywords, "" if len(faculty_keywords) == 0 else faculty_keywords[0],university_keywords,
        "" if len(university_keywords) == 0 else university_keywords[0],"")


@app.callback(
    [Output('graph4_div', 'children'),
     Output("univ_picture_div", 'children')],
    Input('university_name_dropdown', 'value'))
def generate_university_graph(university):
    if university is None or university == "" or len(university) == 0:
        return [[], []]
    df = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, """SELECT U.name, K.name, count(*) as count 
                                                     FROM keyword as K, faculty_keyword as FK, FACULTY AS F, university as U 
                                                     WHERE K.id = FK.keyword_id AND F.id = FK.faculty_id AND F.university_id = U.id
                                                     GROUP BY U.name, K.name order by count desc"""))
    df.columns = ['University', 'Keyword', 'Number of Publication(s)']
    df = df[df["University"].isin([university])]

    if df.empty:
        return [[], []]    
    try:
        univ_photo_url = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, f"SELECT photo_url FROM university WHERE name = \"{university}\" ")).iat[0,0]
        univ_photo_url = html.Img(src=univ_photo_url, alt="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/No_image_available.svg/1200px-No_image_available.svg.png", 
                                  height=70, width=70, style={"display": "block", "margin": "auto", "backgroundColor": "white"}),
    except:
        univ_photo_url = []
    
    fig4: BaseFigure = px.bar(
        df.head(10),
        x="Keyword",
        y="Number of Publication(s)",
        height=370,
        template="plotly_dark",
    )

    fig4.update_layout(
        plot_bgcolor="#23252F",
        font={"family": "Arial"},
        title={
            'text': f"Number of Publications for {university} by Keyword",
            'x':0.5,
            'xanchor': 'center',
            'font': {'size': 16, 'color': 'white', 'family': 'Arial', 'weight': 'bold'}
        },
        xaxis_title={
            'text': 'Keyword',
            'font': {'size': 12, 'color': 'white', 'family': 'Arial', 'weight': 'bold'}
        },
        yaxis_title={
            'text': 'Number of Publication(s)',
            'font': {'size': 12, 'color': 'white', 'family': 'Arial', 'weight': 'bold'}
        })
    fig4.update_traces(marker_color='blue')

    return [dcc.Graph(figure=fig4), univ_photo_url]

@app.callback(
    Output('table1_div', 'children'),
    [Input('num_professors_slider', 'value')],
    [State("university_blacklist_dropdown", "value")])
def update_professors(value, blacklist):
    if value == 0: return [[]]
    global table1
    table1 = table1[~table1["University"].isin([blacklist])]
    
    table1_html = table1.head(value).to_html(classes='table table-striped', index = False)
    return(dcc.Markdown(table1_html, dangerously_allow_html=True))


@app.callback(
    [Output("faculty_picture_div", "children"),
    Output("faculty_info_div", "children")],
    Input("faculty_name_dropdown", "value"), 
    State("keyword_name_dropdown", "value"))
def generate_faculty_page(curr_prof, keywords):

    if keywords is None or keywords == "" or len(keywords) == 0:
        return ([" "], [" "])
        
    #Add wait time to prevent SQL threading issues
    time.sleep(3)
    df = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, f"SELECT Keyword, Professor FROM {univ_keyword_view}"))
    df.columns = ["Keyword", "Professor"]
    #Find Professors associated with given keyword
    proflist = df[df["Keyword"].isin(keywords)]["Professor"].tolist()
    #Filter only to professors with given keyword
    profs = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, """
                                                        SELECT F.name as Professor, position, email, research_interest, U.name as University, F.photo_url 
                                                        FROM faculty as F, University as U WHERE U.id = F.university_id"""))
    profs.columns = ["Professor", "Position", "Email", "Research Interests", "University", "PhotoURL"]

    profs = profs[profs['Professor'].isin(proflist)]

    #Choose current professor and find their stats
    curr_prof = ("" if len(profs) == 0 else profs[0]) if curr_prof is None or curr_prof == "" else curr_prof
    curr_prof_stats = profs[profs["Professor"] == curr_prof]
    if len(curr_prof_stats) == 0:
        return ([" "], [" "])
    curr_prof_stats = curr_prof_stats.iloc[0].tolist()
    photourl = curr_prof_stats.pop()

    #Use MongoDB to find information about specific documents
    faculty_document = faculty_collection.find_one({"name": curr_prof})
    
    num_publications = len(faculty_document.get("publications", []))
    publication_ids = faculty_document.get("publications", [])

    total_citations = 0

    publication_ids = faculty_document.get("publications", [])
    if publication_ids:
        pipeline = [
            {"$match": {"id": {"$in": publication_ids}}},
            {"$group": {"_id": None, "totalCitations": {"$sum": "$numCitations"}}}]
        result = list(publications_collection.aggregate(pipeline))
        
        if result:
            total_citations = result[0]["totalCitations"]
         

    labels = ["FACULTY NAME:", "POSITION:", "EMAIL ADDRESS:", "RESEARCH AREA:", "UNIVERSITY:", "TOTAL PUBLICATIONS:", "TOTAL CITATIONS:"]
    curr_prof_stats.append(num_publications)
    curr_prof_stats.append(total_citations)
    return (
       [
           html.Img(src=photourl, alt=curr_prof, height=300, width=300, style={"display": "block", "margin": "auto", "borderRadius": "10px", "padding": "10px"}),
           html.Table([html.Tbody([html.Tr([html.Td(l, style={"color": "white", "fontWeight": "bold", "textAlign": "right", "fontSize": "16px", "width": "100px"}), 
                                             html.Td(d, style={"color": "Black", "fontSize": "16px", "fontWeight": "bold"})]) for (l, d) in zip(labels, curr_prof_stats)])], style={"flex": 2})
       ]
   )



@app.callback(
    [Output('similar_keywords_dropdown_2', 'value')],
    [Input('similar_keywords_dropdown', 'value')],
    [State('similar_keywords_dropdown_2', 'value'),
     State('similar_keywords_dropdown_2', 'options')])
def similar_type(drop1val, drop2val, drop2options):
    if drop2val is None or drop2val == "" or len(drop2val) == 0:
        drop2val = drop2options[0]
    return [drop2val]


@app.callback(
    [Output('table5_div', 'children')],
    [Input("similar_keywords_dropdown", "value")],
    [Input("similar_keywords_dropdown_2", "value")]
    )
def similarwords(keyword, reltype):
    if keyword is None or keyword == "" or len(keyword) == 0 or reltype == None or reltype == "":
        return [[]]
    cypher_query = ''
    if reltype == "Number of Shared Citations":
        cypher_query = f"""
        MATCH (k1:KEYWORD {{name: '{keyword}' }})-[l:LABEL_BY]-(p:PUBLICATION)-[l2:LABEL_BY]-(k2:KEYWORD)
        RETURN k2.name as keywords,sum(p.numCitations) as NumCitations 
        ORDER BY NumCitations DESC 
        LIMIT 10
        """       
    else:
        cypher_query = f"""
        MATCH (k1:KEYWORD {{name: '{keyword}'}})-[l1:LABEL_BY]-(p:PUBLICATION)-[l2:LABEL_BY]-(k2:KEYWORD)
        RETURN k2.name as keywords, sum(l1.score + l2.score) as score
        ORDER BY score DESC
        LIMIT 10
        """
        reltype = "Similarity"
    try: 
        result = neo4j_conn.query(cypher_query)
    except:
        print("Problem with neo4j query")
        return [[]]
    
    if result is None: 
        return [[]]

    table5 = pd.DataFrame(result)
    table5.columns = ["Top Keywords", "Aggregate Similarity Score" if reltype == "Similarity" else "Number of Concurrent Citations"]
    table5_html = table5.head(8).to_html(classes='table table-striped', index = False)
    return([dcc.Markdown(table5_html, dangerously_allow_html=True)])

@app.callback(
 [Output("dummy_div", "children"),
  Output("image6_div", 'children')],
 [Input("university_blacklist_dropdown", "value")],
 [State("dummy_div", "children")]
 )
def blacklist(blacklist, dummy_val):
    reset_hiding()
    if blacklist is None or len(blacklist) == 0:
        return (dummy_val, [])
    
    hide_university_data_neo4j(neo4j_conn, blacklist)
    mysql_utils.execute_read_query(mysql_connect, f"CALL HideUniversityData(\'{blacklist}\')")
    hide_university_data_mongo(faculty_collection, publications_collection, blacklist)
    create_u_view("University_Keywords")

    univ_photo_url = ''
    try:
        univ_photo_url = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, f"SELECT photo_url FROM university WHERE name = \"{blacklist}\" ")).iat[0,0]
        univ_photo_url = html.Img(src=univ_photo_url, alt="https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/No_image_available.svg/1200px-No_image_available.svg.png", 
                                  height=300, width=300, style={"display": "block", "margin": "auto", "backgroundColor": "white", "paddingTop": "10%"}),
    except:
        univ_photo_url = ""

    return [dummy_val + 1, univ_photo_url]


    

@app.callback(
    [Output("keyword_name_dropdown", "value"),
     Output("similar_keywords_dropdown", "value")],
    [Input("delete_faculty_button", "n_clicks"),
     Input("clear_button", "n_clicks"),
     Input('dummy_div', 'children')], 
    [State("faculty_name_dropdown", "value"),
    State("keyword_name_dropdown", "value")])
def delete_and_clear(del_btn, clear_button, dummy, curr_prof, keywords):
    trigger = callback_context.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'clear_button' or trigger == 'dummy_div' or keywords is None or keywords == "" or len(keywords) == 0:
        pass
    elif trigger == "delete_faculty_button":
        #SQL delete
        time.sleep(1.5)
        
        mysql_utils.execute_read_query(mysql_connect, f"CALL GetProfessorID(\'{curr_prof}\', @prof_id)")
        facid = pd.DataFrame(mysql_utils.execute_read_query(mysql_connect, "SELECT @prof_id")).iat[0,0]
        mysql_utils.delete_record(mysql_connect, "faculty", f"id = {facid}")

        #Mongo delete
        query = { "name": curr_prof }
        faculty_collection.delete_one(query)

        #Neo4j delete
        query = ( "MATCH (p:FACULTY {name: $professor_name}) DETACH DELETE p")
        parameters = {"professor_name": curr_prof}
        neo4j_conn.query(query, parameters)
    else:
        pass

    return ([""], [""])

# Run Application
if __name__ == "__main__":
    app.run_server(debug=False)

mysql_connect.close()
print("SQL connection closed")
neo4j_conn.close()
print("Neo4j connection closed.")
