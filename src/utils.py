import os
import sys
import logging
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

logging.basicConfig(level=logging.INFO, filename="utils.log", filemode="w",
                    format="%(asctime)s - %(levelname)s - %(message)s")

def setup_logging(log_file="app.log"):
    """basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

@lru_cache(maxsize=128)
def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
  # Executable directory
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)
    
    return os.path.join(base_path, relative_path)

def ensure_dir_exists(directory):
    #to ensure a directory exists !create if not!
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"Error creating directory {directory}: {e}")
        return False

def get_latest_folder(base_dir, prefix="search_attempt_"):
    #TO find the latest folder matching the pattern in base_dir
    if not os.path.exists(base_dir):
        raise FileNotFoundError(f"Directory not found: {base_dir}")
        
    folders = [f for f in os.listdir(base_dir) if f.startswith(prefix)]
    if not folders:
        raise FileNotFoundError(f"No folders found in '{base_dir}' with prefix '{prefix}'")
    
    try:
        #sort numeric suffix
        folders.sort(key=lambda x: int(x.split("_")[-1]))
        return folders[-1]
    except (ValueError, IndexError) as e:
        logging.warning(f"Failed to sort folders numerically: {e}")
        #fallback to alphabetical sorting
        folders.sort()
        return folders[-1]

def read_file_safe(filepath, encoding="utf-8"):
    #error handling - reading a file Safely
    try:
        with open(filepath, "r", encoding=encoding) as f:
            return f.read()
    except Exception as e:
        logging.error(f"Error reading file {filepath}: {e}")
        return ""

def write_file_safe(filepath, content, encoding="utf-8"):
    #error handling - writing a file Safely
    try:
        with open(filepath, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        logging.error(f"Error writing file {filepath}: {e}")
        return False

def save_json_safe(data, filepath, indent=2):
    #error handling - Saving JSON file Safely
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
        return True
    except Exception as e:
        logging.error(f"Error saving JSON to {filepath}: {e}")
        return False

def load_json_safe(filepath):
    #error handling - loading JSON file Safely
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading JSON from {filepath}: {e}")
        return None

def get_file_paths_in_dir(directory, extension=None, starts_with=None):
    #get list of file paths in a directory
    if not os.path.exists(directory):
        return []
        
    file_paths = []
    for filename in os.listdir(directory):
        if extension and not filename.endswith(extension):
            continue
        if starts_with and not filename.startswith(starts_with):
            continue
        file_paths.append(os.path.join(directory, filename))
    return file_paths

def is_valid_url(url):
    #Check if the URL is valid """AND""" not from unwanted domains
    BAD_DOMAINS = {
        "facebook.com", "twitter.com", "instagram.com",
        "linkedin.com", "youtube.com", "wikipedia.org",
        "amazon.", "reddit.com", "tiktok.com", "news.google.com"
    }
    
    if not url.startswith(("http://", "https://")): 
        return False
        
    for domain in BAD_DOMAINS:
        if domain in url:
            return False
            
    return True

def get_timestamped_filename(base_name, ext=".txt"):
    #imestamped filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{timestamp}{ext}"

def make_hyperlink(text_widget, text, url):
    #clickable hyperlink for tkinter
    def click_link(event, link=url):
        import webbrowser
        webbrowser.open(link)
    
    tag_name = f"link_{url.replace('.', '_').replace('/', '_').replace(':', '_')}"
    text_widget.tag_configure(tag_name, foreground="blue", underline=True)
    text_widget.insert(tk.END, text, tag_name)
    text_widget.tag_bind(tag_name, "<Button-1>", click_link)

def clear_text_widget(text_widget):
    #clear content Tkinter text widget safely
    try:
        text_widget.config(state=tk.NORMAL)
        text_widget.delete("1.0", tk.END)
        text_widget.config(state=tk.DISABLED)
    except Exception as e:
        logging.error(f"Error clearing text widget: {e}")

def append_to_text_widget(text_widget, text, enable=False):
    #adding text to the text widget
    try:
        text_widget.config(state=tk.NORMAL)
        text_widget.insert(tk.END, text)
        text_widget.config(state=tk.DISABLED if not enable else tk.NORMAL)
        text_widget.see(tk.END)
    except Exception as e:
        logging.error(f"Error appending to text widget: {e}")

def reset_input_field(input_widget):
    #Reset user input
    try:
        input_widget.delete("1.0", tk.END)
        input_widget.mark_set(tk.INSERT, "1.0")
        input_widget.focus_set()
    except Exception as e:
        logging.error(f"Error resetting input field: {e}")

def validate_model_loaded(model_handler, callback):
    #validating model loadeding before everything
    if not model_handler.model:
        error_msg = "[Error: Model not loaded or failed to load. Please check console.]"
        if callable(callback):
            callback(error_msg)
        logging.error("Model not loaded")
        return False
    return True

def get_prompt_template():
    #returning prompt template from config or default
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("prompt_template", "<|{role}|>\n{content}<|end|>\n")
    except Exception as e:
        logging.warning(f"Failed to load prompt template from config: {e}")
        return "<|{role}|>\n{content}<|end|>\n"

def chunk_text_if_needed(text, filename, output_folder, max_words=1500):
    """
    if text is too long, its aves chunks in the same folder as original file.
    It also returns list of chunk strings
    """
    words = text.split()
    if len(words) <= max_words:
        return [text], False
    
    logging.info(f"Splitting large document: {filename} ({len(words)} words)")
    chunks = []
    
    for i, start in enumerate(range(0, len(words), max_words)):
        chunk = ' '.join(words[start:start + max_words])
        chunk_filename = f"{Path(filename).stem}_chunk{i+1}.txt"
        chunk_path = os.path.join(output_folder, chunk_filename)
        
        try:
            with open(chunk_path, "w", encoding="utf-8") as f:
                f.write(chunk)
            chunks.append(chunk)
        except Exception as e:
            logging.error(f"Error saving chunk {i+1} for {filename}: {e}")
            continue
    
    logging.info(f"Created {len(chunks)} chunks for {filename}")
    return chunks, True