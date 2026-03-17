import time
import re
import sys
import os
import logging
import json
from datetime import datetime
from typing import List, Dict, Any
import pandas as pd
from pathlib import Path

import multiprocessing
import concurrent.futures
from functools import partial

from jinja2 import Template

from model.llm_models import llm
from summarize.helpers import load_pages_from_file_data
import argparse


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================================
# JINJA2 TEMPLATES - Load template STRINGS (not Template objects)

def get_template_strings():
    """Get all template strings from prompts file"""
    logger.info("Loading template strings from prompts module")
    from summarize.prompts import (
        memory_log_template,
        summary_template_for_memory_log,
        page_summary_template,
        page_summary_verification_template,
        combine_template,
        combine_verification_template,
        condense_interval_template, 
        final_combine_template,
        final_verification_template, 
        improve_summary_template,
        organization_template
    )
    
    # Return raw strings, not Template objects
    templates = {
        'memory_log': memory_log_template,
        'summary_for_memory': summary_template_for_memory_log,
        'page_summary': page_summary_template,
        'page_verification': page_summary_verification_template,
        'combine': combine_template,
        'verification': combine_verification_template,
        'condense_interval': condense_interval_template,
        'final_combine': final_combine_template, 
        'final_verification': final_verification_template,
        'improve_summary': improve_summary_template,
        'organization': organization_template,
    }
    
    logger.info(f"Loaded {len(templates)} template strings")
    return templates

# ============================================================================
# HELPER FUNCTIONS


def word_count(text):
    """Count words in a text string."""
    if not text or not isinstance(text, str):
        return 0
    return len(text.split())

def concatenate_pages(pages, start_idx, num_pages_to_concat):
    """Concatenate multiple pages starting from start_idx."""
    combined_content = ""
    current_idx = start_idx
    pages_concatenated = 0
    num_pages = len(pages)
    
    while pages_concatenated < num_pages_to_concat and current_idx < num_pages:
        page_content = pages[current_idx]['page_content'].replace("\n", " ")
        
        # Skip empty or placeholder pages
        if "No data to be processed on this page" not in page_content and page_content.strip():
            combined_content += page_content + " "
            pages_concatenated += 1
        
        current_idx += 1
    
    return combined_content.strip(), current_idx - start_idx

def find_next_data_page(pages, start_idx):
    """Find the next page with actual data content."""
    num_pages = len(pages)
    current_idx = start_idx
    
    while current_idx < num_pages:
        content, pages_checked = concatenate_pages(pages, current_idx, 1)
        if content:
            return current_idx
        current_idx += pages_checked
    
    return None

def create_batches(pages, batch_size):
    """Create batches of pages for parallel processing."""
    num_batches = (len(pages) + batch_size - 1) // batch_size
    logger.debug(f"Creating {num_batches} batches from {len(pages)} pages (batch_size={batch_size})")
    return [pages[i : i + batch_size] for i in range(0, len(pages), batch_size)]

# ============================================================================
# MEMORY LOG FUNCTIONS

def process_memory_log_page(pages, page_idx, current_page_content, template_strings):
    """Process a single page for memory log creation."""
    page_number = pages[page_idx]['page_number']
    logger.debug(f"Processing memory log page {page_number}")
    
    response = {
        'page_content': '',
        'page_number': page_number
    }
    
    if current_page_content:
        logger.debug(f"Page {page_number}: Generating summary (content length: {len(current_page_content)} chars)")
        template = Template(template_strings['summary_for_memory'])
        prompt = template.render(current_page=current_page_content)

        time.sleep(0.2)  # Rate limiting delay
        processed_content = llm.run_inference(prompt)
        response['page_content'] = processed_content
        logger.debug(f"Page {page_number}: Summary generated (length: {len(processed_content)} chars)")
    else:
        logger.debug(f"Page {page_number}: No content to process")
    
    return response

def update_memory_log(memory_log, new_summary, template_strings):
    """Update the memory log with new summary information."""
    logger.debug(f"Updating memory log (current length: {len(memory_log)} chars, new summary: {len(new_summary)} chars)")

    template = Template(template_strings['memory_log'])
    prompt = template.render(
        summary=new_summary,
        memory_log=memory_log
    )

    time.sleep(0.2)  # Rate limiting delay
    updated_memory_log = llm.run_inference(prompt)
    logger.debug(f"Memory log updated (new length: {len(updated_memory_log)} chars)")
    return updated_memory_log

