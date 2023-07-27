Source code translator
======================
Rough and ready way to translate source code into English. It will extract and translate blocks of non-ASCII
text and then write it all back to the file. It expects you to pipe/pass as args a list of file paths to translate.
It uses GoogleTranslate from the deep_translate library and works best via pool of rotating proxies. There's no reason
the other deep_translate backends wouldn't work, just untested.

It's been tested with Russian and Chinese source and does as good a job as one could hope. YMMV but it seems to be okay 
at not mangling files.

It batches things up and handles Google's antics as best it can, there's a fair bit of juggling but it should go as
quickly as it can without filling the files with nonsense.

I made it because the Chinese particularly release a lot of interesting code now, and unfortunately its just squiggles
to me.

Prerequisites
-------------
You need Python 3 to run this program, and the following Python packages must also be installed:
argparse
cypunct
charset-normalizer
deep_translator
thefuzz