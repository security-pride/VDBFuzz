#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vector Database (VDB) fuzzing tool - automatic test generator.

This module builds test templates from log files. Workflow:
1. Recursively scan JSON log files in the given directory.
2. Use LogParser to extract HTTP requests.
3. Use TemplateGenerator to produce test templates for each test.
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, "") and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __package__ in (None, ""):
    from vdbfuzz.parser import LogParser
    from vdbfuzz.template_generator import TemplateGenerator
else:
    from .parser import LogParser
    from .template_generator import TemplateGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vdbfuzz.generator')


class VDBTestGenerator:
    """
    VDB test generator that automates the path from log files to test templates.
    """
    
    # Supported VDB types
    SUPPORTED_VDB_TYPES = ['qdrant', 'weaviate', 'milvus']
    
    def __init__(self, logs_dir: str, output_dir: str, target_url: str = '', skip_parsing: bool = False, parsed_requests_dir: str = None, vdb_type: str = None):
        """
        Initialize the test generator.
        
        Args:
            logs_dir: directory containing log files
            output_dir: directory to write generated test templates
            target_url: target VDB server URL (optional)
            skip_parsing: skip parsing and directly use existing parsed results
            parsed_requests_dir: directory of existing parsed results; defaults to output_dir/parsed_requests
            vdb_type: explicitly specified VDB type, overrides directory inference
        """
        self.logs_dir = Path(logs_dir)
        self.output_dir = Path(output_dir)
        self.target_url = target_url
        self.skip_parsing = skip_parsing
        self.explicit_vdb_type = vdb_type.lower() if vdb_type else None
        
        # Validate VDB type
        if self.explicit_vdb_type and self.explicit_vdb_type not in self.SUPPORTED_VDB_TYPES:
            logger.warning(f"Unsupported VDB type: {vdb_type}, will infer from directory name")
            self.explicit_vdb_type = None
        
        # Configure parsed-results directory
        if parsed_requests_dir:
            self.parsed_dir = Path(parsed_requests_dir)
        else:
            self.parsed_dir = self.output_dir / "parsed_requests"
        
        # Ensure output directories exist
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.parsed_dir.mkdir(exist_ok=True, parents=True)
    
    def process_directory(self) -> Dict[str, List[str]]:
        """
        Process a log directory and generate test templates.
        
        Returns:
            dict: {VDB type: [generated template paths]}
        """
        start_time = time.time()
        
        # If skipping parsing, directly use existing parsed results
        if self.skip_parsing:
            logger.info(f"Skip parsing, use existing parsed results: {self.parsed_dir}")
            # Find and load all JSON files
            extracted_files = {}
            vdb_type = self.explicit_vdb_type or "unknown"
            
            for json_file in self.parsed_dir.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        test_name = data.get('test_name')
                        if test_name:
                            extracted_files[test_name] = str(json_file)
                            # Prefer explicit VDB type; otherwise use the first file's type
                            if vdb_type == "unknown":
                                vdb_type = data.get('vdb_type', 'qdrant')
                except Exception as e:
                    logger.warning(f"Failed to load request file {json_file}: {str(e)}")
            
            if not extracted_files:
                logger.error(f"No valid request files found in {self.parsed_dir}")
                return {}
                
            logger.info(f"Loaded {len(extracted_files)} request files from {self.parsed_dir}")
        
        else:
            # Normal parsing flow
            logger.info(f"Start processing log directory: {self.logs_dir}")
            
            # Create parser with explicit VDB type if provided
            parser = LogParser(self.logs_dir, vdb_type=self.explicit_vdb_type)
            
            # Extract and save requests
            extracted_files = parser.save_extracted_requests(self.parsed_dir)
            vdb_type = parser.vdb_type
            
            if not extracted_files:
                logger.error(f"No valid log files found in {self.logs_dir}")
                return {}
            
        # Group by VDB type
        templates_by_type = {}
        
        # Create subdirectory for the VDB type
        vdb_output_dir = self.output_dir / vdb_type
        vdb_output_dir.mkdir(exist_ok=True, parents=True)
        logger.info(f"Templates will be written to: {vdb_output_dir}")
        
        # Generate test templates
        for test_name, request_file in extracted_files.items():
            try:
                logger.info(f"Generate template for test {test_name}")
                generator = TemplateGenerator(
                    input_file=request_file,
                    output_dir=vdb_output_dir,  # use VDB-type subdirectory
                    target_url=self.target_url
                )
                
                template_paths = generator.generate_template()
                
                # In skip-parsing mode, use previously derived VDB type
                if not hasattr(self, 'vdb_type'):
                    self.vdb_type = vdb_type
                    
                if self.vdb_type not in templates_by_type:
                    templates_by_type[self.vdb_type] = []
                    
                templates_by_type[self.vdb_type].extend(template_paths)
                
            except Exception as e:
                logger.error(f"Failed to generate template for test {test_name}: {str(e)}")
        
        # Build summary
        total_templates = sum(len(templates) for templates in templates_by_type.values())
        elapsed_time = time.time() - start_time
        
        logger.info(f"Template generation finished! Time: {elapsed_time:.2f} seconds")
        logger.info(f"Generated {total_templates} test templates under {self.output_dir}")
        
        # Write summary file
        summary_file = self.output_dir / "generation_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump({
                "logs_directory": str(self.logs_dir),
                "templates_directory": str(self.output_dir),
                "generation_time": elapsed_time,
                "total_templates": total_templates,
                "templates_by_type": {k: len(v) for k, v in templates_by_type.items()},
                "template_files": {k: [str(p) for p in v] for k, v in templates_by_type.items()}
            }, f, indent=2)
            
        logger.info(f"Summary saved to {summary_file}")
        
        return templates_by_type


def main():
    """Command-line entrypoint"""
    parser = argparse.ArgumentParser(description='VDB fuzz testing - automatic test template generator')
    parser.add_argument('-i', '--input-dir', type=str, required=False,
                     help='Directory containing JSON log files')
    parser.add_argument('-o', '--output-dir', type=str, default='./templates',
                      help='Directory to output generated test templates')
    parser.add_argument('-t', '--target', type=str, default='',
                      help='Target server URL (e.g., http://localhost:6333)')
    parser.add_argument('-s', '--skip-parsing', action='store_true',
                      help='Skip parsing and use existing parsed results')
    parser.add_argument('-p', '--parsed-dir', type=str, 
                      help='Directory of existing parsed results; defaults to <output-dir>/parsed_requests')
    parser.add_argument('-vdb', '--vdb-type', type=str, choices=['qdrant', 'weaviate', 'milvus'],
                      help='Target VDB type for directed mutation; overrides directory inference')
    
    args = parser.parse_args()
    
    # If skipping parsing, input-dir becomes optional
    if args.skip_parsing and not args.input_dir:
        args.input_dir = '.'  # Use current directory as placeholder
    elif not args.skip_parsing and not args.input_dir:
        parser.error('When not skipping parsing, --input-dir is required')
    
    # Create generator and process
    generator = VDBTestGenerator(
        logs_dir=args.input_dir,
        output_dir=args.output_dir,
        target_url=args.target,
        skip_parsing=args.skip_parsing,
        parsed_requests_dir=args.parsed_dir,
        vdb_type=args.vdb_type
    )
    
    try:
        generator.process_directory()
    except KeyboardInterrupt:
        logger.warning("User interrupted execution")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