def create_memory_log(pages, template_strings, pages_to_concatenate=5):
    """Create a memory log by processing first and last pages of document."""
    logger.info(f"Creating memory log from {len(pages)} pages (concatenating {pages_to_concatenate} pages at a time)")
    memory_log = ""
    num_pages = len(pages)
    
    # Determine how many batches needed to get 10 pages from each end
    max_pages_per_side = 10
    batches_needed = (max_pages_per_side + pages_to_concatenate - 1) // pages_to_concatenate  # Ceiling division
    
    # Adjust if document is too short
    max_possible_batches_per_side = (num_pages + pages_to_concatenate - 1) // (pages_to_concatenate * 2)
    batches_to_process = min(batches_needed, max_possible_batches_per_side)
    
    # Process the first N batches
    logger.info(f"Processing first {batches_to_process} batches for memory log (up to {batches_to_process * pages_to_concatenate} pages)")
    start_idx = find_next_data_page(pages, 0)
    if start_idx is not None:
        logger.info(f"First data page found at index {start_idx}")
        batches_processed = 0
        while batches_processed < batches_to_process and start_idx < num_pages:
            combined_content, pages_checked = concatenate_pages(pages, start_idx, pages_to_concatenate)
            if combined_content:
                logger.info(f"Memory log first batch {batches_processed + 1}/{batches_to_process}: Processing pages starting at {start_idx}")
                summary = process_memory_log_page(pages, start_idx, combined_content, template_strings)["page_content"]
                memory_log = update_memory_log(memory_log, summary, template_strings)
                logger.info(f"Memory log first batch {batches_processed + 1}/{batches_to_process}: Complete (current log length: {len(memory_log)} chars)")
                batches_processed += 1
            start_idx += pages_checked
    else:
        logger.warning("No data pages found in first pass")

    # Process the last N batches (if document is long enough to avoid overlap)
    if batches_to_process > 0 and num_pages > (batches_to_process * pages_to_concatenate * 2):
        logger.info(f"Processing last {batches_to_process} batches for memory log (up to {batches_to_process * pages_to_concatenate} pages)")
        
        # Start from position where we'd get the last N batches worth of pages
        end_start_idx = num_pages - (batches_to_process * pages_to_concatenate)
        current_idx = end_start_idx
        batches_processed = 0
        
        while batches_processed < batches_to_process and current_idx < num_pages:
            next_data_idx = find_next_data_page(pages, current_idx)
            if next_data_idx is None:
                logger.info("No more data pages found in last pass")
                break
            
            combined_content, pages_checked = concatenate_pages(pages, next_data_idx, pages_to_concatenate)
            if combined_content:
                logger.info(f"Memory log last batch {batches_processed + 1}/{batches_to_process}: Processing pages starting at {next_data_idx}")
                summary = process_memory_log_page(pages, next_data_idx, combined_content, template_strings)["page_content"]
                memory_log = update_memory_log(memory_log, summary, template_strings)
                logger.info(f"Memory log last batch {batches_processed + 1}/{batches_to_process}: Complete")
                batches_processed += 1
            
            current_idx = next_data_idx + pages_checked

    logger.info(f"Memory log creation complete (final length: {len(memory_log)} chars)")
    return memory_log

# ============================================================================
# PAGE SUMMARIZATION FUNCTIONS

def process_batch_wrapper(args):
    """Wrapper function for multiprocessing - unpacks arguments and recreates templates"""
    batch, num_pages_to_concat, template_strings = args
    return process_batch(batch, num_pages_to_concat, template_strings)

def process_batch(batch, num_pages_to_concat, template_strings):
    """Process a batch of pages, concatenating and summarizing them."""
    logger.debug(f"Processing batch of {len(batch)} pages (concat={num_pages_to_concat})")
    results = []
    i = 0

    while i < len(batch):
        concat_pages = []
        page_numbers = []
        
        while len(concat_pages) < num_pages_to_concat and i < len(batch):
            current_page = batch[i]['page_content'].replace("\n", " ")
            if "No data to be processed on this page" not in current_page and current_page.strip():
                concat_pages.append(current_page)
                page_numbers.append(batch[i]['page_number'])
            i += 1

        if concat_pages:
            original_document = " ".join(concat_pages)
            logger.debug(f"Batch: Summarizing pages {page_numbers} (combined length: {len(original_document)} chars)")

            # Initial summary
            template = Template(template_strings['page_summary'])
            prompt = template.render(current_page=original_document)
            time.sleep(0.2)  # Rate limiting delay
            initial_summary = llm.run_inference(prompt)
            logger.debug(f"Batch pages {page_numbers}: Initial summary generated (length: {len(initial_summary)} chars)")

            # Verification step
            template = Template(template_strings['page_verification'])
            prompt = template.render(
                original_document=original_document,
                current_summary=initial_summary
            )
            time.sleep(0.2)  # Rate limiting delay
            verified_summary = llm.run_inference(prompt)
            logger.debug(f"Batch pages {page_numbers}: Verified summary generated (length: {len(verified_summary)} chars)")

            results.append({
                "page_content": verified_summary,
                "page_numbers": page_numbers,
                "original_input": original_document
            })

        if not concat_pages:
            break

    logger.debug(f"Batch processing complete: {len(results)} summaries generated")
    return results

