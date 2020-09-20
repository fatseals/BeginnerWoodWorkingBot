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

# Char to use as a separator for votingOptions. It should not be included in any votingOptions
SEPARATOR = ","

# Name of message SQL table
MESSAGE_TABLE_NAME = "messages"

CREATE_TABLE_QUERY = f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} ( PostID text PRIMARY KEY, ReviewTime integer, " \
                     f"VotingTime integer, PostTime integer, ReplyID text, VotingOptions text, Votes text, " \
                     f"Voters text, IsVoteable integer, ReviewState integer );"
# === Table entries: ===
# PostID is the Reddit assigned ID for the post.
# ReviewTime is the UNIX time (in seconds) + 120s that the post was due to be reviewed
# Voting Time is the UNIX time (in seconds) that the voting should conclude on a post
# PostTime is the UNIX time (in seconds) that the post was made
# ReplyID is the Reddit assigned ID for the standard reply made by the bot.
# VotingOptions is a comma denoted list of voting options used for the removal voting process
# Votes keeps track of votes for votingOptions in the same structure as VotingOptions. Used like a dict.
# Voters is a comma denoted list of users who have made a vote on the post
# IsVoteable tracks if voting is enabled. 1=True, 0=False
# ReviewState: 0=First pass done, 1=Second pass done, 3=Voting done (rows should be deleted before 3)
# === Other things to do with the table: ===
# Posts which are removed for double dipping on the first pass should not be added to the table.
# Posts which have been reviewed should be removed form the table
# Posts older than REMOVE_AGE should be removed from the table and an error should be logged with the PostID.

CREATE_MESSAGE_TABLE_QUERY = f"CREATE TABLE IF NOT EXISTS {MESSAGE_TABLE_NAME} ( MessageID text PRIMARY KEY, " \
                             f"Subject text, Body text, Sender text, IsUserMessage integer, MessageTime integer );"
# === Table entries: ===
# MessageID is ideally the ID of the message (only needed as a primary key). It
# Subject is the subject line of the message
# Body is the body text of the message
# Sender is the name of the user that sent the message.
# Is user message is a boolean denoting if the user sent the message of of it is a notification made by the moderator /
#     bot. 0 = moderator bot message/ 1 = message from the user
# MessageTime is the time the message was added to the database

logger = main.mainLogger


def encodeVotingOptions(votingOptions: list) -> str:
    separator = SEPARATOR
    return separator.join(votingOptions)


def encodeVotes(votes: list) -> str:
    separator = SEPARATOR
    return separator.join(list(map(str, votes)))


def encodeVoters(voters: list) -> str:
    separator = SEPARATOR
    return separator.join(voters)


def decodeVotingOptions(votingOptions: str) -> list:
    return votingOptions.split(SEPARATOR)


def decodeVotes(votes: str) -> list:
    logger.debug(f"Decoded votes: {votes}")
    return list(map(int, votes.split(SEPARATOR)))


def decodeVoters(voters: str) -> list:
    return voters.split(SEPARATOR)


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
        connection.commit()
        cursor.execute(CREATE_MESSAGE_TABLE_QUERY)
        connection.commit()
        connection.close()
    except Error as e:
        print(e)


def insertSubmissionIntoDB(connection: sqlite3.Connection, submission: praw.models.Submission, reply,
                           votingOptions: list, isVoteable: bool):
    reviewTime = submission.created_utc + main.PASS_DELAY + ADDITIONAL_PASS_DELAY
    votingTime = submission.created_utc + main.VOTE_ACTION_DELAY
    query = f"INSERT INTO {TABLE_NAME} (PostID, ReviewTime, VotingTime, PostTime, ReplyID, VotingOptions, Votes, " \
            f"Voters, IsVoteable, ReviewState) VALUES (?,?,?,?,?,?,?,?,?,?)"

    if (votingOptions is None) or (len(votingOptions) == 0) or (isVoteable is None):
        return

    numberOfVoteOptions = len(votingOptions)
    encodedVoteOptions = encodeVotingOptions(votingOptions)

    # "Create a string with separated zeros the same length as numberOfVoteOptions
    encodedVotes = ""
    for i in range(numberOfVoteOptions - 1):
        encodedVotes = encodedVotes + "0" + SEPARATOR
    encodedVotes = encodedVotes + "0"

    logger.debug(f"Encoded voting options being put into new db entry: {encodedVoteOptions}")
    logger.debug(f"Encoded votes being put into new db entry: {encodedVotes}")

    values = None
    if (reply is not None) and (reply is not "") and (submission is not None):
        values = (submission.id, reviewTime, votingTime, submission.created_utc, reply.id, encodedVoteOptions,
                  encodedVotes, "", int(isVoteable), 0)
    elif (reply is None) or (reply is ""):
        values = (submission.id, reviewTime, votingTime, submission.created_utc, None, encodedVoteOptions,
                  encodedVotes, "", int(isVoteable), 0)
    else:
        return
    cursor = connection.cursor()
    cursor.execute(query, values)
    connection.commit()


