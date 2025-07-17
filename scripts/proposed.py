import csv
from pathlib import Path
import time
import os
import json
import ast
import importlib.util
import importlib.metadata
import subprocess
import sys
import logging
from typing import List
from segment import get_missing_coverage
import openai
import re
from dotenv import load_dotenv
from get_conditional_line import get_conditional_lines, debug_dependencies
from eval_overall import run_evolution123
from data_utils import write_jsonl, line_code1, reform_code_lines,reform_code_lines_fixed, fix_relative_imports, parse_import_tool, remove_space, code_in_line, remove_external_imports,line_code, remove_comments_and_docstrings, find_closest_test, get_code_from_import_line, extract_python_code_block, extract_external_import_lines,extract_line, extract_test_func, find_enclosing_def_class, re_format_line
from utils.codetransform import static_slicing
from utils.codetransform.next import execute_and_trace


logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

test_apps = Path("codamosa/replication/test-apps")
mutap_benchmarks = Path("MuTAP-benchmarks")
eval_path = Path(__file__).parent.parent

# Load environment variables
load_dotenv()

# Global module availability cache (from coverup.py)
module_available = dict()

def find_imports(python_code: str) -> List[str]:
    """Collects a list of packages needed by a program by examining its 'import' statements"""
    try:
        t = ast.parse(python_code)
    except SyntaxError:
        return []

    modules = []

    for n in ast.walk(t):
        if isinstance(n, ast.Import):
            for name in n.names:
                if isinstance(name, ast.alias):
                    modules.append(name.name.split('.')[0])

        elif isinstance(n, ast.ImportFrom):
            if n.module and n.level == 0:
                modules.append(n.module.split('.')[0])

    return [m for m in modules if m != '__main__']

def missing_imports(modules: List[str]) -> List[str]:
    """Check which modules are missing from the current environment"""
    global module_available

    for module in modules:
        if module not in module_available:
            spec = importlib.util.find_spec(module)
            module_available[module] = 0 if spec is None else 1

    return [m for m in modules if not module_available[m]]

def install_missing_imports(modules: List[str], install_missing: bool = True) -> bool:
    """Install missing modules using pip"""
    global module_available

    if not install_missing:
        return False

    all_ok = True
    for module in modules:
        try:
            # Skip standard library modules and common built-ins
            if module in ['os', 'sys', 'json', 'datetime', 'pathlib', 'typing', 'collections', 
                         'math', 'random', 'time', 're', 'subprocess', 'argparse', 'ast',
                         'importlib', 'shutil', 'signal', 'traceback', 'io', 'linecache']:
                module_available[module] = 1
                continue
                
            print(f"Installing module {module}...")
            p = subprocess.run((f"{sys.executable} -m pip install {module}").split(),
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            version = importlib.metadata.version(module)
            module_available[module] = 2    # originally unavailable, but now added
            print(f"Installed module {module} {version}")

        except subprocess.CalledProcessError as e:
            print(f"Unable to install module {module}: {str(e.stdout, 'UTF-8', errors='ignore')}")
            all_ok = False
        except Exception as e:
            print(f"Error installing module {module}: {e}")
            all_ok = False

    return all_ok

def get_required_modules() -> List[str]:
    """Returns a list of the modules found missing (and not installed)"""
    return [m for m in module_available if not module_available[m]]

def add_dir_to_pythonpath(dir_path: Path):
    """Add directory to PYTHONPATH and sys.path"""
    os.environ['PYTHONPATH'] = str(dir_path) + (f":{os.environ['PYTHONPATH']}" if 'PYTHONPATH' in os.environ else "")
    sys.path.insert(0, str(dir_path))



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

    # Add new arguments for import handling
    ap.add_argument('--install-missing-modules', default=True,
                    action=argparse.BooleanOptionalAction,
                    help='attempt to install any missing modules')
    
    ap.add_argument('--add-to-pythonpath', default=True,
                    action=argparse.BooleanOptionalAction,
                    help='add source directory to PYTHONPATH')

    ap.add_argument('--test-index', type=int, default=None, help='Chỉ chạy test ở vị trí i (theo enumerate)')

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


### SEED TEST GENERATION ####
def testgeneration_multiround(client, prompt, generated_tests, system_message, install_missing=True):
    """Generate test cases with multi-round conversation"""
    template_append="Generate another test method for the function under test. Your answer must be different from previously-generated test cases, and should cover different statements and branches. CRITICAL: You MUST include ALL necessary imports at the very beginning of your test function. Always start your test with the required imports, then the test function. Try different input values, edge cases, and test scenarios but still remain function name."
    messages=[
        {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ]
    for _ in range(10):
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=messages,
            max_tokens=512,
            timeout = 100,
        )
        test_gen = response.choices[0].message.content
        messages.append({"role": "assistant", "content": test_gen})
        messages.append({"role": "user", "content": template_append})

        # Check for missing imports and install them
        if missing := missing_imports(find_imports(test_gen)):
            print(f"Missing modules in generated test: {' '.join(missing)}")
            if install_missing:
                install_missing_imports(missing, install_missing=True)

        generated_tests.append(test_gen)
        print(test_gen)

    return generated_tests

def testgeneration_multiround_error(client, prompt, system_message, install_missing=True):
    """Generate test cases with multi-round conversation"""
    messages=[
        {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ]
    generated_test = []
    for _ in range(2):
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=messages,
            max_tokens=512,
            timeout = 100,
        )
        test_gen = response.choices[0].message.content

        # Check for missing imports and install them
        if missing := missing_imports(find_imports(test_gen)):
            print(f"Missing modules in generated test: {' '.join(missing)}")
            if install_missing:
                install_missing_imports(missing, install_missing=True)

        generated_test.append(test_gen)
        print(test_gen)

    return generated_test
#### TEST GENERATION FOR SPECIFIC LINE ####

def testgeneration_multiround_line(client, prompt, system_message, epoch, install_missing=True):
    """Generate test cases for specific line coverage"""
    template_append="Generate another test method for the function under test. Your answer must be different from previously-generated test cases, and should cover different statements and branches. CRITICAL: You MUST include ALL necessary imports at the very beginning of your test function. Always start your test with the required imports, then the test function. Try different input values, edge cases, and test scenarios but still remain function name."
    generated_tests=[]
    messages=[
            {"role": "user", "content": prompt},
            {"role": "system", "content": system_message},
        ]
    for _ in range(epoch):
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=messages,
            max_tokens=512,
            timeout = 100,
        )
        generated_test=response.choices[0].message.content
        messages.append({"role": "assistant", "content": generated_test})
        messages.append({"role": "user", "content": template_append})

        # Check for missing imports and install them
        if missing := missing_imports(find_imports(generated_test)):
            print(f"Missing modules in generated test: {' '.join(missing)}")
            if install_missing:
                install_missing_imports(missing, install_missing=True)

        generated_tests.append(generated_test)
        print(generated_test)

    return generated_tests




