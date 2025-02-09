import sqlite3
from datetime import datetime
from Roast_test import DatabaseRoaster
from rewing import SpotifyRewind
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import tkinter as tk
from tkinter import ttk, messagebox
from threading import Thread
import time
import geocoder
import folium
import webbrowser
import os
import requests
from io import BytesIO
from PIL import Image, ImageTk
import socket

import openai

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        return s.getsockname()[1]

# Spotify API credentials
SPOTIPY_CLIENT_ID = 'put-id-here'
SPOTIPY_CLIENT_SECRET = 'put-secret-here'
SPOTIPY_REDIRECT_URI = 'http://localhost:3000'

import tkinter as tk

root = tk.Tk()

# Create a Text widget
text_widget = tk.Text(root, wrap="none")
text_widget.pack(side="left", fill="both", expand=True)

# Create a Scrollbar widget
scrollbar = tk.Scrollbar(root, command=text_widget.yview)
scrollbar.pack(side="right", fill="y")

# Configure the Text widget to use the Scrollbar
text_widget.config(yscrollcommand=scrollbar.set)

# Insert some text to make it scrollable
for i in range(50):
    text_widget.insert("end", f"This is line {i}\n")

root.mainloop()

SCOPE = ('user-read-currently-playing user-modify-playback-state '
         'user-read-playback-state user-top-read user-library-modify '
         'user-library-read')

