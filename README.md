# get-tweets
Get all of a user's tweets without an API key or doing any web scraping.  This script uses web requests to get all of a user's tweets as if you were an unauthenticated user.

Data you get:
* All of a user's tweets including retweets and replies
* id
* text
* created_at
* retweet_count
* favorite_count
* reply_count
* quote_count
* retweeted
* is_quote_status
* possibly_sensitive

Requirements are:
* requests - To make the http requests to get the tweet data


# Usage

1. clone the repo
2. pip install -r requirements.txt
3. python get-tweets username --output name_of_file.csv