#### TEST GENERATION FOR SPECIFIC LINE WITH EXECUTION FEEDBACK ####


def testgeneration_feedback(client, prompt, epoch, install_missing=True):
    """Generate test cases with execution feedback"""
    generated_tests=[]
    messages=[
            {"role": "system", "content": open('scripts/prompt/system_exec.txt').read()},
            {"role": "user", "content": prompt},
        ]
    for i in range(epoch):
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=messages,
            max_tokens=2048,
            timeout = 100,
        )
        # print(f'------------------{i} ---------------------{response.choices[0].message.content}')
        generated_test = extract_python_code_block(response.choices[0].message.content)
        if generated_test!="":
            # Check for missing imports and install them
            if missing := missing_imports(find_imports(generated_test)):
                print(f"Missing modules in generated test: {' '.join(missing)}")
                if install_missing:
                    install_missing_imports(missing, install_missing=True)
            
            generated_tests.append(generated_test)
            # print(generated_test)

    return generated_tests

def create_test_file(test_content, test_dir, test_name, source_file_path, install_missing=True):
    """Create a test file with the given content and proper imports (absolute import, no code gốc ghép vào, test file nằm trong cùng package với file gốc)"""
    source_file_path = Path(source_file_path)
    source_file_name = source_file_path.stem
    source_file_dir = source_file_path.parent

    # Đảm bảo test file nằm cùng package với file gốc
    test_dir = source_file_dir
    test_file = test_dir / f"{test_name}.py"

    # Tìm project root (cha của package)
    project_root = Path(__file__).resolve().parent.parent

    # Check for missing imports in test content and install them
    if install_missing:
        if missing := missing_imports(find_imports(test_content)):
            print(f"Missing modules in test content: {' '.join(missing)}")
            install_missing_imports(missing, install_missing=True)

    # Enhanced imports handling
    common_imports = """import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))  # Thêm project root vào sys.path

# Add common imports that might be needed
try:
    import pytest
except ImportError:
    pass

try:
    import json
except ImportError:
    pass

try:
    import datetime
except ImportError:
    pass

try:
    import unittest
    from unittest.mock import patch, Mock, MagicMock
except ImportError:
    pass

try:
    import unittest.mock as mock
    patch = mock.patch
    Mock = mock.Mock
    MagicMock = mock.MagicMock
except ImportError:
    pass

# Common mock objects for testing
try:
    # Mock for file operations
    mock_open = mock.mock_open()
    
    # Mock for subprocess calls
    mock_subprocess = mock.Mock()
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = b'Success'
    
    # Mock for configuration objects
    mock_config = mock.Mock()
    mock_config.get.return_value = 'default_value'
    
    # Mock for display/logging
    mock_display = mock.Mock()
    mock_display.verbosity = 0
    mock_display.display = mock.Mock()
    mock_display.warning = mock.Mock()
    mock_display.error = mock.Mock()
    
    # Mock for parser objects
    mock_parser = mock.Mock()
    mock_parser.add_argument = mock.Mock()
    mock_parser.parse_args = mock.Mock()
    
    # Mock for inventory objects
    mock_inventory = mock.Mock()
    mock_inventory.get_hosts = mock.Mock(return_value=[])
    
    # Mock for variable manager
    mock_variable_manager = mock.Mock()
    
    # Mock for loader
    mock_loader = mock.Mock()
    mock_loader.load = mock.Mock()
    mock_loader.cleanup_all_tmp_files = mock.Mock()
except:
    pass
"""

    # Xác định tên package/module để import
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

    # Fix common issues in test content
    test_content = fix_test_content(test_content)
    
    test_file_content = f"""{common_imports}
{import_line}
{test_content}
"""

    test_file.write_text(test_file_content)
    return test_file

