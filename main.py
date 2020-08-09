import threading
import time as t

import sql
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

# Subreddit for the bot to operate on
SUBREDDIT = "BeginnerWoodWorking"

# Flair text for links the standard reply should not be given on
NO_REPLY_FLAIR_TEXT = "Discussion/Question ⁉️"

def isDoubleDipping(submission):
    if not submission.is_self:
        duplicates = submission.duplicates()
        for duplicate in duplicates:
            # This is pretty loose criteria. It intentionally does not check for reposts of other users links.
            # It also excludes posts made in SUBREDDIT
            if (duplicate.author == submission.author) and (duplicate.subreddit.id != subreddit.id):
                return True

    return False


def removeDoubleDippers(submission):
    reply = submission.reply(DOUBLE_DIPPING_REPLY)
    reply.mod.distinguish(how="yes", sticky=True)

    print(f"=== Removed post by u/{submission.author}: \"{submission.title}\" for double dipping. ID = {submission.id}")
    print("\n")
    if submission.author is not None and submission.title is not None and CREATE_MOD_MAIL:
        pass
        submission.subreddit.message("Removed double dipper",
                                    f"Removed post by u/{submission.author}: \"{submission.title}\" "
                                    f"for double dipping \n\n . ID = {submission.id}")
    submission.mod.remove()


def firstReviewPass(submission, connection):
    if submission is None:
        return

    print(f"Working on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")
    print("\n")

    reply = None

    # Check for double dipping (first pass)
    if isDoubleDipping(submission):
        removeDoubleDippers(submission)

   # Skip standard relpy for posts flaired with NO_REPLY_FLAIR_TEXT
    elif submission.link_flair_text == NO_REPLY_FLAIR_TEXT:
        return

    else:
        print(f"Gave standard reply to \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")
        print("\n")
        reply = submission.reply(STANDARD_REPLY)
        reply.mod.distinguish(how="yes", sticky=True)

    sql.insertSubmissionIntoDB(connection, submission, reply)


def secondReviewPass(submission, connection):
    if submission is None:
        return

    # Check for double dipping and remove submission if needed
    if isDoubleDipping(submission):
        removeDoubleDippers(submission)
        # Remove post from SQL DB
        sql.removePostFromDB(connection, submission)
        return

    # Fetch the replyID from database
    replyID = sql.fetchCommentIDFromDB(connection, submission)

    # Return if there is no reply
    if replyID is None or replyID == "":
        return

    # Un-sticky standard reply
    print(f"Unstickied standard reply on \"{submission.title}\" by u/{submission.author}")
    print("\n")
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
        print(f"Deleted standard reply on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")
        print("\n")

    # Remove post from SQL DB
    sql.removePostFromDB(connection, submission)

    # Message
    print(f"Finished review on \"{submission.title}\" by u/{submission.author}. ID = {submission.id}")
    print("\n")


def review(submission):
    connection = sql.createDBConnection(sql.DB_FILE)

    firstReviewPass(submission, connection)

    # Waiting for PASS_DELAY seconds allows the bot to pick up on double dippers if they post in other subreddits after
    # posting in beginner wood working. Also allows the standard reply to be removed to cut down on spam.
    t.sleep(PASS_DELAY)

    secondReviewPass(submission, connection)


def main():
    for submission in subreddit.stream.submissions(skip_existing=True):
        if submission is None:
            continue

        # skip self posts
        if submission.is_self:
            continue
        thread = threading.Thread(target=review, args=[submission])
        thread.start()


def persistence():
    connection = sql.createDBConnection(sql.DB_FILE)
    while True:
        sql.removeExpiredPostsFromDB(connection)
        postIDList = sql.fetchUnreviewedPostsFromDB(connection)
        for postID in postIDList:
            submission = reddit.submission(postID)
            if submission is not None:
                secondReviewPass(submission, connection)
            t.sleep(5)  # Throttles the bot some to avoid hitting the rate limit

        t.sleep(300)  # No need to query the DB constantly doing persistence checks. 300s = 5m


if __name__ == "__main__":
    # Setup
    reddit = praw.Reddit(PRAW_INI_SITE, user_agent=USER_AGENT)
    subreddit = reddit.subreddit(SUBREDDIT)
    sql.createTable()

    # Add posts that were created during downtime (up to PASS_DELAY seconds ago) to the SQL DB
    # Submissions that were made during the downtime will only get the second review pass.
    connection = sql.createDBConnection(sql.DB_FILE)
    postIDs = sql.fetchAllPostIDsFromDB(connection)
    filterTime = t.time() - PASS_DELAY
    for possibleMissedSubmission in subreddit.stream.submissions(pause_after=0):
        # Exit when complete
        if possibleMissedSubmission is None:
            break

        # skip self posts
        if possibleMissedSubmission.is_self:
            continue

        # Add all posts made in the last PASS_DELAY seconds and not already in the database into the database
        # Changing the algorithm to add posts made before PASS_DELAY seconds is a bad idea
        if (not possibleMissedSubmission.id in postIDs) and (possibleMissedSubmission.created_utc > filterTime):
            print(f"Missed during downtime: {possibleMissedSubmission.title} {possibleMissedSubmission.id}. Adding...")
            print("\n")
            sql.insertSubmissionIntoDB(connection, possibleMissedSubmission, None)

    connection.close()

    # Start threads
    mainThread = threading.Thread(target=main)
    persistenceThread = threading.Thread(target=persistence)
    mainThread.start()
    persistenceThread.start()

    print("Started bot")
    print("\n")
