import os
import logging
from pathlib import Path

#local imports
from utils import chunk_text_if_needed

logging.basicConfig(level=logging.INFO, filename="deep_search.log", filemode="w",
                    format="%(asctime)s - %(levelname)s - %(message)s")

def summarize_search_attempt(model_handler, base_dir="web_searches", summary_dir="model_search_summary"):
    """
    Summarizes all search result documents in the latest web search folder.
    
    Args:
        model_handler: Instance of ModelHandler for generating summaries
        base_dir: Base directory containing search attempts
        summary_dir: Directory where summaries will be saved
    
    Return:
        str: Path to the folder containing generated summaries
    """
    logging.info("Finding latest search attempt...")
    
    if not os.path.exists(base_dir):
        raise FileNotFoundError(f"Base directory not found: {base_dir}")
        
    folders = [f for f in os.listdir(base_dir) if f.startswith("search_attempt_")]
    if not folders:
        raise FileNotFoundError(f"No search attempts found in '{base_dir}'")
    
    try:
        #sort numeric suffix
        folders.sort(key=lambda x: int(x.split("_")[-1]))
        latest_folder = folders[-1]
    except (ValueError, IndexError):
        #fallback to alphabetical sorting
        folders.sort()
        latest_folder = folders[-1]

    latest_path = os.path.join(base_dir, latest_folder)
    summary_folder_name = f"{latest_folder}_summary"
    summary_folder_path = os.path.join(summary_dir, summary_folder_name)
    
    os.makedirs(summary_folder_path, exist_ok=True)
    
    logging.info(f"Reading from: {latest_path}")
    logging.info(f"Saving summaries to: {summary_folder_path}")

    for filename in sorted(os.listdir(latest_path)):
        if not filename.endswith(".txt") or not filename.startswith("search_data_"):
            continue
            
        filepath = os.path.join(latest_path, filename)
        logging.info(f"Processing: {filename}")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            lines = content.strip().split('\n')
            article_title = lines[0] if lines else "Unknown Title"
            article_url = lines[1] if len(lines) > 1 else "Unknown URL"
            
            if len(lines) > 2:
                article_content = '\n'.join(lines[2:]).strip()
            else:
                article_content = content.strip()
                
            if not article_content:
                logging.warning(f"Content for '{filename}' is empty after stripping metadata. Skipping.")
                continue

            chunks, was_split = chunk_text_if_needed(article_content, filename, latest_path)
            
            final_summary = ""
            valid_summaries = 0
            
            for idx, chunk_text in enumerate(chunks):
                prompt = f"""<|system|>
You are an AI assistant that summarizes technical documents concisely. Aim for around 100-150 words per summary.
Focus on the key information and main points of the provided text.
Input document title: {article_title}
Input document URL: {article_url}
<|end|>
<|user|>
Summarize this document chunk:
---
{chunk_text}
---
<|end|>
<|assistant|>
"""
                logging.info(f"Summarizing {'chunk' if was_split else 'full text'} {idx+1}/{len(chunks)} for '{filename}'...")
                
                try:
                    response = model_handler.generate_full_response(prompt, max_tokens_gen=200)
                    
                    if response and not response.startswith("[Error:"):
                        valid_summaries += 1
                        final_summary += f"[{'Chunk' if was_split else 'Document'} {idx+1} Summary for '{filename}']:\n{response.strip()}\n\n"
                        logging.info(f"Summary received for chunk {idx+1}.")
                    elif response.startswith("[Error:"):
                        logging.error(f"Error from model for {filename}, chunk {idx+1}: {response}")
                    else:
                        logging.warning(f"Empty or invalid response from model for {filename}, chunk {idx+1}")
                        
                except Exception as e:
                    logging.exception(f"Error calling model_handler.generate_full_response: {e}")
                    continue
                    
            if valid_summaries == 0:
                logging.warning(f"No valid summaries generated for {filename}. Skipping file.")
                continue
                
            summary_filename = filename.replace(".txt", "_summary.txt")
            summary_path = os.path.join(summary_folder_path, summary_filename)
            
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(final_summary.strip())
                
            logging.info(f"Saved combined summary: {summary_filename} to {summary_folder_path}")
            
        except Exception as e:
            logging.exception(f"Error processing file {filename}: {e}")
            continue

    logging.info("All processable files summarized and saved.")
    return summary_folder_path


def answer_from_summaries(model_handler, summary_base_dir="model_search_summary"):
    """
    Generates answers based on individual summaries from multiple documents.
    
    Args:
        model_handler: Instance of ModelHandler for answering questions
        summary_base_dir: Directory containing summary folders
        
    Return:
        str: Combined answers from all summaries
    """
    logging.info("Finding latest summary folder...")
    
    if not os.path.exists(summary_base_dir):
        raise FileNotFoundError(f"Summary directory not found: {summary_base_dir}")
        
    folders = [f for f in os.listdir(summary_base_dir) if f.endswith("_summary")]
    
    if not folders:
        raise FileNotFoundError(f"No summary folders found in '{summary_base_dir}'")
    
    try:
        folders.sort(key=lambda x: int(x.split("_")[2]))  #search_attempt_NUMBER_summary
    except (ValueError, IndexError):
        #fallback to alphabetical sorting
        folders.sort()
        
    latest_summary_folder = folders[-1]
    latest_summary_path = os.path.join(summary_base_dir, latest_summary_folder)
    
    logging.info(f"Reading summaries from: {latest_summary_path}")
    
    all_answers_text = ""
    
    for filename in sorted(os.listdir(latest_summary_path)):
        if not filename.endswith("_summary.txt"):
            continue
            
        filepath = os.path.join(latest_summary_path, filename)
        logging.info(f"Loading summary file: {filename}")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                summary_content = f.read().strip()
                
            if not summary_content:
                logging.warning(f"Summary file '{filename}' is empty. Skipping.")
                continue
                
            prompt = f"""<|system|>
You are an AI assistant. Your task is to analyze the provided document summary and answer the questions clearly and concisely.
<|end|>
<|user|>
Document Summary:
---
{summary_content}
---
Based *only* on the summary provided above, please answer the following questions:
1. What is this document primarily about?
2. What are the key ideas, facts, or conclusions presented in this summary?
3. Is there any new or particularly interesting information mentioned in this summary? If so, what is it?
Provide your answer for these three points.
<|end|>
<|assistant|>
"""
            logging.info(f"Generating answer for {filename}...")
            
            try:
                response = model_handler.generate_full_response(prompt, max_tokens_gen=350)
                
                if response and not response.startswith("[Error:"):
                    answer_block = f"Answer based on '{filename}':\n{response.strip()}\n{'-'*60}\n"
                    all_answers_text += answer_block
                    logging.info(f"Answer generated for '{filename}'")
                elif response.startswith("[Error:"):
                    logging.error(f"Error from model for '{filename}': {response}")
                else:
                    logging.warning(f"Empty or invalid response for '{filename}'")
                    
            except Exception as e:
                logging.exception(f"Error calling model_handler.generate_full_response for '{filename}': {e}")
                continue
                
        except Exception as e:
            logging.exception(f"Error reading summary file {filename}: {e}")
            continue

    if not all_answers_text.strip():
        logging.error("No valid answers could be generated from any summaries.")
        return ""

    output_filename = "all_deep_search_answers.txt"
    output_path = os.path.join(latest_summary_path, output_filename)
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(all_answers_text.strip())
        logging.info(f"All deep search answers saved to: {output_path}")
    except Exception as e:
        logging.error(f"Failed to save deep search answers: {e}")

    return all_answers_text.strip()