def run_test_generation_for_file(client, file_path, package, output_dir, prompt_template, system_message, pkg_top):
    """Run test generation for a single Python file with coverage measurement using logic from test_new.ipynb"""
    print(f"Processing file: {file_path}")
    # Convert relative path to absolute path using pkg_top 
    if not Path(file_path).is_absolute():
        # Use pkg_top (package root directory) to construct absolute path
        absolute_path = pkg_top / file_path
        file_path = str(absolute_path)
    
    try:
        file_path_obj = Path(file_path)
        pkg_top_obj = Path(pkg_top)
        if file_path_obj.is_relative_to(pkg_top_obj):
            relative_path = file_path_obj.relative_to(pkg_top_obj)
            if len(relative_path.parts) > 1:
                # Use the actual package structure (last parts of the path)
                # For example: if file is in black/src/blib2to3/pgen2/file.py
                # the package should be blib2to3.pgen2
                path_parts = list(relative_path.parts[:-1])  # Exclude filename
                if len(path_parts) >= 2:
                    # Use the last two parts as package name
                    package_for_imports = '.'.join(path_parts[-2:])
                elif len(path_parts) == 1:
                    package_for_imports = path_parts[0]
                else:
                    package_for_imports = package
            else:
                package_for_imports = package
        else:
            package_for_imports = package
        
        with open(file_path_obj, 'r') as f:
            python_code = f.read()
            python_code = fix_relative_imports(python_code, package_for_imports)
            python_code1 = python_code
            python_code = reform_code_lines_fixed(python_code)
            # print(f'python_code: ------------{python_code}------------')
            
    except FileNotFoundError:
        # print(os.getcwd())
        print(f"Warning: File {file_path} not found")
        return None
    
    if not python_code.strip():
        # print(os.getcwd())
        print(f"No content in file {file_path}")
        return None
    
    print(f"Read {len(python_code)} characters from {file_path}")
    
    # Initialize result tracking like in test_new.ipynb
    result_execute = []
    all_execution_line = set()
    total_filter_nums = 0
    sucess_run = 0
    fail_run = 0
    all_line_before_filter = 0
    # python_code = fix_line_breaks_in_code(python_code)
    # Phase 1: Basic test generation for this file
    print(f"Phase 1: Basic test generation for {file_path}")
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
    
    if not divide_code:
        print(f"Warning: No class segments found in {file_path}")
        # Tạo một segment duy nhất với toàn bộ code
        divide_code = [python_code]
    for i, class_segment in enumerate(divide_code):
        # Xác định tên file an toàn
        safe_file_id = str(Path(file_path).relative_to(pkg_top)).replace('/', '_').replace('\\', '_').replace('.', '_')
        # Xử lý class_segment là object hay string
        # if isinstance(class_segment, str):
        #     class_name = Path(file_path).stem  # hoặc 'global'
        #     try:
        #         lineno = class_segment.end - 1  # type: ignore
        #         class_segment_code, _, _, _ = static_slicing.static_slicing(python_code, lineno)
        #     except AttributeError:
        #         # Nếu không có attribute end thì dùng toàn bộ code
        #         class_segment_code = python_code
        # else:
        #     # Nếu là CodeSegment object - sử dụng getattr để tránh lỗi linter
        #     class_name = getattr(class_segment, 'name', Path(file_path).stem)
        #     try:
        #         lineno = class_segment.end - 1
        #         class_segment_code, _, _, _ = static_slicing.static_slicing(python_code, lineno)
        #     except Exception as e:
        #         class_segment_code = python_code
        #         print(f"[WARNING] static_slicing failed for {file_path} (CodeSegment): {e}")
        #         continue
        class_segment_code = class_segment.get_excerpt(tag_lines = False)
        class_name = class_segment.name
        
 
        prompt = open('scripts/prompt/template_base_no_import.txt').read().format(program=class_segment_code, func_name=class_name)

        generated_tests = []
        generated_tests = testgeneration_multiround(client, prompt, generated_tests, system_message, install_missing=True)

        testing_data = {
            'task_num': f"{package}_{Path(file_path).stem}_{i}",
            'task_title': f"Test generation for {package} - {Path(file_path).name}",
            'code': python_code,
            'tests': generated_tests
        }
        
        test_file = output_dir / f"testing_{safe_file_id}_newc_{i}.jsonl"
        try:
            write_jsonl([testing_data], str(test_file))
            print(f"Saved {len(generated_tests)} tests to {test_file}")
        except Exception as e:
            print(f"[WARNING] write_jsonl failed: {e}")

        if generated_tests:
            # Gọi run_evolution123 với check_error=True để lấy error feedback
            _, missing_line, result_execute, all_execution_line, error_feedback = run_evolution123(
                result_execute, str(test_file), func_name=class_name, all_executed_lines=all_execution_line, line_cover=0,
                package_root=str(pkg_top.parent), package_name=pkg_top.name, check_error=True
            )
            # Nếu có error_feedback, sửa lại từng test bị lỗi (chỉ sửa 1 lần)
            print(f'-----------------\n\n FIX ERROR \n\n\n--------------')
            if error_feedback:
                print(f'-----------------\n\n FIX ERROR \n\n\n------ {len(error_feedback)}------\n----  --')
                fixed_tests = []
                for lineno, info in error_feedback.items():
                    old_test = info['test']
                    error_msg = info['error']
                    prompt = open('scripts/prompt/fix_error.txt').read().format(code = class_segment_code, test = old_test, error = error_msg)
                    fixed = testgeneration_multiround_error(client, prompt, system_message)
                    if len(fixed)!=0:
                        for x in fixed:
                            fixed_tests.append(x)
                    # Dùng testgeneration_feedback để sinh lại test

                # Gộp test đã pass + test đã sửa lại
                testing_data = {
                    'task_num': f"{package}_{Path(file_path).stem}_{i}",
                    'task_title': f"Test generation for {package} - {Path(file_path).name}",
                    'code': python_code,
                    'tests': fixed_tests
                }
                test_file = output_dir / f"testing_{safe_file_id}_fix1_{i}.jsonl"
                try:
                    write_jsonl([testing_data], str(test_file))
                    print(f"Saved {len(generated_tests)} tests to {test_file}")
                except Exception as e:
                    print(f"[WARNING] write_jsonl failed: {e}")
                # Test lại coverage với test đã sửa
                _, missing_line, result_execute, all_execution_line = run_evolution123(
                    result_execute, str(test_file), func_name=class_name, all_executed_lines=all_execution_line, line_cover=0,
                    package_root=str(pkg_top.parent), package_name=pkg_top.name
                )

    
    all_execution_line_set_phase1 = set(all_execution_line)
    covered_lines_phase1 = len(line_code1(python_code1)) - len(line_code(python_code)) + len(all_execution_line_set_phase1)
    coverage_percentage_phase1 = (covered_lines_phase1 / len(line_code1(python_code1))) * 100 

    coverage_result_phase1 = {
        'file': file_path,
        'total_lines': len(line_code1(python_code1)),
        'covered_lines': covered_lines_phase1,
        'missing_lines': missing_line,
        'len_missing_lines': len(missing_line),
        'coverage_percentage': coverage_percentage_phase1
    }
    with open("repos_ran_cc.txt", "a") as f:
        f.write(f"Phase 1:  {covered_lines_phase1}\n\n\n")
    try:
        with open(output_dir / f"{Path(file_path).stem}_phase1_coverage.json", "w") as f:
            json.dump(coverage_result_phase1, f, indent=2)
        print(f"Saved phase 1 coverage to {output_dir / f'{Path(file_path).stem}_phase1_coverage.json'}")
    except Exception as e:
        print(f"Error writing phase 1 coverage file: {e}")
    
    # #########################################Phase 2: Target line coverage for this file#########################################
    
    
    
