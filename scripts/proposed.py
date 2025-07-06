import csv
from pathlib import Path
import os
import json
from segment import get_missing_coverage, CodeSegment
import anthropic
from dotenv import load_dotenv
import sys
from typing import Union

# Add TestGeneration to pat
# Import required modules
# import eval_overall
from eval_overall import run_evolution123
from data_utils import write_jsonl, add_lineno, line_code1, code_in_line, line_code, extract, fix_line_breaks_in_code, find_path_from_target_to_root, similarity, solve, extract_python_code_block, extract_line, extract_test_func, find_enclosing_def_class, seg_code_divide_class, extract_class_names
from utils.codetransform import static_slicing, utils1
from utils.codetransform.next import execute_and_trace

# Import coverage measurement from coverup
# try:
#     from coverup.testrunner import measure_suite_coverage, measure_test_coverage
#     from coverup.segment import get_missing_coverage, CodeSegment
#     from coverup.utils import summary_coverage
#     COVERUP_AVAILABLE = True
# except ImportError:
#     print("Warning: CoverUp modules not available, using fallback coverage measurement")
#     COVERUP_AVAILABLE = False

test_apps = Path("codamosa/replication/test-apps")
mutap_benchmarks = Path("MuTAP-benchmarks")
eval_path = Path(__file__).parent.parent

# Load environment variables
load_dotenv()

def parse_args():
    import argparse
    ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    ap.add_argument('package', type=str, nargs='?',
                    help='only process the given package')

    ap.add_argument('--dry-run', dest='dry_run', action='store_true',
                help="only print out the command(s), but don't execute them")
    ap.add_argument('--no-dry-run', dest='dry_run', action='store_false',
                    help="execute the commands instead of just printing them")
    ap.set_defaults(dry_run=False)

    ap.add_argument('--suite', choices=['cm', '1_0', 'mutap'], default='cm',
                    help='suite of modules to compare')

    ap.add_argument('--skip-package', action='append', default=[], help='skip given package')

    ap.add_argument('--config', type=str, help='specify a (non-default) configuration to use')

    ap.add_argument('--get-test-coverage', dest='get_test_coverage', action='store_true',
                help='measure per-test coverage (rather than run CoverUp)')
    ap.add_argument('--no-get-test-coverage', dest='get_test_coverage', action='store_false',
                    help='run CoverUp instead of measuring per-test coverage')
    ap.set_defaults(get_test_coverage=True)

    ap.add_argument('--interactive', dest='interactive', action='store_true',
                help='interactive')
    ap.add_argument('--no-interactive', dest='interactive', action='store_false',
                    help='interactive')
    ap.set_defaults(interactive=True)

    ap.add_argument('--only', dest='only', action='store_true',
                help='only run the specified test(s)')
    ap.add_argument('--no-only', dest='only', action='store_false',
                    help='run all tests (not just specified ones)')
    ap.set_defaults(only=False)

    ap.add_argument('--pip-cache', dest='pip_cache', action='store_true',
                help='mount pip cache volume in Docker container')
    ap.add_argument('--no-pip-cache', dest='pip_cache', action='store_false',
                    help='do not mount pip cache volume in Docker container')
    ap.set_defaults(pip_cache=True)

    args = ap.parse_args()

    if args.interactive and not args.package:
        ap.error("package is required when using --interactive.")

    return args

def load_suite(suite):
    pkg = dict()

    if suite == 'mutap':
        for d in sorted(mutap_benchmarks.iterdir()):
            pkg[d] = {
                'package': d.name,
                'src': Path(),
                'files': [str(Path(d.name) / "__init__.py")]
            }
    else:
        modules_csv = test_apps / f"{suite}_modules.csv"
        with modules_csv.open() as f:
            reader = csv.reader(f)
            for d, m in reader:
                d = Path(d)
                assert d.parts[0] == 'test-apps'
                pkg_top = test_apps / d.parts[1] # package topdir
                pkg_name = m.split('.')[0] # package/module name
                src = Path(*d.parts[2:]) # relative path to 'src' or similar

                if pkg_top not in pkg:
                    pkg[pkg_top] = {
                        'package': pkg_name,
                        'src': src,
                        'files': []
                    }
                else:
                    assert pkg[pkg_top]['package'] == pkg_name
                    assert pkg[pkg_top]['src'] == src

                pkg[pkg_top]['files'].append(str(src / (m.replace('.','/') + ".py")))

    return pkg