# This only updates the database. It does not make any edits to posts
def updateVotes(connection: sqlite3.Connection, submissionID: str, votes: list):
    if (connection is None) or (submissionID is None) or (submissionID == "") or (votes is None) or (len(votes) == 0):
        return

    # Check if the amount of votes matches the amount of votingOptions
    selectQuery = f"SELECT VotingOptions FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(selectQuery, (submissionID,))
    votingOptionsTupleList = cursor.fetchall()
    connection.commit()
    numberOfVotingOptions = len(decodeVotingOptions(votingOptionsTupleList[0][0]))

    logger.debug(f"Voting options tuple list: {votingOptionsTupleList}")

    if len(votes) != numberOfVotingOptions:
        return

    # Update the votes in the database
    updateQuery = f"UPDATE {TABLE_NAME} SET Votes = ? WHERE PostID = ?"
    encodedVotes = encodeVotes(votes)
    cursor = connection.cursor()
    cursor.execute(updateQuery, (encodedVotes, submissionID))
    connection.commit()


def updateVoters(connection: sqlite3.Connection, submissionID: str, voters: list):
    if (connection is None) or (submissionID is None) or (submissionID == "") or (voters is None) or (len(voters) == 0):
        return

    # Update the voters in the database
    query = f"UPDATE {TABLE_NAME} SET Voters = ? WHERE PostID = ?"
    encodedVoters = encodeVoters(voters)
    cursor = connection.cursor()
    cursor.execute(query, (encodedVoters, submissionID))
    connection.commit()


def isVoteable(connection: sqlite3.Connection, submissionID: str) -> bool:
    if (connection is None) or (submissionID is None) or (submissionID == ""):
        return False

    query = f"SELECT IsVoteable FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, (submissionID,))
    tupleList = cursor.fetchall()
    connection.commit()

    return bool(tupleList[0][0])


def updateVotingEligibility(connection: sqlite3.Connection, submissionID: str, votingEligibility: bool):
    if (connection is None) or (submissionID is None) or (submissionID == "") or (votingEligibility is None):
        return

    # Update the voters in the database
    query = f"UPDATE {TABLE_NAME} SET IsVoteable = ? WHERE PostID = ?"
    cursor = connection.cursor()
    cursor.execute(query, (int(votingEligibility), submissionID))
    connection.commit()


def fetchVotes(connection: sqlite3.Connection, submissionID: str) -> dict:

    if (connection is None) or (submissionID is None) or (submissionID == ""):
        return {}

    query = f"SELECT VotingOptions, Votes FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, (submissionID,))
    tupleList = cursor.fetchall()
    connection.commit()

    decodedVotingOptions = decodeVotingOptions(tupleList[0][0])
    decodedVotes = decodeVotes(tupleList[0][1])
    return dict(zip(decodedVotingOptions, decodedVotes))


def fetchVoters(connection: sqlite3.Connection, submissionID: str) -> list:
    if (connection is None) or (submissionID is None) or (submissionID == ""):
        return []

    query = f"SELECT Voters FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor = connection.cursor()
    cursor.execute(query, (submissionID,))
    tupleList = cursor.fetchall()
    connection.commit()

    return decodeVoters(tupleList[0][0])


def insertUserMessageIntoDB(connection: sqlite3.Connection, message: praw.models.Submission):
    if connection is None:
        return

    query = f"INSERT INTO {MESSAGE_TABLE_NAME} (MessageID , Subject, Body, Sender, IsUserMessage, MessageTime) " \
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
            f"VALUES (?,?,?,?,?)"
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
    cursor.execute(query, (postID,))
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
    cursor.execute(query, (messageID,))
    connection.commit()
    print(f"{messageID} removed from database {MESSAGE_TABLE_NAME}")
    print()


def removeExpiredPostsFromDB(connection: sqlite3.Connection):
    if connection is None:
        return

    currentUNIXTime = time.time()
    filter = (currentUNIXTime - REMOVE_AGE,)
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

    query = f"SELECT MessageID, Subject, Body, Sender, IsUserMessage, MessageTime FROM {MESSAGE_TABLE_NAME}"
    cursor = connection.cursor()
    cursor.execute(query)
    messageTuples = cursor.fetchall()
    connection.commit()

    return messageTuples


def incrementReviewState(connection: sqlite3.Connection, submissionID: str):
    if (connection is None) or (submissionID == "") or (submissionID is None):
        return

    cursor = connection.cursor()

    # Get current ReviewState
    query = f"SELECT ReviewState FROM {TABLE_NAME} WHERE PostID = ?;"
    cursor.execute(query, (submissionID, ))
    reviewState = cursor.fetchall()[0][0] + 1
    connection.commit()

    # Update the ReviewState
    query = f"UPDATE {TABLE_NAME} SET ReviewState = ? WHERE PostID = ?"
    cursor.execute(query, (reviewState, submissionID))
    connection.commit()


# TODO This currently only does a second review on posts that it missed. Make it more better.
def fetchUnreviewedPostsFromDB(connection: sqlite3.Connection):
    if connection is None:
        return

    reviewState = (0,)
    query = f"SELECT PostID FROM {TABLE_NAME} WHERE ReviewState = ?;"
    cursor = connection.cursor()
    cursor.execute(query, reviewState)
    postIDTupleList = cursor.fetchall()
    connection.commit()

    postIDList = []
    for postIDTuple in postIDTupleList:
        postIDList.append("".join(postIDTuple))

    return postIDList


def fetchPostsNeedingVotingFromDB(connection: sqlite3.Connection):
    if connection is None:
        return

    currentUNIXTime = (time.time(),)
    query = f"SELECT PostID FROM {TABLE_NAME} WHERE VotingTime < ?;"
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
