import sqlite3
import openai

# Explicitly set API key at the module level
OPENAI_API_KEY = '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'
openai.api_key = OPENAI_API_KEY

if not openai.api_key:
    raise ValueError("OpenAI API key is missing. Ensure it is set properly.")

# Database file name
DATABASE_NAME = "spotify_plays.db"

class DatabaseRoaster:
    def __init__(self):
        """Initialize and verify database structure."""
        self._verify_database()

    def _verify_database(self):
        """Ensure the database structure matches expected tables."""
        required_tables = {
            'songs': ['track_id', 'name', 'artist', 'album', 'duration_ms', 'uri'],
            'plays': ['play_id', 'track_id', 'timestamp', 'latitude', 'longitude']
        }
        
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            
            # Check table existence
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}
            
            if not required_tables.keys() <= existing_tables:
                raise ValueError("Database is missing required tables.")
                
            # Check column structure
            for table, columns in required_tables.items():
                cursor.execute(f"PRAGMA table_info({table})")
                existing_columns = {row[1] for row in cursor.fetchall()}
                if not set(columns) <= existing_columns:
                    raise ValueError(f"Table {table} has an incorrect structure.")

    def get_top_tracks(self, limit=10):
        """Retrieve the most played tracks from the database."""
        query = """
            SELECT s.name, s.artist, COUNT(p.track_id) as play_count
            FROM plays p
            JOIN songs s ON p.track_id = s.track_id
            GROUP BY s.track_id
            ORDER BY play_count DESC
            LIMIT ?
        """
        
        with sqlite3.connect(DATABASE_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, (limit,))
            tracks = cursor.fetchall()

        if not tracks:
            print("DEBUG: No play history found.")
        else:
            print("DEBUG: Top tracks retrieved from database.")

        return tracks

    def generate_roast(self):
        """Generate a roast based on the most played tracks."""
        tracks = self.get_top_tracks()
        if not tracks:
            return "No play history found - your music taste is... nonexistent? 🤔"

        track_list = "\n".join(
            [f"{i+1}. {row['name']} by {row['artist']} (played {row['play_count']}x)"
             for i, row in enumerate(tracks)]
        )

        print(f"DEBUG: Sending the following track list to OpenAI:\n{track_list}")  # Debugging print

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": f"""Create a funny roast about someone's music taste:
                    {track_list}
                    
                    Rules:
                    - Playfully mock musical choices
                    - Reference specific artists/songs
                    - Mention play counts if interesting
                    - Max 2 sentences
                    - Include emojis"""
                }],
                temperature=0.8,
                max_tokens=250
            )
            
            roast_text = response.choices[0].message['content'].strip()
            print("DEBUG: OpenAI Response Received:\n", roast_text)  # Print response
            return roast_text

        except Exception as e:
            print(f"DEBUG: OpenAI API Call Error - {str(e)}")  # Debugging print
            raise RuntimeError(f"Roast failed: {str(e)}")

if __name__ == "__main__":
    try:
        roaster = DatabaseRoaster()
        result = roaster.generate_roast()
        
        print("\n🔥 YOUR SPOTIFY ROAST 🔥")
        print(result)
        print("\nBased on your most played tracks:")
        
        for i, track in enumerate(roaster.get_top_tracks()):
            print(f"{i+1}. {track['name']} by {track['artist']} ({track['play_count']} plays)")
            
    except Exception as e:
        print(f"Error: {str(e)}")
