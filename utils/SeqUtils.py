from itertools import chain
import pickle
from utils import FastText
from collections import defaultdict
from functools import reduce
import torch
from torch.utils.data import Dataset

import numpy as np


def load(file='test-output/sequences/words-types.p'):
    with open(file, 'rb') as f:
        wss, tss = pickle.load(f)
    return wss, tss


def get_all_unique(iterable_of_sequences):
    return set([x for x in chain.from_iterable(iterable_of_sequences)])


def make_oov_files(input_file='test-output/sequences/words-types.p', iv_vectors_file='wiki.nl/wiki.nl/vec',
                   oov_words_file='wiki.nl/oov.txt', oov_vectors_file='wiki.nl/oov.vec'):
    with open(input_file, 'rb') as f:
        ws, ts = pickle.load(f)

    all_words = get_all_unique(ws)

    model_vectors = FastText.load_vectors(iv_vectors_file)
    oov_words = FastText.find_oov(all_words, model_vectors)
    FastText.write_oov(oov_words, oov_words_file=oov_words_file)
    FastText.vectorize_oov(oov_words_file, oov_vectors_file)


def get_type_occurrences(type_sequences):
    all_types = get_all_unique(type_sequences)
    counts = {t: 0 for t in all_types}
    for ts in type_sequences:
        for t in ts:
            counts[t] = counts[t] + 1
    return counts


def get_all_chars(word_sequences):
    return list(reduce(set.union, [set(''.join(w)) for w in word_sequences], set()))


def get_high_occurrence_sequences(word_sequences, type_sequences, threshold):
    """
    Given an iterable of word sequences, an iterable of their corresponding type sequences, and a minimum occurrence
    threshold, returns a new pair of iterables by pruning type sequences containing low occurrence types.
    :param word_sequences:
    :param type_sequences:
    :param threshold:
    :return:
    """
    assert (len(word_sequences) == len(type_sequences))
    type_occurrences = get_type_occurrences(type_sequences)
    kept_indices = [i for i in range(len(word_sequences)) if not
                    list(filter(lambda x: type_occurrences[x] <= threshold, type_sequences[i]))]
    return [word_sequences[i] for i in kept_indices], [type_sequences[i] for i in kept_indices]


def get_low_len_sequences(word_sequences, type_sequences, max_len):
    """

    :param word_sequences:
    :param type_sequences:
    :param max_len:
    :return:
    """
    assert len(word_sequences) == len(type_sequences)
    kept_indices = [i for i in range(len(word_sequences)) if len(word_sequences[i]) <= max_len]
    return [word_sequences[i] for i in kept_indices], [type_sequences[i] for i in kept_indices]


def get_low_len_words(word_sequences, type_sequences, max_word_len):
    assert len(word_sequences) == len(type_sequences)
    kept_indices = [i for i in range(len(word_sequences)) if
                    all(map(lambda x: len(x) <= max_word_len, word_sequences[i]))]
    return [word_sequences[i] for i in kept_indices], [type_sequences[i] for i in kept_indices]


def map_ws_to_vs(word_sequence, vectors):
    return torch.Tensor(list(map(lambda x: vectors[x], word_sequence)))

def map_cs_to_is(char_sequence, char_dict, max_len):
    a = torch.zeros(max_len)
    b = torch.Tensor(list(map(lambda x: char_dict[x], char_sequence)))
    a[:len(b)] = b
    return a


