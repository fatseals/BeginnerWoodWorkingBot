import sqlite3
from sqlite3 import Error
import time

import main

# SQL Database File Path
DB_FILE = "sql.dat"

# Time (seconds) to add to main.PASS_DELAY to get ReviewTime. Works as buffer to make sure posts aren't reviewed twice
ADDITIONAL_PASS_DELAY = 30

# Age of post (seconds) that should be removed from the database (1 day = 86400 seconds)
REMOVE_AGE = 86400

# Name of SQL table
TABLE_NAME = "posts"

CREATE_TABLE_QUERY = f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} ( PostID text PRIMARY KEY, ReviewTime integer, " \
                     f"PostTime integer, ReplyID text ); "


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
    connection = None
    try:
        connection = sqlite3.connect(file)
    except Error as e:
        print(e)
    return connection


def createTable():
    try:
        connection = createDBConnection(DB_FILE)
        cursor = connection.cursor()
        cursor.execute(CREATE_TABLE_QUERY)
        connection.commit()
        connection.close()
    except Error as e:
        print(e)
        exit()


def insertSubmissionIntoDB(connection, submission, reply):
    reviewTime = submission.created_utc + main.PASS_DELAY + ADDITIONAL_PASS_DELAY
    query = f"INSERT INTO {TABLE_NAME} ( PostID, ReviewTime, PostTime, ReplyID) VALUES (?,?,?,?)"
    if (not reply is None) and (not submission is None):
        values = (submission.id, reviewTime, submission.created_utc, reply.id)
    elif reply is None:
        values = (submission.id, reviewTime, submission.created_utc, None)
    else:
        return
    cursor = connection.cursor()
    cursor.execute(query, values)
    connection.commit()


def removePostFromDB(connection, submission):
    query = f"DELETE FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, (submission.id,))
    connection.commit()


def removePostByIDFromDB(connection, postID):
    query = f"DELETE FROM {TABLE_NAME} WHERE PostID = {postID};"
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()


# Not thread safe due to file IO!
def removeExpiredPostsFromDB(connection):
    currentUNIXTime = time.time()
    filter = (currentUNIXTime - REMOVE_AGE,)
    query = f"SELECT PostID FROM {TABLE_NAME} WHERE PostTime < ?;"
    cursor = connection.cursor()
    cursor.execute(query, filter)
    postIDList = cursor.fetchall()
    connection.commit()

    for postID in postIDList:
        # TODO log error in file
        removePostByIDFromDB(connection, "".join(postID))


def fetchUnreviewedPostsFromDB(connection):
    currentUNIXTime = (time.time(),)
    query = f"SELECT PostID FROM {TABLE_NAME} WHERE ReviewTime < ?;"
    cursor = connection.cursor()
    cursor.execute(query, currentUNIXTime)
    postIDTupleList = cursor.fetchall()
    connection.commit()

    postIDList = []
    for postIDTuple in postIDTupleList:
        postIDList.append("".join(postIDTuple))

    return postIDList


def fetchCommentIDFromDB(connection, submission):
    postId = (submission.id,)
    query = f"SELECT ReplyID FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, postId)
    commentIDTupleList = cursor.fetchall()
    connection.commit()
    return "".join(commentIDTupleList[0])


def fetchAllPostIDsFromDB(connection):
    query = f"SELECT PostID FROM {TABLE_NAME};"
    cursor = connection.cursor()
    cursor.execute(query)
    postIDTupleList = cursor.fetchall()
    connection.commit()

    postIDList = []
    for postIDTuple in postIDTupleList:
        postIDList.append("".join(postIDTuple))

    return postIDList
