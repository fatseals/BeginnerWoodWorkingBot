import threading
import time as t

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
PASS_DELAY = 600


def isDoubleDipping(submission):
    poster = submission.author
    # Check the posters submissions in all subreddits
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
    print(f"Removed post by u/{submission.author}: \"{submission.name}\" for double dipping")
    submission.subreddit.message(f"Removed post by u/{submission.author}: \"{submission.name}\"" \ 
                                 f"for double dipping \n\n Permalink: {submission.permalink}")
    submission.mod.remove()


# The main actions of the bot are performed here.
def review(submission):
    print(f"Working on \"{submission.title}\" by u/{submission.author}")

    # Check for double dipping (first pass)
    if isDoubleDipping(submission):
        removeDoubleDippers(submission)
        return

    # Give standard reply and save the ID of the reply
    else:
        reply = submission.reply(STANDARD_REPLY)
        reply.mod.distinguish(how="yes", sticky=True)

    # Waiting for PASS_DELAY seconds allows the bot to pick up on double dippers if they post in other subreddits after
    # posting in beginner wood working. Also allows the standard reply to be removed to cut down on spam.
    t.sleep(PASS_DELAY)

    # Check for double dipping (second pass)
    if isDoubleDipping(submission):
        removeDoubleDippers(submission)
        return

    # Unsticky standard reply
    reply.mod.undistinguish()
    reply.mod.distinguish(how="yes", sticky=False)

    # Assumes the oldest top level comment by the poster is the writeup
    # If the writeup exists, the standard reply should be deleted (assuming it has no children)
    oldestOPComment = None

    topComments = submission.comments.replace_more(limit=0)
    # iterates through top level comments and finds the oldest one by the poster
    for comment in topComments:
        if comment.is_sunmitter:
            if oldestOPComment == None:
                oldestOPComment = comment
            elif oldestOPComment.created_utc > comment:
                oldestOPComment = comment

    # Remove standard reply if it has no children
    deleteFlag = True
    comments = submission.comments.replace_more(limit=None)
    for comment in comments:
        if comment.parent_id == reply.id:
            deleteFlag = False
            break

    if deleteFlag and oldestOPComment != None:
        reply.delete()

    print(f"Finished review on \"{submission.title}\" by u/{submission.author}")
    print(f"oldestOPComment = {oldestOPComment}")
    print(f"deleteFlag = {deleteFlag}")


if __name__ == '__main__':
    reddit = praw.Reddit("bot", user_agent="BWoodworkingBotTest by u/-CrashDive-")

    subreddit = reddit.subreddit("CrashDiveTesting")

    for submission in subreddit.stream.submissions(skip_existing=True):
        thread = threading.Thread(target=review, args=[submission])
        thread.start()