def generate_summaries(pages, template_strings, batch_size=20, num_pages_to_concat=5):
    """Generate summaries for all pages using parallel processing."""
    logger.info(f"Generating summaries for {len(pages)} pages (batch_size={batch_size}, concat={num_pages_to_concat})")
    batches = create_batches(pages, batch_size)
    logger.info(f"Created {len(batches)} batches for parallel processing")
    
    results = []
    max_workers = 20  # Batches per interval
    logger.info(f"Using ThreadPoolExecutor with max_workers={max_workers}")
    
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Prepare arguments for each batch
        batch_args = [(batch, num_pages_to_concat, template_strings) for batch in batches]
        
        # Submit all jobs
        futures = [executor.submit(process_batch_wrapper, args) for args in batch_args]
        logger.info(f"Submitted {len(futures)} batch jobs")
        
        # Collect results as they complete
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                batch_results = future.result()
                results.extend(batch_results)
                completed += 1
                logger.info(f"Batch {completed}/{len(futures)} completed ({len(batch_results)} summaries)")
            except Exception as e:
                logger.error(f"Batch processing failed: {e}", exc_info=True)
                completed += 1

    elapsed = time.time() - start_time
    logger.info(f"Summary generation complete: {len(results)} summaries in {elapsed:.2f}s")
    return results

# ============================================================================
# SUMMARY COMBINING FUNCTIONS

def combine_and_verify_pair_wrapper(args):
    """Wrapper for parallel combining"""
    summary_1, summary_2, template_strings = args
    return combine_and_verify_pair(summary_1, summary_2, template_strings)

def condense_interval_summary(interval_summary: dict, template_strings: dict) -> dict:
    """
    Condense interval summary to exactly 10.
    """
    logger.info("Condensing interval summary to top 18 bulletpoints")
    
    original_content = interval_summary["page_content"] if isinstance(interval_summary, dict) else interval_summary
    
    # Create condensation prompt
    template = Template(template_strings['condense_interval'])
    prompt = template.render(full_interval_summary=original_content)
    
    condensed_content = llm.run_inference(prompt)
    
    logger.info(f"Condensed summary from {len(original_content)} to {len(condensed_content)} characters")
    
    return {
        "page_content": condensed_content,
        "page_numbers": interval_summary.get("page_numbers", [])
    }


def combine_and_verify_pair(summary_1, summary_2, template_strings):
    """Combine two summaries and verify the result."""
    logger.debug(f"Combining summaries for pages {summary_1['page_numbers']} and {summary_2['page_numbers']}")

    # Combine
    template = Template(template_strings['combine'])
    prompt = template.render(
        summary_1=summary_1["page_content"],
        summary_2=summary_2["page_content"]
    )
    time.sleep(0.2)  # Rate limiting delay
    combined_summary = llm.run_inference(prompt)
    logger.debug(f"Combined summary generated (length: {len(combined_summary)} chars)")

    # Verify
    template = Template(template_strings['verification'])
    prompt = template.render(
        current_combined_summary=combined_summary,
        summary_1=summary_1["page_content"],
        summary_2=summary_2["page_content"]
    )
    time.sleep(0.2)  # Rate limiting delay
    verified_summary = llm.run_inference(prompt)
    logger.debug(f"Verified combined summary (length: {len(verified_summary)} chars)")
    
    result = {
        "page_content": verified_summary,
        "page_numbers": summary_1["page_numbers"] + summary_2["page_numbers"]
    }
    logger.debug(f"Combined pages {result['page_numbers']}")
    return result