class DatabaseManager:
    def __init__(self, db_name='spotify_plays.db'):
        self.db_name = db_name
        self.create_tables()

    def create_tables(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS songs (
                    track_id TEXT PRIMARY KEY,
                    name TEXT,
                    artist TEXT,
                    album TEXT,
                    duration_ms INTEGER,
                    uri TEXT,
                    album_art_url TEXT  -- 新增字段
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS plays (
                    play_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id TEXT,
                    timestamp DATETIME,
                    latitude REAL,
                    longitude REAL,
                    FOREIGN KEY(track_id) REFERENCES songs(track_id)
                )
            ''')
            conn.commit()

    def log_play(self, track, location):
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO songs 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    track['id'],
                    track['name'],
                    ', '.join([a['name'] for a in track['artists']]),
                    track['album']['name'],
                    track['duration_ms'],
                    track['uri'],
                    track['album']['images'][0]['url'] if track['album']['images'] else None  # 新增字段
                ))
                cursor.execute('''
                    INSERT INTO plays 
                    VALUES (NULL, ?, ?, ?, ?)
                ''', (
                    track['id'],
                    datetime.now().isoformat(),
                    location[0],
                    location[1]
                ))
                conn.commit()
        except sqlite3.Error as e:
            print("Database error:", e)

    def get_play_history(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.name, s.artist, s.album, p.timestamp, p.latitude, p.longitude, s.album_art_url
                FROM plays p
                JOIN songs s ON p.track_id = s.track_id
                ORDER BY p.timestamp DESC
            ''')
            return cursor.fetchall()

class SpotifyPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Spotify Player")
        self.root.geometry("1000x800")
        
        self.db = DatabaseManager()
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope=SCOPE,
            cache_path='.spotify_cache'))
        self.device_id = None
        self.update_devices()
        
        self.create_widgets()
        self.current_track_id = None
        self.current_image = None
        self.update_interval = 5000
        self.update_playback_info()

    def create_widgets(self):
        # Navigation Bar
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(side="top", fill=tk.X, padx=10, pady=5)

        self.home_button = ttk.Button(nav_frame, text="Home", command=self.show_home)
        self.home_button.pack(side=tk.LEFT, padx=5)

        self.search_button = ttk.Button(nav_frame, text="Search", command=self.show_search)
        self.search_button.pack(side=tk.LEFT, padx=5)

        self.history_button = ttk.Button(nav_frame, text="History", command=self.show_play_history)
        self.history_button.pack(side=tk.LEFT, padx=5)

        self.map_button = ttk.Button(nav_frame, text="Map", command=self.show_listening_map)
        self.map_button.pack(side=tk.LEFT, padx=5)


        # Add "Roast Me" button
        self.roast_button = ttk.Button(nav_frame, text="Roast Me", command=self.show_roast)
        self.roast_button.pack(side=tk.LEFT, padx=5)

        self.rewind_button = ttk.Button(nav_frame, text="Rewind", command=self.show_rewind)
        self.rewind_button.pack(side=tk.LEFT, padx=5)

        # Main Content Container
        self.container = ttk.Frame(self.root)
        self.container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Bottom Control Panel
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(side="bottom", fill=tk.X, padx=10, pady=5)

        # Track Info
        track_info_frame = ttk.Frame(bottom_frame)
        track_info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.album_art_label = ttk.Label(track_info_frame)
        self.album_art_label.pack(side=tk.LEFT, padx=5)

        text_info_frame = ttk.Frame(track_info_frame)
        text_info_frame.pack(side=tk.LEFT, fill=tk.Y)

        self.song_label = ttk.Label(text_info_frame, text="No track playing", font=('Helvetica', 10, 'bold'))
        self.song_label.pack(anchor=tk.W)
        self.artist_label = ttk.Label(text_info_frame, text="", font=('Helvetica', 9))
        self.artist_label.pack(anchor=tk.W)
        self.album_label = ttk.Label(text_info_frame, text="", font=('Helvetica', 9))
        self.album_label.pack(anchor=tk.W)

        # Playback Controls
        control_frame = ttk.Frame(bottom_frame)
        control_frame.pack(side=tk.RIGHT, padx=5)

        self.prev_button = ttk.Button(control_frame, text="⏮", command=self.previous_track)
        self.prev_button.pack(side=tk.LEFT, padx=2)
        self.play_button = ttk.Button(control_frame, text="⏸", command=self.play_pause)
        self.play_button.pack(side=tk.LEFT, padx=2)
        self.next_button = ttk.Button(control_frame, text="⏭", command=self.next_track)
        self.next_button.pack(side=tk.LEFT, padx=2)
        self.like_button = ttk.Button(control_frame, text="♡", command=self.toggle_like)
        self.like_button.pack(side=tk.LEFT, padx=5)

        # Initialize frames
        self.home_frame = ttk.Frame(self.container)
        self.search_frame = ttk.Frame(self.container)
        self.history_frame = ttk.Frame(self.container)
        self.roast_frame = ttk.Frame(self.container)  # New frame for Roast Me
        self.rewind_frame = ttk.Frame(self.container) 

        self.create_home_frame()
        self.show_home()


    def create_home_frame(self):
        # Liked Songs
        liked_frame = ttk.LabelFrame(self.home_frame, text="Liked Songs")
        liked_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.liked_canvas = tk.Canvas(liked_frame)
        self.liked_scrollbar = ttk.Scrollbar(liked_frame, orient="vertical", command=self.liked_canvas.yview)
        self.liked_scrollable_frame = ttk.Frame(self.liked_canvas)

        self.liked_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.liked_canvas.configure(
                scrollregion=self.liked_canvas.bbox("all")
            )
        )

        self.liked_canvas.create_window((0, 0), window=self.liked_scrollable_frame, anchor="nw")
        self.liked_canvas.configure(yscrollcommand=self.liked_scrollbar.set)

        self.liked_canvas.pack(side="left", fill="both", expand=True)
        self.liked_scrollbar.pack(side="right", fill="y")

        # Playlists
        playlist_frame = ttk.LabelFrame(self.home_frame, text="Playlists")
        playlist_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.playlist_canvas = tk.Canvas(playlist_frame)
        self.playlist_scrollbar = ttk.Scrollbar(playlist_frame, orient="vertical", command=self.playlist_canvas.yview)
        self.playlist_scrollable_frame = ttk.Frame(self.playlist_canvas)

        self.playlist_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.playlist_canvas.configure(
                scrollregion=self.playlist_canvas.bbox("all")
            )
        )

        self.playlist_canvas.create_window((0, 0), window=self.playlist_scrollable_frame, anchor="nw")
        self.playlist_canvas.configure(yscrollcommand=self.playlist_scrollbar.set)

        self.playlist_canvas.pack(side="left", fill="both", expand=True)
        self.playlist_scrollbar.pack(side="right", fill="y")

        # Albums
        album_frame = ttk.LabelFrame(self.home_frame, text="Albums")
        album_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.album_canvas = tk.Canvas(album_frame)
        self.album_scrollbar = ttk.Scrollbar(album_frame, orient="vertical", command=self.album_canvas.yview)
        self.album_scrollable_frame = ttk.Frame(self.album_canvas)

        self.album_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.album_canvas.configure(
                scrollregion=self.album_canvas.bbox("all")
            )
        )

        self.album_canvas.create_window((0, 0), window=self.album_scrollable_frame, anchor="nw")
        self.album_canvas.configure(yscrollcommand=self.album_scrollbar.set)

        self.album_canvas.pack(side="left", fill="both", expand=True)
        self.album_scrollbar.pack(side="right", fill="y")

        self.load_home_data()

    def load_home_data(self):
        try:
            # Liked Songs
            liked = self.sp.current_user_saved_tracks(limit=10)['items']
            for widget in self.liked_scrollable_frame.winfo_children():
                widget.destroy()
            
            for track in liked:
                t = track['track']
                frame = ttk.Frame(self.liked_scrollable_frame)
                frame.pack(fill=tk.X, padx=5, pady=2)
                
                ttk.Button(frame, text="▶", width=3, command=lambda uri=t['uri']: self.play_uri(uri)).pack(side=tk.LEFT)
                
                if t['album']['images']:
                    image_url = t['album']['images'][0]['url']
                    response = requests.get(image_url)
                    img = Image.open(BytesIO(response.content))
                    img = img.resize((32, 32), Image.Resampling.LANCZOS)
                    img_tk = ImageTk.PhotoImage(img)
                    label = ttk.Label(frame, image=img_tk)
                    label.image = img_tk  # 保持引用
                    label.pack(side=tk.LEFT, padx=5)
                
                ttk.Label(frame, text=t['name'], width=40).pack(side=tk.LEFT)
                ttk.Label(frame, text=', '.join(a['name'] for a in t['artists']), width=30).pack(side=tk.LEFT)
                ttk.Label(frame, text=t['album']['name'], width=30).pack(side=tk.LEFT)

            # Playlists
            playlists = self.sp.current_user_playlists(limit=10)['items']
            for widget in self.playlist_scrollable_frame.winfo_children():
                widget.destroy()
            
            for pl in playlists:
                frame = ttk.Frame(self.playlist_scrollable_frame)
                frame.pack(fill=tk.X, padx=5, pady=2)
                
                ttk.Label(frame, text=pl['name'], width=40).pack(side=tk.LEFT)
                ttk.Label(frame, text=pl['owner']['display_name'], width=20).pack(side=tk.LEFT)
                ttk.Button(frame, text="▶", 
                        command=lambda uri=pl['uri']: self.play_playlist(uri)).pack(side=tk.RIGHT)

            # Albums
            albums = self.sp.current_user_saved_albums(limit=10)['items']
            for widget in self.album_scrollable_frame.winfo_children():
                widget.destroy()
            
            for alb in albums:
                album = alb['album']
                album_frame = ttk.Frame(self.album_scrollable_frame)
                album_frame.pack(fill=tk.X, padx=5, pady=2)
                
                header_frame = ttk.Frame(album_frame)
                header_frame.pack(fill=tk.X)
                
                ttk.Button(header_frame, text="▶", width=3,
                        command=lambda uri=album['uri']: self.play_uri(uri)).pack(side=tk.LEFT)
            
                if album['images']:
                    image_url = album['images'][0]['url']
                    response = requests.get(image_url)
                    img = Image.open(BytesIO(response.content))
                    img = img.resize((32, 32), Image.Resampling.LANCZOS)
                    img_tk = ImageTk.PhotoImage(img)
                    label = ttk.Label(header_frame, image=img_tk)
                    label.image = img_tk 
                    label.pack(side=tk.LEFT, padx=5)
                
                ttk.Label(header_frame, text=album['name'], width=40).pack(side=tk.LEFT)
                ttk.Label(header_frame, text=', '.join(a['name'] for a in album['artists']), width=30).pack(side=tk.LEFT)
                ttk.Button(header_frame, text="▼", width=3,
                        command=lambda f=album_frame, a=album: self.toggle_album_tracks(f, a)).pack(side=tk.RIGHT)
                
                # Hidden track list frame
                self.track_list_frame = ttk.Frame(album_frame)
                self.track_list_frame.pack_forget()

        except Exception as e:
            print("Error loading home data:", e)

    def toggle_album_tracks(self, parent_frame, album):
        if hasattr(parent_frame, 'track_frame'):
            parent_frame.track_frame.pack_forget()
            del parent_frame.track_frame
        else:
            parent_frame.track_frame = ttk.Frame(parent_frame)
            parent_frame.track_frame.pack(fill=tk.X, padx=20)
            
            try:
                tracks = self.sp.album_tracks(album['id'])['items']
                for track in tracks:
                    track_frame = ttk.Frame(parent_frame.track_frame)
                    track_frame.pack(fill=tk.X, padx=5, pady=2)
                    
                    ttk.Button(track_frame, text="▶", width=3,
                            command=lambda uri=track['uri']: self.play_uri(uri)).pack(side=tk.LEFT)
                    
                    if album['images']:
                        image_url = album['images'][0]['url']
                        response = requests.get(image_url)
                        img = Image.open(BytesIO(response.content))
                        img = img.resize((32, 32), Image.Resampling.LANCZOS)
                        img_tk = ImageTk.PhotoImage(img)
                        label = ttk.Label(track_frame, image=img_tk)
                        label.image = img_tk
                        label.pack(side=tk.LEFT, padx=5)
                    
                    ttk.Label(track_frame, text=track['name'], width=40).pack(side=tk.LEFT)
                    ttk.Label(track_frame, text=', '.join(a['name'] for a in track['artists']), width=30).pack(side=tk.LEFT)
                    ttk.Label(track_frame, text=album['name'], width=30).pack(side=tk.LEFT)
            except Exception as e:
                print("Error loading album tracks:", e)

    def play_uri(self, uri):
        try:
            self.sp.start_playback(uris=[uri])
            self.update_playback_info()
        except Exception as e:
            messagebox.showerror("Playback Error", str(e))

    def play_playlist(self, playlist_uri):
        try:
            self.sp.start_playback(context_uri=playlist_uri)
            self.update_playback_info()
        except Exception as e:
            messagebox.showerror("Playback Error", str(e))

    def show_home(self):
        self.home_frame.pack(fill=tk.BOTH, expand=True)
        self.search_frame.pack_forget()
        self.history_frame.pack_forget()
        self.roast_frame.pack_forget()
        self.rewind_frame.pack_forget()


    def show_search(self):
        self.search_frame.pack(fill=tk.BOTH, expand=True)
        self.home_frame.pack_forget()
        self.history_frame.pack_forget()
        self.roast_frame.pack_forget()
        self.rewind_frame.pack_forget()
        
        for widget in self.search_frame.winfo_children():
            widget.destroy()
        
        search_entry = ttk.Entry(self.search_frame)
        search_entry.pack(fill=tk.X, padx=5, pady=5)
        search_entry.bind('<Return>', lambda e: self.perform_search(search_entry.get()))
        ttk.Button(self.search_frame, text="Search", 
                 command=lambda: self.perform_search(search_entry.get())).pack(pady=5)

    def perform_search(self, query):
        try:
            results = self.sp.search(q=query, type='track', limit=10)
            self.display_search_results(results['tracks']['items'])
        except Exception as e:
            messagebox.showerror("Search Error", str(e))

    def display_search_results(self, tracks):
        results_frame = ttk.Frame(self.search_frame)
        results_frame.pack(fill=tk.BOTH, expand=True)
        
        tree = ttk.Treeview(results_frame, columns=('artist', 'album'), show='headings')
        tree.heading('#0', text='Song')
        tree.column('#0', width=200)
        tree.heading('artist', text='Artist')
        tree.heading('album', text='Album')
        
        vsb = ttk.Scrollbar(results_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        for track in tracks:
            tree.insert('', 'end', text=track['name'],
                       values=(', '.join(a['name'] for a in track['artists']), track['album']['name']))
        
        tree.bind('<Double-1>', lambda e: self.play_from_treeview(tree))

    def play_from_treeview(self, tree):
        selected = tree.selection()
        if selected:
            item = tree.item(selected[0])
            track_name = item['text']
            artists = item['values'][0]
            query = f"{track_name} {artists}"
            results = self.sp.search(q=query, type='track', limit=1)
            if results['tracks']['items']:
                track_uri = results['tracks']['items'][0]['uri']
                self.sp.start_playback(uris=[track_uri])
                self.update_playback_info()

    def update_album_art(self, image_url):
        def load_image():
            try:
                response = requests.get(image_url)
                img = Image.open(BytesIO(response.content))
                img = img.resize((64, 64), Image.Resampling.LANCZOS)
                
                # Store the image in a persistent variable
                self.current_image = ImageTk.PhotoImage(img)
                
                # Update the label with the new image
                self.album_art_label.config(image=self.current_image)
            except Exception as e:
                print("Error loading album art:", e)
                self.album_art_label.config(image='')
        
        # Schedule the image loading on the main thread
        self.root.after(0, load_image)

    def update_playback_info(self):
        try:
            current = self.sp.current_playback()
            if current and current['is_playing']:
                track = current['item']
                if self.current_track_id != track['id']:
                    self.current_track_id = track['id']
                    Thread(target=self.log_play_event, args=(track,), daemon=True).start()
                
                self.song_label.config(text=track['name'][:40])
                self.artist_label.config(text=", ".join([a['name'] for a in track['artists']])[:40])
                self.album_label.config(text=track['album']['name'][:40])
                
                if track['album']['images']:
                    self.update_album_art(track['album']['images'][0]['url'])
                
                is_liked = self.sp.current_user_saved_tracks_contains([self.current_track_id])[0]
                self.like_button.config(
                    text="❤️" if is_liked else "♡",
                    style="Red.TButton" if is_liked else "TButton"
                )
                self.play_button.config(text="⏸")
            elif current:
                self.play_button.config(text="▶")
            else:
                self.song_label.config(text="No track playing")
                self.artist_label.config(text="")
                self.album_label.config(text="")
                self.album_art_label.config(image='')
        except Exception as e:
            print("Error updating playback info:", e)
        finally:
            self.root.after(self.update_interval, self.update_playback_info)

    def log_play_event(self, track):
        location = geocoder.ip('me').latlng
        if location:
            self.db.log_play(track, location)


    def toggle_like(self):
        if self.current_track_id:
            try:
                currently_liked = self.sp.current_user_saved_tracks_contains([self.current_track_id])[0]
                if currently_liked:
                    self.sp.current_user_saved_tracks_delete([self.current_track_id])
                else:
                    self.sp.current_user_saved_tracks_add([self.current_track_id])
                self.update_playback_info()
            except Exception as e:
                print("Error toggling like:", e)

    def play_pause(self):
        try:
            current = self.sp.current_playback()
            if current and current['is_playing']:
                self.sp.pause_playback()
                self.play_button.config(text="▶")
            else:
                self.sp.start_playback()
                self.play_button.config(text="⏸")
        except spotipy.SpotifyException as e:
            if e.http_status == 404 and "No active device" in str(e):
                messagebox.showinfo("No Active Device", "Please ensure Spotify is active on a device.")
            else:
                print("Error in play/pause:", e)
        except Exception as e:
            print("Error in play/pause:", e)

    def next_track(self):
        try:
            self.sp.next_track()
            time.sleep(0.1)
            self.update_playback_info()
        except Exception as e:
            print("Error skipping track:", e)

    def previous_track(self):
        try:
            self.sp.previous_track()
            time.sleep(0.1)
            self.update_playback_info()
        except Exception as e:
            print("Error going back:", e)

    def show_play_history(self):
        self.history_frame.pack(fill=tk.BOTH, expand=True)
        self.home_frame.pack_forget()
        self.search_frame.pack_forget()
        self.roast_frame.pack_forget()
        self.rewind_frame.pack_forget()
        
        for widget in self.history_frame.winfo_children():
            widget.destroy()
        
        history = self.db.get_play_history()
        tree = ttk.Treeview(self.history_frame, columns=('Song', 'Artist', 'Album', 'Location', 'Album Art'), show='headings')
        tree.heading('#0', text='Date & Time')
        tree.column('#0', width=150)
        tree.heading('Song', text='Song')
        tree.heading('Artist', text='Artist')
        tree.heading('Album', text='Album')
        tree.heading('Location', text='Location')
        tree.heading('Album Art', text='Album Art')
        
        vsb = ttk.Scrollbar(self.history_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        for item in history:
            dt = datetime.fromisoformat(item[3]).strftime('%Y-%m-%d %H:%M:%S')
            tree.insert('', 'end', text=dt, values=(
                item[0],
                item[1],
                item[2],
                f"{item[4]:.4f}, {item[5]:.4f}",
                item[6]  # 专辑照片URL
            ))
            
    def show_listening_map(self):
        Thread(target=self.generate_map).start()

    def generate_map(self):
        try:
            history = self.db.get_play_history()
            if not history:
                return

            latitudes = [p[4] for p in history]
            longitudes = [p[5] for p in history]
            avg_lat = sum(latitudes)/len(latitudes)
            avg_lon = sum(longitudes)/len(longitudes)
            
            m = folium.Map(location=[avg_lat, avg_lon], zoom_start=10)
            
            for play in history:
                folium.Marker(
                    location=[play[4], play[5]],
                    popup=f"{play[0]} by {play[1]}\nAlbum: {play[2]}",
                    tooltip=datetime.fromisoformat(play[3]).strftime('%Y-%m-%d %H:%M'),
                    icon=folium.Icon(color='green' if play == history[0] else 'gray')
                ).add_to(m)
            
            from folium.plugins import HeatMap
            HeatMap([[p[4], p[5]] for p in history]).add_to(m)
            
            map_file = 'play_history_map.html'
            m.save(map_file)
            webbrowser.open(f'file://{os.path.abspath(map_file)}')
            
        except Exception as e:
            print("Error generating map:", e)

    def update_devices(self):
        if self.device_id is None:
            messagebox.showinfo("No Device", "Please ensure Spotify is active on a device.")
        return 


    def show_roast(self):
        """Show the Roast Me frame and generate the roast."""
        self.roast_frame.pack(fill=tk.BOTH, expand=True)
        self.home_frame.pack_forget()
        self.search_frame.pack_forget()
        self.history_frame.pack_forget()
        self.rewind_frame.pack_forget()

        # Clear previous content
        for widget in self.roast_frame.winfo_children():
            widget.destroy()

        # Add a label to display the roast
        self.roast_label = ttk.Label(self.roast_frame, text="Generating roast...", font=('Helvetica', 20), wraplength=800)
        self.roast_label.pack(pady=20)

        # Generate the roast in a separate thread to avoid blocking the UI
        Thread(target=self.generate_roast, daemon=True).start()


    def generate_roast(self):
        """Generate and display the roast."""
        try:
            roaster = DatabaseRoaster()
            roast_text = roaster.generate_roast()
            self.roast_label.config(text=roast_text)
        except Exception as e:
            self.roast_label.config(text=f"Error generating roast: {str(e)}")

    def show_rewind(self):
        """Show the Rewind frame."""
        self.rewind_frame.pack(fill=tk.BOTH, expand=True)
        self.home_frame.pack_forget()
        self.search_frame.pack_forget()
        self.history_frame.pack_forget()
        self.roast_frame.pack_forget()

        # Clear previous content
        for widget in self.rewind_frame.winfo_children():
            widget.destroy()

        # Instantiate the SpotifyRewind class
        rewind = SpotifyRewind()

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.configure("Red.TButton", foreground="red")
    player = SpotifyPlayer(root)
    root.mainloop()
