import os
import sqlite3
import threading
import time
import logging

import sql
import notifier

import praw

# Reply for encouraging discussion - placed on every image post
STANDARD_REPLY = "Thank you for posting to r/BeginnerWoodWorking! If you have submitted a finished build we'd like to" \
                 " encourage you to share more details about it. Sharing progress photos, lessons learned, tips, " \
                 "and construction details helps others to learn. You can find our [posting guidelines here](" \
                 "https://www.reddit.com/r/BeginnerWoodWorking/wiki/posting_guidelines). \n\n This response has been " \
                 "made automatically by a bot. "

# Reply when the user has cross posted / doubled dipped - the post concerned will be removed
DOUBLE_DIPPING_REPLY = "Your submission to r/BeginnerWoodWorking has been removed. As per [rule #4](" \
                       "https://www.reddit.com/r/BeginnerWoodWorking/about/rules/), images and links posted in this " \
                       "subreddit cannot also be posted in other subreddits. \n\n This action has been performed " \
                       "automatically by a bot. If you believe that your post has been removed in error then please [" \
                       "message the moderators](https://www.reddit.com/message/compose?to=%2Fr%2FBeginnerWoodWorking). "

# How long to wait in seconds before checking the post again to delete the standard reply and/ or to remove the
# submission for double dipping (900s = 15m)
PASS_DELAY = 900

# If the bot should create a mod mail when it removes a post.
# If set to true and the bot is a moderator it will spam the mod discussions which cannot be archived (annoying)
# Tabs can be kept on the bot by looking in the moderation log
CREATE_MOD_MAIL = False

# User agent to connect to Reddit
USER_AGENT = "BeginnerWoodworkBot by u/-CrashDive-"

# Site in praw.ini with bot credentials
PRAW_INI_SITE = "bot"

# Bot username
BOT_USERNAME = "BeginnerWoodworkBot"

# Subreddit for the bot to operate on
SUBREDDIT = "BeginnerWoodWorking"

# Flair text for links the standard reply should not be given on
NO_REPLY_FLAIR_TEXT = "Discussion/Question"

# Location of the log file
LOG_FILE = "bot.log"

# Level of detail for the logger
LOGGING_LEVEL = logging.DEBUG


def isDoubleDipping(submission: praw.models.Submission):
    if not submission.is_self:
        duplicates = submission.duplicates()
        for duplicate in duplicates:
            # This is pretty loose criteria. It intentionally does not check for reposts of other users links.
            # It also excludes posts made in SUBREDDIT
            if (duplicate.author == submission.author) and (duplicate.subreddit.id != subreddit.id):
                return True

    return False


def isAQuestion(submission: praw.models.Submission):

    flairText = submission.link_flair_text
    if submission.link_flair_text is None:
        flairText = ""

    if "?" in submission.title:
        return True

    elif NO_REPLY_FLAIR_TEXT in flairText:
        return True

    return False


def removeDoubleDippers(connection: sqlite3.Connection, submission: praw.models.Submission, logger: logging.Logger):
    reply = submission.reply(DOUBLE_DIPPING_REPLY)
    reply.mod.distinguish(how="yes", sticky=True)

    logger.info(f"=== Removed post by u/{submission.author}: \"{submission.title}\" for double dipping. "
                f"ID = {submission.id}")

    if submission.author is not None and submission.title is not None and CREATE_MOD_MAIL:
        subject = "Removed double dipping post (Rule #4)"
        body = f"Automatically removed post \"{submission.title}\" by u/{submission.author.name} for rule #4 violation."
        sql.insertBotMessageIntoDB(connection, subject, body)
        logger.debug(f"Inserted mod mail into the db for submission: {submission.title}")
    submission.mod.remove()


def firstReviewPass(submission: praw.models.Submission, connection: sqlite3.Connection, logger: logging.Logger):
    if submission is None:
        logger.debug("Submission is None. Ignoring.")
        return False

    logger.info(f"Working on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")

    # Give standard reply for posts that aren't questions
    if isAQuestion(submission):
        logger.info(f"Gave no reply to \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")
        return False

    # Check for double dipping (first pass)
    if isDoubleDipping(submission):
        removeDoubleDippers(connection, submission, logger)
        return False

    # Actions to perform if the post is not double dipping and is not a question
    logger.info(f"Gave standard reply to \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")
    reply = submission.reply(STANDARD_REPLY)
    reply.mod.distinguish(how="yes", sticky=True)
    reply.downvote()
    sql.insertSubmissionIntoDB(connection, submission, reply)
    return True


def secondReviewPass(submission: praw.models.Submission, connection: sqlite3.Connection, logger: logging.Logger):
    if submission is None:
        logger.debug("Submission is None. Ignoring.")
        return

    # Check for double dipping and remove submission if needed
    if isDoubleDipping(submission):
        removeDoubleDippers(connection, submission, logger)
        # Remove post from SQL DB
        sql.removePostFromDB(connection, submission)
        return

    # Fetch the replyID from database
    replyID = sql.fetchCommentIDFromDB(connection, submission)

    # Return if there is no reply
    if replyID is None or replyID == "":
        return

    # Un-sticky standard reply
    logger.info(f"Un-stickied standard reply on \"{submission.title}\" by u/{submission.author}")
    reply = reddit.comment(replyID)
    reply.mod.undistinguish()
    reply.mod.distinguish(how="yes", sticky=False)

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

    if deleteFlag and oldestOPComment is not None:
        reply.delete()
        logger.info(f"Deleted standard reply on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")

    # Remove post from SQL DB
    sql.removePostFromDB(connection, submission)

    # Message
    logger.info(f"Finished review on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")