#################       Ablatation 1: with SLICING  ############################# ########
    print(f"Phase 2: Target line coverage with slicingfor {file_path}")
    missing_test = [x for x in missing_line if x in re_format_line(python_code)]
    # missing_final = []
    all_execution_line1 = set(all_execution_line)
    while len(missing_test) > 0:
        print(f'line code ----------{extract_line(python_code, missing_test[0])}----------------------')
        # print(f'line code real {line_code(python_code)}------------')
        lineno = missing_test[0]
        lineno1 = extract_line(python_code, lineno)
        filtered_code, _, filter_num_lines, _ = static_slicing.static_slicing(python_code, lineno)
        # class_name, function_name = find_enclosing_def_class(python_code, lineno)
        try:
            class_name, function_name = find_enclosing_def_class(python_code, lineno)
        except Exception as e:
            print(f"[WARNING] find_enclosing_def_class failed: {e}")
            # Try to find actual class/function names in the code
            try:
                tree = ast.parse(python_code)
                class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                func_names = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
                
                if class_names:
                    class_name = class_names[0]  # Use first class found
                elif func_names:
                    class_name = func_names[0]  # Use first function found
                else:
                    class_name = Path(file_path).stem  # Fallback to filename
            except:
                class_name = Path(file_path).stem  # Fallback to filename
        

            
        print(f'class_name: {class_name}')
        print(f'function_name: {function_name}')
        print(f'-------------------TEST {lineno}---------- REMOVE -------------{filter_num_lines}-------------')
        
        total_filter_nums += filter_num_lines
        all_line_before_filter += len(line_code1(python_code))
        
        # response_line = client.chat.completions.create(
        #     model='deepseek-v3-0324',
        #     messages=[
        #     {"role": "system", "content": open('scripts/prompt/system_import.txt').read()},
        #     {"role": "user", "content": open('scripts/prompt/find_import.txt').read().format(code=remove_external_imports(filtered_code), import_tool=extract_external_import_lines(python_code))},
        # ],
        #     max_tokens=1024,
        # )
        
        # print(f'--------NEED IMPORT: --------- \n {response_line.choices[0].message.content} ---------')
        # import_tool1 = response_line.choices[0].message.content
        # try:
        #     import_tool1 = parse_import_tool(import_tool1)
        # except Exception as e:
        #     print(f"[WARNING] parse_import_tool failed: {e}. import_tool1: {import_tool1}")
        #     import_tool1 = []
        # external_code = ''
        # for import_line in import_tool1:
        #     # Xử lý trường hợp import_line là list
        #     if isinstance(import_line, list):
        #         import_line = import_line[0] if import_line else ""
            
        #     if isinstance(import_line, str):
        #         try:
        #             _, code = get_code_from_import_line(import_line)
        #             if code:
        #                 external_code += f"\n# ===== {import_line} =====\n" + remove_space(remove_comments_and_docstrings(code)) + "\n"
        #         except Exception as e:
        #             print(f"[WARNING] get_code_from_import_line failed for {import_line}: {e}")
        # Đưa external_code vào đầu prompt
        # prompt = prompt_template.format(program=class_segment_code, func_name=class_name, import_tool=external_code)
        external_code = ''
        if external_code != '':
            prompt_line = open('scripts/prompt/template_line.txt').read().format(
                # func_name=function_name, 
                import_tool=external_code,
                class_name=class_name, 
                program=code_in_line(filtered_code), 
                lineno=lineno1
            )
            prompt_line_not_slicing = open('scripts/prompt/template_line.txt').read().format(
                # func_name=function_name, 
                import_tool=external_code,
                class_name=class_name, 
                program=code_in_line(python_code), 
                lineno=lineno1
            )
        else:
            prompt_line = open('scripts/prompt/template_line_no_import.txt').read().format(
                func_name=function_name, 
                class_name=class_name, 
                program=code_in_line(filtered_code), 
                lineno=lineno1
            )
            prompt_line_not_slicing = open('scripts/prompt/template_line_no_import.txt').read().format(
                func_name=function_name, 
                class_name=class_name, 
                program=code_in_line(python_code), 
                lineno=lineno1
            )
        generate_test = testgeneration_multiround_line(client, prompt_line, system_message, epoch = 9, install_missing=True)
        generate_test_not_slicing = testgeneration_multiround_line(client, prompt_line_not_slicing, system_message, epoch = 1, install_missing=True)
        testing_data = {
            'task_num': f"{package}_{safe_file_id}_{lineno}",
            'task_title': f"Line coverage for {package}",
            'code': python_code,
            'tests': generate_test
        }
        testing_data_not_slicing = {
            'task_num': f"{package}_{safe_file_id}_{lineno}_not_slicing",
            'task_title': f"Line coverage for {package}",
            'code': python_code,
            'tests': generate_test_not_slicing
        }
        test_file = output_dir / f"testing_{safe_file_id}_{lineno}.jsonl"
        write_jsonl([testing_data], str(test_file))
        test_file_not_slicing = output_dir / f"testing_{safe_file_id}_{lineno}_not_slicing.jsonl"
        write_jsonl([testing_data_not_slicing], str(test_file_not_slicing))
        
        
        _, missing_line_phase2, result_execute, all_execution_line = run_evolution123(
            result_execute, str(test_file), func_name=class_name, all_executed_lines=all_execution_line, line_cover=lineno,
            package_root=str(pkg_top.parent), package_name=pkg_top.name
        )
        
        _, missing_line_p2_not_slicing, result_execute, all_execution_line1 = run_evolution123(
            result_execute, str(test_file_not_slicing), func_name=class_name, all_executed_lines=all_execution_line1, line_cover=lineno,
            package_root=str(pkg_top.parent), package_name=pkg_top.name
        )

        
        if lineno not in missing_line_phase2:
            sucess_run+=1
            print(f'Line {lineno} is covered')
            with open("repos_ran_cc.txt", "a") as f:
                f.write(f"Phase 2:   Line:  {lineno} is covered\n")
        else:
            print(f'Line {lineno} is not covered')
            fail_run+=1
            with open("repos_ran_cc.txt", "a") as f:
                f.write(f"Phase 2:   Line:  {lineno} is not covered\n")
            # missing_final.append(lineno)
        
        missing_test.remove(lineno)
        
        for x in missing_test[:]:  # Create a copy to avoid modification during iteration
            if x not in missing_line_phase2:
                print(f'Line {lineno} is covered and continue to cover line {x}')
                missing_test.remove(x)
        print(f'Lines left to cover: {missing_test}')
    
    # Sau khi phase 2 kết thúc, ghi coverage phase 2
    all_execution_line_set_phase2 = set(all_execution_line)
    covered_lines_phase2 = len(line_code1(python_code1)) - len(line_code(python_code)) + len(all_execution_line_set_phase2)
    coverage_percentage_phase2 = (covered_lines_phase2 / len(line_code1(python_code1))) * 100 
    coverage_result_phase2 = {
        'file': file_path,
        'total_lines': len(line_code1(python_code1)),
        'covered_lines': covered_lines_phase2,
        'missing_lines': missing_line_phase2,
        'len_missing_lines': len(missing_line_phase2),
        'coverage_percentage': coverage_percentage_phase2
    }
    try:
        with open(output_dir / f"{Path(file_path).stem}_phase2_coverage.json", "w") as f:
            json.dump(coverage_result_phase2, f, indent=2)
        print(f"Saved phase 2 coverage to {output_dir / f'{Path(file_path).stem}_phase2_coverage.json'}")
    except Exception as e:
        print(f"Error writing phase 2 coverage file: {e}")
        
    all_execution_line_set_phase2_not_slicing = set(all_execution_line1)
    covered_lines_phase2_not_slicing = len(line_code1(python_code1)) - len(line_code(python_code)) + len(all_execution_line_set_phase2_not_slicing)
    coverage_percentage_phase2_not_slicing = (covered_lines_phase2_not_slicing / len(line_code1(python_code1))) * 100 
    coverage_result_phase2_not_slicing = {
        'file': file_path,
        'total_lines': len(line_code1(python_code1)),
        'covered_lines': covered_lines_phase2_not_slicing,
        'missing_lines': missing_line_p2_not_slicing,
        'len_missing_lines': len(missing_line_p2_not_slicing),
        'coverage_percentage': coverage_percentage_phase2_not_slicing
    }
    try:
        with open(output_dir / f"{Path(file_path).stem}_phase2_coverage_not_slicing.json", "w") as f:
            json.dump(coverage_result_phase2_not_slicing, f, indent=2)
        print(f"Saved phase 2 coverage to {output_dir / f'{Path(file_path).stem}_phase2_coverage_not_slicing.json'}")
    except Exception as e:
        print(f"Error writing phase 2 coverage file: {e}")

    # Phase 3: Generate with feedback for this file
    print(f"Phase 3: Generate with feedback for {file_path}")
    miss_feedback = []
    missing_final = [x for x in missing_line_phase2 if x in re_format_line(python_code)]
    all_execution_line2 = set(all_execution_line)
    all_execution_line3 = set(all_execution_line)
    while len(missing_final) > 0:
        lineno = missing_final[0]
        print(f'-------------------TEST {lineno}---------- FEEDBACK -------------')
        
        try:
            filtered_code, _, filter_num_lines, _ = static_slicing.static_slicing(python_code, lineno)
        except Exception as e:
            print(f"[WARNING] static_slicing failed: {e}")
            filtered_code = ''
        try:
            class_name, function_name = find_enclosing_def_class(python_code, lineno)
        except Exception as e:
            print(f"[WARNING] find_enclosing_def_class failed: {e}")
            # Try to find actual class/function names in the code
            try:
                tree = ast.parse(python_code)
                class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                func_names = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
                
                if class_names:
                    class_name = class_names[0]  # Use first class found
                elif func_names:
                    class_name = func_names[0]  # Use first function found
                else:
                    class_name = Path(file_path).stem  # Fallback to filename
            except:
                class_name = Path(file_path).stem  # Fallback to filename
  ######### find closet test ##########      
        try:
            test_good = find_closest_test(result_execute,lineno, python_code)
        except Exception as e:
            print(f"[WARNING] solve failed: {e}")
            test_good = None
        
        # Xử lý trường hợp solve trả về None
        print(f'len(result_execute): {len(result_execute)}')
        if test_good is None:
            print(f'Line {lineno} cannot be solved with feedback')
            miss_feedback.append(lineno)
            missing_final.remove(lineno)
            continue
        
        try:
            test_run = extract_test_func(test_good, class_name)
        except Exception as e:
            print(f"[WARNING] extract_test_func failed: {e}")
            test_run = ''
        
