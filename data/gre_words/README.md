from https://ankiweb.net/shared/info/2134439881

copyright status uncertain; presumed to be acceptable for transformative
usage.

generation instructions:

1) unzip the apkg
2) sqlite3 collection.anki2 "SELECT * FROM notes;" > notes.txt
3) python3 convert_notes_to_json.py notes.txt notes.json
