import math
import time as t
from datetime import timedelta, datetime

from redis import Redis
from rq import Queue
import praw

import jobs
import os

# Reply for encouraging disccusion - placed on every image post
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


def main():
    # Make the job queue
    redis_conn = Redis()
    q = Queue(connection=redis_conn)

    print("Started BWoodworkingBotTest")

    #A rq worker must be available for every job that is queued
    for submission in subreddit.stream.submissions(skip_existing=True):

        q.enqueue(jobs.review, submission, job_timeout=(PASS_DELAY + 60))
        print(f"{datetime.now()}: Working on \"{submission.title}\" by u/{submission.author}")

        # passes bash command to terminal creating a burst worker - super hacky
        # if you need the logs form the workers then direct the hup log to not /dev/null
        os.system("nohup rq worker --burst >/dev/null &")


if __name__ == "__main__":
    # Login ot reddit and configure
    # Credentials in praw.ini
    reddit = praw.Reddit("bot", user_agent="BWoodworkingBotTest by u/-CrashDive-")

    subreddit = reddit.subreddit("CrashDiveTesting")

    main()
