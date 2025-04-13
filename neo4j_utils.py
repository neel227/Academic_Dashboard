from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

class Neo4jConnection:
    def __init__(self, url, user, password, db):
        self._driver = GraphDatabase.driver(url, auth=(user, password))
        self.db = db
        print("Successful authentication of Neo4j")

    def close(self):
        self._driver.close()

    def query(self, query, parameters=None, **kwargs):
        with self._driver.session(database=self.db) as session:
            try:
                result = session.run(query, parameters, **kwargs)
                return [val for val in result]
            except ServiceUnavailable as e:
                print(f"Error: '{e}'")
                return None

# Connect to the Neo4j database
neo4j_conn = Neo4jConnection(url="bolt://localhost:7687", user="neo4j", password="Aleen@isacat411", db="academicworld")

# Function to create a node
def create_node(label, properties):
    properties_str = ", ".join(f"{key}: '{value}'" for key, value in properties.items())
    query = f"CREATE (n:{label} {{ {properties_str} }}) RETURN n"
    result = neo4j_conn.query(query)
    return result

# Function to create a relationship between two nodes
def create_relationship(node1_label, node1_properties, node2_label, node2_properties, relationship_type):
    node1_props_str = ", ".join(f"{key}: '{value}'" for key, value in node1_properties.items())
    node2_props_str = ", ".join(f"{key}: '{value}'" for key, value in node2_properties.items())
    query = (
        f"MATCH (a:{node1_label} {{ {node1_props_str} }}), (b:{node2_label} {{ {node2_props_str} }}) "
        f"CREATE (a)-[r:{relationship_type}]->(b) RETURN r"
    )
    result = neo4j_conn.query(query)
    return result

# Function to find nodes
def find_nodes(label, properties=None):
    if properties:
        properties_str = " AND ".join(f"{key}: '{value}'" for key, value in properties.items())
        query = f"MATCH (n:{label}) WHERE {properties_str} RETURN n"
    else:
        query = f"MATCH (n:{label}) RETURN n"
    result = neo4j_conn.query(query)
    return result

# Find nodes
#found_nodes = neo4j_conn.query("MATCH (n) RETURN n LIMIT 25")
#print("Found nodes:", found_nodes)

# Close the connection
#neo4j_conn.close()
#print("Neo4j connection closed.")
