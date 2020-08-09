import time

import sql
import main

import praw

# Site in praw.ini with notifier bot credentials
NOTIFIER_PRAW_INI_SITE = "notifierBot"

# User agent for notifier bot
NOTIFIER_USER_AGENT = "B-W-Notifier-Bot by u/-CrashDive-"

def notifier():

    connection = sql.createDBConnection(sql.DB_FILE)
    reddit = praw.Reddit(NOTIFIER_PRAW_INI_SITE, user_agent=NOTIFIER_USER_AGENT)
    subreddit = reddit.subreddit(main.SUBREDDIT)

    while True:
        # Tuple structure: [0] MessageID , [1] Subject, [2] Body, [3] Sender, [4] IsUserMessage, [5] MessageTime
        messageTupleList = sql.fetchAllMessagesFromDB(connection)
        for messageTuple in messageTupleList:
            if messageTuple[4] == 0:  # IsUserMessage == False
                subreddit.message(messageTuple[1], messageTuple[2])
                print(f"Sent modmail \"{messageTuple[1]}\" from mod bot")
                print("\n")
            else:
                subject = f"{messageTuple[1]} from u/{messageTuple[3]}"
                body = f"{messageTuple[2]} \n\nThe above message was sent to BeginnerWoodworkBot by u/{messageTuple[3]}"
                subreddit.message(subject, body)
                print(f"sent modmail \"{messageTuple[1]}\" from u/{messageTuple[3]}")
                print("\n")
            sql.removeMessageByIDFromDB(connection, messageTuple[0])

            time.sleep(60)
