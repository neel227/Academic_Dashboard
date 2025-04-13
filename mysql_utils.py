import mysql.connector
from mysql.connector import Error
import pandas as pd
import plotly.express as px
from plotly.basedatatypes import BaseFigure


# Function to create initial connection to database
def create_connection(host, user, password, database):
    connection = None
    try:
        connection = mysql.connector.connect(
            host= host,      
            user= user,
            password= password,
            database= database
        )
        if connection.is_connected():
            print("SQL Connection successful")
    except Error as e:
        print(f"Error: '{e}'")
    return connection

# Function for database modifications (e.g., CREATE, INSERT, UPDATE)
def execute_write_query(connection, query):
    c = connection.cursor()
    try:
        c.execute(query)
        connection.commit()
    except Error as e:
        print(f"Error: '{e}'")

# Function for querying data (e.g., SELECT)
def execute_read_query(connection, query):
    c = connection.cursor()
    output = None
    try:
        c.execute(query)
        output = c.fetchall()
        return output
    except Error as e:
        print(f"Error: '{e}'")

#Function to create a view
def create_view(connection, view_name, select_query):
    create_view_query = f"CREATE VIEW {view_name} AS {select_query}"
    execute_write_query(connection, create_view_query)

#Function to Delete records
def delete_record(connection, table_name, condition):
    c = connection.cursor()
    try:
        sql_delete_query = f"DELETE FROM {table_name} WHERE {condition}"
        c.execute(sql_delete_query)
        connection.commit()
        print(f"{c.rowcount} record(s) deleted successfully")
    except Error as e:
        print(f"Error: {e}")

def column_exists(connection, table, column):
    query = f"""
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE
        TABLE_SCHEMA = DATABASE() AND
        TABLE_NAME = '{table}' AND
        COLUMN_NAME = '{column}'
    """
    cursor = connection.cursor()
    cursor.execute(query)
    result = cursor.fetchone()
    return result[0] == 1

def create_stored_procedure(connection):
    create_procedure_query = """
    DELIMITER //
    CREATE PROCEDURE GetProfessorID(IN professor_name VARCHAR(255), OUT professor_id INT)
    BEGIN
        SELECT id INTO professor_id FROM faculty WHERE name = professor_name;
    END //
    DELIMITER ;
    """
    execute_write_query(connection, create_procedure_query)

def drop_view_if_exists(connection, view_name):
    check_view_query = f"""
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.VIEWS
    WHERE TABLE_SCHEMA = '{connection.database}' AND TABLE_NAME = '{view_name}';
    """
    cursor = connection.cursor()
    cursor.execute(check_view_query)
    result = cursor.fetchone()
    if result[0] > 0:
        drop_view_query = f"DROP VIEW IF EXISTS {view_name}"
        execute_write_query(connection, drop_view_query)