def parallel_combine(summaries, template_strings, depth=0):
    """Combine summaries"""
    indent = "  " * depth
    logger.info(f"{indent}Parallel combine: {len(summaries)} summaries at depth {depth}")
    
    if len(summaries) == 1:
        logger.info(f"{indent}Single summary remaining, returning")
        return summaries[0]
    elif len(summaries) == 2:
        logger.info(f"{indent}Two summaries, combining directly")
        return combine_and_verify_pair(summaries[0], summaries[1], template_strings)

    # Sort summaries based on the first page number in each summary
    sorted_summaries = sorted(summaries, key=lambda x: min(x["page_numbers"]))
    logger.debug(f"{indent}Sorted {len(sorted_summaries)} summaries by page number")

    # Pair adjacent summaries
    pairs = [(sorted_summaries[i], sorted_summaries[i+1]) 
             for i in range(0, len(sorted_summaries) - 1, 2)]
    logger.info(f"{indent}Created {len(pairs)} pairs for parallel processing")
    
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:  # Combining workers
        # Prepare arguments
        pair_args = [(pair[0], pair[1], template_strings) for pair in pairs]
        
        futures = [executor.submit(combine_and_verify_pair_wrapper, args) for args in pair_args]
        combined_results = []
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                combined_results.append(result)
                completed += 1
                logger.debug(f"{indent}Pair {completed}/{len(pairs)} combined")
            except Exception as e:
                logger.error(f"{indent}Pair combining failed: {e}", exc_info=True)

    elapsed = time.time() - start_time
    logger.info(f"{indent}Parallel combining complete: {len(combined_results)} results in {elapsed:.2f}s")

    # If there's an odd number of summaries, add the last one to the combined results
    if len(sorted_summaries) % 2 != 0:
        logger.info(f"{indent}Adding unpaired summary to results")
        combined_results.append(sorted_summaries[-1])

    # Recursively combine the results
    logger.info(f"{indent}Recursing with {len(combined_results)} summaries")
    return parallel_combine(combined_results, template_strings, depth + 1)

def combine_summaries(summaries, template_strings):
    """Combine all summaries into a single summary."""
    if not summaries:
        logger.warning("No summaries to combine")
        return None, ""

    logger.info(f"Starting summary combination with {len(summaries)} summaries")
    final_summary = parallel_combine(summaries, template_strings)
    logger.info("Summary combination complete")
    return final_summary, ""

def process_summaries(page_summaries, template_strings):
    """Process summaries by combining them."""
    logger.info(f"Processing {len(page_summaries)} page summaries")
    combined_summary, memory_log = combine_summaries(page_summaries, template_strings)
    logger.info("Summary processing complete")
    return combined_summary, memory_log

# ============================================================================
# INTERVAL PROCESSING

def process_interval_wrapper(args):
    """Wrapper for multiprocessing - unpacks arguments"""
    interval_index, start_index, interval_size, pages, template_strings = args
    return process_interval(interval_index, start_index, interval_size, pages, template_strings)

def process_interval(interval_index, start_index, interval_size, pages, template_strings):
    """Process a single interval of pages."""
    end_index = start_index + interval_size
    interval_pages = pages[start_index:end_index]

    logger.info(f"Interval {interval_index}: Processing pages {start_index+1} to {end_index} ({len(interval_pages)} pages)")
    
    start_time = time.time()
    page_summaries = generate_summaries(interval_pages, template_strings)
    logger.info(f"Interval {interval_index}: Generated {len(page_summaries)} page summaries")
    
    combined_summary, _ = process_summaries(page_summaries, template_strings)
    logger.info(f"Interval {interval_index}: Combined summaries")

    # condensed_summary = condense_interval_summary(combined_summary, template_strings)
    # logger.info(f"Interval {interval_index}: Condensed to final bulletpoints")
    
    # elapsed = time.time() - start_time
    # logger.info(f"Interval {interval_index}: Complete in {elapsed:.2f}s")
    
    return combined_summary
    
def process_file(pages, sha1, output_directory, template_strings):
    """Process a file by dividing it into intervals and processing them in parallel."""
    total_pages = len(pages)
    
    # Handle empty document case
    if total_pages == 0:
        logger.warning(f"Document {sha1} has no pages")
        return [], {"summaries": []}
    
    logger.info(f"Processing document {sha1} with {total_pages} pages")
    
    # Divide into 4 intervals
    num_intervals = 4
    base_interval_size = total_pages // num_intervals
    extra_pages = total_pages % num_intervals
    interval_sizes = [
        base_interval_size + (1 if i < extra_pages else 0) for i in range(num_intervals)
    ]
    
    logger.info(f"Divided into {num_intervals} intervals: {interval_sizes}")
    
    # Process intervals using ProcessPoolExecutor
    logger.info("Starting parallel interval processing")
    start_time = time.time()

    interval_summaries = []
    max_workers = 4  # Intervals per file (all 4 intervals in parallel)

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Prepare arguments for each interval
        interval_args = [
            (i, sum(interval_sizes[:i]), interval_sizes[i], pages, template_strings)
            for i in range(num_intervals)
        ]
        
        # Submit all interval jobs
        futures = [executor.submit(process_interval_wrapper, args) for args in interval_args]
        logger.info(f"Submitted {len(futures)} interval jobs to ProcessPoolExecutor")
        
        # Collect results as they complete
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                interval_summaries.append(result)
                completed += 1
                logger.info(f"Interval {completed}/{num_intervals} completed")
            except Exception as e:
                logger.error(f"Interval processing failed: {e}", exc_info=True)
                completed += 1
    
    elapsed = time.time() - start_time
    logger.info(f"All intervals processed in {elapsed:.2f}s")
    
    # Create citations data from original pages
    logger.info("Creating citations data")
    citations_data = {
        "summaries": [
            {
                "page_number": page["page_number"],
                "original_input": page["page_content"]
            }
            for page in pages
        ]
    }
    
    return interval_summaries, citations_data