def testgeneration_multiround(claude, prompt, generated_tests, system_message):
    """Generate test cases with multi-round conversation"""
    template_append="Generate another test method for the function under test. Your answer must be different from previously-generated test cases, and should cover different statements and branches. Make sure to include necessary imports like 'import datetime', 'import json', etc. if your test uses them. Try different input values, edge cases, and test scenarios."
    messages=[
            {"role": "user", "content": prompt},
        ]
    for _ in range(1):
        response = claude.messages.create(
            model='claude-3-5-sonnet-20241022',
            system=system_message,
            messages=messages,
            max_tokens=256,
        )
        test_gen = response.content[0].text
        messages.append({"role": "assistant", "content": test_gen})
        messages.append({"role": "user", "content": template_append})

        generated_tests.append(test_gen)
        print(test_gen)

    return generated_tests

def testgeneration_multiround_line(claude, prompt, system_message):
    """Generate test cases for specific line coverage"""
    template_append="Generate another test method for the function under test. Your answer must be different strategies from previously-generated test cases to reach target line"
    generated_tests=[]
    messages=[
            {"role": "user", "content": prompt},
        ]
    for _ in range(1):
        response = claude.messages.create(
            model='claude-3-5-sonnet-20241022',
            system=system_message,
            messages=messages,
            max_tokens=256,
        )
        generated_test=response.content[0].text
        messages.append({"role": "assistant", "content": generated_test})
        messages.append({"role": "user", "content": template_append})

        generated_tests.append(generated_test)
        print(generated_test)

    return generated_tests

def testgeneration_feedback(claude, prompt):
    """Generate test cases with execution feedback"""
    generated_tests=[]
    messages=[
            {"role": "user", "content": prompt},
        ]
    for i in range(1):
        response = claude.messages.create(
            model='claude-3-5-sonnet-20241022',
            system=open('scripts/prompt/system_exec.txt').read(),
            messages=messages,
            max_tokens=1024,
        )
        print(f'------------------{i} ---------------------{response.content[0].text}')
        generated_test = extract_python_code_block(response.content[0].text)
        if generated_test!="":
            generated_tests.append(generated_test)
            print(generated_test)

    return generated_tests

def create_test_file_original(test_content, test_dir, test_name, source_file_path):
    """Create a test file with the given content and proper imports"""
    test_file = test_dir / f"{test_name}.py"
    
    # Add proper imports and setup for the test
    source_file_name = Path(source_file_path).stem
    source_file_dir = Path(source_file_path).parent
    
    # Common imports that are often needed
    common_imports = """import sys
import os
import time
import datetime
import json
import re
import math
import random
import collections
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

# Try to import pytest, but don't fail if not available
try:
    import pytest
except ImportError:
    pass
"""
    
    # Create a proper test file with imports
    test_file_content = f"""{common_imports}
# Add source directory to path
source_dir = Path(\"{source_file_dir}\")
if str(source_dir) not in sys.path:
    sys.path.insert(0, str(source_dir))

# Import the module to test
try:
    import {source_file_name}
except ImportError as e:
    print(f\"Warning: Could not import {source_file_name}: {{e}}\")

{test_content}
"""
    
    test_file.write_text(test_file_content)
    return test_file

