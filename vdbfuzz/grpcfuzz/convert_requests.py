#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert a single request file into the batch format expected by the fuzzer
"""

import json
import os
import glob
import argparse
import time
from datetime import datetime

def convert_single_request_to_batch(input_file, output_file=None):
    """Convert a single-request JSON file into batch request format."""
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
        
        # Check whether the file is already in batch format
        if "requests" in data and isinstance(data["requests"], list):
            print(f"File {input_file} is already in batch format; no conversion is needed")
            return input_file
        
        # Create the batch-format payload
        batch_data = {
            "timestamp": int(time.time()),
            "script": os.path.basename(input_file),
            "requests": [data]
        }
        
        # If no output file is provided, create a new file in the same directory
        if output_file is None:
            directory = os.path.dirname(input_file)
            filename = os.path.basename(input_file)
            name, ext = os.path.splitext(filename)
            output_file = os.path.join(directory, f"{name}_batch{ext}")
        
        # Write the output file
        with open(output_file, 'w') as f:
            json.dump(batch_data, f, indent=2)
        
        print(f"Successfully converted {input_file} to batch format and saved it to {output_file}")
        return output_file
    
    except Exception as e:
        print(f"Failed to convert file {input_file}: {e}")
        return None

def convert_directory(directory, pattern="*.json"):
    """Convert all matching JSON files in a directory."""
    files = glob.glob(os.path.join(directory, "**", pattern), recursive=True)
    converted_count = 0
    
    for file in files:
        if convert_single_request_to_batch(file) is not None:
            converted_count += 1
    
    print(f"Converted a total of {converted_count} files")

def main():
    parser = argparse.ArgumentParser(description="Convert a single request file into the batch format required by the fuzzer")
    parser.add_argument("--file", help="Path to the single JSON file to convert")
    parser.add_argument("--dir", help="Directory to convert; all JSON files in the directory will be processed")
    parser.add_argument("--output", help="Output file path (used only for single-file conversion)")
    
    args = parser.parse_args()
    
    if args.file:
        convert_single_request_to_batch(args.file, args.output)
    elif args.dir:
        convert_directory(args.dir)
    else:
        print("Please specify either --file or --dir")

if __name__ == "__main__":
    main()
