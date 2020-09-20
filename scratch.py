for template in subreddit.flair.link_templates:
    if template["type"] == "text":  # Bullshit magic strings -> gets the text of the flair which is the useful bit
        flairs.append(template["text"])

USER_AGENT = "BeginnerWoodworkBot by u/-CrashDive-"
# USER_AGENT = "BeginnerWoodworkBotTesting by u/-CrashDive-"

# Site in praw.ini with bot credentials
PRAW_INI_SITE = "bot"

# Bot username
BOT_USERNAME = "BeginnerWoodworkBot"

# Subreddit for the bot to operate on
SUBREDDIT = "BeginnerWoodWorking"
