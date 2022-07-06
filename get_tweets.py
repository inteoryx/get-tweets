import requests
import re
import csv
import sys
import json
import argparse
from time import sleep

GUEST_TOKEN_ENDPOINT = "https://api.twitter.com/1.1/guest/activate.json"
STATUS_ENDPOINT = "https://twitter.com/i/api/graphql/"

CURSOR_PATTERN = re.compile('TimelineCursor","value":"([^\"]+)"[^\}]+Bottom"')
ID_PATTERN = re.compile('"rest_id":"([^"]+)"')
COUNT_PATTERN = re.compile('"statuses_count":([0-9]+)')

variables = {
    "count": 200,
    "withTweetQuoteCount": True,
    "includePromotedContent": True,
    "withQuickPromoteEligibilityTweetFields": False,
    "withSuperFollowsUserFields": True,
    "withUserResults": True,
    "withBirdwatchPivots": False,
    "withDownvotePerspective": False,
    "withReactionsMetadata": False,
    "withReactionsPerspective": False,
    "withSuperFollowsTweetFields": True,
    "withVoice": True,
    "withV2Timeline": False,
}

features = {
    "standardized_nudges_misinfo": True, "dont_mention_me_view_api_enabled": True, "responsive_web_edit_tweet_api_enabled": True, "interactive_text_enabled": True, "responsive_web_enhance_cards_enabled": True, "responsive_web_uc_gql_enabled": True, "vibe_tweet_context_enabled": True,
}

def send_request(url, session_method, headers, params=None):
    if params:
        response = session_method(url, headers=headers, stream=True, params={
                                  "variables": json.dumps(params),
                                  "features": json.dumps(features)
                            })
    else:
        response = session_method(url, headers=headers, stream=True)

    if response.status_code != 200:
        print(response.request.url)
        print(response.status_code)

    assert response.status_code == 200, f"Failed request to {url}.  {response.status_code}.  Please submit an issue including this information. {response.text}"
    result = [line.decode("utf-8") for line in response.iter_lines()]
    return "".join(result)


def search_json(j, target_key, result):
    if type(j) == dict:
        for key in j:
            if key == target_key:
                result.append(j[key])

            search_json(j[key], target_key, result)
        return result

    if type(j) == list:
        for item in j:
            search_json(item, target_key, result)

        return result

    return result


def tweet_subset(d):
    return {
        "id": d["id_str"],
        "text": d["full_text"],
        "created_at": d["created_at"],
        "retweet_count": d["retweet_count"],
        "favorite_count": d["favorite_count"],
        "reply_count": d["reply_count"],
        "quote_count": d["quote_count"],
        "retweeted": d["retweeted"],
        "is_quote_status": d["is_quote_status"],
        "possibly_sensitive": d.get("possibly_sensitive", "No data"),
    }


def get_tweets(query_id, session, headers, variables, expected_total):
    resp = send_request(
        f"{STATUS_ENDPOINT}{query_id}/UserTweetsAndReplies", session.get, headers, variables)
    j = json.loads(resp)
    all_tweets = search_json(j, "legacy", [])

    all_tweets = [tweet for tweet in all_tweets if "id_str" in tweet]
    ids = {tweet["id_str"] for tweet in all_tweets}

    while True:
        cursor = CURSOR_PATTERN.findall(resp)[0]
        variables["cursor"] = cursor
        resp = send_request(
            f"{STATUS_ENDPOINT}{query_id}/UserTweetsAndReplies", session.get, headers, variables)
        j = json.loads(resp)

        next_tweets = search_json(j, "legacy", [])
        next_tweets = [tweet for tweet in next_tweets if "id_str" in tweet]
        next_ids = {tweet["id_str"] for tweet in next_tweets}

        old_id_size = len(ids)
        ids.update(next_ids)
        if old_id_size == len(ids):
            break

        all_tweets.extend(next_tweets)
        if args.output:
            print(f"{len(all_tweets)} / {expected_total}", end="\r")

    all_tweets = [tweet for tweet in all_tweets if "full_text" in tweet and tweet.get(
        "user_id_str", "") == variables["userId"]]
    return all_tweets