###########  OUR PROPOSED METHOD ############        
      
        prompt_line = open('scripts/prompt/feedback_line.txt').read().format(
        func_name=function_name, 
        class_name=class_name, 
        test=test_run, 
        code=code_in_line(execute_and_trace(filtered_code)), 
        code_linene=extract_line(python_code, lineno)
        )


######### ABLATION STUDY ##########
        prompt_line_no_exe = open('scripts/prompt/feedback_line_no_execution.txt').read().format(
        func_name=function_name, 
        class_name=class_name, 
        test=test_run, 
        code=filtered_code, 
        code_linene=extract_line(python_code, lineno)
        )
######### ABLATION STUDY ##########

        prompt_line_no_test = open('scripts/prompt/feedback_line_no_test.txt').read().format(
        func_name=function_name, 
        class_name=class_name, 
        code = filtered_code,
        code_linene=extract_line(python_code, lineno)
        )
        generate_test = testgeneration_feedback(client, prompt_line, epoch = 6, install_missing=True)
        generate_test_no_exe = testgeneration_feedback(client, prompt_line_no_exe, epoch = 1, install_missing=True)
        generate_test_no_test = testgeneration_feedback(client, prompt_line_no_test, epoch = 1, install_missing=True)
        
        
        if len(generate_test) > 0:
            testing_data = {
                'task_num': f"{package}_{safe_file_id}_{lineno}_feedback",
                'code': python_code,
                'tests': generate_test
            }
            testing_data_no_exe = {
                'task_num': f"{package}_{safe_file_id}_{lineno}_feedback_no_exe",
                'code': python_code,
                'tests': generate_test_no_exe
            }
            testing_data_no_test = {
                'task_num': f"{package}_{safe_file_id}_{lineno}_feedback_no_test",
                'code': python_code,
                'tests': generate_test_no_test
            }
            test_file = output_dir / f"feed_testing1_{package}_{safe_file_id}_{lineno}.jsonl"
            test_file_no_exe = output_dir / f"feed_testing1_{package}_{safe_file_id}_{lineno}_no_exe.jsonl"
            test_file_no_test = output_dir / f"feed_testing1_{package}_{safe_file_id}_{lineno}_no_test.jsonl"
            write_jsonl([testing_data], str(test_file))
            write_jsonl([testing_data_no_exe], str(test_file_no_exe))
            write_jsonl([testing_data_no_test], str(test_file_no_test))
            _, missing_line_phase3, result_execute, all_execution_line = run_evolution123(
                result_execute, str(test_file), func_name=class_name, all_executed_lines=all_execution_line, line_cover=lineno, 
                package_root=str(pkg_top.parent), package_name=pkg_top.name
            )
            _, missing_line_phase3_no_exe, result_execute, all_execution_line2 = run_evolution123(
                result_execute, str(test_file_no_exe), func_name=class_name, all_executed_lines=all_execution_line2, line_cover=lineno, 
                package_root=str(pkg_top.parent), package_name=pkg_top.name
            )
            _, missing_line_phase3_no_test, result_execute, all_execution_line3 = run_evolution123(
                result_execute, str(test_file_no_test), func_name=class_name, all_executed_lines=all_execution_line3, line_cover=lineno, 
                package_root=str(pkg_top.parent), package_name=pkg_top.name
            )

            if lineno not in missing_line_phase3:
                sucess_run+=1
                print(f'Line {lineno} is covered')
                with open("repos_ran_cc.txt", "a") as f:
                    f.write(f"Phase 3:   Line:  {lineno} is covered\n")
            else:
                print(f'Line {lineno} is not covered')
                fail_run+=1
                with open("repos_ran_cc.txt", "a") as f:
                    f.write(f"Phase 3:   Line:  {lineno} is not covered\n")
            
            missing_final.remove(lineno)
            for x in missing_final[:]:  # Create a copy to avoid modification during iteration
                if x not in missing_line_phase3:
                    print(f'Line {lineno} is covered and continue to cover line {x}')
                    missing_final.remove(x)
            print(f'Lines left to cover: {missing_final}')
        else:
            print(f'Line {lineno} is not covered')
            missing_final.remove(lineno)
    

    with open("repos_ran_cc.txt", "a") as f:
        f.write(f"Sucess run: {sucess_run}\n")
        f.write(f"Fail run: {fail_run}\n")
        f.write(f"Total run: {sucess_run+fail_run}\n")
 
    all_execution_line_set_phase3 = set(all_execution_line)
    covered_lines_phase3 = len(line_code1(python_code1)) - len(line_code(python_code)) + len(all_execution_line_set_phase3)
    coverage_percentage_phase3 = (covered_lines_phase3 / len(line_code1(python_code1))) * 100 
    coverage_result_phase3 = {
        'file': file_path,
        'total_lines': len(line_code1(python_code1)),
        'covered_lines': covered_lines_phase3,
        'missing_lines': missing_line_phase3,
        'len_missing_lines': len(missing_line_phase3),
        'filter_nums': (total_filter_nums/all_line_before_filter)*100,
        'coverage_percentage': coverage_percentage_phase3
    }
    # Phase 3 not execute
    all_execution_line_set_phase3_not_exe = set(all_execution_line2)
    covered_lines_phase3_not_exe = len(line_code1(python_code1)) - len(line_code(python_code)) + len(all_execution_line_set_phase3_not_exe)
    coverage_percentage_phase3_not_exe = (covered_lines_phase3_not_exe / len(line_code1(python_code1))) * 100 
    coverage_result_phase3_not_exe = {
        'file': file_path,
        'total_lines': len(line_code1(python_code1)),
        'covered_lines': covered_lines_phase3_not_exe,
        'missing_lines': missing_line_phase3_no_exe,
        'len_missing_lines': len(missing_line_phase3_no_exe),
        'coverage_percentage': coverage_percentage_phase3_not_exe
    }
    # Phase 3 not test
    all_execution_line_set_phase3_not_test = set(all_execution_line3)
    covered_lines_phase3_not_test = len(line_code1(python_code1)) - len(line_code(python_code)) + len(all_execution_line_set_phase3_not_test)
    coverage_percentage_phase3_not_test = (covered_lines_phase3_not_test / len(line_code1(python_code1))) * 100 
    coverage_result_phase3_not_test = {
        'file': file_path,
        'total_lines': len(line_code1(python_code1)),
        'covered_lines': covered_lines_phase3_not_test,
        'missing_lines': missing_line_phase3_no_test,
        'len_missing_lines': len(missing_line_phase3_no_test),
        'coverage_percentage': coverage_percentage_phase3_not_test
    }
    
    
    
    # }
    try:
        with open(output_dir / f"{Path(file_path).stem}_phase3_coverage.json", "w") as f:
            json.dump(coverage_result_phase3, f, indent=2)
        print(f"Saved phase 3 coverage to {output_dir / f'{Path(file_path).stem}_phase3_coverage.json'}")
        with open(output_dir / f"{Path(file_path).stem}_phase3_coverage_not_exe.json", "w") as f:
            json.dump(coverage_result_phase3_not_exe, f, indent=2)
        print(f"Saved phase 3 coverage to {output_dir / f'{Path(file_path).stem}_phase3_coverage_not_exe.json'}")
        with open(output_dir / f"{Path(file_path).stem}_phase3_coverage_not_test.json", "w") as f:
            json.dump(coverage_result_phase3_not_test, f, indent=2)
        print(f"Saved phase 3 coverage to {output_dir / f'{Path(file_path).stem}_phase3_coverage_not_test.json'}")
    except Exception as e:
        print(f"Error writing phase 3 coverage file: {e}")
    



    # }
    
    return coverage_result_phase3