class Sequencer(Dataset):
    def __init__(self, word_sequences, type_sequences, vectors, max_sentence_length=None,
                 minimum_type_occurrence=None, return_char_sequences=False, return_word_distributions=False,
                 max_word_len=20):
        """
        Necessary in the case of larger data sets that cannot be stored in memory.
        :param word_sequences:
        :param type_sequences:
        :param vectors:
        :param max_sentence_length:
        :param minimum_type_occurrence:
        """

        print('Received {} samples..'.format(len(word_sequences)))
        if max_sentence_length:
            word_sequences, type_sequences = get_low_len_sequences(word_sequences, type_sequences, max_sentence_length)
            print(' .. of which {} are ≤ the maximum sentence length ({}).'.format(len(word_sequences),
                                                                                     max_sentence_length))
        if minimum_type_occurrence:
            word_sequences, type_sequences = get_high_occurrence_sequences(word_sequences, type_sequences,
                                                                           minimum_type_occurrence)
            print(' .. of which {} are ≥ the minimum type occurrence ({}).'.format(len(word_sequences),
                                                                                       minimum_type_occurrence))
        if return_char_sequences:
            word_sequences, type_sequences = get_low_len_words(word_sequences, type_sequences, max_word_len)
            print(' .. of which {} are ≤ the minimum word length ({}).'.format(len(word_sequences), max_word_len))

        self.word_sequences = word_sequences
        self.type_sequences = type_sequences
        self.max_sentence_length = max_sentence_length
        self.types = {t: i+1 for i, t in enumerate(get_all_unique(type_sequences))}
        self.words = {w: torch.zeros(len(self.types)) for i, w in enumerate(get_all_unique(word_sequences))}
        self.types[None] = 0
        self.vectors = vectors
        assert len(word_sequences) == len(type_sequences)
        self.len = len(word_sequences)

        self.return_word_distributions = return_word_distributions
        if self.return_word_distributions:
            self.build_word_lexicon()
            self.word_lexicon_to_pdf()

        self.return_char_sequences = return_char_sequences
        if self.return_char_sequences:
            self.chars = {c: i+1 for i, c in enumerate(get_all_chars(self.word_sequences))}
            self.chars[None] = 0
            self.max_word_len = max_word_len

        print('Constructed dataset of {} word sequences with a total of {} unique types'.
              format(self.len, len(self.types) - 1))
        print('Average sentence length is {}'.format(np.mean(list(map(len, word_sequences)))))

    def __len__(self):
        return self.len

    def get_item_without_chars(self, index):
        try:
            return (map_ws_to_vs(self.word_sequences[index], self.vectors),
                    torch.Tensor(list(map(lambda x: self.types[x], self.type_sequences[index]))))
        except KeyError:
            return None

    def __getitem__(self, index):
        temp = self.get_item_without_chars(index)
        if not temp:
            return None
        vectors, types = temp
        if self.return_char_sequences:
            char_sequences = torch.stack(list(map(lambda x: map_cs_to_is(x, self.chars, self.max_word_len),
                                                  self.word_sequences[index])))
        if self.return_word_distributions:
            word_distributions = torch.stack(list(map(lambda word: self.tensorize_dict(word),
                                                      self.word_sequences[index])))

        if self.return_char_sequences:
            if self.return_word_distributions:
                return vectors, char_sequences, word_distributions, types
            else:
                return vectors, char_sequences, types
        elif self.return_word_distributions:
            return vectors, word_distributions, types
        else:
            return vectors, types

    def build_word_lexicon(self):
        self.words = {w: dict() for w in get_all_unique(self.word_sequences)}
        for ws, ts in zip(self.word_sequences, self.type_sequences):
            for w, t in zip(ws, ts):
                if self.types[t] in self.words[w].keys():
                    self.words[w][self.types[t]] = self.words[w][self.types[t]] + 1
                else:
                    self.words[w][self.types[t]] = 1

    def word_lexicon_to_pdf(self):
        self.words = {w: {k: v/sum(self.words[w].values())} for w in self.words for k, v in self.words[w].items()}

    def tensorize_dict(self, word):
        a = torch.zeros(len(self.types))
        for k, v in self.words[word].items():
            a[k] = v
        return a


def fake_vectors():
    return defaultdict(lambda: np.random.random(300))


def check_uniqueness(word_sequences, type_sequences):
    u = dict()
    bad = 0
    for ws, ts in zip(word_sequences, type_sequences):
        ws = ' '.join([w for w in ws])
        if ws in u.keys():
            try:
                assert u[ws] == ts
            except AssertionError:
                bad += 1
        else:
            u[ws] = ts
    print('{} sequences are assigned non-singular types'.format(bad))


def __main__(sequence_file='test-output/sequences/words-types.p', inv_file='wiki.nl/wiki.nl.vec',
         oov_file='wiki.nl/oov.vec', return_char_sequences=False, return_word_distributions=False, fake=False):
    ws, ts = load(sequence_file)
    # check_uniqueness(ws, ts)

    if fake:
        vectors = fake_vectors()
    else:
        vectors = FastText.load_vectors([inv_file, oov_file])

    sequencer = Sequencer(ws, ts, vectors, max_sentence_length=10, minimum_type_occurrence=10,
                          return_char_sequences=return_char_sequences,
                          return_word_distributions=return_word_distributions)
    # dl = DataLoader(sequencer, batch_size=32,
    #                 collate_fn=lambda batch: sorted(filter(lambda x: x is not None, batch),
    #                                                 key=lambda y: y[0].shape[0]))
    return sequencer
