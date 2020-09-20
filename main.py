import math
import sqlite3
import threading
import time
import logging

import sql
import notifier

import praw
from prawcore import ServerError
from praw.exceptions import APIException

# Reply for encouraging discussion - placed on every image post
# Do not use pipes "|" in it
STANDARD_REPLY = "Thank you for posting to r/BeginnerWoodWorking! If you have not chosen a post flair then please " \
                 "add one to your post. If you have submitted a finished build, please consider leaving a comment " \
                 "about it so that others can learn."

# Reply when the user has cross posted / doubled dipped - the post concerned will be removed
# Do not use pipes "|" in it
DOUBLE_DIPPING_REPLY = "**Your submission to r/BeginnerWoodWorking has been removed**. As per [rule #4](" \
                       "https://www.reddit.com/r/BeginnerWoodWorking/about/rules/), images and links posted in this " \
                       "subreddit cannot also be posted in other subreddits. \n\n This action has been performed " \
                       "automatically by a bot. If you believe that your post has been removed in error then please [" \
                       "message the moderators](https://www.reddit.com/message/compose?to=%2Fr%2FBeginnerWoodWorking)."

# This part is added to the standard reply when a posy is voteable.
VOTING_TEXT = "\n\n**Public vote: Do you think this post is a good fit for /r/BeginnerWoodWorking?** If you do then " \
              "reply to **this comment** with `!yes`. If you don't then reply with `!no`. Voting determines if a " \
              "post will be removed so please vote if you feel strongly.\n"

# Part of a reply to indicate voting has closed
VOTING_CLOSED_TEXT = "\n\n**Voting on this submission has closed**."

# How long to wait in seconds before checking the post again to delete the standard reply and/ or to remove the
# submission for double dipping (900s = 15m)
PASS_DELAY = 900

# How long to wait in seconds after the post was made to carry out voting actions (21600s = 6 hours)
VOTE_ACTION_DELAY = 14400

# If the bot should create a mod mail when it removes a post.
# Tabs can be kept on the bot by looking in the moderation log if set to false
CREATE_MOD_MAIL = True

# User agent to connect to Reddit
USER_AGENT = "BeginnerWoodworkBot by u/-CrashDive-"

# Site in praw.ini with bot credentials
PRAW_INI_SITE = "bot"

# Bot username
BOT_USERNAME = "BeginnerWoodworkBot"

# Subreddit for the bot to operate on
SUBREDDIT = "BeginnerWoodWorking"

# Flair texts for links the standard reply should not be given on
NO_REPLY_FLAIR_TEXTS = ["Discussion/Question !?", "Funny Friday"]

# If the title contains any of the following the standard reply will not be given
NO_REPLY_TITLE_TEXTS = ["?"]

# Flair texts for links that should not be voted on
NO_VOTE_FLAIR_TEXTS = ["Discussion/Question !?", "Funny Friday", "SAFETY - NSFW (GORE)"]

# If the title contains any of the following it will not be voted on
NO_VOTE_TITLE_TEXTS = ["?"]

# Location of the log file
LOG_FILE = "bot.log"

# Level of detail for the logger: logging.DEBUG, logger.INFO, or logger.WARNING
LOGGING_LEVEL = logging.DEBUG

# Command prefix for flair voting. Do not use uppercase letters.
COMMAND_PREFIX = "!"

# Voting options and commands
# Format: {"Command-without-prefix": "Option", ...} do not use spaces in commands or pipes ("|") in either.
VOTING_DICTIONARY = {"yes": "Beginner", "no": "Not Beginner"}

# ======================================================================================================================
#                                             End configurable variables
# ======================================================================================================================

VOTING_COMMANDS = list(VOTING_DICTIONARY.keys())
VOTING_OPTIONS = list(VOTING_DICTIONARY.values())


def stripVotingTableFromBody(body: str) -> str:
    return body[:body.find("|")]


