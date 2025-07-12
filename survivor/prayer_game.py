import os
import sys

try:
    from rapidfuzz import process, fuzz
except ImportError:
    sys.stderr.write("Error: rapidfuzz is required. Install with `pip install rapidfuzz`\n")
    sys.exit(1)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PRAYERS_DIR = os.path.join(ROOT_DIR, "survivor/prayers")
FILE_ENCODING = 'utf-8'

class PrayerCounter:
    def _load_prayers(self, directory: str = PRAYERS_DIR):
        """
        Read all files in the given directory and return a list of
        (filename, content) tuples.
        """
        prayers = []
        if not os.path.isdir(directory):
            sys.stderr.write(f"Error: directory '{directory}' not found.\n")
            sys.exit(1)
        for fname in os.listdir(directory):
            path = os.path.join(directory, fname)
            if os.path.isfile(path):
                print(f"loading prayer {path}")
                try:
                    with open(path, encoding=FILE_ENCODING) as f:
                        content = f.read().strip().replace("\n", " ")
                        if content:
                            prayers.append((fname, content))
                except Exception as e:
                    sys.stderr.write(f"Warning: could not read '{path}': {e}\n")
        self.prayers = prayers


    def __init__(self, directory: str = PRAYERS_DIR):
        self._load_prayers(directory=directory)

    def match_prayer(self, query: str, confidence_threshold=0.75):
        """
        Given an input query string and a list of (filename, content),
        return (best_filename, score) using fuzzy matching.
        """
        query = query.lower()
        # Build a mapping of filename -> content

        choices = {filename: text.lower() for filename, text in self.prayers}
        # Use token sort ratio for order-independent fuzzy matching
        best = process.extractOne(query, choices, scorer=fuzz.token_sort_ratio)
        # extractOne returns (key, score, _index)
        if best:
            if best[1] > confidence_threshold * 100:
                print("prayer matched.")
                return best[2], best[1]
        return None, 0



def main():
    prayer_counter = PrayerCounter()
    text = input("What is your prayer?\n")
    match, score = prayer_counter.match_prayer(text)
    if match:
        print(f"Match: {match}\nConfidence: {score:.2f}")
        sys.exit(0)
    else:
        print("No matching prayer found.")
        sys.exit(1)


if __name__ == "__main__":
    main()