def combine_and_verify_final_pair(summary_1: str, summary_2: str, template_strings: dict) -> str:
    """
    Combine two summaries using final_combine and final_verification templates.

    Args:
        summary_1: First summary text
        summary_2: Second summary text
        template_strings: Dictionary of template strings

    Returns:
        Verified combined summary
    """
    logger.debug(f"Combining and verifying pair (S1: {len(summary_1)} chars, S2: {len(summary_2)} chars)")

    # Step 1: Combine using final_combine_template
    template = Template(template_strings['final_combine'])
    prompt = template.render(
        summary_1=summary_1,
        summary_2=summary_2
    )
    time.sleep(0.2)  # Rate limiting delay
    combined_summary = llm.run_inference(prompt)
    logger.debug(f"Combined summary generated (length: {len(combined_summary)} chars)")

    # Step 2: Verify using final_verification_template
    template = Template(template_strings['final_verification'])
    prompt = template.render(
        current_combined_summary=combined_summary,
        summary_1=summary_1,
        summary_2=summary_2
    )
    time.sleep(0.2)  # Rate limiting delay
    verified_summary = llm.run_inference(prompt)
    logger.debug(f"Verified combined summary (length: {len(verified_summary)} chars)")

    return verified_summary


def hierarchical_combine_final(summaries: List[str], template_strings: dict, depth: int = 0) -> str:
    """
    Hierarchically combine summaries using final_combine and final_verification.

    Args:
        summaries: List of summary strings to combine
        template_strings: Dictionary of template strings
        depth: Current recursion depth (for logging)

    Returns:
        Single combined and verified summary
    """
    indent = "  " * depth
    logger.info(f"{indent}Hierarchical final combine: {len(summaries)} summaries at depth {depth}")

    if len(summaries) == 1:
        logger.info(f"{indent}Single summary remaining, returning")
        return summaries[0]
    elif len(summaries) == 2:
        logger.info(f"{indent}Two summaries, combining and verifying")
        return combine_and_verify_final_pair(summaries[0], summaries[1], template_strings)

    # Combine pairs in parallel
    pairs = []
    for i in range(0, len(summaries) - 1, 2):
        pairs.append((summaries[i], summaries[i + 1]))

    logger.info(f"{indent}Created {len(pairs)} pairs for parallel processing")

    start_time = time.time()
    combined_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # Prepare arguments for each pair
        pair_args = [(pair[0], pair[1], template_strings) for pair in pairs]

        # Submit all jobs
        futures = [
            executor.submit(lambda args: combine_and_verify_final_pair(*args), args)
            for args in pair_args
        ]

        # Collect results
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                combined_results.append(result)
                completed += 1
                logger.debug(f"{indent}Pair {completed}/{len(pairs)} combined and verified")
            except Exception as e:
                logger.error(f"{indent}Pair combining failed: {e}", exc_info=True)

    elapsed = time.time() - start_time
    logger.info(f"{indent}Parallel combining complete: {len(combined_results)} results in {elapsed:.2f}s")

    # If there's an odd number of summaries, add the last one to results
    if len(summaries) % 2 != 0:
        logger.info(f"{indent}Adding unpaired summary to results")
        combined_results.append(summaries[-1])

    # Recursively combine the results
    logger.info(f"{indent}Recursing with {len(combined_results)} summaries")
    return hierarchical_combine_final(combined_results, template_strings, depth + 1)


def improve_with_memory_log(summary: str, memory_log: str, template_strings: dict) -> str:
    """
    Improve summary by incorporating important information from memory log.

    Args:
        summary: Current summary text
        memory_log: Memory log text with high-level information
        template_strings: Dictionary of template strings

    Returns:
        Improved summary with memory log information
    """
    logger.info("Improving summary with memory log")
    logger.debug(f"Summary length: {len(summary)} chars, Memory log length: {len(memory_log)} chars")

    template = Template(template_strings['improve_summary'])
    prompt = template.render(
        summary=summary,
        memory_log=memory_log
    )

    time.sleep(0.2)  # Rate limiting delay
    improved_summary = llm.run_inference(prompt)

    logger.info(f"Improved summary generated (length: {len(improved_summary)} chars)")
    return improved_summary


