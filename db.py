import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DBNAME", "cardswap")]

users = db["users"]
users.create_index("username", unique=True)

listings = db["listings"]

offers = db["offers"]
