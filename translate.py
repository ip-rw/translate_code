import argparse
import concurrent
import random
import string
import sys
import time
import unicodedata
import re
from charset_normalizer import from_path
from deep_translator import GoogleTranslator
from thefuzz import fuzz
from thefuzz.process import extract
import concurrent.futures


def char_batch(iterable, n=1):
    char_batch = set()
    total_char = 0
    for text in iterable:
        total_char += len(text)
        char_batch.add(text)
        if total_char > n:
            yield list(char_batch)
            char_batch.clear()
            total_char = 0
    yield list(char_batch)


def random_delimiter():
    a, b = tuple(random.choices(string.ascii_letters, k=2))
    delimiter = f" {a.upper()}{b.lower() * random.randint(1, 5)}{a.upper()} "
    delimiter_regex = "\\s*".join([f'{c}+' for c in delimiter[1:-1]])
    return delimiter, delimiter_regex


def find_most_common_string(contains_dupes, threshold=70, scorer=fuzz.token_set_ratio):
    contains_dupes = [e for e in contains_dupes if len(e) > 0]
    extractor = []
    for item in contains_dupes:
        matches = extract(item, contains_dupes, limit=None, scorer=scorer)
        filtered = [x for x in matches if x[1] > threshold]

        if len(filtered) > 1:
            filtered = sorted(filtered, key=lambda x: x[1])
            filter_sort = sorted(filtered, key=lambda x: len(x[0]), reverse=True)
            extractor.append(filter_sort[-1][0])

    keys = {}
    for e in extractor:
        keys[e] = 1
    return list(keys.keys())


def get_solved_keys(translated, min_score=80):
    solved = []
    for key in translated:
        dupes = find_most_common_string(translated[key])
        if len(dupes) > 0:
            # print(dupes)
            solved.append(key)
    return solved


def translate_batch(batch, translator, translated_blocks, retries=15):
    batch_size = len(batch)
    delimiter, delimiter_regex = random_delimiter()
    random.shuffle(batch)  # we do this so we can retry cache free if google decides to mangle our delimiters
    try:
        comb = delimiter.join(batch)
        tlated = re.sub(r"[\n\"'|]", "", str(translator.translate(comb)))
        time.sleep(2)

        if not str(tlated):
            return
        output = re.sub(delimiter_regex, delimiter, tlated, re.I | re.U)
        blocks = output.split(delimiter)

        for i, translation in enumerate(blocks):
            if i >= len(batch): break
            if batch[i] not in translated_blocks:
                translated_blocks[batch[i]] = []
            translated_blocks[batch[i]].append(translation.strip())

        removed = get_solved_keys(translated_blocks)
        if len(removed) > 0:
            [batch.remove(x) for x in removed if x in batch]
            print("removing %d keys from batch" % (batch_size - len(batch)))

        if len(batch) > 0 and len(blocks) != batch_size:
            if retries > 0:
                print(
                    "%d/%d - retrying in a different "
                    "order" % (
                        len(blocks), len(batch)))
                # print(translated)
                return translate_batch(batch, translator, translated_blocks, retries - 1)
            else:
                print(
                    "%d/%d - giving up after 5" % (
                        len(blocks), len(batch)))

    except Exception as e:
        # raise e
        if retries > 0:
            print(f"unknown exception ({e}). waiting 5 seconds")
            time.sleep(5)
            return translate_batch(batch, translator, translated_blocks, retries - 1)
        else:
            print(f"unknown exception ({e}). giving up.")

    return translated_blocks


def get_punctuation_by_category(categories):
    """Return a set of punctuation characters based on given unicode categories."""
    punctuations = set()
    for i in range(0x10FFFF):  # loop over all valid unicode codepoints
        char = chr(i)
        if unicodedata.category(char) in categories:
            punctuations.add(char)
    return punctuations


# Create the set of characters based on the Unicode categories and additional characters
fs = get_punctuation_by_category(["Pf", "Pi"]).union(frozenset("><\"'/${}*|;"))


def is_punctuation(s):
    """Check if the entire string consists of punctuation characters."""
    return all(unicodedata.category(c).startswith('P') for c in s)


def extract_unicode_blocks(text):
    blocks = set()
    for line in text.splitlines():
        for chunk in re.split("|".join(map(re.escape, fs)), line):
            norm = unicodedata.normalize('NFKC', chunk.strip())
            if norm.isascii() or is_punctuation(norm):
                # print(norm)
                continue
            # else:
            #     print(norm)
            blocks.add(chunk.strip())
    return blocks


def translate_file(path, translator, translated_chunks):
    try:
        d = from_path(path)
        file_contents = str(d.best())
        blocks_in_file = extract_unicode_blocks(file_contents)
        blocks_to_translate = [b for b in blocks_in_file if b not in translated_chunks]
        if len(blocks_in_file) - len(blocks_to_translate) > 0:
            print("%d cached" % (len(blocks_in_file) - len(blocks_to_translate)))

        if not blocks_to_translate:
            print(f"nothing to translate in {path}")
            return
        print("%d blocks to translate %s" % (len(blocks_to_translate), path))

        num_translated = 0
        total = len(blocks_to_translate)

        for batch in char_batch(blocks_to_translate, 1500):
            batch_size = len(batch)
            out = translate_batch(batch, translator, {})
            if out and len(out) > 0:
                num_translated += len(out)
                for o in out:
                    out[o] = [a for a in out[o] if len(a.strip()) > 0 and not is_punctuation(a)]
                    if o not in translated_chunks:
                        translated_chunks[o] = []
                    translated_chunks[o].extend(out[o])
                print("translated %d/%d of a total of %d/%d blocks in %s" % (
                    len(out), batch_size, num_translated, total, path))

        keys = list(translated_chunks.keys())
        keys.sort(key=len, reverse=True)
        for key in keys:
            if key in blocks_in_file and key in translated_chunks:
                found = find_most_common_string(translated_chunks[key])
                if len(found) == 0 and len(translated_chunks[key]) > 0:
                    found.append(translated_chunks[key][-1])
                if found:
                    if len(translated_chunks[key]) > 1:
                        print(translated_chunks[key])
                    print(key, " => ", found[0].replace('\u200b', ''))
                    file_contents = file_contents.replace(key, found[0].replace('\u200b', ''))
        f = open(path, "w")
        f.write(file_contents)

    except Exception as e:
        # raise (e)
        print(e)


def main(arg):
    proxies = {"https": arg.proxy, "http": arg.proxy} if arg.proxy else {}
    translator_engine = GoogleTranslator(source='auto', target='en', proxies=proxies)

    translated_chunks = {}
    if len(arg.paths) > 0:
        paths = arg.paths
    else:
        paths = [p.strip() for p in sys.stdin.readlines()]

    with concurrent.futures.ThreadPoolExecutor(max_workers=arg.threads) as executor:
        executor.map(lambda p: translate_file(p, translator_engine, translated_chunks), paths)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Translate source code')
    parser.add_argument('--threads', type=int, default=1, help='Number of threads to use (default 1)')
    parser.add_argument('--proxy', type=str, help='Proxy to use for translation')
    parser.add_argument('paths', nargs="*", help='Paths to translate')
    args = parser.parse_args()
    main(args)