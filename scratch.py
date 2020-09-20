for template in subreddit.flair.link_templates:
    if template["type"] == "text":  # Bullshit magic strings -> gets the text of the flair which is the useful bit
        flairs.append(template["text"])