def run_test_generation_algorithm(package, src, files, output_dir, pkg_top, config='default', install_missing=True, add_to_pythonpath=True):
    """Run test generation algorithm for a specific package with coverage measurement using logic from test_new.ipynb"""
    # print(f"Running test generation algorithm for package: {package}")
    
    # Add package directory to PYTHONPATH if requested
    # result_execute = []
    if add_to_pythonpath:
        add_dir_to_pythonpath(pkg_top)
        print(f"Added {pkg_top} to PYTHONPATH")
    
    # Initialize Claude client
    client = openai.OpenAI(api_key=os.getenv('coverup'), base_url=os.getenv("ANTHROPIC_BASE_URL"))
    
    # Load templates
    # prompt_template = open('scripts/prompt/template_base.txt').read()
    prompt_template = open('scripts/prompt/template_base.txt').read()

    system_template = open('scripts/prompt/system.txt').read()
    system_message = system_template.format(lang='python')
    
    print(f"Processing {len(files)} files for package {package}")
    # print(f"Source files: {files}")
    # print(f"Package root: {pkg_top}")
    
    # Process each file separately and collect coverage results
    all_coverage_results = []
    all_missing_lines = []
    
    for i, file_path in enumerate(files):
        # if file_path != 'typesystem/fields.py':
        #     print(file_path)
        #     continue
        if i<=2:
            continue
        coverage_result = run_test_generation_for_file(
            client, file_path, package, output_dir, prompt_template, system_message, pkg_top
        )
        if coverage_result:
            all_coverage_results.append(coverage_result)
            all_missing_lines.extend(coverage_result['missing_lines'])
            file_name = Path(file_path).stem
            print(f"Output dir: {output_dir}")
            print(f"Coverage result for {file_name}: {json.dumps(coverage_result, indent=2)}")
            try:
                with open("repos_ran.txt", "a") as f:
                    f.write(f"{pkg_top} {json.dumps(coverage_result)}\n\n")
         
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

