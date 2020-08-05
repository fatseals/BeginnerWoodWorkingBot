import threading
import time as t

import sql
import praw

# Reply for encouraging discussion - placed on every image post
STANDARD_REPLY = "Thank you for posting to r/BeginnerWoodWorking! As a community for beginners, we encourage users to" \
                 " share details and knowledge about the posts they submit. Sharing lessons learned, in-progress " \
                 "photos, and other information help others to learn. We also encourage users to ask questions about " \
                 "the posts they see. \n\n This is an automated response created by a bot. "

# Reply when the user has cross posted / doubled dipped - the post concerned will be removed
DOUBLE_DIPPING_REPLY = "Your submission to r/BeginnerWoodWorking has been removed. Unfortunately, we do not allow " \
                       "image content posted in this subreddit to be posted in other subreddits or vice versa. This " \
                       "reduces karma farming in a subreddit that is focused on learning. \n\n This process has been " \
                       "performed automatically by a bot. If you believe that your post has been removed in error, then" \
                       " please [message the moderators](" \
                       "https://www.reddit.com/message/compose?to=%2Fr%2FBeginnerWoodWorking). "

# How long to wait in seconds before checking the post again to delete the standard reply and/ or to remove the
# submission for double dipping (900s = 15m)
PASS_DELAY = 30

# If the bot should create a mod mail when it removes a post.
# If set to true and the bot is a moderator it will spam the mod discussions which cannot be archived (annoying)
# Tabs can be kept on the bot by looking in the moderation log
CREATE_MOD_MAIL = False

# User agent to connect to Reddit
USER_AGENT = "BWoodworkingBotTest by u/-CrashDive-"

# Site in praw.ini with bot credentials
PRAW_INI_SITE = "bot"

# Subreddits for the bot to operate on
SUBREDDITS = "CrashDiveTesting"

def isDoubleDipping(submission):
    poster = submission.author
    if poster == None:
        return True
    for posterSubmisionElsewhere in poster.submissions.new():
        # Check if it is an image post
        if not posterSubmisionElsewhere.is_self and (posterSubmisionElsewhere.id != submission.id):
            # Check if the title or URL is the same as the submission in question. If so, that is not allowed and the
            # post should be removed
            if (posterSubmisionElsewhere.title == submission.title) or (posterSubmisionElsewhere.url == submission.url):
                return True
    return False


def removeDoubleDippers(submission):
    reply = submission.reply(DOUBLE_DIPPING_REPLY)
    reply.mod.distinguish(how="yes", sticky=True)
    print(f"Removed post by u/{submission.author}: \"{submission.title}\" for double dipping")
    if (submission.author != None) and (submission.title != None) and (CREATE_MOD_MAIL):
        submission.subreddit.message("Removed double dipper",
                                     f"Removed post by u/{submission.author}: \"{submission.title}\" "
                                     f"for double dipping \n\n Permalink: {submission.permalink}")
    submission.mod.remove()


def firstReviewPass(submission, connection):
    if submission == None:
        return

    print(f"Working on \"{submission.title}\" by u/{submission.author}")

    # Check for double dipping (first pass)
    if isDoubleDipping(submission):
        removeDoubleDippers(submission)
        return

    # Give standard reply and add post to SQL DB
    else:
        reply = submission.reply(STANDARD_REPLY)
        reply.mod.distinguish(how="yes", sticky=True)
        sql.insertPostIntoDB(connection, submission, reply)

def secondReviewPass(submission, connection):
    if submission == None:
        return


    if isDoubleDipping(submission):
        removeDoubleDippers(submission)
        # Remove post from SQL DB
        sql.removePostFromDB(connection, submission)
        return

    # Unsticky standard reply
    replyID = sql.fetchCommentIDFromDB(connection, submission)
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
            if oldestOPComment == None:
                oldestOPComment = comment
            elif oldestOPComment.created_utc > comment.created_utc:
                oldestOPComment = comment

    # Remove standard reply if it has no children
    deleteFlag = True

    comments = submission.comments.list()
    print(f"comments = {comments}")
    for comment in comments:
        if comment.parent_id == ("t1_" + reply.id):
            deleteFlag = False
            break

    printFlag = False
    if deleteFlag and oldestOPComment != None:
        reply.delete()
        printFlag = True


    #Remove post from SQL DB
    sql.removePostFromDB(connection, submission)

    print(f"Finished review on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")


def review(submission):
    connection = sql.createDBConnection(sql.DB_FILE)

    firstReviewPass(submission, connection)

    # Waiting for PASS_DELAY seconds allows the bot to pick up on double dippers if they post in other subreddits after
    # posting in beginner wood working. Also allows the standard reply to be removed to cut down on spam.
    t.sleep(PASS_DELAY)

    secondReviewPass(submission, connection)


def main():
    for submission in subreddit.stream.submissions(skip_existing=True):
        thread = threading.Thread(target=review, args=[submission])
        thread.start()


def persistence():
    connection = sql.createDBConnection(sql.DB_FILE)
    while True:
        sql.removeExpiredPostsFromDB(connection)
        postIDList = sql.fetchUnreviewedPostsFromDB(connection)
        for postID in postIDList:
            submission = reddit.submission(postID)
            if submission != None:
                secondReviewPass(submission, connection)
            t.sleep(5) # Throttles the bot some to avoid hitting the rate limit
        t.sleep(300) # No need to query the DB constantly doing persistence checks


if __name__ == "__main__":

    # Setup
    reddit = praw.Reddit(PRAW_INI_SITE, user_agent=USER_AGENT)
    subreddit = reddit.subreddit(SUBREDDITS)
    sql.createTable()

    # Add posts that were created during downtime (up to PASS_DELAY seconds ago) to the SQL DB
    # TODO

    # Start threads
    mainThread = threading.Thread(target=main)
    persistenceThread = threading.Thread(target=persistence)
    mainThread.start()
    persistenceThread.start()

    print("Started bot")



