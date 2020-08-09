import os
import sqlite3
from sqlite3 import Error
import time

import main

import praw

# SQL Database File Path
DB_FILE = "sql.dat"

# Time (seconds) to add to main.PASS_DELAY to get ReviewTime. Works as buffer to make sure posts aren't reviewed twice
ADDITIONAL_PASS_DELAY = 30

# Age of post (seconds) that should be removed from the database (1 day = 86400 seconds)
REMOVE_AGE = 86400

# Name of SQL table
TABLE_NAME = "posts"

# Name of message SQL table
MESSAGE_TABLE_NAME = "messages"

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

CREATE_MESSAGE_TABLE_QUERY = f"CREATE TABLE IF NOT EXISTS {MESSAGE_TABLE_NAME} ( MessageID text PRIMARY KEY, " \
                             f"Subject text, Body text, From text, IsUserMessage integer, MessageTime integer );"
# === Table entries: ===
# MessageID is ideally the ID of the message (only needed as a primary key). It
# Subject is the subject line of the message
# Body is the body text of the message
# From is the name of the user that sent the message.
# Is user message is a boolean denoting if the user sent the message of of it is a notification made by the moderator /
#     bot. 0 = moderator bot message/ 1 = message from the user
# MessageTime is the time the message was added to the database


def createDBConnection(file: str):
    connection = None
    try:
        connection = sqlite3.connect(file)
    except Error as e:
        print(e)
    return connection


def createTables():
    try:
        connection = createDBConnection(DB_FILE)
        cursor = connection.cursor()
        cursor.execute(CREATE_TABLE_QUERY)
        cursor.execute(CREATE_MESSAGE_TABLE_QUERY)
        connection.commit()
        connection.close()
    except Error as e:
        print(e)


def insertSubmissionIntoDB(connection: sqlite3.Connection, submission: praw.models.Submission, reply: str):
    reviewTime = submission.created_utc + main.PASS_DELAY + ADDITIONAL_PASS_DELAY
    query = f"INSERT INTO {TABLE_NAME} (PostID, ReviewTime, PostTime, ReplyID) VALUES (?,?,?,?)"
    values = None
    if ((reply is not None) or (reply is "")) and (submission is not None):
        values = (submission.id, reviewTime, submission.created_utc, reply.id)
    elif reply is None or reply is "":
        values = (submission.id, reviewTime, submission.created_utc, None)
    else:
        return
    cursor = connection.cursor()
    cursor.execute(query, values)
    connection.commit()


def insertUserMessageIntoDB(connection: sqlite3.Connection, message: praw.models.Submission):
    if connection is None:
        return

    query = f"INSERT INTO {MESSAGE_TABLE_NAME} (MessageID , Subject, Body, From, IsUserMessage, MessageTime) " \
            f"VALUES (?,?,?,?,?,?)"
    values = None
    if message is not None:
        values = (message.id, message.subject, message.body, message.author.name, 1, time.time())
    else:
        return
    cursor = connection.cursor()
    cursor.execute(query, values)
    connection.commit()


def insertBotMessageIntoDB(connection: sqlite3.Connection, subject: str, body: str):
    if connection is None:
        return

    query = f"INSERT INTO {MESSAGE_TABLE_NAME} (MessageID , Subject, Body, IsUserMessage, MessageTime) " \
            f"VALUES (?,?,?,?,?,?)"
    values = None
    if subject is not None or subject is "":
        UID = str(time.time()) + body
        values = (UID, subject, body, 0, time.time())
    else:
        return
    cursor = connection.cursor()
    cursor.execute(query, values)
    connection.commit()


def removePostFromDB(connection: sqlite3.Connection, submission: praw.models.Submission):
    if connection is None:
        return

    query = f"DELETE FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, (submission.id,))
    connection.commit()
    print(f"{submission.id} removed from table {TABLE_NAME}")
    print()


def removePostByIDFromDB(connection: sqlite3.Connection, postID: str):
    if connection is None:
        return

    query = f"DELETE FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, (postID, ))
    connection.commit()
    print(f"{postID} removed from table {TABLE_NAME}")
    print()


def removeMessageFromDB(connection: sqlite3.Connection, message: praw.models.Message):
    if connection is None:
        return

    query = f"DELETE FROM {MESSAGE_TABLE_NAME} WHERE MessageID = ?"
    cursor = connection.cursor()
    cursor.execute(query, (message.id,))
    connection.commit()
    print(f"{message.id} removed from table {MESSAGE_TABLE_NAME}")
    print()


def removeMessageByIDFromDB(connection: sqlite3.Connection, messageID: str):
    if connection is None:
        return


    query = f"DELETE FROM {MESSAGE_TABLE_NAME} WHERE MessageID = ?"
    cursor = connection.cursor()
    cursor.execute(query, (messageID, ))
    connection.commit()
    print(f"{messageID} removed from table {MESSAGE_TABLE_NAME}")
    print()


def removeExpiredPostsFromDB(connection: sqlite3.Connection):
    if connection is None:
        return

    currentUNIXTime = time.time()
    filter = (currentUNIXTime - REMOVE_AGE, )
    postsQuery = f"SELECT PostID FROM {TABLE_NAME} WHERE PostTime < ?;"
    messagesQuery = f"SELECT MessageID FROM {MESSAGE_TABLE_NAME} WHERE MessageTime < ?"

    cursor = connection.cursor()
    cursor.execute(postsQuery, filter)
    postIDList = cursor.fetchall()
    connection.commit()

    for postID in postIDList:
        try:
            removePostByIDFromDB(connection, "".join(postID))
        except Error as e:
            print("There's an issue with the removePostByIDFromDB. Probably a tuple thing.")
            print(e)
            print("\n")

    cursor.execute(messagesQuery, filter)
    messageIDList = cursor.fetchall()
    connection.commit()

    for messageID in messageIDList:
        try:
            removeMessageByIDFromDB(connection, "".join(messageID))
        except Error as e:
            print("There's an issue with the removePostByIDFromDB. Probably a tuple thing.")
            print(e)
            print("\n")


def fetchAllMessagesFromDB(connection: sqlite3.Connection):
    if connection is None:
        return

    query = f"SELECT MessageID , Subject, Body, From, IsUserMessage, MessageTime from {MESSAGE_TABLE_NAME}"
    cursor = connection.cursor()
    cursor.execute(query)
    messageTuples = cursor.fetchall()
    connection.commit()

    return messageTuples


def fetchUnreviewedPostsFromDB(connection: sqlite3.Connection):
    if connection is None:
        return

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


def fetchCommentIDFromDB(connection: sqlite3.Connection, submission: praw.models.Submission):
    if connection is None:
        return

    postId = (submission.id,)
    query = f"SELECT ReplyID FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, postId)
    commentIDTupleList = cursor.fetchall()
    connection.commit()
    try:
        if commentIDTupleList[0][0] is None:
            return ""
        else:
            return "".join(commentIDTupleList[0][0])
    except Exception as e:
        print("=======================================================================================================")
        print("This method gets unhappy when testing.")
        print(f"commentIDTupleList = {commentIDTupleList}")
        print("=======================================================================================================")
        print(e)
        print("=======================================================================================================")
        print("\n")
        return ""


def fetchAllPostIDsFromDB(connection: sqlite3.Connection):
    if connection is None:
        return

    query = f"SELECT PostID FROM {TABLE_NAME};"
    cursor = connection.cursor()
    cursor.execute(query)
    postIDTupleList = cursor.fetchall()
    connection.commit()

    postIDList = []
    for postIDTuple in postIDTupleList:
        postIDList.append("".join(postIDTuple))

    return postIDList
