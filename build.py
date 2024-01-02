#!/usr/bin/env python3
import json
import logging
import os
import sys
from os.path import join
import shutil
import random
# from compress import Questions, WordDictionary, calculate_word_frequency, MAX_MAIN_DICT_SIZE, \
#   MAX_PROPER_NOUN_DICT_SIZE_BYTES
from QADPatch.QuizQuestions import QuizQuestion, QuestionList
from QADPatch.WordDictionary import WordDictionary
from util import check_zip_hash, extract_zip, deinterleave, concatenate, patch, split, interleave, build_zip

WORKING_DIR = join(".", "temp")
OUTPUT_DIR = join(".", "patched")
CLEAN_ROM_DIR = "clean_rom"
ZIP_FILENAME = "qad.zip"
ROM1A = "qdu_36a.12f"
ROM1B = "qdu_42a.12h"
ROM2A = "qdu_37a.13f"
ROM2B = "qdu_43a.13h"
MAX_PROPER_NOUN_DICT_SIZE = 88
MAX_PROPER_NOUN_DICT_SIZE_BYTES = 0x30e
MAX_MAIN_DICT_SIZE = 0x3973


def build_rom():
    """
        Given qad.zip, extract out ROM files process as follows:
        1. Extract zip
        2. Deinterlace all 4 ROM files, one pair at a time
        3. Concatenate deinterlaced ROMs
        4. Apply patches
        5. Work backwards through steps 3,2,1
    """
    logger = logging.getLogger('QADPatch')
    logger.setLevel(logging.INFO)
    sh = logging.StreamHandler()
    logger.addHandler(sh)
    try:
        if not check_zip_hash(CLEAN_ROM_DIR, ZIP_FILENAME):
            logger.error("qad.zip file hash does not match. Make sure you're using the most recent version of qad.zip")
            sys.exit(1)
    except FileNotFoundError:
        logger.error("qad.zip not found in clean_rom directory.")
        sys.exit(1)
    logger.info("Extracting, deinterleaving, and combining ROM files")
    extract_zip(CLEAN_ROM_DIR, ZIP_FILENAME)
    deinterleave(ROM1A, ROM1B, "rom1.bin")
    deinterleave(ROM2A, ROM2B, "rom2.bin")
    concatenate("rom1.bin", "rom2.bin", "combined.bin")

    with open(join(WORKING_DIR, "combined.bin"), "rb") as f:
        f.seek(0x1dcb6)
        byte_reference_table = f.read(0xc0)

    questions = QuestionList(byte_reference_table)

    with open("questions.json", "r") as f:
        question_json = json.load(f)

    logger.info("Validating questions")
    # Validate and add questions
    for q in question_json:
        question = QuizQuestion(category=q["category"],
                                question_text=q["question"],
                                answers=q["answers"])
        logger.info("Question failed validation. Skipping")
        valid = question.validate(questions.allowed_chars)
        if valid:
            questions.add_question(question)

    if questions.category_count() > 14:
        logger.error(f"Too many categories. There can be a max of 14. Exiting")
        sys.exit(1)

    logger.info("Building main dictionary")
    # Build both dictionaries
    frequency = questions.calculate_word_frequency()
    main_dict = WordDictionary(questions, frequency, max_size=MAX_MAIN_DICT_SIZE, max_word_count=2048,
                               proper=False)
    main_dict.build()

    logger.info("Building proper noun dictionary")
    proper_noun_dict = WordDictionary(questions, frequency, max_size=MAX_PROPER_NOUN_DICT_SIZE_BYTES,
                                      max_word_count=MAX_PROPER_NOUN_DICT_SIZE, proper=True,
                                      exclusions=list(main_dict.words)[0:100])
    proper_noun_dict.build()

    logger.info("Encoding questions and dumping")
    # Dump metadata includes things like offsets of categories, question, counts
    dump_metadata = questions.dump(join(WORKING_DIR, "questions.bin"), proper_noun_dict, main_dict)

    logger.info("Dumping dictionaries")
    main_dict.dump(join(WORKING_DIR, "main_dict.bin"))
    proper_noun_dict.dump(join(WORKING_DIR, "proper_noun_dict.bin"))

    logger.info("Patching binary")
    """ Offsets for changing total question count in the random pre-gen (0x1661 by default) """
    patch("combined.bin", 0x6034, patch_value=dump_metadata["question_count"].to_bytes(2, "big"))
    patch("combined.bin", 0x604c, patch_value=dump_metadata["question_count"].to_bytes(2, "big"))
    patch("combined.bin", 0x60b8, patch_value=dump_metadata["question_count"].to_bytes(2, "big"))
    patch("combined.bin", 0x60c0, patch_value=dump_metadata["question_count"].to_bytes(2, "big"))

    # Category random seeds. These should be random numbers from 1 to <number of categories>. 1 byte each"""
    # We want an even distribution of categories, just shuffled around.
    category_id_rands = []
    total_categories = len(dump_metadata['categories'])
    for i in range(0, 59):
        category_id_rands.append((i % total_categories))
    random.shuffle(category_id_rands)

    # Patch in the seeds
    for i, category_id in enumerate(category_id_rands):
        patch("combined.bin", 0x25368 + i, patch_value=(category_id + 1).to_bytes(1, 'big'))

    """ Debugging patches for forcing certain categories/questions to be chosen """
    # patch("combined.bin", 0x5b46, patch_value=b'\x30\x3C\x00\x00') # Always choose category 0
    # patch("combined.bin", 0x6198, patch_value=b'\x30\x3C\x00\x00') # Always choose question 0 from selected category

    current_category_name_offset = 0x1DC1E
    for name, info in dump_metadata["categories"].items():
        offset = info["offset"]
        index = info["index"]
        question_count = info["count"]
        # Patch category offsets
        patch("combined.bin", 0x1DBE6 + (4 * index), patch_value=(offset + 0x3C82).to_bytes(4, "big"))
        # Patch category question counts
        patch("combined.bin", 0x1DC9A + (2 * index), patch_value=question_count.to_bytes(2, "big"))
        # Patch category name and increase offset
        patch("combined.bin", current_category_name_offset, patch_value=name.encode("utf-8") + b'\x00')
        current_category_name_offset += len(name) + 1

    # Fill in unused categories with 0s
    if len(dump_metadata["categories"]) < 14:
        for i in range(len(dump_metadata["categories"]), 14):
            patch("combined.bin", 0x1DC9A + (2 * i), patch_value=b'\x00\x00')

    # Patch in generated files
    patch("combined.bin", 0x29370, patch_fn="questions.bin")
    patch("combined.bin", 0x256EE, patch_fn="proper_noun_dict.bin")
    patch("combined.bin", 0x259FC, patch_fn="main_dict.bin")

    # Value at this address *must* equal len(proper_noun_dict)+1. If there are stubbed out word(s) at the end,
    # those must be included in the count.
    patch("combined.bin", 0x5E09,
          patch_value=(len(proper_noun_dict.words) + proper_noun_dict.dummy_words + 1).to_bytes(1, 'big'))

    logger.info("Re-assembling qad.zip")
    split('combined.bin', 'rom1.bin', 'rom2.bin', 0x40000)
    interleave("rom1.bin", ROM1A, ROM1B)
    interleave("rom2.bin", ROM2A, ROM2B)
    os.remove(join(WORKING_DIR, "rom1.bin"))
    os.remove(join(WORKING_DIR, "rom2.bin"))
    os.remove(join(WORKING_DIR, "combined.bin"))
    os.remove(join(WORKING_DIR, "main_dict.bin"))
    os.remove(join(WORKING_DIR, "proper_noun_dict.bin"))
    os.remove(join(WORKING_DIR, "questions.bin"))
    build_zip()


    print(
        f"Build complete. Inserted {dump_metadata['question_count']} questions from {len(dump_metadata['categories'])} categories")


if __name__ == "__main__":
    build_rom()
