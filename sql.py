import sqlite3
from sqlite3 import Error
import time

import main

# Time (seconds) to add to main.PASS_DELAY to get ReviewTime. Works as buffer to make sure posts aren't reviewed twice
ADDITIONAL_PASS_DELAY = 60

# Age of post (seconds) that should be removed from the database (1 day = 86400 seconds)
REMOVE_AGE = 86400

# Name of SQL table
TABLE_NAME = "posts"

CREATE_TABLE_QUERY = f"CREATE TABLE IF NOT EXISTS {DB_NAME} ( PostID text PRIMARY KEY, ReviewTime integer, PostTime integer, ReplyID text );"
# === Table entries: ===
# PostID is the Reddit assigned ID for the post.
# ReviewTime is the UNIX time (in seconds) + 120s that the post was due to be reviewed
# PostTime is the UNIX time (in seconds) that the post was made
# ReplyID is the Reddit assigned ID for the standard reply made by the bot.
# === Other things to do with the table: ===
# Posts which are removed for double dipping on the first pass should not be added to the table.
# Posts which have been reviewed should be removed form the table
# Posts older than REMOVE_AGE should be removed from the table and an error should be logged with the PostID.

def createDBConnection(file):
    conn = None
    try:
        conn = sqlite3.connect(file)
    except Error as e:
        print(e)
    finally:
        if conn:
            conn.close()

def createTable(connection):
    try:
        cursor = connection.cursor()
        cursor.execute(CREATE_TABLE_QUERY)
        connection.commit()
    except Error as e:
        print(e)

def insertPostIntoDB(connection, submission, reply):
    reviewTime = submission.created_utc + main.PASS_DELAY + ADDITIONAL_PASS_DELAY
    query = f"INSERT INTO {DB_NAME} ( PostID, ReviewTime, PostTime, ReviewBool, ReplyID)" \
            f"VALUES (" \
            f"{submission.id}, " \
            f"{reviewTime},"  \
            f"{submission.created_utc}, " \
            f"{reply.id});"
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()

def removePostFromDB(connection, post):
    query = f"DELETE FROM {TABLE_NAME} WHERE PostID = {post.id};"
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()

def removePostByIDFromDB(connection, postID):
    query = f"DELETE FROM {TABLE_NAME} WHERE PostID = {postID};"
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()

def removeExpiredPostsFromDB(connection):
    currentUNIXTime = time.time()
    filter = currentUNIXTime - REMOVE_AGE
    query = f"SELECT PostID FROM {TABLE_NAME} WHERE PostTime < {filter};"
    cursor = connection.cursor()
    cursor.execute(query)
    postIDList = cursor.fetchall()
    connection.commit()

    for postID in postIDList:
        # TODO log error
        removePostByIDFromDB(connection, postID)

def fetchUnreviewedPostsFromDB(connection):
    currentUNIXTime = time.time()
    query = f"SELECT PostID FROM {TABLE_NAME} WHERE ReviewTime < {currentUNIXTime};"
    cursor = connection.cursor()
    cursor.execute(query)
    postIDList = cursor.fetchall()
    connection.commit()

    return postIDList