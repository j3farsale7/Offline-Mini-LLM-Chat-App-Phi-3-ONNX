import tkinter as tk
from tkinter import scrolledtext, messagebox, END
import os
import threading
import json
import logging
import platform
import sys

#local imports
from connect import ModelHandler
from search import start_web_search
from deep_search import summarize_search_attempt, answer_from_summaries

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

logging.basicConfig(level=logging.INFO, filename="app.log", filemode="w",
                    format="%(asctime)s - %(levelname)s - %(message)s")

#Global flags
deep_search_active = False
deep_search_stop_flag = threading.Event()

class ChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title(CONFIG["app_title"])
        self.root.geometry(CONFIG["default_window_size"])
        self.root.minsize(*map(int, CONFIG["min_window_size"].split("x")))
        
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        icon_path = os.path.join(base_path, "icon.ico")

        try:
            self.root.iconbitmap(icon_path)
        except Exception as e:
            logging.warning(f"Could not load icon: {e}")


        #Initialize model handler from connect
        self.model_handler = ModelHandler()
        
        self.create_ui()
        self.setup_initial_state()

    def create_ui(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        #Chat Display Box
        #Experimental 'failed due to old tkinter version, was meant to choose emoji-supporting font 'aided'
        if platform.system() == 'Windows':
            chat_font = ("Segoe UI Emoji", 12)
        elif platform.system() == 'Darwin':  #for mac
            chat_font = ("Apple Color Emoji", 12)
        else: #forlinux
            chat_font = ("Noto Color Emoji", 12)

        self.chat_box = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, width=60, height=20, font=chat_font)
        self.chat_box.pack(fill=tk.BOTH, expand=True)
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.bind("<Double-Button-1>", self.handle_double_click)


        #User input frame
        input_frame = tk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(10, 0))
        input_frame.grid_columnconfigure(0, weight=1)


        self.user_input = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, width=60, height=3, font=chat_font)
        self.user_input.grid(row=0, column=0, sticky="ew")
        self.user_input.bind("<Return>", self.send_message)
        self.user_input.bind("<Shift-Return>", lambda e: self.user_input.insert(tk.INSERT, "\n"))


        button_send_stop = tk.Frame(input_frame)
        button_send_stop.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self.send_button = tk.Button(button_send_stop, text="Send", command=self.send_message, width=8)
        self.send_button.pack(pady=1, fill=tk.X)

        self.stop_button = tk.Button(button_send_stop, text="Stop", command=self.stop_action, bg="darkred", fg="white", width=8, state=tk.DISABLED)
        self.stop_button.pack(fill=tk.X)

        #button Panel
        button_panel = tk.Frame(main_frame)
        button_panel.pack(fill=tk.X, pady=(10, 0))

        self.search_button = tk.Button(button_panel, text="Search Web", command=self.search_action)
        self.search_button.pack(side=tk.LEFT, padx=2)

        self.deep_search_button = tk.Button(button_panel, text="Deep Search", command=self.deep_search_action, state=tk.DISABLED)
        self.deep_search_button.pack(side=tk.LEFT, padx=2)

        self.abort_search_button = tk.Button(button_panel, text="Abort Deep Search", command=self.abort_search_action, bg="#8B0000", fg="white", state=tk.DISABLED)
        self.abort_search_button.pack(side=tk.LEFT, padx=2)

        self.save_clear_button = tk.Button(button_panel, text="Save & Clear Chat", command=self.save_and_clear_action)
        self.save_clear_button.pack(side=tk.RIGHT, padx=2)

    def setup_initial_state(self):
        self.chat_box.config(state=tk.NORMAL)
        if self.model_handler.model:
            self.chat_box.insert(tk.END, CONFIG["initial_message"] + "\n")
        else:
            self.chat_box.insert(tk.END, CONFIG["model_loading_message"] + "\n"
                                      "If loading fails, chat and deep search will not work.\n")
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.see(tk.END)

        if not self.model_handler.model:
            self.send_button.config(state=tk.DISABLED)
            self.search_button.config(state=tk.DISABLED)

        #for enabling deep search button if previous results exists
        if os.path.exists(CONFIG["search_result_dir"]) and any(
                f.startswith("search_attempt_") for f in os.listdir(CONFIG["search_result_dir"])
        ):
            self.deep_search_button.config(state=tk.NORMAL)

    def add_hyperlink(self, text, url):
        def click_link(event):
            import webbrowser
            webbrowser.open(url)
        tag_name = f"link_{url.replace('.', '_').replace('/', '_').replace(':', '_')}"
        self.chat_box.tag_configure(tag_name, foreground="blue", underline=True)
        self.chat_box.insert(tk.END, text, tag_name)
        self.chat_box.tag_bind(tag_name, "<Button-1>", click_link)

    def send_message(self, event=None):
        user_text = self.user_input.get("1.0", END).strip()
        if not user_text:
            return "break"

        self._update_chat_display(f"You: {user_text}\n", enable=False)
        self.reset_input_field()

        if not self.model_handler.model:
            self._update_chat_display(CONFIG["model_not_loaded_message"] + "\n")
            return

        self._update_chat_display("Assistant: ")
        self.send_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        threading.Thread(target=self.start_streaming, args=(user_text,), daemon=True).start()
        return "break"

    def start_streaming(self, user_text):
        def update_gui(chunk):
            self.chat_box.config(state=tk.NORMAL)
            self.chat_box.insert(tk.END, chunk)
            self.chat_box.config(state=tk.DISABLED)
            self.chat_box.see(tk.END)

        try:
            self.model_handler.get_response(user_text, update_gui)
        except Exception as e:
            logging.error(f"Error during streaming: {e}")
            self._update_chat_display(f"\n[Error during streaming setup: {e}]\n")
        finally:
            self._update_chat_display("\n")
            self.send_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

    def stop_action(self):
        self._update_chat_display("[Stopping model response...]\n")
        self.model_handler.stop_response()

    def reset_input_field(self):
        self.user_input.delete("1.0", tk.END)
        self.user_input.mark_set(tk.INSERT, "1.0")
        self.user_input.focus_set()

    def save_and_clear_action(self):
        chat_content = self.chat_box.get("1.0", tk.END).strip()
        if not chat_content:
            messagebox.showwarning("Empty Chat", "There's no chat to save.")
            return

        folder = CONFIG["chat_file_dir"]
        os.makedirs(folder, exist_ok=True)
        index = 1
        while os.path.exists(os.path.join(folder, f"chat_history_{index}.txt")):
            index += 1
        filename = os.path.join(folder, f"chat_history_{index}.txt")

        with open(filename, "w", encoding="utf-8") as file:
            file.write(chat_content)

        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.delete("1.0", tk.END)
        self.chat_box.insert(tk.END, "Chat cleared. Model is ready.\n" if self.model_handler.model else "Chat cleared. Model not loaded.\n")
        self.chat_box.config(state=tk.DISABLED)

        self.model_handler.clear_history()
        messagebox.showinfo("Saved", f"Chat saved as {filename}")
        self.reset_input_field()

    def search_action(self):
        user_query = self.user_input.get("1.0", END).strip()
        if not user_query:
            messagebox.showwarning("Empty Input", "Please enter something to search.")
            return

        self._update_chat_display(f"You: {user_query}\n")
        self._update_chat_display("Assistant: Starting web search... This may take a few moments.\n")
        self.reset_input_field()

        threading.Thread(target=self.run_search_in_background, args=(user_query,), daemon=True).start()

    def run_search_in_background(self, query):
        try:
            self.search_button.config(state=tk.DISABLED)
            result_folder = start_web_search(query)
            self.display_search_results(result_folder)
            self.deep_search_button.config(state=tk.NORMAL)
        except Exception as e:
            logging.error(f"Search error: {e}")
            self._update_chat_display(f"Assistant: An error occurred during web search: {str(e)}\n")
        finally:
            self.search_button.config(state=tk.NORMAL)

    def display_search_results(self, result_folder):
        urls_file = os.path.join(result_folder, "urls_n_headlines.txt")
        if not os.path.exists(urls_file) or os.path.getsize(urls_file) == 0:
            self._update_chat_display("Assistant: No search results (URLs and headlines) found to display.\n")
            return

        self._update_chat_display("Assistant: Search results (click to open):\n")
        try:
            with open(urls_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                title = lines[i].strip()
                i += 1
                if i < len(lines):
                    url = lines[i].strip()
                    i += 1
                    if i < len(lines) and lines[i].strip() == "":
                        i += 1
                    if title and url.startswith(("http://", "https://")): 
                        self.chat_box.insert(tk.END, f"- {title}: ")
                        self.add_hyperlink(url + "\n", url)
                    elif title:
                        self.chat_box.insert(tk.END, f"- {title}\n")
                elif title:
                    self.chat_box.insert(tk.END, f"- {title}\n")
            self.chat_box.insert(tk.END, "\n")
        except Exception as e:
            logging.error(f"Display error: {e}")
            self._update_chat_display(f"Assistant: Error reading or displaying search results: {str(e)}\n")
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.see(tk.END)

    def deep_search_action(self):
        if not self.model_handler.model:
            messagebox.showerror("Model Error", "The language model is not loaded. Cannot perform deep search.")
            return

        self._update_chat_display("Assistant: Starting Deep Search... This will take some time.\n"
                                  "Summarizing web results first, then generating answers.\n")
        self.reset_input_field()

        self.deep_search_button.config(state=tk.DISABLED)
        self.abort_search_button.config(state=tk.NORMAL)

        global deep_search_active
        deep_search_active = True
        deep_search_stop_flag.clear()
        threading.Thread(target=self.run_deep_search, daemon=True).start()

    def abort_search_action(self):
        global deep_search_active
        if deep_search_active:
            deep_search_stop_flag.set()
            self._update_chat_display("Deep search abort signal sent. May take a moment to halt.\n")
        else:
            self._update_chat_display("No active deep search to abort.\n")

    def run_deep_search(self):
        global deep_search_active
        try:
            self._update_chat_display("Summarizing web results...\n")
            summary_path = summarize_search_attempt(self.model_handler)
            if deep_search_stop_flag.is_set():
                self._update_chat_display("Deep search summarization interrupted by user.\n")
                return

            if not summary_path or not os.listdir(summary_path):
                self._update_chat_display("Deep Search: No summaries were generated from web results. Cannot proceed.\n")
                return

            self._update_chat_display(f"Summaries saved. Path: {os.path.relpath(summary_path)}\n")
            self._update_chat_display("Generating final answers from summaries...\n")

            final_answer_text = answer_from_summaries(self.model_handler)
            if deep_search_stop_flag.is_set():
                self._update_chat_display("Deep search was interrupted before completion.\n")
                return

            if not final_answer_text.strip():
                self._update_chat_display("Deep Search: No final answers could be generated from the summaries.\n")
                return

            self._update_chat_display("Deep Search Final Answers:\n")
            self._update_chat_display(final_answer_text + "\n")
            self.model_handler.base_history.append({
                "role": "assistant",
                "content": f"[Deep Search Summary Note]: {final_answer_text[:1000]}..."
            })
            self._update_chat_display("Deep search findings noted in conversation context.\n")

        except FileNotFoundError as e:
            self._update_chat_display(f"Error during Deep Search (File Not Found): {str(e)}\n")
        except Exception as e:
            logging.exception("Unexpected error during deep search")
            self._update_chat_display(f"Unexpected error during deep search: {str(e)}\n")
        finally:
            deep_search_active = False
            self.deep_search_button.config(state=tk.NORMAL if os.path.exists(CONFIG["search_result_dir"]) and any(
                os.listdir(CONFIG["search_result_dir"])) else tk.DISABLED)
            self.abort_search_button.config(state=tk.DISABLED)

    def _update_chat_display(self, message, enable=True):
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, message)
        self.chat_box.config(state=tk.DISABLED if not enable else tk.NORMAL)
        self.chat_box.see(tk.END)

    def handle_double_click(self, event):
        index = self.chat_box.index(f"@{event.x},{event.y}")
        line_text = self.chat_box.get(f"{index} linestart", f"{index} lineend")
        if any(kw in line_text for kw in ("web_searches", "saved_chats", "model_search_summary")):
            return "break"
        return None


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatApp(root)
    root.mainloop()