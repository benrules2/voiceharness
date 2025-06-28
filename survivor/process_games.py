import os
import json
from survivor.prayer_game import PrayerCounter

class SurvivorGames:
    def __init__(self):
        self.prayer_tracker = PrayerCounter()
        # Initialize the prayer score file relative to the project root directory
        ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.score_file = os.path.join(ROOT_DIR, "survivor/prayers/prayer_score.json")
        if not os.path.exists(self.score_file):
            with open(self.score_file, "w") as f:
                json.dump({}, f)

    def update_prayer_score(self, prayer_key):
        # Load current scores, increment the count for prayer_key, and save back to file.
        with open(self.score_file, "r") as f:
            scores = json.load(f)
        scores[prayer_key] = scores.get(prayer_key, 0) + 1
        with open(self.score_file, "w") as f:
            json.dump(scores, f)

    def request_cb(self, text):
        prayer, score = self.prayer_tracker.match_prayer(text)
        if prayer: 
            self.update_prayer_score(prayer)