def organize_summary(summary: str, memory_log: str, template_strings: dict) -> str:
    """
    Organize summary into domain-appropriate structure with headers.

    Args:
        summary: Summary text to organize
        memory_log: Memory log for additional context
        template_strings: Dictionary of template strings

    Returns:
        Organized summary with structured headers and bulletpoints
    """
    logger.info("Organizing summary into final structure")
    logger.debug(f"Summary length: {len(summary)} chars, Memory log length: {len(memory_log)} chars")

    template = Template(template_strings['organization'])
    prompt = template.render(
        summaries=summary,
        memory_log=memory_log
    )

    time.sleep(0.2)  # Rate limiting delay
    organized_summary = llm.run_inference(prompt)

    logger.info(f"Organized summary generated (length: {len(organized_summary)} chars)")
    return organized_summary


def combine_and_finalize_summaries(
    interval_summaries: List[dict],
    memory_log: str,
    template_strings: dict
) -> str:
    """
    Combine interval summaries into one final summary using hierarchical combining,
    then improve with memory log and organize into final structure.

    Args:
        interval_summaries: List of interval summary dicts with 'page_content'
        memory_log: Memory log text with high-level document information
        template_strings: Dictionary of template strings

    Returns:
        Final organized summary string
    """
    logger.info(f"Starting final summary combination and organization for {len(interval_summaries)} intervals")

    # Extract summary text from interval summary dicts
    summary_texts = []
    for i, interval_summary in enumerate(interval_summaries, 1):
        if isinstance(interval_summary, dict):
            content = interval_summary.get("page_content", "")
        else:
            content = interval_summary

        if content and content.strip():
            summary_texts.append(content.strip())
            logger.debug(f"Interval {i}: {len(content)} chars")

    if not summary_texts:
        logger.warning("No summary content to combine")
        return ""

    logger.info(f"Extracted {len(summary_texts)} interval summaries for processing")

    # Step 1: Hierarchically combine all interval summaries into one
    logger.info("Step 1/3: Hierarchically combining interval summaries")
    combined_summary = hierarchical_combine_final(summary_texts, template_strings)
    logger.info(f"Hierarchical combining complete (result: {len(combined_summary)} chars)")

    # Step 2: Improve with memory log
    logger.info("Step 2/3: Improving summary with memory log")
    improved_summary = improve_with_memory_log(combined_summary, memory_log, template_strings)
    logger.info(f"Improvement complete (result: {len(improved_summary)} chars)")

    # Step 3: Organize into final structure
    logger.info("Step 3/3: Organizing summary into final structure")
    final_summary = organize_summary(improved_summary, memory_log, template_strings)
    logger.info(f"Organization complete (result: {len(final_summary)} chars)")

    logger.info("✅ Final summary combination and organization complete")
    return final_summary

def process_file_wrapper(args):
    """Wrapper function for multiprocessing - unpacks arguments for file processing"""
    file_idx, file_data, output_dir, template_strings = args
    
    file_id = file_data.get('sha1', f"file_{file_idx}")
    file_name = file_data.get('file_name', f"file_{file_idx}")
    logger.info(f"Processing {file_name} ({file_idx + 1})")
    
    try:
        # Convert file data to pages list format
        pages = load_pages_from_file_data(file_data, file_idx)
        
        if not pages:
            logger.warning(f"No pages found for {file_name}, skipping")
            summary_data = file_data.copy()
            summary_data['summary'] = None
            summary_data['error'] = "No pages found"
            return summary_data
        
        logger.info(f"Loaded {len(pages)} pages for {file_name}")
        
        # Create memory log for this file
        logger.info(f"Creating memory log for {file_name}")
        memory_log = create_memory_log(pages, template_strings)
        
        # Process file into interval summaries
        logger.info(f"Processing {file_name} into interval summaries")
        interval_summaries, citations_data = process_file(pages, file_id, output_dir, template_strings)
        
        if not interval_summaries:
            logger.warning(f"No interval summaries generated for {file_name}")
            summary_data = file_data.copy()
            summary_data['summary'] = None
            summary_data['error'] = "No summaries generated"
            return summary_data
        
        # Combine, improve, and organize summaries into final format
        logger.info(f"Combining and finalizing summaries for {file_name}")
        full_summary = combine_and_finalize_summaries(interval_summaries, memory_log, template_strings)
        
        # Store summary - keep original metadata, replace OCR with summary
        summary_data = file_data.copy()
        summary_data['summary'] = full_summary
        summary_data['num_pages'] = len(pages)
        summary_data['num_intervals'] = len(interval_summaries)
        
        logger.info(f"✓ Successfully processed {file_name}")
        return summary_data
        
    except Exception as e:
        logger.error(f"Failed to process {file_name}: {e}", exc_info=True)
        summary_data = file_data.copy()
        summary_data['summary'] = None
        summary_data['error'] = str(e)
        return summary_data
    

