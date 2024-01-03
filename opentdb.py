#!/usr/bin/env python3
import requests
import sys
import time
import re
from unidecode import unidecode
import json
from urllib.parse import unquote
from typing import List

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
SELECTED_CATEGORY_IDS = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 23, 27]

# Request this many questions at a time. This can be set to a lower
# amount to reduce the chances that newer questions will be excluded,
# as the API will not return any questions if there are fewer questions
# left in a category than this amount, but the exact amount is not
# reliable. As a workaround, the script will retry twice if the API
# reports that all available questions have been exhausted before the
# amount reported was downloaded, with 1 fewer question each time.
# The OpenTDB API allows downloading up to 50 questions per request.
QUESTION_REQUEST_AMOUNT = 50

# The OpenTDB API limits requests to 1 per IP every 5 seconds.
# Set this delay (in seconds) longer if you get frequent API rate limit
# errors.
API_REQUEST_INTERVAL = 6

# Some questions in the OpenTDB dataset have accented letters and other
# characters that are not supported in the Quiz & Dragons font.
# Unidecode can process accented letters into unaccented letters, but
# this can cause some correct answers to appear incorrect, or vice
# versa.
# If these settings are True, these questions will be written to
# a file named questions_error.json to allow the user to correct them
# manually before inserting them into questions.json. This script does
# not validate the length of these strings, so any questions or answers
# that exceed the limits in Quiz & Dragons will still be rejected by
# build.py.
# PRINT_INVALID_QUESTIONS can be set to True if you want to see
# questions that get filtered during the download process.
FILTER_INVALID_CHARACTERS_IN_QUESTIONS = False
FILTER_INVALID_CHARACTERS_IN_ANSWERS = True
PRINT_INVALID_QUESTIONS = False

### No more configurable options after this point.


def check_text(text: str | List[str]) -> str:
    """Check the strings in the argument for invalid characters, which
    can be a string (a question) or a list of strings (answers).
    If no errors are found, returns an empty string. Otherwise, returns
    a string that contains the text with invalid characters.
    """

    allowed_characters = re.compile('^[ !"$%&\'()+,-./0-9:;<=>?A-Z_a-z\{\}“”ʻ’…÷*~]*$')

    if isinstance(text,str):
        if allowed_characters.fullmatch(text) is None:
            return f"Question {text} contains invalid characters"

    elif isinstance(text,list):
        errors = []
        for a in text:
            if allowed_characters.fullmatch(a) is None:
                errors.append(a)
        if len(errors) == 1:
            return f"Answer {errors[0]} contains invalid characters"
        elif len(errors) > 1:
            return f"Answers {errors} contain invalid characters"

    return ""


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
    questions_error = []
    for id in SELECTED_CATEGORY_IDS:

        # Get total number of questions in easy and medium difficulties.
        url = f"https://opentdb.com/api_count.php?category={id}"
        while True:
            try:
                r = requests.get(url)
                j = r.json()
                print(f"\nDownloading category ID {j['category_id']}.")
                easy_questions = j["category_question_count"]["total_easy_question_count"]
                medium_questions = j["category_question_count"]["total_medium_question_count"]
                print(f"{str(easy_questions)} easy questions and {str(medium_questions)} medium questions in this category.")
                time.sleep(API_REQUEST_INTERVAL)
            except requests.ConnectionError as e:
                print(e)
                print("Cannot connect to OpenTDB API. Retrying in 5 seconds.")
                time.sleep(5)
                continue
            break

        for difficulty in ["easy","medium"]:
            if difficulty == "easy":
                remaining_questions = easy_questions
            elif difficulty == "medium":
                remaining_questions = medium_questions

            # The total number of questions per difficulty reported by the
            # API is not always accurate. When response code 4 is returned,
            # try one more time with 1 fewer question up to twice before
            # continuing with the next difficulty.
            retries = 2

            while True:
                if remaining_questions == 0:
                    break
                if remaining_questions >= QUESTION_REQUEST_AMOUNT:
                    next_questions = QUESTION_REQUEST_AMOUNT
                else:
                    next_questions = remaining_questions

                params = {
                    "token": session_token,
                    "category": id,
                    "difficulty": difficulty,
                    "amount": next_questions,
                    "encode": "url3986",
                    # "type": "multiple"
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
                    time.sleep(API_REQUEST_INTERVAL)
                    if retries > 0 and remaining_questions > retries:
                        retries -= 1
                        remaining_questions -= 1
                        continue
                    else:
                        break

                # If a rate limit is reached, wait 5 seconds before the next request.
                elif j["response_code"] == 5:
                    print("API rate limit reached. Waiting 5 seconds.")
                    time.sleep(5)
                    continue

                for question in j["results"]:
                    if question["type"] != "multiple":
                        continue

                    error = ""
                    error2 = ""
                    category = unquote(question["category"])
                    # Category needs to be short
                    category = category.split(":")[-1].strip()
                    text = unquote(question["question"].strip())
                    if FILTER_INVALID_CHARACTERS_IN_QUESTIONS:
                        error = check_text(text)
                        if error != "" and PRINT_INVALID_QUESTIONS:
                            print(f"Warning: In category {category}, question '{text}' has invalid characters.")
                    else:
                        text = fix_str(text,question=True)

                    answers = [unquote(question["correct_answer"].strip())] + [unquote(i.strip()) for i in question["incorrect_answers"]]
                    if FILTER_INVALID_CHARACTERS_IN_ANSWERS:
                        error2 = check_text(answers)
                        if error2 != "" and PRINT_INVALID_QUESTIONS:
                            print(f"Warning: In category {category}, question '{text}' has answers with invalid characters.\nAnswers: {answers}")
                            if error != "":
                                error += "\n" + error2
                            else:
                                error = error2
                    else:
                        answers = [fix_str(i) for i in answers]

                    if error == "":
                        question_dict = {
                            "category": category,
                            "question": text,
                            "answers": answers
                        }
                    else:
                        question_dict = {
                            "category": category,
                            "question": text,
                            "answers": answers,
                            "error" : error
                        }

                    if error == "":
                        questions.append(question_dict)
                    else:
                        questions_error.append(question_dict)

                print(f"{len(questions)} questions added.")
                remaining_questions -= next_questions
                time.sleep(API_REQUEST_INTERVAL)

    with open("questions.json", "w") as f:
        questions_sorted = sorted(questions, key=lambda q: q['category'])
        json.dump(questions_sorted, f, indent=4)
    if questions_error:
        with open("questions_error.json", "w", encoding="utf8") as f:
            questions_sorted = sorted(questions_error, key=lambda q: q['category'])
            json.dump(questions_sorted, f, ensure_ascii=False, indent=4)

    print(f"\nWrote {len(questions)} questions to questions.json.")
    print(f"Wrote {len(questions_error)} questions with errors to questions_error.json. You can review these questions, manually correct them, and insert them into questions.json.")


if __name__ == "__main__":
    main()