def createBodyWithNewVotingTable(connection: sqlite3.Connection, submission: praw.models.Submission, body: str) -> str:
    if (connection is None) or (submission is None) or (body is None):
        return ""

    # Trim existing table
    body = stripVotingTableFromBody(body)

    votes = sql.fetchVotes(connection, submission.id)

    keys = votes.keys()
    values = votes.values()
    values = list(map(str, values))

    table = "\n\n| " + " | ".join(keys) + " |\n|"
    for i in range(len(keys)):
        table = table + ":-:|"
    table = table + "\n| " + " | ".join(values) + " |"

    return body + table


def isDoubleDipping(submission: praw.models.Submission) -> bool:
    if not submission.is_self:
        duplicates = submission.duplicates()
        for duplicate in duplicates:
            # This is pretty loose criteria. It intentionally does not check for reposts of other users links.
            # It also excludes posts made in SUBREDDIT
            if (duplicate.author == submission.author) and (duplicate.subreddit.id != subreddit.id):
                return True

    return False


def isAQuestion(submission: praw.models.Submission) -> bool:
    flairText = reddit.submission(id=submission.id).link_flair_text  # Ensures is gets the most recent flair
    if flairText is None:
        flairText = ""

    mainLogger.debug(f"{submission.title} -> flair = {flairText}")

    for text in NO_REPLY_TITLE_TEXTS:
        if text in submission.title:
            return True

    if flairText in NO_REPLY_FLAIR_TEXTS:
        return True

    return False


def removeDoubleDippers(connection: sqlite3.Connection, submission: praw.models.Submission, logger: logging.Logger):
    try:
        reply = submission.reply(DOUBLE_DIPPING_REPLY)
        reply.mod.distinguish(how="yes", sticky=True)

        if (submission.author is not None) and (submission.title is not None) and CREATE_MOD_MAIL:
            subject = "Removed double dipping post (Rule #4)"
            body = f"Automatically removed post \"[{submission.title}]({submission.permalink})\" " \
                   f"by u/{submission.author.name} for rule #4 violation. "
            sql.insertBotMessageIntoDB(connection, subject, body)
            logger.debug(f"Inserted mod mail into the db for submission: {submission.title}")
    except Exception as e:
        logger.warning("Unable to send modmail")
        logger.warning("Printing stack trace")
        logger.warning(e)
    finally:
        submission.mod.remove()
        logger.info(f"=== Removed post by u/{submission.author}: \"{submission.title}\" for double dipping. "
                    f"ID = {submission.id}")


def findVotingEligibility(submission: praw.models.Submission, logger: logging.Logger):
    flairText = reddit.submission(id=submission.id).link_flair_text  # Ensures is gets the most recent flair
    if flairText is None:
        flairText = ""

    mainLogger.debug(f"{submission.title} -> flair = {flairText}")

    for text in NO_VOTE_TITLE_TEXTS:
        if text in submission.title:
            return False

    if flairText in NO_VOTE_FLAIR_TEXTS:
        False

    return True


def firstReviewPass(submission: praw.models.Submission, connection: sqlite3.Connection, logger: logging.Logger):
    if submission is None:
        logger.debug("Submission is None. Ignoring.")
        return False

    logger.info(f"Working on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")

    # TODO add shit for voting

    # Give standard reply for posts that aren't questions
    if isAQuestion(submission):
        logger.info(f"Gave no reply to \"{submission.title}\" by u/{submission.author}.")
        return False

    # Check for double dipping (first pass)
    if isDoubleDipping(submission):
        removeDoubleDippers(connection, submission, logger)
        return False

    # Actions to perform if the post is not double dipping and is not a question
    body = STANDARD_REPLY
    votingEligibility = findVotingEligibility(submission, logger)
    logger.info(f"Gave standard reply to \"{submission.title}\" by u/{submission.author}.")
    reply = submission.reply(body)
    reply.mod.distinguish(how="yes", sticky=True)
    reply.downvote()

    # Add to db
    sql.insertSubmissionIntoDB(connection, submission, reply, VOTING_OPTIONS, votingEligibility)
    sql.incrementReviewState(connection, submission.id)

    # If the post is voteable then it adds the voting text and the voting table
    if votingEligibility:
        logger.info(f"\"{submission.title}\" by u/{submission.author} is voteable. Adding voting text and vote table")
        body = createBodyWithNewVotingTable(connection, submission, body + VOTING_TEXT)
        reply.edit(body)

    return True