def fix_test_content(test_content):
    """Fix common issues in generated test content"""
    # Add missing imports if needed
    if 'patch(' in test_content and 'from unittest.mock import patch' not in test_content:
        test_content = "from unittest.mock import patch, Mock, MagicMock\n" + test_content
    
    if 'Mock(' in test_content and 'from unittest.mock import Mock' not in test_content:
        if 'from unittest.mock import patch' not in test_content:
            test_content = "from unittest.mock import Mock, MagicMock\n" + test_content
    
    # Add pytest import if using pytest features
    if 'pytest.' in test_content and 'import pytest' not in test_content:
        test_content = "import pytest\n" + test_content
    
    return test_content

if __name__ == "__main__":
    args = parse_args()
    pkg = load_suite(args.suite)
    pkg_key = list(pkg.keys())
    # for i, k in enumerate(pkg_key):
    #     print(f'{i} {k}')
    start_time = time.time()
    if args.test_index is not None:
        if args.test_index < 0 or args.test_index >= len(pkg_key):
            raise IndexError(f"test_index {args.test_index} out of range (0, {len(pkg_key)-1})")
        pkg_top = pkg_key[args.test_index]

        # Các điều kiện kiểm tra, nếu không thỏa mãn thì return hoặc exit
        if args.package and args.package not in str(pkg_top):
            sys.exit(0)
        package = pkg[pkg_top]['package']
        src = pkg[pkg_top]['src']
        files = pkg[pkg_top]['files']
        if package in args.skip_package:
            sys.exit(0)
        if args.only:
            if args.only not in files:
                print(f"{args.only} not among {package} suite files.")
                sys.exit(0)
            files = [args.only]
        output = Path("output") / (args.suite + (f".{args.config}" if args.config else "")) / package
        if (output / "final.json").exists() and not (args.dry_run or args.interactive or args.get_test_coverage):
            if args.package : print(f"{str(output/'final.json')} exists, skipping.")
            sys.exit(0)
        if not args.dry_run:
            output.mkdir(parents=True, exist_ok=True)
        if not args.dry_run:
            run_test_generation_algorithm(
                package, src, files, output, pkg_top, 
                args.config if args.config else 'default',
                install_missing=getattr(args, 'install_missing_modules', True),
                add_to_pythonpath=getattr(args, 'add_to_pythonpath', True)
            )
        else:
            print(f"Would run test generation algorithm for package {package} with output to {output}")
        print(f"Total running time: {time.time() - start_time:.2f} seconds")
    else:
        # Vòng lặp cho toàn bộ pkg như cũ (nếu không truyền test_index)
        print('NO - NO - NO')
    print(f"Total running time: {time.time() - start_time:.2f} seconds")