def create_test_file(test_content, test_dir, test_name, source_file_path):
    """Create a test file with the given content and proper imports (absolute import, no code gốc ghép vào)"""
    test_file = test_dir / f"{test_name}.py"
    source_file_path = Path(source_file_path)
    source_file_name = source_file_path.stem
    source_file_dir = source_file_path.parent

    # Tìm project root (cha của package)
    # Giả sử project root là 2 cấp trên file test (scripts/../..)
    project_root = Path(__file__).resolve().parent.parent

    common_imports = """import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))  # Thêm project root vào sys.path
"""

    # Xác định tên package/module để import
    # Giả sử source_file_path là mypkg/foo.py => package_name = mypkg
    # Nếu source_file_path là mypkg/subpkg/foo.py => package_name = mypkg.subpkg
    try:
        rel_path = source_file_path.relative_to(project_root)
        parts = rel_path.parts[:-1]  # Bỏ tên file, chỉ lấy các thư mục
        if parts:
            package_name = ".".join(parts)
            import_line = f"from {package_name}.{source_file_name} import *\n"
        else:
            import_line = f"import {source_file_name}\n"
    except Exception:
        # Fallback nếu không xác định được package
        import_line = f"import {source_file_name}\n"

    test_file_content = f"""{common_imports}
{import_line}
{test_content}
"""

    test_file.write_text(test_file_content)
    return test_file

