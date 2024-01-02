# QAD Custom

![Screenshot](screenshot.png)

Tool for inserting custom questions/answers into the Quiz & Dragons MAME rom (qad.zip). Built using the OpenTDB API,
but questions can be added from any source.

For detailed info on how QaD stores and interprets questions, see [Notes](notes.md).

Requires Python3, [Requests](https://docs.python-requests.org/en/latest/index.html), and [Unidecode](https://pypi.org/project/Unidecode/).

## Installation

1. Move a clean copy of qad.zip to the clean_rom directory
2. (Optional) Open opentdb.py and configure the options at the top of the file. `SELECTED_CATEGORY_IDS` should include a maximum of 14 categories.
3. Run `pip3 install requests Unidecode`
4. Run `./opentdb.py`
5. (Optional) Review `questions_error.json` for questions that contain characters not supported by Quiz & Dragons,
   and manually correct and insert them into questions.json
6. Run `./build.py`
7. Move `patched/qad.zip` to your MAME roms directory and run mame from command line to skip CRC
   checks (`./mame.exe qad`)

## Using a question source besides OpenTDB

This is simple enough, just write your questions to `questions.json` in the same directory as `build.py`. There is a
sample file called `questions_sample.json` for reference. The first answer is the correct one. Make sure you're aware of
the limits described in the "Questions/Answers" section of [Notes](notes.md). Once questions.json exists and is filled
with trivia, run `build.py`.

## Notes on OpenTDB API Limits

The OpenTDB API has a limit of 50 questions per request and 1 request per IP every 5 seconds. The `opentdb.py` script will
pause every 6 seconds (by default) to attempt to respect the rate limits.

Additionally, while the total number of questions in a given category and difficulty can be queried, the API will report
the total number of questions including true/false questions, which Quiz & Dragons does not support. To maximize the number
of questions this script can retrieve, it will download all available questions and then filter out true/false questions, at
the expense of extra API requests that can potentially return 0 useful questions. As a result of this, the number of
questions added to questions.json by the script will be lower than the total reported by the API.