def secondReviewPass(submission: praw.models.Submission, connection: sqlite3.Connection, logger: logging.Logger):
    if submission is None:
        logger.debug("Submission is None. Ignoring.")
        return False

    # Check for double dipping and remove submission if needed
    if isDoubleDipping(submission):
        removeDoubleDippers(connection, submission, logger)
        # Remove post from SQL DB
        sql.removePostFromDB(connection, submission)
        return False

    # Fetch the replyID from database
    replyID = sql.fetchCommentIDFromDB(connection, submission)

    # Return if there is no reply
    if replyID is None or replyID == "":
        return False

    # Un-sticky standard reply if it is not voteable. Keep the standard reply and update if it is voteable
    votingEligibility = findVotingEligibility(submission, logger)
    reply = reddit.comment(replyID)
    logger.debug(f"Voting eligibility -> {votingEligibility}")

    if votingEligibility:
        logger.info(f"Did not un-sticky standard reply on \"{submission.title}\" by u/{submission.author} (voteable)")
        body = reply.body

        # Add the voting text if it's not there already
        if VOTING_TEXT not in body:
            body = body + VOTING_TEXT

        # Add the voting table
        body = createBodyWithNewVotingTable(connection, submission, body)

        logger.info(f"Edited standard reply on \"{submission.title}\" by u/{submission.author} to include voting")
        reply.edit(body)

        # Grant voting eligibility
        sql.updateVotingEligibility(connection, submission.id, True)

    else:
        # Un-sticky reply
        logger.info(f"Un-stickied standard reply on \"{submission.title}\" by u/{submission.author}")
        reply.mod.undistinguish()
        reply.mod.distinguish(how="yes", sticky=False)

        # Remove voting table and voting text
        logger.info(f"Edited standard reply on \"{submission.title}\" by u/{submission.author} to remove voting")
        reply.edit(STANDARD_REPLY)

    # Update the voting eligibility
    sql.updateVotingEligibility(connection, submission.id, votingEligibility)

    # Assumes the oldest top level comment by the poster is the writeup
    # If the writeup exists, the standard reply should be deleted (assuming it has no children)
    oldestOPComment = None
    submission.comments.replace_more(limit=None)
    topComments = submission.comments
    # iterates through top level comments and finds the oldest one by the poster
    for comment in topComments:
        if comment.is_submitter:
            if oldestOPComment is None:
                oldestOPComment = comment
            elif oldestOPComment.created_utc > comment.created_utc:
                oldestOPComment = comment

    # Remove standard reply if it has no children
    deleteFlag = True
    comments = submission.comments.list()
    for comment in comments:
        if comment.parent_id == ("t1_" + reply.id):
            deleteFlag = False
            break

    if (deleteFlag) and (oldestOPComment is not None) and (not votingEligibility):
        reply.delete()
        logger.info(f"Deleted standard reply on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")

    # Message
    logger.info(f"Finished second review on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")

    # Increment review state
    sql.incrementReviewState(connection, submission.id)
    return True


