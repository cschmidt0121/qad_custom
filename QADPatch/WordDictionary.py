class WordDictionary:
    """
    Word dictionary used for compressing question text. QAD uses two dictionaries: one for capitalized proper nouns,
    and one for other words (including less common capitalized words).
    """

    def __init__(self, question_list, word_frequency, max_size, max_word_count=0, proper=False, exclusions=[]):
        self.question_list = question_list
        self.word_frequency = word_frequency
        self.max_size = max_size  # bytes
        self.max_word_count = max_word_count
        self.proper = proper
        self.words = []
        self.dummy_words = 0
        # self.words except each word's first character's capitalization is flipped. To -> to, the -> The, etc
        self.words_flipped = []
        self.exclusions = exclusions

    def serialize(self):
        """ Generate a bytearray object in the format that the word dictionary will take in the final ROM"""
        out = bytearray()
        for word in self.words:
            out += len(word).to_bytes(1, 'big')
            out += word.encode("utf-8")
        return out

    def from_file(self, filename):
        with open(filename, "rb") as f:
            data = f.read()
            i = 0
            while i < len(data):
                word_length = data[i]
                word = data[i + 1:i + word_length + 1].decode("utf-8")
                self.words.append(word)
                i += word_length + 1
        for word in self.words:
            if word[0].isupper():
                flipped = word[0].lower() + word[1:]
            else:
                flipped = word[0].upper() + word[1:]
            self.words_flipped.append(flipped)

    def build(self):
        # Words sorted highest frequency first, removing words which only appear once.
        word_list = [k for k, v in self.word_frequency.items() if v > 1]
        # If the word is too big we skip and try a few more times in case we have one small enough to fit.
        attempts = 10
        for word in word_list:
            if attempts == 0:
                break
            if word in self.exclusions:
                continue

            # Proper noun dict should only have capitalized words
            if self.proper:
                if not word[0].isupper() or len(word) < 3:
                    continue
            if len(self.words) == self.max_word_count:
                break

            if len(self.serialize()) + len(word) + 1 > self.max_size:
                attempts -= 1
                continue
            elif word in self.words or word in self.words_flipped:
                continue

            self.words.append(word)
            if word[0].isupper():
                flipped = word[0].lower() + word[1:]
            else:
                flipped = word[0].upper() + word[1:]
            self.words_flipped.append(flipped)

    def dump(self, filename):
        """ Dump out of self.serialize to specified filename """
        with open(filename, "wb") as f:
            f.write(self.serialize())
            # pad if size isn't exactly right.
            pos = f.tell()
            while pos < self.max_size:
                if self.max_size - pos == 3:
                    f.write(b'\x02\x61\x62')
                    pos += 3
                else:
                    f.write(b'\x01\x61')
                    pos += 2
                self.dummy_words += 1
            f.close()
