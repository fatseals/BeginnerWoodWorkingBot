import time as t
from _datetime import datetime

import main

def isDoubleDipping(submission):
    print("Checking double dipping on \"{submission.title}\" by u/{submission.author}")
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
    reply = submission.reply(main.DOUBLE_DIPPING_REPLY)
    reply.mod.distinguish(how="yes", sticky=True)
    print(f"Removed post by u/{submission.author}: \"{submission.name}\" for double dipping")
    # TODO send a mod mail to inform of action
    submission.mod.remove()

#The main actions of the bot are performed here.
def review(submission):

    print(f"{datetime.now()}: Working on \"{submission.title}\" by u/{submission.author}")

    # Check for double dipping (first pass)
    if isDoubleDipping(submission):
        removeDoubleDippers(submission)
        return

    # Give standard reply and save the ID of the reply
    else:
        reply = submission.reply(main.STANDARD_REPLY)
        reply.mod.distinguish(how="yes", sticky=True)

    # Waiting for PASS_DELAY seconds allows the bot to pick up on double dippers if they post in other subreddits after
    # posting in beginner wood working. Also allows the standard reply to be removed to cut down on spam.
    t.sleep(main.PASS_DELAY)

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
    #iterates through top level comments and finds the oldest one by the poster
    for comment in topComments:
        if comment.is_sunmitter:
            if oldestOPComment == None:
                oldestOPComment = comment
            elif oldestOPComment.created_utc > comment:
                oldestOPComment = comment

    #Remove standard reply if it has no children
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