def votingAction(submission: praw.models.Submission, connection: sqlite3.Connection, logger: logging.Logger):
    if submission is None:
        logger.debug("Submission is None. Ignoring.")
        return False

    if not sql.isVoteable(connection, submission.id):
        logger.error(f"Tried to do a voting action on a submission that was not voteable: {submission.title}")
        return False

    logger.debug(f"Doing voting action on: {submission.title}")

    # Lock the comment and strip table (voting is already disabled but it makes it obvious for users)
    commentID = sql.fetchCommentIDFromDB(connection, submission)
    comment = reddit.comment(id=commentID)

    commentBody = createBodyWithNewVotingTable(connection, submission, STANDARD_REPLY + VOTING_CLOSED_TEXT)
    comment.edit(commentBody)
    comment.mod.lock()

    # Get the votes
    votes = sql.fetchVotes(connection, submission.id)

    # Determine the result of the vote
    upvotes = submission.score
    threshold = math.floor(-1*(3.7272*(pow(math.e, (0.002*upvotes)))))
    # If the score is below threshold the post will be removed
    score = votes["Beginner"] - votes["Not Beginner"]
    removePost = score <= threshold

    logger.debug(f"Remove {submission.title} due to voting?: removePost = {removePost}")

    # Actions to take
    if removePost:
        #TODO add remove post functionality

        # Send mod mail
        try:
            if (submission.author is not None) and (submission.title is not None) and CREATE_MOD_MAIL:
                subject = "A post was voted to be removed"
                body = f"\"[{submission.title}]({submission.permalink})\" by u/{submission.author.name} " \
                       f"has been flagged for removal by community voting. \n\n" \
                       f"No action was taken because the bot is in trial mode. Manual intervention required. \n\n" \
                       f"Results = {str(votes)} \n\n" \
                       f"Threshold for removal = {threshold}"
                sql.insertBotMessageIntoDB(connection, subject, body)
                logger.debug(f"Inserted mod mail into the db for submission: {submission.title}")
        except Exception as e:
            logger.warning("Unable to send mod mail")
            logger.warning("Printing stack trace")
            logger.warning(e)
    else:
        # Actions of the post is not to be removed
        pass

    logger.info(f"VOTING: Did voting action on {submission.title} by u/{submission.author}")

    sql.incrementReviewState(connection, submission.id)

    return True


def review(submission: praw.models.Submission, logger: logging.Logger):
    connection = sql.createDBConnection(sql.DB_FILE)

    if firstReviewPass(submission, connection, logger):
        # Waiting for PASS_DELAY seconds allows the bot to pick up on double dippers if they post in other subreddits
        # after posting in beginner wood working. Also allows the standard reply to be removed to cut down on spam.
        time.sleep(PASS_DELAY)

        secondReviewPass(submission, connection, logger)


def main(logger: logging.Logger):
    while True:
        logger.debug("Starting submission stream.")
        try:
            for submission in subreddit.stream.submissions(skip_existing=True):
                if submission is None:
                    logger.debug("Submission is None. Ignoring.")
                    continue

                # skip self posts
                if submission.is_self:
                    logger.info(f"Skipping submission {submission.title}: submission is self.")
                    continue

                # Start a review of the post in it's own thread.
                logger.debug(f"Making thread for {submission.title}")
                thread = threading.Thread(target=review, args=[submission, logger])
                thread.start()
                logger.debug(f"made thread for {submission.title}")

        except ServerError as e:
            logger.error("Reddit server error. Restarting submission stream.")
            logger.error(e)
        except APIException as e:
            logger.error("APIException. Restarting submission stream.")
            logger.error(e)
        except Exception as e:
            # Log the error
            logger.error("Unable to handle a submission in the main thread for an unknown reason. "
                         "The program will continue but the submission will not be reviewed. "
                         "Printing stack trace.")
            logger.error(e)
            logger.error("Restarting submission stream")


def persistence(logger: logging.Logger):
    # Persistence does not handle messages sent during downtime
    connection = sql.createDBConnection(sql.DB_FILE)

    # Add posts that were created during downtime (up to PASS_DELAY seconds ago) to the SQL DB
    # Submissions that were made during the downtime will only get the second review pass.
    postIDList = sql.fetchAllPostIDsFromDB(connection)
    filterTime = time.time() - PASS_DELAY
    for submission in subreddit.stream.submissions(pause_after=0):
        # Exit when complete
        if submission is None:
            break

        # skip self posts
        if submission.is_self:
            continue

        # Add all posts made in the last PASS_DELAY seconds and not already in the database into the database
        # Changing the algorithm to add posts made before PASS_DELAY seconds is a bad idea
        if (submission.id not in postIDList) and (submission.created_utc > filterTime):
            logger.info(f"Missed during downtime: {submission.title} {submission.id}. Adding...")
            sql.insertSubmissionIntoDB(connection, submission, "", VOTING_OPTIONS,
                                       findVotingEligibility(submission, logger))

    while True:
        try:
            sql.removeExpiredPostsFromDB(connection)
            postIDList = sql.fetchUnreviewedPostsFromDB(connection)
            for postID in postIDList:
                submission = reddit.submission(postID)
                if submission is not None:
                    secondReviewPass(submission, connection, logger)
                time.sleep(5)  # Throttles the bot some to avoid hitting the rate limit

            time.sleep(300)  # No need to query the DB constantly doing persistence checks. 300s = 5m
        except Exception as e:
            logger.warning("The persistence thread raised an exception. It will try to continue.")
            logger.warning("Printing stack strace...")
            logger.warning(e)


