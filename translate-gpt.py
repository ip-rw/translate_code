import os
import argparse
import sys
import re
import unicodedata
from charset_normalizer import from_path
import concurrent.futures
import openai
from GlotScript import get_script_predictor

sp = get_script_predictor()
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

def translate_with_chatgpt(batch):
    response = openai.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {
                "role": "system",
                "content": """
Your role involves translating non-English text from source code into concise English. These translations will replace the original text in the code, so brevity is key. Focus on translating GUI labels concisely, treating them as labels or proper nouns rather than detailed descriptions. If possible, use acronyms, omit standard stopwords, and use shorter English equivalents to keep the translations compact.

Maintain any existing punctuation or symbols in the translations, as they are critical for preserving code context and functionality.

Given the compact nature of Chinese, be mindful of the layout impact when translating brief Chinese phrases into potentially longer English phrases.

Present your translations line-by-line, ensuring that the number of output lines matches the number of input lines exactly. This alignment is crucial for integrating the translations back into the source code seamlessly."""
            },
            {
                "role": "user",
                "content": "\n".join(batch)
            }
        ], top_p=1, frequency_penalty=0, stream=True)
    content = ""
    for chunk in response:
        delta_content = chunk.choices[0].delta.content if chunk.choices[0].delta.content is not None else None
        if delta_content:
            print(delta_content, end="", flush=True, )
            content += delta_content
        #      time.sleep(0.1)  # Delay
        else:
            print("done!")

    translations = content.split("\n")  #response.choices[0].message.content.strip().split("\n")
    return dict(zip(batch, translations))


def get_punctuation_by_category(categories):
    """Return a set of punctuation characters based on given unicode categories."""
    punctuations = set()
    for i in range(0x10FFFF):  # loop over all valid unicode codepoints
        char = chr(i)
        if unicodedata.category(char) in categories:
            punctuations.add(char)
    return punctuations


# Create the set of characters based on the Unicode categories and additional characters
fs = get_punctuation_by_category(["Pf", "Pi"]).union(frozenset("><\"`'/${}*|;"))


def is_punctuation(s):
    """Check if the entire string consists of punctuation characters."""
    return all(unicodedata.category(c).startswith('P') for c in s)


escapes = ['n','r','t','b','f','x']
def extract_unicode_blocks(text):
    blocks = set()
    for line in text.splitlines():
        line = line.strip()
        for chunk in re.split("|".join(map(re.escape, fs)), line):
            norm = unicodedata.normalize('NFKC', chunk.strip())
            chunk = re.sub(r"(^[^\w]+)|([^\w]+$)", "", chunk)
            if re.match(r"^[nrt][^a-z]", chunk):
                chunk = chunk[1:]
            langs = sp(chunk.strip())
            if norm.isascii() or is_punctuation(norm) or langs[0] == "Zyyy":
                continue
            #    print(chunk.strip())
            blocks.add(chunk.strip())
    return blocks


def translate_file(path, translated_chunks):
    try:
        print(path)
        d = from_path(path)
        file_contents = str(d.best())
        blocks_in_file = extract_unicode_blocks(file_contents)
        blocks_to_translate = [b for b in blocks_in_file if b not in translated_chunks]
        if len(blocks_in_file) - len(blocks_to_translate) > 0:
            print("%d cached" % (len(blocks_in_file) - len(blocks_to_translate)))

        if not blocks_to_translate:
            #print(f"nothing to translate in {path}")
            return
        print("%d blocks to translate %s" % (len(blocks_to_translate), path))
        #print(blocks_to_translate)
        num_translated = 0
        total = len(blocks_to_translate)

        translations = translate_with_chatgpt(blocks_to_translate)
        translated_chunks.update(translations)

        keys = list(translated_chunks.keys())
        keys.sort(key=len, reverse=True)
        for key in keys:
            if key in blocks_in_file and key in translated_chunks:
                file_contents = file_contents.replace(key, translated_chunks[key])
                print(key, " => ", translated_chunks[key])

        f = open(path, "w")
        f.write(file_contents)
    except Exception as e:
        print(e)


def main(args):
    translated_chunks = {}

    paths = args.paths if args.paths else [p.strip() for p in sys.stdin.readlines()]

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        executor.map(lambda p: translate_file(p, translated_chunks), paths)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Translate source code')
    parser.add_argument('--threads', type=int, default=1, help='Number of threads to use (default 1)')
    parser.add_argument('paths', nargs="*", help='Paths to translate')
    args = parser.parse_args()
    main(args)