def get_id_and_tweet_count(session, headers, query_id, username):
    resp = send_request(
        f"{STATUS_ENDPOINT}{query_id}/UserByScreenName",
        session.get,
        headers,
        params={
            "screen_name": username,
            "withSafetyModeUserFields": True,
            "withSuperFollowsUserFields": True
        }
    )

    ids = ID_PATTERN.findall(resp)
    assert len(
        ids) == 1, f"Failed to find user id for {username}.  Please open this as an issue including this message."

    counts = COUNT_PATTERN.findall(resp)
    assert len(
        counts) == 1, f"Failed to find tweet count for {username}.  Please open this as an issue including this message."

    return ids[0], int(counts[0])

def user_tweets(username):
    print(f"Getting Tweets for {username}")
    session = requests.Session()
    headers = {}

    # One of the js files from original url holds the bearer token and query id.
    container = send_request(
        f"https://twitter.com/{username}", session.get, headers
    )
    js_files = re.findall("src=['\"]([^'\"()]*js)['\"]", container)

    bearer_token = None
    query_id = None
    user_query_id = None

    # Search the javascript files for a bearer token and UserTweets queryId
    for f in js_files:
        file_content = send_request(f, session.get, headers)
        bt = re.search(
            '["\'](AAA[a-zA-Z0-9%-]+%[a-zA-Z0-9%-]+)["\']', file_content)

        ops = re.findall(
            '\{queryId:"[a-zA-Z0-9_]+[^\}]+UserTweetsAndReplies"', file_content)
        query_op = [op for op in ops if "UserTweetsAndReplies" in op]

        if len(query_op) == 1:
            query_id = re.findall('queryId:"([^"]+)"', query_op[0])[0]

        if bt:
            bearer_token = bt.group(1)

        ops = re.findall(
            '\{queryId:"[a-zA-Z0-9_]+[^\}]+UserByScreenName"', file_content)
        user_query_op = [op for op in ops if "UserByScreenName" in op]

        if len(user_query_op) == 1:
            user_query_id = re.findall(
                'queryId:"([^"]+)"', user_query_op[0])[0]

    assert bearer_token, f"Did not find bearer token.  Are you sure you used the right username? {username}"
    assert query_id, f"Did not find query id.  Are you sure you used the right twitter username? {username}"
    assert user_query_id, f"Did not find user query id.  Are you sure you used the right twitter username? {username}"

    headers['authorization'] = f"Bearer {bearer_token}"

    guest_token_resp = send_request(
        GUEST_TOKEN_ENDPOINT, session.post, headers)
    guest_token = json.loads(guest_token_resp)['guest_token']
    assert guest_token, f"Did not find guest token.  Probably means the script is broken.  Please submit an issue.  Include this message in your issue: {username}"
    headers['x-guest-token'] = guest_token

    user_id, total_count = get_id_and_tweet_count(
        session, headers, user_query_id, username
    )

    session.close()

    variables["userId"] = user_id

    resp = get_tweets(query_id, session, headers, variables, total_count)
    all_tweets = [tweet_subset(tweet) for tweet in resp]

    for tweet in all_tweets:
        tweet["url"] = f"https://twitter.com/{username}/status/{tweet['id']}"
        tweet["username"] = username

    return all_tweets

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Get tweets for a user.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--username", 
        help="The username of the user to get tweets for.",
        required=False
    )
    group.add_argument(
        "--usersFile", 
        help="A file containing a list of usernames to get tweets for.",
        required=False
    )    
    parser.add_argument(
        "--output", help="The output file to write to.  If not specified, prints to stdout."
    )
    
    args = parser.parse_args()    

    usernames = []

    if args.username:
        usernames.append(args.username)

    if args.usersFile:
        with open(args.usersFile) as f:
            usernames.extend(f.read().splitlines())

    all_tweets = []
    for username in usernames:
        try:
            all_tweets.extend(user_tweets(username))
            print("Sleeping 10s to avoid rate limit.")
            sleep(10)
        except Exception as e:
            print(f"Failed to get tweets for {username}")
            print(e)

    headers = all_tweets[0].keys()
    writer = csv.DictWriter(open(args.output, "w")
                            if args.output else sys.stdout, fieldnames=headers)
    writer.writeheader()
    writer.writerows(all_tweets)