# This does the actions after a vote finishes.
def voting(logger: logging.Logger):
    connection = sql.createDBConnection(sql.DB_FILE)

    time.sleep(30)  # staggers voting actions and persistence actions

    while True:
        try:
            postIDList = sql.fetchPostsNeedingVotingFromDB(connection)
            for postID in postIDList:
                try:
                    logger.debug(postID)
                    submission = reddit.submission(postID)
                    if submission is not None:
                        if sql.isVoteable(connection, submission.id):
                            votingAction(submission, connection, logger)
                        sql.removePostFromDB(connection, submission)
                    logger.debug(f"Processed voting on {submission}")
                    time.sleep(5)  # Throttles the bot some to avoid hitting the rate limit
                except Exception as innerException:
                    logger.warning(f"There was an issue processing voting for post {postID}")
                    logger.warning("The post was removed from the database and will not be processed")
                    logger.warning("Printing stack strace...")
                    logger.warning(innerException)

            time.sleep(300)  # No need to query the DB constantly doing voting. 300s = 5m
        except Exception as outerException:
            logger.warning("The voting thread raised an exception. It will try to continue.")
            logger.warning("Printing stack strace...")
            logger.warning(outerException)


def messagePasser(logger: logging.Logger):
    connection = sql.createDBConnection(sql.DB_FILE)

    while True:
        logger.debug("Starting inbox stream")
        try:
            for message in reddit.inbox.stream(skip_existing=True):
                # Skip replies of comments
                if message.was_comment:
                    continue
                logger.info(f"Got message \"{message.subject}\" from u/{message.author.name}")
                sql.insertUserMessageIntoDB(connection, message)

        except ServerError as e:
            logger.error("Reddit server error. Restarting message stream.")
            logger.error(e)
        except APIException as e:
            logger.error("APIException. Restarting message stream.")
            logger.error(e)
        except Exception as e:
            # Log the error
            logger.error("Unable to handle a message in the inbox stream an unknown reason. "
                         "The program will continue but the message will not be sent. "
                         "Printing stack trace.")
            logger.error(e)
            logger.error("Restarting message stream")


