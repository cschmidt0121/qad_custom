import logging
import re
from collections import OrderedDict

MAX_QUESTION_LIST_SIZE = 0x56C90


class BadStringError(Exception):
    def __init__(self, message, character=None):
        self.message = message
        self.character = character


class QuestionTooLongError(Exception):
    def __init__(self, message):
        self.message = message


class QuizQuestion:
    def __init__(self, category, question_text, answers):
        self.category = category
        self.question_text = question_text
        # First answer is always the correct one
        self.answers = answers
        self.logger = logging.getLogger('QADPatch')

    def validate(self, allowed_chars):
        """ Validate a given question. Returns False if there is an issue """
        try:
            self.has_bad_chars(self.question_text, allowed_chars)
            self.wrap()
        except BadStringError as e:
            self.logger.warning(f"Text error in question {self.question_text}: {e.message}. {hex(ord(e.character))}")
            return False
        except QuestionTooLongError:
            self.logger.warning(f"Question {self.question_text} too long")
            return False
        for answer in self.answers:
            try:
                self.has_bad_chars(answer, allowed_chars)
            except BadStringError as e:
                self.logger.warning(f"Text error in answer {answer}: {e.message}. {hex(ord(e.character))}")
                return False
            if len(answer) > 22:
                self.logger.warning(f"Answer too long: {answer}")
                return False

        return True

    @staticmethod
    def has_bad_chars(s, allowed_chars):
        """ Check for disallowed characters """
        for char in s:
            if char not in allowed_chars:
                raise BadStringError("Disallowed character", character=char)
            elif char == ">":
                raise BadStringError("> char decodes to ★ which is probably unintended", character=char)
            elif char == "<":
                raise BadStringError("< char decodes to ♥ which is probably unintended", character=char)

    def wrap(self):
        """ Add newlines to a question so that there are no more than 34 characters on a line. """
        out = ""
        words = self.question_text.split(" ")
        current_line_length = 0
        current_line = 0
        for word in words:
            if current_line > 3:
                raise QuestionTooLongError("Question too long")
            if len(word) + current_line_length > 34:
                out = out.rstrip()  # Remove trailing space
                out += "\n%s " % word
                current_line += 1
                current_line_length = len(word) + 1
            else:
                out += "%s " % word
                current_line_length += (len(word) + 1)
        return out