def run_test_generation_for_file(claude, file_path, package, output_dir, prompt_template, system_message, pkg_top):
    """Run test generation for a single Python file with coverage measurement using logic from test_new.ipynb"""
    print(f"Processing file: {file_path}")
    
    # Convert relative path to absolute path using pkg_top like eval_coverup.py does
    if not Path(file_path).is_absolute():
        # Use pkg_top (package root directory) to construct absolute path
        absolute_path = pkg_top / file_path
        file_path = str(absolute_path)
    
    try:
        with open(file_path, 'r') as f:
            python_code = f.read()
    except FileNotFoundError:
        print(os.getcwd())
        print(f"Warning: File {file_path} not found")
        return None
    
    if not python_code.strip():
        print(os.getcwd())
        print(f"No content in file {file_path}")
        return None
    
    print(f"Read {len(python_code)} characters from {file_path}")
    
    # Initialize result tracking like in test_new.ipynb
    result_execute = []
    all_execution_line = []
    all_missing_line = []
    # python_code = fix_line_breaks_in_code(python_code)
    # Phase 1: Basic test generation for this file
    print(f"Phase 1: Basic test generation for {file_path}")
    # print(f"python_code: ------------{python_code}\n ------------")
    # divide_code = seg_code_divide_class(python_code)
    coverage = {
    "files": {
        file_path: {
            "missing_lines": line_code(python_code),
            "executed_lines": [],
            "missing_branches": set()
        }
    }
}
    divide_code = get_missing_coverage(coverage, line_limit=100)
    generated_tests = []
    print(f'divide_code:--------------------------- {len(divide_code)} ---------------------------')
    # print(f"divide_code: ------------{divide_code}\n ------------")
    
    if not divide_code:
        print(f"Warning: No class segments found in {file_path}")
        # Tạo một segment duy nhất với toàn bộ code
        divide_code = [python_code]
    # print(f'divide_code:--------------------------- {code_in_line(python_code)} ---------------------------')
    # print(f'line code:--------------------------- {line_code(python_code)} ---------------------------')
    for i, class_segment in enumerate(divide_code):
        # Xác định tên file an toàn
        safe_file_id = str(Path(file_path).relative_to(pkg_top)).replace('/', '_').replace('\\', '_').replace('.', '_')
        # Xử lý class_segment là object hay string
        if hasattr(class_segment, 'name') and hasattr(class_segment, 'get_code'):
            class_name = class_segment.name
            class_segment_code = class_segment.get_code()
        else:
            class_name = Path(file_path).stem  # hoặc 'global'
            class_segment_code = class_segment
        
        prompt = prompt_template.format(program=class_segment_code, func_name=class_name)
        
        print(f"Generating tests for class: {class_name}")
        generated_tests = []
        testgeneration_multiround(claude, prompt, generated_tests, system_message)
        
        # Save generated tests for this class
        testing_data = {
            'task_num': f"{package}_{Path(file_path).stem}_{i}",
            'task_title': f"Test generation for {package} - {Path(file_path).name}",
            'func_name': class_name,
            'difficulty': 'medium',
            'code': python_code,
            'tests': generated_tests
        }
        
        test_file = output_dir / f"testing_{safe_file_id}_{i}.jsonl"
        write_jsonl([testing_data], str(test_file))
        print(f"Saved {len(generated_tests)} tests to {test_file}")
        
        # Tạo file test thực tế (không ghép code gốc vào)
        if generated_tests:
            for idx, test_content in enumerate(generated_tests):
                create_test_file(test_content, output_dir, f"test_{safe_file_id}_{i}_{idx}", file_path)
        
        # Measure coverage for this test set using run_evolution123
        if generated_tests:
            accuracy, missing_line, result_execute, run_exe = run_evolution123(
                result_execute, str(test_file), func_name=class_name, line_cover=0
            )
            
            for x in run_exe:
                if x not in all_execution_line:
                    all_execution_line.append(x)
    
    # Find missing lines after Phase 1
    for x in line_code(python_code):
        if x not in all_execution_line:
            all_missing_line.append(x)
    
    print(f"Missing lines after Phase 1: {all_missing_line}")
    
    # Phase 2: Target line coverage for this file
    print(f"Phase 2: Target line coverage for {file_path}")
    missing_test = all_missing_line.copy()
    missing_final = []
    while len(missing_test) > 0:
        print(f'line code ----------{extract_line(python_code, missing_test[0])}----------------------')
        # print(f'line code real {line_code(python_code)}------------')
        lineno = missing_test[0]
        lineno1 = extract_line(python_code, lineno)
        filtered_code, orig_num_lines, filter_num_lines, reachable_lines = static_slicing.static_slicing(python_code, lineno)
        class_name, function_name = find_enclosing_def_class(python_code, lineno)
        if class_name == None:
            class_name ='unknown_func'
        if function_name == None:
            function_name = ''
            
        print(f'class_name: {class_name}')
        print(f'function_name: {function_name}')
        print(f'-------------------TEST {lineno}---------- REMOVE -------------{filter_num_lines}-------------')
        prompt_line = open('scripts/prompt/template_line.txt').read().format(
            func_name=function_name, 
            class_name=class_name, 
            program=code_in_line(filtered_code), 
            lineno=lineno1
        )
        
        generate_test = testgeneration_multiround_line(claude, prompt_line, system_message)
        testing_data = {
            'task_num': f"{package}_{safe_file_id}_{lineno}",
            'task_title': f"Line coverage for {package}",
            'func_name': class_name,
            'difficulty': 'medium',
            'code': python_code,
            'tests': generate_test
        }
        
        test_file = output_dir / f"testing_{safe_file_id}_{lineno}.jsonl"
        write_jsonl([testing_data], str(test_file))
        
        accuracy, missing_line_new, result_execute, _ = run_evolution123(
            result_execute, str(test_file), func_name=class_name, line_cover=lineno
        )
        
        if lineno not in missing_line_new[0][1]:
            print(f'Line {lineno} is covered')
        else:
            print(f'Line {lineno} is not covered')
            missing_final.append(lineno)
        
        missing_test.remove(lineno)
        for x in missing_test[:]:  # Create a copy to avoid modification during iteration
            if x not in missing_line_new[0][1]:
                print(f'Line {lineno} is covered and continue to cover line {x}')
                missing_test.remove(x)
        print(f'Lines left to cover: {missing_test}')
    
    # Phase 3: Generate with feedback for this file
    print(f"Phase 3: Generate with feedback for {file_path}")
    miss_feedback = []
    
    while len(missing_final) > 0:
        lineno = missing_final[0]
        print(f'-------------------TEST {lineno}---------- FEEDBACK -------------')
        
        best, test_good, execution_good, simi = solve(result_execute, python_code, lineno)
        
        # Xử lý trường hợp solve trả về None
        if best is None or test_good is None:
            print(f'Line {lineno} cannot be solved with feedback')
            miss_feedback.append(lineno)
            missing_final.remove(lineno)
            continue
        
        test_run = extract_test_func(test_good, package)
        filtered_code, orig_num_lines, filter_num_lines, reachable_lines = static_slicing.static_slicing(python_code, lineno)
        class_name, function_name = find_enclosing_def_class(python_code, lineno)
        filtered_code = f'{filtered_code}\n{test_run}'
        if class_name == None:
            class_name ='unknown_func'
        if function_name == None:
            function_name = ''
        prompt_line = open('scripts/prompt/feedback_line.txt').read().format(
            func_name=function_name, 
            class_name=class_name, 
            test=test_run, 
            code=code_in_line(execute_and_trace(filtered_code)), 
            code_linene=extract_line(python_code, lineno)
        )
        
        print(f'Check first --------------- {code_in_line(execute_and_trace(filtered_code))} ---------')
        generate_test = testgeneration_feedback(claude, prompt_line)
        
        if len(generate_test) > 0:
            testing_data = {
                'task_num': f"{package}_{safe_file_id}_{lineno}_feedback",
                'task_title': f"Feedback generation for {package}",
                'func_name': class_name,
                'difficulty': 'medium',
                'code': python_code,
                'tests': generate_test
            }
            
            test_file = output_dir / f"feed_testing1_{package}_{safe_file_id}_{lineno}.jsonl"
            write_jsonl([testing_data], str(test_file))
            
            accuracy, missing_line_new, result_execute, _ = run_evolution123(
                result_execute, str(test_file), func_name=class_name, line_cover=lineno
            )
            
            if lineno not in missing_line_new[0][1]:
                print(f'Line {lineno} is covered')
            else:
                print(f'Line {lineno} is not covered')
                miss_feedback.append(lineno)
            
            missing_final.remove(lineno)
            for x in missing_final[:]:  # Create a copy to avoid modification during iteration
                if x not in missing_line_new[0][1]:
                    print(f'Line {lineno} is covered and continue to cover line {x}')
                    missing_final.remove(x)
            print(f'Lines left to cover: {missing_final}')
        else:
            print(f'Line {lineno} is not covered')
            miss_feedback.append(lineno)
            missing_final.remove(lineno)
    
    print(f"Final missing lines: {miss_feedback}")
    
    # Calculate final coverage statistics
    total_lines_set = set(line_code(python_code))
    all_execution_line_set = set(all_execution_line)
    # Lấy các dòng bổ sung: có trong line_code1 nhưng không có trong line_code
    additional_line = set(line_code1(python_code)) - total_lines_set
    # Thêm các dòng bổ sung vào cả tập dòng thực thi và tổng số dòng
    total_lines_set.update(additional_line)
    all_execution_line_set.update(additional_line)
    total_lines = len(total_lines_set)
    covered_lines = len(all_execution_line_set & total_lines_set)
    coverage_percentage = (covered_lines / total_lines) * 100 if total_lines > 0 else 0
    coverage_result = {
        'file': file_path,
        'total_lines': total_lines,
        'covered_lines': covered_lines,
        'missing_lines': miss_feedback,
        'coverage_percentage': coverage_percentage
    }
    
    return coverage_result