def process_case(input_json_path: Path, output_dir: Path, template_strings):
    """Process a single case: summarize each file in parallel and save results."""
    case_name = input_json_path.stem.replace('agency_case_file_bundle-', '')
    
    logger.info("="*80)
    logger.info(f"Processing case: {case_name}")
    logger.info(f"JSON path: {input_json_path}")
    logger.info("="*80)
    
    # Load case data
    try:
        with open(input_json_path, 'r') as f:
            case_json = json.load(f)
        
        case_files = case_json.get('case_files', [])
        logger.info(f"Loaded {len(case_files)} files for case {case_name}")
            
    except Exception as e:
        logger.error(f"Failed to load case data: {e}", exc_info=True)
        
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        failure_log_path = logs_dir / f"FAILED_{case_name}.txt"
        with open(failure_log_path, 'w') as f:
            f.write(f"Case: {case_name}\n")
            f.write(f"Status: FAILED TO LOAD CASE DATA\n")
            f.write(f"Input JSON: {input_json_path}\n")
            f.write(f"Error: {str(e)}\n\n")
            f.write("="*80 + "\n")
            f.write("FULL TRACEBACK:\n")
            f.write("="*80 + "\n")
            import traceback
            f.write(traceback.format_exc())
        logger.info(f"Wrote failure log to {failure_log_path}")
        
        return None
    
    if not case_files:
        logger.warning(f"No files found in case {case_name}")
        
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        failure_log_path = logs_dir / f"FAILED_{case_name}.txt"
        with open(failure_log_path, 'w') as f:
            f.write(f"Case: {case_name}\n")
            f.write(f"Status: NO FILES FOUND\n")
            f.write(f"Input JSON: {input_json_path}\n")
            f.write(f"Case files list was empty\n")
        logger.info(f"Wrote failure log to {failure_log_path}")
        
        return None
    
    # Prepare arguments for parallel processing
    file_args = [
        (file_idx, file_data, output_dir, template_strings)
        for file_idx, file_data in enumerate(case_files)
    ]
    
    # Process files in parallel
    num_workers = 10  # Files per case
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        case_summaries = list(executor.map(process_file_wrapper, file_args))
    
    # Check if we got any successful summaries
    successful_summaries = [s for s in case_summaries if s.get('summary') is not None]
    failed_files = [s for s in case_summaries if s.get('error') is not None]
    
    # Write failure log if any files failed
    if failed_files:
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        failure_log_path = logs_dir / f"FAILED_{case_name}.txt"
        with open(failure_log_path, 'w') as f:
            f.write(f"Case: {case_name}\n")
            f.write(f"Input JSON: {input_json_path}\n")
            f.write(f"Total files: {len(case_files)}\n")
            f.write(f"Successful: {len(successful_summaries)}\n")
            f.write(f"Failed: {len(failed_files)}\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n" + "="*80 + "\n")
            f.write("FAILED FILES DETAILS\n")
            f.write("="*80 + "\n\n")
            
            for idx, failed in enumerate(failed_files, 1):
                f.write(f"[{idx}] File: {failed.get('file_name', 'Unknown')}\n")
                f.write(f"    SHA1: {failed.get('sha1', 'N/A')}\n")
                f.write(f"    Error: {failed.get('error', 'Unknown error')}\n")
                
                # Include additional context if available
                if 'num_pages' in failed:
                    f.write(f"    Pages: {failed.get('num_pages')}\n")
                
                f.write("\n")
        
        logger.info(f"Wrote failure log to {failure_log_path}")
        logger.warning(f"{len(failed_files)} file(s) failed in case {case_name}")
    
    if not successful_summaries:
        logger.warning(f"No files successfully processed for case {case_name}")
        return None
    
    # Save output - mirror input structure but with summaries instead of OCR
    output_data = {
        "case_files": case_summaries,
        "redacted": case_json.get('redacted', False)
    }
    
    output_path = output_dir / input_json_path.name
    try:
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Saved summaries to {output_path}")
        logger.info(f"Successfully summarized {len(successful_summaries)}/{len(case_files)} files")
    except Exception as e:
        logger.error(f"Failed to save summaries: {e}", exc_info=True)

        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        failure_log_path = logs_dir / f"FAILED_{case_name}.txt"
        with open(failure_log_path, 'w') as f:
            f.write(f"Case: {case_name}\n")
            f.write(f"Status: FAILED TO SAVE OUTPUT\n")
            f.write(f"Output path: {output_path}\n")
            f.write(f"Error: {str(e)}\n\n")
            f.write("="*80 + "\n")
            f.write("FULL TRACEBACK:\n")
            f.write("="*80 + "\n")
            import traceback
            f.write(traceback.format_exc())
        logger.info(f"Wrote failure log to {failure_log_path}")
        
        return None
    
    return output_path


