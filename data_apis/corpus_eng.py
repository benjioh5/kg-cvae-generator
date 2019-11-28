from data_apis.corpus import CVAECorpus
from collections import Counter
import numpy as np
import nltk
import os
import pickle

# Copyright (C) 2017 Tiancheng Zhao, Carnegie Mellon University


class SWDADialogCorpus(CVAECorpus):
    dialog_act_id = 0
    sentiment_id = 1
    liwc_id = 2

    vocab = None
    rev_vocab = None
    unk_id = None

    topic_vocab = None
    rev_topic_vocab = None

    dialog_act_vocab = None
    rev_dialog_act_vocab = None

    def __init__(self, config):
        self.sil_utt = ["<s>", "<sil>", "</s>"]
        super(SWDADialogCorpus, self).__init__(config)

    def process(self, data):
        """new_dialog: [(a, 1/0), (a,1/0)], new_meta: (a, b, topic), new_utt: [[a,b,c)"""
        """ 1 is own utt and 0 is other's utt"""
        new_dialog = []
        new_meta = []
        new_utts = []
        # 最初の会話を表す
        bod_utt = ["<s>", "<d>", "</s>"]
        all_lenes = []

        for l in data:
            lower_utts = [(caller, ["<s>"] + nltk.WordPunctTokenizer().tokenize(utt.lower()) + ["</s>"], feat)
                          for caller, utt, feat in l["utts"]]
            all_lenes.extend([len(u) for c, u, f in lower_utts])

            a_age = float(l["A"]["age"])/100.0
            b_age = float(l["B"]["age"])/100.0
            a_edu = float(l["A"]["education"])/3.0
            b_edu = float(l["B"]["education"])/3.0
            vec_a_meta = [a_age, a_edu] + ([0, 1] if l["A"]["sex"] == "FEMALE" else [1, 0])
            vec_b_meta = [b_age, b_edu] + ([0, 1] if l["B"]["sex"] == "FEMALE" else [1, 0])

            # for joint model we mode two side of speakers together. if A then its 0 other wise 1
            meta = (vec_a_meta, vec_b_meta, l["topic"])
            dialog = [(bod_utt, 0, None)] + \
                     [(utt, int(caller == "B"), feat) for caller, utt, feat in lower_utts]

            new_utts.extend([bod_utt] + [utt for caller, utt, feat in lower_utts])
            new_dialog.append(dialog)
            new_meta.append(meta)

        print("Max utt len %d, mean utt len %.2f" % (np.max(all_lenes), float(np.mean(all_lenes))))
        return new_dialog, new_meta, new_utts

    def build_vocab(self, max_vocab_cnt):
        all_words = []
        for tokens in self.train_corpus[self.utt_id]:
            all_words.extend(tokens)
        vocab_count = Counter(all_words).most_common()
        raw_vocab_size = len(vocab_count)
        discard_wc = np.sum([c for t, c, in vocab_count[max_vocab_cnt:]])
        vocab_count = vocab_count[0:max_vocab_cnt]
        oov_rate = float(discard_wc) / len(all_words)

        # create vocabulary list sorted by count
        print("Load corpus with train size %d, valid size %d, "
              "test size %d raw vocab size %d vocab size %d at cut_off %d OOV rate %f"
              % (len(self.train_corpus), len(self.valid_corpus), len(self.test_corpus),
                 raw_vocab_size, len(vocab_count), vocab_count[-1][1], oov_rate))

        self.vocab = ["<pad>", "<unk>"] + [t for t, cnt in vocab_count]
        self.rev_vocab = {t: idx for idx, t in enumerate(self.vocab)}
        self.unk_id = self.rev_vocab["<unk>"]
        print("<d> index %d" % self.rev_vocab["<d>"])
        print("<sil> index %d" % self.rev_vocab.get("<sil>", -1))

        # create topic vocab
        all_topics = []
        for a, b, topic in self.train_corpus[self.meta_id]:
            all_topics.append(topic)
        self.topic_vocab = [t for t, cnt in Counter(all_topics).most_common()]
        self.rev_topic_vocab = {t: idx for idx, t in enumerate(self.topic_vocab)}
        print("%d topics in train data" % len(self.topic_vocab))

        # get dialog act labels
        all_dialog_acts = []
        for dialog in self.train_corpus[self.dialog_id]:
            dialog_act_list = [feat[self.dialog_act_id] for
                               caller, utt, feat in dialog if feat is not None]
            all_dialog_acts.extend(dialog_act_list)
        self.dialog_act_vocab = [t for t, cnt in Counter(all_dialog_acts).most_common()]
        self.rev_dialog_act_vocab = {t: idx for idx, t in enumerate(self.dialog_act_vocab)}
        print(self.dialog_act_vocab)
        print("%d dialog acts in train data" % len(self.dialog_act_vocab))

    def save_vocab(self, vocab_path):
        vocab_file_dict = {}
        vocab_file_dict["vocab"] = self.vocab
        vocab_file_dict["rev_vocab"] = self.rev_vocab

        vocab_file_dict["topic_vocab"] = self.topic_vocab
        vocab_file_dict["rev_topic_vocab"] = self.rev_topic_vocab

        vocab_file_dict["dialog_act_vocab"] = self.dialog_act_vocab
        vocab_file_dict["rev_dialog_act_vocab"] = self.rev_dialog_act_vocab

        with open(vocab_path, 'wb') as vocab_writer:
            pickle.dump(vocab_file_dict, vocab_writer)

    def load_vocab(self, vocab_path):
        with open(vocab_path, 'rb') as vocab_reader:
            vocab_file_dict = pickle.load(vocab_reader)

        self.vocab = vocab_file_dict["vocab"]
        self.rev_vocab = vocab_file_dict["rev_vocab"]
        self.unk_id = self.unk_id = self.rev_vocab["<unk>"]

        print("<d> index %d" % self.rev_vocab["<d>"])

        self.topic_vocab = vocab_file_dict["topic_vocab"]
        self.rev_topic_vocab = vocab_file_dict["rev_topic_vocab"]
        print("%d topics in train data" % len(self.topic_vocab))

        self.dialog_act_vocab = vocab_file_dict["dialog_act_vocab"]
        self.rev_dialog_act_vocab = vocab_file_dict["rev_dialog_act_vocab"]
        print(self.dialog_act_vocab)
        print("%d dialog acts in train data" % len(self.dialog_act_vocab))

        print("Successfully loaded.")

    def load_word2vec(self):
        if not os.path.exists(self.word_vec_path):
            return
        with open(self.word_vec_path, "r") as f:
            lines = f.readlines()
        raw_word2vec = {}
        for l in lines:
            w, vec = l.split(" ", 1)
            raw_word2vec[w] = vec
        # clean up lines for memory efficiency
        self.word2vec = []
        oov_cnt = 0
        for v in self.vocab:
            str_vec = raw_word2vec.get(v, None)
            if str_vec is None:
                oov_cnt += 1
                vec = np.random.randn(self.word2vec_dim) * 0.1
            else:
                vec = np.fromstring(str_vec, sep=" ")
            self.word2vec.append(vec)
        print("word2vec cannot cover %f vocab" % (float(oov_cnt)/len(self.vocab)))

    def get_dialog_corpus(self):
        def _to_id_corpus(data):
            results = []
            for dialog in data:
                temp = []
                # convert utterance and feature into numeric numbers
                for utt, floor, feat in dialog:
                    if feat is not None:
                        id_feat = list(feat)
                        id_feat[self.dialog_act_id] = self.rev_dialog_act_vocab[feat[self.dialog_act_id]]
                    else:
                        id_feat = None
                    temp.append(([self.rev_vocab.get(t, self.unk_id) for t in utt], floor, id_feat))
                results.append(temp)
            return results
        id_train = _to_id_corpus(self.train_corpus[self.dialog_id])
        id_valid = _to_id_corpus(self.valid_corpus[self.dialog_id])
        id_test = _to_id_corpus(self.test_corpus[self.dialog_id])
        return {'train': id_train, 'valid': id_valid, 'test': id_test}