def run_test_generation_algorithm(package, src, files, output_dir, pkg_top, config='default'):
    """Run test generation algorithm for a specific package with coverage measurement using logic from test_new.ipynb"""
    # print(f"Running test generation algorithm for package: {package}")
    
    # Initialize Claude client
    claude = anthropic.Anthropic(api_key=os.getenv('CLAUDE'), base_url=os.getenv("ANTHROPIC_BASE_URL"))
    
    # Load templates
    prompt_template = open('scripts/prompt/template_base.txt').read()
    system_template = open('scripts/prompt/system.txt').read()
    system_message = system_template.format(lang='python')
    
    print(f"Processing {len(files)} files for package {package}")
    # print(f"Source files: {files}")
    # print(f"Package root: {pkg_top}")
    
    # Process each file separately and collect coverage results
    all_coverage_results = []
    all_missing_lines = []
    
    for file_path in files:
        coverage_result = run_test_generation_for_file(
            claude, file_path, package, output_dir, prompt_template, system_message, pkg_top
        )
        if coverage_result:
            all_coverage_results.append(coverage_result)
            all_missing_lines.extend(coverage_result['missing_lines'])
            file_name = Path(file_path).stem
            print(f"Output dir: {output_dir}")
            print(f"Coverage result for {file_name}: {json.dumps(coverage_result, indent=2)}")
            try:
                with open(output_dir / f"{file_name}_coverage.json", "w") as f:
                    json.dump(coverage_result, f, indent=2)
                print(f"Saved coverage to {output_dir / f'{file_name}_coverage.json'}")
            except Exception as e:
                print(f"Error writing coverage file: {e}")
    
    # Calculate overall package coverage
    total_package_lines = sum(result['total_lines'] for result in all_coverage_results)
    total_package_covered = sum(result['covered_lines'] for result in all_coverage_results)
    overall_coverage = (total_package_covered / total_package_lines) * 100 if total_package_lines > 0 else 0
    
    # Print coverage summary
    print("\n" + "="*60)
    print(f"COVERAGE SUMMARY FOR PACKAGE: {package}")
    print("="*60)
    
    for result in all_coverage_results:
        print(f"\nFile: {Path(result['file']).name}")
        print(f"  Total lines: {result['total_lines']}")
        print(f"  Covered lines: {result['covered_lines']}")
        print(f"  Coverage: {result['coverage_percentage']:.2f}%")
        if result['missing_lines']:
            print(f"  Missing lines: {result['missing_lines']}")
    
    print(f"\nOVERALL PACKAGE COVERAGE: {overall_coverage:.2f}%")
    print(f"Total package lines: {total_package_lines}")
    print(f"Total package covered: {total_package_covered}")
    print(f"Total missing lines: {len(all_missing_lines)}")
    if all_missing_lines:
        print(f"Missing lines: {sorted(all_missing_lines)}")
    print("="*60)
    
    # Save final results
    final_results = {
        'package': package,
        'overall_coverage_percentage': overall_coverage,
        'total_lines': total_package_lines,
        'covered_lines': total_package_covered,
        'missing_lines': sorted(all_missing_lines),
        'file_coverage': all_coverage_results
    }
    
    with open(output_dir / "final.json", 'w') as f:
        json.dump(final_results, f, indent=2)
    
    print(f"Test generation algorithm completed for {package}")
    print(f"Results saved to {output_dir}")

if __name__ == "__main__":
    args = parse_args()
    pkg = load_suite(args.suite)
    max_packages = 5
    pkg = dict(list(pkg.items())[:max_packages])
    
    for pkg_top in pkg:
        if args.package and args.package not in str(pkg_top):
            continue

        package = pkg[pkg_top]['package']
        src = pkg[pkg_top]['src']
        files = pkg[pkg_top]['files']

        if package in args.skip_package:
            continue

        if args.only:
            if args.only not in files:
                print(f"{args.only} not among {package} suite files.")
                continue
            files = [args.only]

        output = Path("output") / (args.suite + (f".{args.config}" if args.config else "")) / package

        if (output / "final.json").exists() and not (args.dry_run or args.interactive or args.get_test_coverage):
            if args.package : print(f"{str(output/'final.json')} exists, skipping.")
            continue

        if not args.dry_run:
            output.mkdir(parents=True, exist_ok=True)

        # Run test generation algorithm
        if not args.dry_run:
            run_test_generation_algorithm(package, src, files, output, pkg_top, args.config if args.config else 'default')
        else:
            print(f"Would run test generation algorithm for package {package} with output to {output}")
