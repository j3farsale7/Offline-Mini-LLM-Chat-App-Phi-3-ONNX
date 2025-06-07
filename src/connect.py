import os
import threading
import json
import logging
import sys

#local imports
from utils import resource_path

import onnxruntime_genai as og

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

logging.basicConfig(level=logging.INFO, filename="model.log", filemode="w",
                    format="%(asctime)s - %(levelname)s - %(message)s")

class ModelHandler:
    def __init__(self):
        #Initializing paths and model
        self.model_path = self._build_model_path()
        self.model = None
        self.tokenizer = None
        self.load_model_threaded()

        #For chat history
        self.base_history = [
            {"role": "system", "content": CONFIG["system_prompt"]}
        ]

        #control generation 
        self.stop_response_flag = False
        self.generating_response_lock = threading.Lock()
        self.current_generator = None

    def _build_model_path(self):
        #using config
        model_name = CONFIG["model_name"]
        subpaths = CONFIG["model_subpath_elements"]
        return os.path.join(resource_path(model_name), *subpaths)

    def load_model_threaded(self):
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model directory not found: {self.model_path}")
            logging.info(f"Loading model from: {self.model_path}")
            self.model = og.Model(self.model_path)
            self.tokenizer = og.Tokenizer(self.model)
            logging.info("Model and Tokenizer loaded successfully!")
        except Exception as e:
            logging.error(f"Error loading model: {e}")
            self.model = None
            self.tokenizer = None

    def _build_prompt_from_history(self):
        """Constructs the full prompt from chat history using the template."""
        prompt = ""
        for item in self.base_history:
            prompt += CONFIG["prompt_template"].format(role=item["role"], content=item["content"])
        prompt += CONFIG["assistant_start_token"]
        return prompt

    def get_response(self, user_input, callback):
        """
        Streams a response from the model for the given user input.
        Uses the callback to update the UI incrementally.
        """
        if not self.model or not self.tokenizer:
            callback("\n[Error: Model not loaded or failed to load.]\n")
            return

        with self.generating_response_lock:
            self.stop_response_flag = False
            try:
                #adding user message to history
                self.base_history.append({"role": "user", "content": user_input})
                full_prompt = self._build_prompt_from_history()

                #encoding input tokens
                input_tokens = self.tokenizer.encode(full_prompt)

                #generation parameters
                params = og.GeneratorParams(self.model)
                params.input_ids = input_tokens
                gen_config = CONFIG["generation_params"]
                params.set_search_options(
                    max_length=gen_config["max_length"],
                    temperature=gen_config["temperature"],
                    top_p=gen_config["top_p"],
                    do_sample=gen_config["do_sample"],
                    repetition_penalty=gen_config["repetition_penalty"]
                )

                self.current_generator = og.Generator(self.model, params)
                assistant_response = ""
                response_tokens = []

                while not self.current_generator.is_done():
                    if self.stop_response_flag:
                        logging.info("Generation stopped by user.")
                        break

                    self.current_generator.compute_logits()
                    self.current_generator.generate_next_token()
                    new_token_id = self.current_generator.get_next_tokens()[0]
                    response_tokens.append(new_token_id)

                    decoded = self.tokenizer.decode(response_tokens)
                    chunk = decoded[len(assistant_response):]
                    if chunk:
                        callback(chunk)
                        assistant_response = decoded

                final_response = assistant_response.strip()
                if final_response:
                    self.base_history.append({"role": "assistant", "content": final_response})

                if self.stop_response_flag:
                    callback("\n[Model response stopped by user]\n")

            except Exception as e:
                logging.error(f"Error during model generation: {e}", exc_info=True)
                callback(f"\n[Error generating response: {e}]\n")
            finally:
                self.current_generator = None
                self.stop_response_flag = False

    def generate_full_response(self, prompt_string, max_tokens_gen=None):
        """
        Generates a full response from a given prompt string.
        Useful for summarization and deep search tasks.
        """
        if not self.model or not self.tokenizer:
            logging.error("Model not loaded.")
            return "[Error: Model not loaded.]"

        with self.generating_response_lock:
            try:
                input_tokens = self.tokenizer.encode(prompt_string)
                params = og.GeneratorParams(self.model)
                params.input_ids = input_tokens

                gen_config = CONFIG["generation_params"]
                max_len = len(input_tokens) + (max_tokens_gen or gen_config["max_length"])
                params.set_search_options(
                    max_length=max_len,
                    temperature=gen_config["temperature"],
                    top_p=gen_config["top_p"],
                    do_sample=gen_config["do_sample"],
                    repetition_penalty=gen_config["repetition_penalty"]
                )

                generator = og.Generator(self.model, params)
                response_tokens = []

                while not generator.is_done() and len(response_tokens) < (max_tokens_gen or gen_config["max_length"]):
                    generator.compute_logits()
                    generator.generate_next_token()
                    new_token_id = generator.get_next_tokens()[0]
                    response_tokens.append(new_token_id)

                return self.tokenizer.decode(response_tokens).strip()

            except Exception as e:
                logging.error(f"Error generating full response: {e}", exc_info=True)
                return f"[Error: {e}]"

    def stop_response(self):
        #Stopping the current response generation
        self.stop_response_flag = True

    def clear_history(self):
        #Clears the conversation history keeping only the system prompt!!
        if self.base_history and self.base_history[0]["role"] == "system":
            self.base_history = [self.base_history[0]]
        else:
            self.base_history = []
        logging.info("Chat history cleared.")

    def add_to_history(self, role, content):
        #Adding the message to the chathistory
        self.base_history.append({"role": "assistant", "content": content})