def commentStream(logger: logging.Logger):
    connection = sql.createDBConnection(sql.DB_FILE)

    while True:
        logger.debug("Starting comment stream.")
        try:
            for comment in subreddit.stream.comments(skip_existing=True):
                if (comment is None) or (comment.submission is None):
                    logger.debug("Comment or comment's submission is None - ignoring")
                    continue

                submissionID = comment.submission.id

                # Check if the comment is a reply to the bot, the comment is a command, that voting has not ended, and
                # that the submission is voteable
                parentID: str = comment.parent_id

                # TODO find a better way to accommodate mobile users and autocorrect
                # and (comment.body.lower().startswith(COMMAND_PREFIX)) \
                if (not parentID.startswith("t3_")) \
                    and (reddit.comment(id=parentID.split("_")[-1]).author == BOT_USERNAME) \
                    and (comment.submission.created_utc + VOTE_ACTION_DELAY > time.time()) \
                    and (sql.isVoteable(connection, comment.submission.id)):

                    # Ensure the person is not voting twice
                    if comment.author.name in sql.fetchVoters(connection, submissionID):
                        comment.mod.remove()
                        logger.info(f"{comment.author.name} attempted to double vote")
                        continue

                    # Strip command prefix and whitespace then convert to lower case
                    command = comment.body.replace(COMMAND_PREFIX, "").strip().lower()

                    logger.debug(f"An attempt to vote: \"{command}\" is being made")
                    # Only count the vote if it was actually for one of the votingOptions (ignore junk)
                    if command in VOTING_COMMANDS:
                        # Get the votes from the database: dict[str, int]
                        votes = sql.fetchVotes(connection, submissionID)
                        logger.debug(f"Votes: {votes}")

                        # Make sure the flair we're voting for exists
                        try:
                            votedOption = VOTING_DICTIONARY[command]
                            votes[votedOption] = votes[votedOption] + 1

                            # Cast vote
                            logger.debug(f"Votes about to be written to db after voting: {votes}")
                            sql.updateVotes(connection, submissionID, list(votes.values()))

                            # Update voters
                            voters = sql.fetchVoters(connection, submissionID)
                            voters.append(comment.author.name)
                            logger.info(f"{comment.author.name} voted for {votedOption} in {comment.submission.name}"
                                        f"by typing {comment.body}")
                            sql.updateVoters(connection, submissionID, voters)

                            # Update voting table in the bot comment
                            botComment = reddit.comment(id=comment.parent_id.split("_")[-1])
                            botCommentBody = createBodyWithNewVotingTable(connection, comment.submission,
                                                                          botComment.body)
                            botComment.edit(botCommentBody)

                        except KeyError as e:
                            logger.warning(f"Attempted to cast a vote for an unrecognized options.")
                            logger.warning(f"Command was = {command}")
                            logger.warning(f"Available flairs were: {votes.keys()}")
                            logger.warning(f"Printing stack stace")
                            logger.warning(e)
                            continue

                    # Everything's done so delete the comment to avoid clutter
                    comment.mod.remove()
                    logger.debug(f"Removed vote comment: {comment.body}")
                else:
                    logger.debug(f"Did not vote on comment: {comment.body }")

        except ServerError as e:
            logger.error("Reddit server error. Restarting comment stream.")
            logger.error(e)
        except APIException as e:
            logger.error("APIException. Restarting comment stream.")
            logger.error(e)
        except Exception as e:
            # Log the error
            logger.error("Unable to handle a comment in the comment stream for an unknown reason. "
                         "The program will continue but the comment will not be considered. "
                         "Printing stack trace.")
            logger.error(e)
            logger.error("Restarting comment stream")


# Setup logging
mainLogger = logging.getLogger(__name__)
mainLogger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(created)f : %(asctime)s : %(name)s : %(funcName)s : %(levelname)s :: %(message)s")

fileHandler = logging.FileHandler(LOG_FILE)
fileHandler.setLevel(LOGGING_LEVEL)
fileHandler.setFormatter(formatter)

streamHandler = logging.StreamHandler()
streamHandler.setFormatter(formatter)

mainLogger.addHandler(fileHandler)
mainLogger.addHandler(streamHandler)

if __name__ == "__main__":

    # Setup reddit
    reddit = praw.Reddit(PRAW_INI_SITE, user_agent=USER_AGENT)
    reddit.validate_on_submit = True
    subreddit = reddit.subreddit(SUBREDDIT)
    sql.createTables()

    time.sleep(2)  # Hacky way of making sure the tables have had time to be created

    # Start threads
    mainThread = threading.Thread(target=main, args=[mainLogger])
    persistenceThread = threading.Thread(target=persistence, args=[mainLogger])
    messagePasserThread = threading.Thread(target=messagePasser, args=[mainLogger])
    notifierThread = threading.Thread(target=notifier.notifier, args=[mainLogger])
    commentThread = threading.Thread(target=commentStream, args=[mainLogger])
    votingThread = threading.Thread(target=voting, args=[mainLogger])


    mainThread.start()
    persistenceThread.start()
    messagePasserThread.start()
    notifierThread.start()
    commentThread.start()
    votingThread.start()

    mainLogger.info("Started bot")
