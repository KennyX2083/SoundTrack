import sqlite3
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import openai
from collections import Counter
from datetime import datetime
import json
import tkinter as tk
from tkinter import ttk
import threading
import os
from PIL import Image, ImageTk
import io

# Spotify API Credentials
SPOTIPY_CLIENT_ID = 'client-id'
SPOTIPY_CLIENT_SECRET = 'client-secret'
SPOTIPY_REDIRECT_URI = 'http://localhost:8888/callback'
SCOPE = ('user-read-recently-played user-top-read user-library-read')

# Google API Credentials
GOOGLE_API_KEY = 'AIzaSyAcXfKjFkZaN4p6Fc8iu5kKWBiaJBXUSzE'
GOOGLE_CX = 'c21816f5610004210'

# OpenAI API Key
openai.api_key = 'api-key'

class SpotifyRewind:
    def __init__(self, db_name='spotify_plays.db'):
        self.db_name = db_name
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope=SCOPE
        ))
        self.root = tk.Tk()
        self.root.title("Spotify Rewind")
        self.root.geometry("800x600")
        self.current_frame = None
        self.categories = ["Top Songs", "Top Artists", "Top Genres", "Top Locations", "Summary"]
        self.current_category_index = 0
        self.rewind_data = self.generate_rewind()
        self.update_display()
        self.root.mainloop()
    
    def get_play_data(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.name, s.artist, p.timestamp, p.latitude, p.longitude
                FROM plays p
                JOIN songs s ON p.track_id = s.track_id
            ''')
            return cursor.fetchall()
    
    def generate_rewind(self):
        data = self.get_play_data()
        if not data:
            return None
        
        song_counts = Counter((entry[0], entry[1]) for entry in data)
        top_songs = song_counts.most_common(5)
        
        artist_counts = Counter(entry[1] for entry in data)
        top_artists = artist_counts.most_common(5)
        
        top_genres = self.get_top_genres([artist[0] for artist in top_artists])
        
        location_counts = Counter((entry[3], entry[4]) for entry in data if entry[3] and entry[4])
        top_locations = location_counts.most_common(5)
        
        summary = self.generate_summary(top_songs, top_artists, top_genres, top_locations)
        
        rewind_data = {
            "Top Songs": [],
            "Top Artists": [],
            "Top Genres": [],
            "Top Locations": [],
            "Summary": {"text": summary, "image": None}
        }
        
        # Top Songs
        for (song, artist), count in top_songs:
            image_url = self.get_image_url(f"{song} {artist} album cover")
            photo = self.get_photo_image(image_url)
            rewind_data["Top Songs"].append({
                "name": song,
                "artist": artist,
                "count": count,
                "photo": photo
            })
        
        # Top Artists
        for artist, count in top_artists:
            image_url = self.get_image_url(f"{artist} music artist")
            photo = self.get_photo_image(image_url)
            rewind_data["Top Artists"].append({
                "name": artist,
                "count": count,
                "photo": photo
            })
        
        # Top Genres
        for genre, count in top_genres:
            image_url = self.get_image_url(f"{genre} music genre")
            photo = self.get_photo_image(image_url)
            rewind_data["Top Genres"].append({
                "name": genre,
                "count": count,
                "photo": photo
            })
        
        # Top Locations
        for (lat, lon), count in top_locations:
            location_name = self.get_location_name(lat, lon)
            image_url = self.get_image_url(f"{location_name} city view")
            photo = self.get_photo_image(image_url)
            rewind_data["Top Locations"].append({
                "name": location_name,
                "count": count,
                "photo": photo
            })
        
        # Summary Image
        image_url = self.get_image_url("music celebration")
        rewind_data["Summary"]["image"] = self.get_photo_image(image_url)
        
        return rewind_data
    
    def get_top_genres(self, artist_names):
        genres = []
        for artist in artist_names:
            results = self.sp.search(q=artist, type='artist', limit=1)
            if results['artists']['items']:
                genres.extend(results['artists']['items'][0]['genres'])
        return Counter(genres).most_common(5)
    
    def generate_summary(self, top_songs, top_artists, top_genres, top_locations):
        prompt = f"""
        Here is the user's Spotify rewind:

        Top Songs:
        {top_songs}

        Top Artists:
        {top_artists}

        Top Genres:
        {top_genres}

        Top Listening Locations:
        {top_locations}

        Generate a fun and quirky summary about their listening habits. Make it entertaining!
        """

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a witty AI music analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300  # Limiting the response to 300 tokens
        )
        return response['choices'][0]['message']['content']
    
    def get_image_url(self, query):
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'q': query,
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CX,
            'searchType': 'image'
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                results = response.json()
                if results.get('items'):
                    return results['items'][0]['link']
            return None
        except Exception as e:
            print(f"Error fetching image: {e}")
            return None
    
    def get_photo_image(self, image_url):
        if not image_url:
            return None
        try:
            response = requests.get(image_url, stream=True, timeout=10)
            if response.status_code == 200:
                image_data = response.content
                image = Image.open(io.BytesIO(image_data))
                image = image.resize((150, 150), Image.LANCZOS)
                return ImageTk.PhotoImage(image)
            return None
        except Exception as e:
            print(f"Error loading image: {e}")
            return None
    
    def get_location_name(self, lat, lon):
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'latlng': f"{lat},{lon}",
            'key': GOOGLE_API_KEY
        }
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('results'):
                    return data['results'][0]['formatted_address']
            return f"Lat: {lat}, Lon: {lon}"
        except Exception as e:
            print(f"Error geocoding: {e}")
            return f"Lat: {lat}, Lon: {lon}"
    
    def update_display(self):
        if self.current_frame:
            self.current_frame.destroy()
        
        self.current_frame = tk.Frame(self.root, bg='black')
        self.current_frame.pack(fill=tk.BOTH, expand=True)
        
        if not self.rewind_data:
            label = tk.Label(self.current_frame, text="No data available", fg='white', bg='black')
            label.pack()
            self.root.after(20000, self.update_display)
            return
        
        current_category = self.categories[self.current_category_index]
        category_data = self.rewind_data.get(current_category, [])
        
        title_label = tk.Label(self.current_frame, text=current_category, fg='cyan', bg='black', font=('Arial', 18, 'bold'))
        title_label.pack(pady=10)
        
        if current_category == "Summary":
            text_frame = tk.Frame(self.current_frame, bg='black')
            text_frame.pack(pady=20, fill=tk.BOTH, expand=True)
            
            text_widget = tk.Label(text_frame, text=self.rewind_data["Summary"]["text"], fg='white', bg='black', wraplength=500, justify='left')
            text_widget.pack(side=tk.LEFT, padx=20)
            
            if self.rewind_data["Summary"]["image"]:
                image_label = tk.Label(text_frame, image=self.rewind_data["Summary"]["image"], bg='black')
                image_label.image = self.rewind_data["Summary"]["image"]
                image_label.pack(side=tk.RIGHT, padx=20)
        else:
            for item in category_data:
                item_frame = tk.Frame(self.current_frame, bg='black')
                item_frame.pack(pady=10, fill=tk.X)
                
                if item['photo']:
                    img_label = tk.Label(item_frame, image=item['photo'], bg='black')
                    img_label.image = item['photo']
                    img_label.pack(side=tk.LEFT, padx=10)
                
                text = item['name']
                if 'artist' in item:
                    text += f" by {item['artist']}"
                if 'count' in item:
                    text += f" - {item['count']} plays"
                
                text_label = tk.Label(item_frame, text=text, fg='white', bg='black', font=('Arial', 12))
                text_label.pack(side=tk.LEFT)
        
        self.current_category_index = (self.current_category_index + 1) % len(self.categories)
        self.root.after(20000, self.update_display)

if __name__ == "__main__":
    SpotifyRewind()
