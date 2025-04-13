from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError

# Function to create initial connection to database
def connect_to_mongodb(url, database_name):
    try:
        client = MongoClient(url)
        
        db = client[database_name]
        
        print(f"Successfully connected to the MongoDB database: {database_name}")
        
        return db
    except (ConnectionFailure, ConfigurationError) as e:
        print(f"Error: '{e}'")
        return None

def update_hidden_status(db, collection_name, filter_query, new_value):
    collection = db[collection_name]
    result = collection.update_many(filter_query, {"$set": {"is_hidden": new_value}})
    return result.modified_count
# MongoDB connection details
mongodb_url = "mongodb://localhost:27017"
database_name = "academicworld"

# Connect to the MongoDB database
#db = connect_to_mongodb(mongodb_url, database_name)


#if db is not None:
#    pass
    #List collections
    #collections = db.list_collection_names()
    #print("Collections in the database:", collections)

    # Access specific collection
    #collection_name = "faculty" 
    #collection = db[collection_name]

    # Find all documents in the collection
    #documents = collection.find()
    #for document in documents:
        #print(document)