def review(submission: praw.models.Submission, logger: logging.Logger):
    connection = sql.createDBConnection(sql.DB_FILE)

    if firstReviewPass(submission, connection, logger):

        # Waiting for PASS_DELAY seconds allows the bot to pick up on double dippers if they post in other subreddits
        # after posting in beginner wood working. Also allows the standard reply to be removed to cut down on spam.
        time.sleep(PASS_DELAY)

        secondReviewPass(submission, connection, logger)


def main(logger: logging.Logger):
    logger.debug("Entered main()")
    for submission in subreddit.stream.submissions(skip_existing=True):
        logger.debug("Top of main loop")
        try:
            if submission is None:
                logger.debug("Submission is None. Ignoring.")
                continue

            # skip self posts
            if submission.is_self:
                logger.info(f"Skipping submission {submission.title}: submission is self.")
                continue

            # Start a review of the post in it's own thread.
            thread = threading.Thread(target=review, args=[submission])
            thread.start()

        except Exception as mainException:
            # Log the error
            logger.error("Unable to handle a submission in the main thread. "
                         "The program will continue but the submission will not be reviewed. "
                         "Printing stack trace and sending notification.")
            logger.error(mainException)

            # Send a mod mail
            try:
                if CREATE_MOD_MAIL:
                    connection = sql.createDBConnection(sql.DB_FILE)
                    subject = "Bot error. Bot was unable to handle a submission."
                    body = f"Unable to handle {submission.id}:{submission.title}.The bot will continue to function."
                    sql.insertBotMessageIntoDB(connection, subject, body)
                    logger.debug(f"Inserted mod mail into the db for submission: {submission.title}")
            except Exception as mailException:
                logger.error("Was unable to send mod mail about unreviewed post. Printing stack stace.")
                logger.error(mailException)

    # Actions to perform if main loop ever exits
    logger.critical("The main loop has exited. The bot will no longer function. Sending notification")
    try:
        if CREATE_MOD_MAIL:
            connection = sql.createDBConnection(sql.DB_FILE)
            subject = "Critical bot error. Bot needs to be restarted"
            body = f"The main loop was exited. Check {LOG_FILE} for details."
            sql.insertBotMessageIntoDB(connection, subject, body)
            logger.debug(f"Inserted mod mail into the db for main loop exit")
    except Exception as mailException:
        logger.error("Was unable to send mod mail about unreviewed post. Printing stack stace.")
        logger.error(mailException)

    # Exit
    os._exit(1)


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
            sql.insertSubmissionIntoDB(connection, submission, "")
    
    while True:
        sql.removeExpiredPostsFromDB(connection)
        postIDList = sql.fetchUnreviewedPostsFromDB(connection)
        for postID in postIDList:
            submission = reddit.submission(postID)
            if submission is not None:
                secondReviewPass(submission, connection, logger)
            time.sleep(5)  # Throttles the bot some to avoid hitting the rate limit

        time.sleep(300)  # No need to query the DB constantly doing persistence checks. 300s = 5m


def messagePasser(logger: logging.Logger):
    connection = sql.createDBConnection(sql.DB_FILE)
    for message in reddit.inbox.stream(skip_existing=True):
        # Skip replies of comments
        if message.was_comment:
            continue
        logger.info(f"Got message \"{message.subject}\" from u/{message.author.name}")
        sql.insertUserMessageIntoDB(connection, message)


if __name__ == "__main__":
    # Setup logging
    mainLogger = logging.getLogger(__name__)
    mainLogger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(created)f:%(name)s:%(message)s")

    fileHandler = logging.FileHandler(LOG_FILE)
    fileHandler.setLevel(LOGGING_LEVEL)
    fileHandler.setFormatter(formatter)

    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)

    mainLogger.addHandler(fileHandler)
    mainLogger.addHandler(streamHandler)

    # Setup reddit
    reddit = praw.Reddit(PRAW_INI_SITE, user_agent=USER_AGENT)
    subreddit = reddit.subreddit(SUBREDDIT)
    sql.createTables()

    time.sleep(1)  # Hacky way of making sure the tables have had time to be created

    # Start threads
    mainThread = threading.Thread(target=main, args=[mainLogger])
    persistenceThread = threading.Thread(target=persistence, args=[mainLogger])
    messagePasserThread = threading.Thread(target=messagePasser, args=[mainLogger])
    notifierThread = threading.Thread(target=notifier.notifier)

    mainThread.start()
    persistenceThread.start()
    messagePasserThread.start()
    notifierThread.start()

    mainLogger.info("Started bot")
