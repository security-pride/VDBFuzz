#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge multiple gRPC request log files into one combined request set
"""

import json
import os
import glob
import argparse
import time

def merge_request_files(input_files, output_file=None):
    """Merge multiple request files into one combined request set."""
    all_requests = []
    
    for file in input_files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
            
            # Check the file format and extract requests
            if "requests" in data and isinstance(data["requests"], list):
                all_requests.extend(data["requests"])
            else:
                # If the file contains a single request, append it directly
                all_requests.append(data)
            
            print(f"Extracted from file {file}: extracted {len(data.get('requests', [1]))} requests")
        except Exception as e:
            print(f"Failed to process file {file}: {e}")
    
    # Create the merged payload
    merged_data = {
        "timestamp": int(time.time()),
        "script": "merged_requests",
        "requests": all_requests
    }
    
    # If no output file is provided, use a default filename
    if output_file is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        output_file = f"merged_requests_{timestamp}.json"
    
    # Write the output file
    with open(output_file, 'w') as f:
        json.dump(merged_data, f, indent=2)
    
    print(f"Successfully merged {len(all_requests)} requests into file {output_file}")
    return output_file

def find_request_files(directory, pattern="*_batch.json"):
    """Find all matching request files in a directory."""
    return glob.glob(os.path.join(directory, "**", pattern), recursive=True)

def main():
    parser = argparse.ArgumentParser(description="Merge multiple gRPC request log files")
    parser.add_argument("--dir", help="Directory to scan; all matching JSON files will be merged")
    parser.add_argument("--pattern", default="*_batch.json", help="Filename pattern to match; defaults to *_batch.json")
    parser.add_argument("--files", nargs="+", help="List of files to merge")
    parser.add_argument("--output", help="Output file path")
    
    args = parser.parse_args()
    
    if args.dir:
        files = find_request_files(args.dir, args.pattern)
        if files:
            merge_request_files(files, args.output)
        else:
            print(f"No files matching {args.dir} were found in directory {args.pattern}")
    elif args.files:
        merge_request_files(args.files, args.output)
    else:
        print("Please specify either --dir or --files")

if __name__ == "__main__":
    main()