class QuestionList:
    def __init__(self, byte_reference_table):
        # question_list is a list of QuizQuestions
        self.question_list = []
        self.byte_reference_table = byte_reference_table
        self.allowed_chars = []
        for i in range(0, len(self.byte_reference_table)):
            if self.byte_reference_table[i] == 0:
                self.allowed_chars.append(chr(i))
        self.logger = logging.getLogger('QADPatch')

    def add_question(self, question):
        """ Add a QuizQuestion to internal list """
        self.question_list.append(question)

    def category_count(self):
        """ Count number of categories represented in the QuestionList """
        categories = []
        for q in self.question_list:
            if q.category not in categories:
                categories.append(q.category)

        return len(categories)

    def calculate_word_frequency(self):
        """ Given a list of QuizQuestions, return an ordered frequency dict ({"word": <usage count>}) """
        frequency_dict = {}

        for question in self.question_list:
            question_str = question.question_text
            frequency_dict = self.calculate_frequency_from_str(question_str, frequency_dict)

            for answer in question.answers:
                frequency_dict = self.calculate_frequency_from_str(answer, frequency_dict)

        return OrderedDict(sorted(frequency_dict.items(), reverse=True, key=
        lambda kv: (kv[1], kv[0])))

    @staticmethod
    def calculate_frequency_from_str(s, frequency_dict):
        """ Split a string into words, then return a dict representing frequency of each str """
        separators = r'[\s|"|!|#|$|%|&|\'|(|)|\+|,|-|\.|/|:|;|<|=|>|\?|{|}]+'
        words = re.split(separators, s)
        for word in words:
            word = word.strip("{}")  # Remove stray braces which are used to indicate italics
            # Only calculate frequency of words that contain some amount of alphanumeric and allowed special chars
            # I'm not sure if other special chars would work, but these are the only ones in the original ROM's dictionary.
            if not re.match(r'^[a-zA-Z\.\-\'\*]+$', word):
                continue
            if len(word) < 2:
                continue
            if word in frequency_dict:
                frequency_dict[word] += 1
            else:
                frequency_dict[word] = 1
        return frequency_dict

    def encode_str(self, s, proper_noun_dictionary, main_dictionary):
        """ There's gotta be a better way to do this dear god """

        s_bytes = s.encode("utf-8").replace(b'\n', b'\x01')
        output = [{"type": "unencoded", "data": s_bytes}]

        # First encode proper nouns
        while True:
            new_output = self.do_replacement(items=output, d=proper_noun_dictionary, proper=True, flip=False)
            if new_output == output:
                break
            else:
                output = new_output

        # Now encode words from main_dictionary
        while True:
            new_output = self.do_replacement(items=output, d=main_dictionary, proper=False, flip=False)
            if new_output == output:
                break
            else:
                output = new_output

        # Finally check if we can flip capitalization for any dictionary words
        while True:
            new_output = self.do_replacement(items=output, d=main_dictionary, proper=False, flip=True)
            if new_output == output:
                break
            else:
                output = new_output

        final_bytes = bytearray()
        for item in output:
            final_bytes.extend(item["data"])

        return final_bytes

    def do_replacement(self, items, d, proper=False, flip=False):
        """
        When possible, replaces full words with 1-2 byte equivalents. Called until no additiona replacements can be
        made.
        items is a list of dictionaries in this format:
        {"type": "unencoded", "data": b'\x41\x53\x53'}
        If type is encoded, it should be skipped.
        """
        new_items = []

        replaced = False
        for item in items:
            if item["type"] == "encoded":
                new_items.append(item)
                continue
            if replaced:
                new_items.append(item)
                continue
            for w in d.words:
                word_encoded = w.encode("utf-8")
                if word_encoded in item["data"]:
                    d_index = d.words.index(w)
                    word_index = item["data"].index(word_encoded)
                    before = item["data"][0:word_index]
                    after = item["data"][word_index + len(w):]
                    if proper:
                        replacement_bytes = self.byte_reference_table.index(d_index + 1).to_bytes(1, 'big')
                    else:
                        pre_space = (word_index != 0) and item["data"][word_index - 1] == " "
                        post_space = (word_index != (len(item["data"]) - 1)) and item["data"][word_index - 1] == " "
                        replacement_bytes = self.encode_word(d_index, pre_space, post_space, flip=flip)
                    if len(before) != 0:
                        new_items.append({"type": "unencoded", "data": before})
                    new_items.append({"type": "encoded", "data": replacement_bytes})
                    if len(after) != 0:
                        new_items.append({"type": "unencoded", "data": after})
                    replaced = True
                    break
            if not replaced:
                new_items.append(item)

        return new_items

    @staticmethod
    def encode_word(d_index, pre_space=False, post_space=False, flip=False):
        # bits 1 and 2 are always 1
        # if there should be a space before the word, bit 3 is 1
        # if there should be a space after the word, bit 4 is 1
        # if the capitalization should be flipped, bit 5 is 1
        # bits 6,7,8 are the upper bits of the word index (if needed)
        mask = 0xc0

        mask = mask | 0x20 if pre_space else mask
        mask = mask | 0x10 if post_space else mask
        mask = mask | 0x08 if flip else mask

        byte1 = (mask | d_index >> 8).to_bytes(1, "big")
        byte2 = (d_index - ((d_index >> 8) << 8)).to_bytes(1, "big")

        return b''.join([byte1, byte2])

    def dump(self, filename, proper_noun_dictionary, main_dictionary):
        """ Write questions until we are at max length or out of questions"""
        questions_sorted = sorted(self.question_list, key=lambda q: q.category)
        current_category = None
        current_category_index = -1
        metadata = {"question_count": 0, "categories": {}}
        f = open(filename, "wb")
        for question in questions_sorted:
            self.logger.info(f"Encoding question {question.question_text}")
            question_bin = bytearray()
            category = question.category
            if category != current_category:
                if current_category:
                    f.write(b'\x00')  # Each category section is null-terminated
                current_category = category
                current_category_index += 1
                metadata["categories"][category] = {"name": category, "offset": f.tell(), "count": 0,
                                                    "index": current_category_index}
            question_wrapped = question.wrap().rstrip("?").rstrip()
            question_bin.extend(
                self.encode_str(question_wrapped, proper_noun_dictionary, main_dictionary))
            question_bin += b'\x00'
            for answer in question.answers:
                question_bin.extend(self.encode_str(answer, proper_noun_dictionary, main_dictionary))
                question_bin += b'\x01'
            block_length = len(question_bin)
            if (block_length + 1 + f.tell()) > MAX_QUESTION_LIST_SIZE:
                f.write(bytearray(MAX_QUESTION_LIST_SIZE - f.tell()))
                self.logger.warning("Exiting early because we are at max length. ")
                f.close()
                return metadata

            f.write((block_length + 1).to_bytes(1, 'big'))
            f.write(question_bin)
            metadata["categories"][category]["count"] += 1
            metadata["question_count"] += 1

        f.write(bytearray(MAX_QUESTION_LIST_SIZE - f.tell()))
        f.close()
        return metadata
