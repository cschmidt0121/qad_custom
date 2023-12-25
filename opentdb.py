#!/usr/bin/env python3 
import requests
import sys
import time
import re
from unidecode import unidecode
import json
from urllib.parse import unquote

# Grab a ton of questions from openTDB
'''
Categories by ID:
9 - General Knowledge
10 - Entertainment: Books
11 - Entertainment: Film
12 - Entertainment: Music
13 - Entertainment: Musicals & Theatres
14 - Entertainment: Television
15 - Entertainment: Video Games
16 - Entertainment: Board Games
17 - Science & Nature
18 - Science: Computers
19 - Science: Mathematics
20 - Mythology
21 - Sports
22 - Geography
23 - History
24 - Politics
25 - Art
26 - Celebrities
27 - Animals
28 - Vehicles
29 - Entertainment: Comics
30 - Science: Gadgets
31 - Entertainment: Japanese Anime & Manga
32 - Entertainment: Cartoon & Animations
'''
SELECTED_CATEGORY_IDS = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 23, 23, 27]

def fix_str(s, question=False):
    """ Remove/replace non-ascii chars """
    s = unidecode(s)

    # Replace pairs of quotes with { } to italicize
    if question:
        while True:
            quotes = re.findall(r'(")', s)
            ticks = re.findall(r'(`)', s)
            if len(quotes) >= 2:
                index = s.index('"')
                s = s[0:index] + "{" + s[index+1:]
                index = s.index('"')
                s = s[0:index] + " }" + s[index + 1:]
            elif len(ticks) >= 2:
                index = s.index('`')
                s = s[0:index] + "{" + s[index+1:]
                index = s.index('`')
                s = s[0:index] + " }" + s[index + 1:]
            else:
                break
    return s


def main():
    print("Downloading questions")
    try:
        r = requests.get("https://opentdb.com/api_token.php?command=request")
    except requests.ConnectionError as e:
        print("Cannot connect to OpenTDB API. Wait a few moments and try again.")
        exit(1)
    session_token = r.json()["token"]

    questions = []
    for id in SELECTED_CATEGORY_IDS:
        for difficulty in ["medium", "easy"]:
            while True:
                params = {
                    "token": session_token,
                    "category": id,
                    "difficulty": difficulty,
                    "amount": 50,
                    "encode": "url3986",
                    "type": "multiple"
                }
                url = "https://opentdb.com/api.php"
                try:
                    r = requests.get(url, params=params)
                except requests.ConnectionError as e:
                    print(e)
                    print("Cannot connect to OpenTDB API. Retrying in 5 seconds.")
                    time.sleep(5)
                    continue
                j = r.json()
                if j["response_code"] in [1, 2, 3]:
                    sys.exit("Error from OpenTDB: %s" % j["response_message"])
                elif j["response_code"] == 4:
                    break
                # If a rate limit is reached, wait 5 seconds before the next request.
                elif j["response_code"] == 5:
                    print("API rate limit reached. Waiting 5 seconds.")
                    time.sleep(5)
                    continue
                for question in j["results"]:
                    category = unquote(question["category"])
                    # Category needs to be short
                    category = category.split(":")[-1].strip()
                    try:
                        text = fix_str(unquote(question["question"].strip()), question=True)
                    except Exception as e:
                        print(e)
                        print("Skipping question.")
                        continue
                    answers = [fix_str(unquote(question["correct_answer"]))]
                    for a in question["incorrect_answers"]:
                        answers.append(fix_str(unquote(a)))
                    question_dict = {
                        "category": category,
                        "question": text,
                        "answers": answers
                    }
                    questions.append(question_dict)
                print(f"{len(questions)} questions downloaded.")
                # As of December 2023, the OpenTDB API limits requests to 1 per IP every 5 seconds.
                time.sleep(7)

    with open("questions.json", "w") as f:
        questions_sorted = sorted(questions, key=lambda q: q['category'])
        json.dump(questions_sorted, f, indent=4)
    print(f"Wrote {len(questions)} to {'questions.json'}")

if __name__ == "__main__":
    main()
