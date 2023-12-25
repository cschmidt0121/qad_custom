# QAD Custom

![Screenshot](screenshot.png)

Tool for inserting custom questions/answers into the Quiz and Dragons MAME rom (qad.zip). Built using the OpenTDB API,
but questions can be added from any source.

For detailed info on how QaD stores and interprets questions, see [Notes](notes.md).

Requires Python3, [requests](https://docs.python-requests.org/en/latest/index.html), and [unidecode](https://pypi.org/project/Unidecode/).

## Installation

1. Move a clean copy of qad.zip to the clean_rom directory
2. (Optional) Modify `SELECTED_CATEGORY_IDS` in opentdb.py to the categories you want to include. Max 14 categories.
3. Run `pip3 install Unidecode`
4. Run `./opentdb.py`
5. Run `./build.py`
6. Move `patched/qad.zip` to your MAME roms directory and run mame from command line to skip CRC
   checks (`./mame.exe qad`)

## Using a question source besides OpenTDB

This is simple enough, just write your questions to `questions.json` in the same directory as `build.py`. There is a
sample file called `questions_sample.json` for reference. The first answer is the correct one. Make sure you're aware of
the limits described in the "Questions/Answers" section of [Notes](notes.md). Once questions.json exists and is filled
with trivia, run `build.py`.