def process_case_wrapper(args):
    """Wrapper function for parallel case processing - unpacks arguments"""
    idx, json_path, output_dir, template_strings, already_processed = args

    case_name = json_path.stem.replace('agency_case_file_bundle-', '')

    # Skip if already processed
    if json_path.name in already_processed:
        logger.info(f"⊘ Already processed, skipping case {idx}: {case_name}")
        return ('skipped', case_name, idx)

    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"Case {idx}")
        logger.info(f"{'='*80}")

        output_path = process_case(json_path, output_dir, template_strings)

        if output_path:
            logger.info(f"✓ Successfully processed case {idx}: {case_name}")
            return ('success', case_name, idx)
        else:
            logger.warning(f"✗ No summaries generated for case {idx}: {case_name}")
            return ('failed', case_name, idx)

    except Exception as e:
        logger.error(f"✗ Error processing case {idx}: {case_name}")
        logger.error(f"Error details: {e}", exc_info=True)
        return ('failed', case_name, idx)


def main(input_directory, output_directory):
    """Main function to process all cases in the input directory."""
    logger.info("="*80)
    logger.info("CASE SUMMARIZATION PIPELINE")
    logger.info("="*80)
    
    input_dir = Path(input_directory)
    output_dir = Path(output_directory)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Input directory: {input_dir}")
    logger.info(f"Output directory: {output_dir}")
    
    # Load templates
    logger.info("Loading Jinja2 template strings")
    try:
        template_strings = get_template_strings()
    except Exception as e:
        logger.error(f"Failed to load templates: {e}", exc_info=True)
        return
    
    # Find all JSON files in input directory
    json_files = list(input_dir.glob("agency_case_file_bundle-*.json"))
    logger.info(f"Found {len(json_files)} case JSON files to process")
    
    if len(json_files) == 0:
        logger.error("No case JSON files found!")
        return
    
    # Check which cases have already been processed
    already_processed = set()
    for output_file in output_dir.glob("agency_case_file_bundle-*.json"):
        already_processed.add(output_file.name)

    if already_processed:
        logger.info(f"Found {len(already_processed)} already processed cases")

    # Prepare arguments for parallel case processing
    case_args = [
        (idx, json_path, output_dir, template_strings, already_processed)
        for idx, json_path in enumerate(json_files, 1)
    ]

    # Process cases in parallel
    case_workers = 15  # Cases in parallel
    logger.info(f"Processing cases in parallel with {case_workers} workers")

    successful = 0
    failed = 0
    skipped = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=case_workers) as executor:
        futures = [executor.submit(process_case_wrapper, args) for args in case_args]

        for future in concurrent.futures.as_completed(futures):
            try:
                status, case_name, idx = future.result()
                if status == 'success':
                    successful += 1
                elif status == 'failed':
                    failed += 1
                elif status == 'skipped':
                    skipped += 1
            except Exception as e:
                failed += 1
                logger.error(f"Case processing exception: {e}", exc_info=True)
    
    # Final summary
    logger.info("\n" + "="*80)
    logger.info("PIPELINE COMPLETE")
    logger.info("="*80)
    logger.info(f"Total cases: {len(json_files)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Skipped: {skipped}")
    logger.info(f"Failed: {failed}")
    if (len(json_files) - skipped) > 0:
        logger.info(f"Success rate: {(successful/(len(json_files)-skipped)*100):.1f}%")
    logger.info("="*80)


if __name__ == "__main__":    
    parser = argparse.ArgumentParser(description='Generate summaries for case files')
    parser.add_argument('--input', default='../data/input', help='Input directory containing case JSON files')
    parser.add_argument('--output', default='../data/output/all', help='Output directory for summaries')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose (DEBUG) logging')
    
    args = parser.parse_args()
    
    # Adjust logging level if verbose
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled")
    
    logger.info(f"Starting case summarization pipeline")
    logger.info(f"Input directory: {args.input}")
    logger.info(f"Output directory: {args.output}")
    
    try:
        main(args.input, args.output)
    except KeyboardInterrupt:
        logger.warning("\nPipeline interrupted by user")
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}", exc_info=True)
        sys.exit(1)