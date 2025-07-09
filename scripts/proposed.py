import csv
from pathlib import Path
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
import anthropic
import openai
import re
from dotenv import load_dotenv

# Configure logging to reduce HTTP request logs
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

# Add TestGeneration to pat
# Import required modules
# import eval_overall
from eval_overall import run_evolution123
from data_utils import write_jsonl, line_code1, fix_relative_imports, parse_import_tool, remove_space, code_in_line, remove_external_imports,line_code, remove_comments_and_docstrings, solve, get_code_from_import_line, extract_python_code_block, extract_external_import_lines,extract_line, extract_test_func, find_enclosing_def_class
from utils.codetransform import static_slicing
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

# def check_and_install_common_dependencies():
#     """Check and install common dependencies that might be needed"""
#     common_deps = [
#         'pytest', 'coverage', 'tqdm', 'anthropic', 'python-dotenv'
#     ]
    
#     print("Checking common dependencies...")
#     for dep in common_deps:
#         try:
#             importlib.metadata.version(dep)
#             print(f"✓ {dep} is already installed")
#         except:
#             print(f"Installing {dep}...")
#             try:
#                 subprocess.run((f"{sys.executable} -m pip install {dep}").split(),
#                                check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
#                 print(f"✓ Installed {dep}")
#             except Exception as e:
#                 print(f"✗ Failed to install {dep}: {e}")
    
#     print("Dependency check completed.")

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

def testgeneration_multiround(client, prompt, generated_tests, system_message, install_missing=True):
    """Generate test cases with multi-round conversation"""
    template_append="Generate another test method for the function under test. Your answer must be different from previously-generated test cases, and should cover different statements and branches. CRITICAL: You MUST include ALL necessary imports at the very beginning of your test function. Always start your test with the required imports, then the test function. Try different input values, edge cases, and test scenarios but still remain function name."
    messages=[
        {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ]
    for _ in range(9):
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=messages,
            max_tokens=512,
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

def testgeneration_multiround_line(client, prompt, system_message, install_missing=True):
    """Generate test cases for specific line coverage"""
    template_append="Generate another test method for the function under test. Your answer must be different from previously-generated test cases, and should cover different statements and branches. CRITICAL: You MUST include ALL necessary imports at the very beginning of your test function. Always start your test with the required imports, then the test function. Try different input values, edge cases, and test scenarios but still remain function name."
    generated_tests=[]
    messages=[
            {"role": "user", "content": prompt},
            {"role": "system", "content": system_message},
        ]
    for _ in range(3):
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=messages,
            max_tokens=512,
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

def testgeneration_feedback(client, prompt, install_missing=True):
    """Generate test cases with execution feedback"""
    generated_tests=[]
    messages=[
            {"role": "system", "content": open('scripts/prompt/system_exec.txt').read()},
            {"role": "user", "content": prompt},
        ]
    for i in range(1):
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=messages,
            max_tokens=1024,
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
    
    # Convert relative path to absolute path using pkg_top like eval_coverup.py does
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
        # print(f'class_segment: ------------{class_segment}------------')
        # Xác định tên file an toàn
        safe_file_id = str(Path(file_path).relative_to(pkg_top)).replace('/', '_').replace('\\', '_').replace('.', '_')
        # Xử lý class_segment là object hay string
        if isinstance(class_segment, str):
            class_name = Path(file_path).stem  # hoặc 'global'
            try:
                lineno = class_segment.end - 1  # type: ignore
                class_segment_code, _, _, _ = static_slicing.static_slicing(python_code, lineno)
            except AttributeError:
                # Nếu không có attribute end thì dùng toàn bộ code
                class_segment_code = python_code
        else:
            # Nếu là CodeSegment object - sử dụng getattr để tránh lỗi linter
            class_name = getattr(class_segment, 'name', Path(file_path).stem)
            try:
                lineno = class_segment.end - 1
                class_segment_code, _, _, _ = static_slicing.static_slicing(python_code, lineno)
            except Exception as e:
                class_segment_code = python_code
                print(f"[WARNING] static_slicing failed for {file_path} (CodeSegment): {e}")
                continue
        
        response = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=[
            {"role": "system", "content": open('scripts/prompt/system_import.txt').read()},
            {"role": "user", "content": open('scripts/prompt/find_import.txt').read().format(code=remove_external_imports(class_segment_code), import_tool=extract_external_import_lines(python_code))},
        ],
            max_tokens=1024,
        )
        print(f'--------NEED IMPORT: --------- \n {response.choices[0].message.content} ---------')
        import_tool1 = response.choices[0].message.content
        try:
            import_tool1 = parse_import_tool(import_tool1)
        except Exception as e:
            print(f"[WARNING] parse_import_tool failed: {e}. import_tool1: {import_tool1}")
            import_tool1 = []
        # Flatten nếu là list các list
        def flatten_imports(imports):
            if isinstance(imports, list):
                flat = []
                for x in imports:
                    if isinstance(x, list):
                        flat.extend(x)
                    else:
                        flat.append(x)
                return flat
            return imports
        import_tool1 = flatten_imports(import_tool1)
        # Assert: tất cả phần tử phải là string, nếu không thì bỏ qua toàn bộ
        if not all(isinstance(x, str) for x in import_tool1):
            print(f"[WARNING] LLM import output sai format, bỏ qua: {import_tool1}")
            import_tool1 = []
        # Lấy code của các external tool cần thiết
        external_code = ''
        if import_tool1 != []:
            for import_line in import_tool1:
                # Xử lý trường hợp import_line là list
                if isinstance(import_line, list):
                    import_line = import_line[0] if import_line else ""
                
                if not isinstance(import_line, str):
                    print(f"[WARNING] import_line không phải string, bỏ qua: {import_line}")
                    continue
                try:
                    _, code = get_code_from_import_line(import_line)
                    if code:
                        external_code += f"\n# ===== {import_line} =====\n" + remove_space(remove_comments_and_docstrings(code)) + "\n"
                except Exception as e:
                    print(f"[WARNING] get_code_from_import_line failed for {import_line}: {e}")
        if external_code != '':
            prompt = open('scripts/prompt/template_base.txt').read().format(program=class_segment_code,import_tool=external_code, func_name=class_name)
        else:
            prompt = open('scripts/prompt/template_base_no_import.txt').read().format(program=class_segment_code, func_name=class_name)
        # if i ==0:
            # print(f'prompt: ------------{prompt}------------')
        # print(f'class_segment_code: ------------{class_segment_code}------------')
        # print(f"Generating tests for class: {class_name}")
        generated_tests = []
        generated_tests = testgeneration_multiround(client, prompt, generated_tests, system_message, install_missing=True)
        
        # Post-process generated tests to ensure correct function names
#         for idx, test_content in enumerate(generated_tests):
#             # Replace generic test function names with actual function name
#             test_content = test_content.replace('test_get_file_name', f'test_{class_name}')
#             test_content = test_content.replace('unknown_func', class_name)
#             test_content = test_content.replace('test_unknown_func', f'test_{class_name}')
#             # Fix import issues
#             test_content = test_content.replace('cookiecutter.replay.get_file_name', f'{class_name}')
#             test_content = test_content.replace('cookiecutter.replay.dump', f'{class_name}')
            
#             # Add mocks for file operations to avoid OSError
#             if 'dump(' in test_content or 'get_file_name(' in test_content or 'makedirs(' in test_content or 'replay_dir' in test_content:
#                 test_content = """import os
# import tempfile
# from pathlib import Path
# from unittest.mock import patch, mock_open, MagicMock

# # Mock file operations
# @patch('builtins.open', new_callable=mock_open)
# @patch('os.makedirs')
# @patch('pathlib.Path.mkdir')
# @patch('pathlib.Path.exists', return_value=False)
# @patch('tempfile.mkdtemp', return_value='/tmp/mocked_temp_dir')
# def test_with_mocks(mock_mkdtemp, mock_exists, mock_mkdir, mock_makedirs, mock_file):
#     mock_file.return_value.__enter__.return_value.write.return_value = None
#     mock_mkdir.return_value = None
#     mock_makedirs.return_value = None
#     mock_exists.return_value = False
#     mock_mkdtemp.return_value = '/tmp/mocked_temp_dir'
    
#     # Your test code here
#     """ + test_content
            
#             generated_tests[idx] = test_content
        
#         if i ==0:
#             print(f'prompt: ------------{prompt}------------')
        # Save generated tests for this class
        testing_data = {
            'task_num': f"{package}_{Path(file_path).stem}_{i}",
            'task_title': f"Test generation for {package} - {Path(file_path).name}",
            'code': python_code,
            'tests': generated_tests
        }
        
        test_file = output_dir / f"testing_{safe_file_id}_{i}.jsonl"
        try:
            write_jsonl([testing_data], str(test_file))
            print(f"Saved {len(generated_tests)} tests to {test_file}")
        except Exception as e:
            print(f"[WARNING] write_jsonl failed: {e}")
        
        # Tạo file test thực tế (không ghép code gốc vào)
        # if generated_tests:
        #     for idx, test_content in enumerate(generated_tests):
        #         create_test_file(test_content, output_dir, f"test_{safe_file_id}_{i}_{idx}", file_path, install_missing=True)
        
        # Measure coverage for this test set using run_evolution123
        if generated_tests:
            _, _, result_execute, run_exe = run_evolution123(
                result_execute, str(test_file), func_name=class_name, all_executed_lines=all_execution_line, line_cover=0,
                package_root=str(pkg_top.parent), package_name=pkg_top.name
            )
            
            for x in run_exe:
                if x not in all_execution_line:
                    all_execution_line.add(x)
    
    # Find missing lines after Phase 1
    for x in line_code(python_code):
        if x not in all_execution_line:
            all_missing_line.append(x)
    
    print(f"Missing lines after Phase 1: {all_missing_line}")
    
    # Sau khi phase 1 kết thúc, ghi coverage phase 1
    total_lines_set_phase1 = set(line_code(python_code))
    all_execution_line_set_phase1 = set(all_execution_line)
    additional_line_phase1 = set(line_code1(python_code)) - total_lines_set_phase1
    total_lines_set_phase1.update(additional_line_phase1)
    all_execution_line_set_phase1.update(additional_line_phase1)
    total_lines_phase1 = len(total_lines_set_phase1)
    covered_lines_phase1 = len(all_execution_line_set_phase1 & total_lines_set_phase1)
    coverage_percentage_phase1 = (covered_lines_phase1 / total_lines_phase1) * 100 if total_lines_phase1 > 0 else 0
    coverage_result_phase1 = {
        'file': file_path,
        'total_lines': total_lines_phase1,
        'covered_lines': covered_lines_phase1,
        'missing_lines': [x for x in line_code(python_code) if x not in all_execution_line],
        'coverage_percentage': coverage_percentage_phase1
    }
    try:
        with open(output_dir / f"{Path(file_path).stem}_phase1_coverage.json", "w") as f:
            json.dump(coverage_result_phase1, f, indent=2)
        print(f"Saved phase 1 coverage to {output_dir / f'{Path(file_path).stem}_phase1_coverage.json'}")
    except Exception as e:
        print(f"Error writing phase 1 coverage file: {e}")
    
    # Phase 2: Target line coverage for this file
    print(f"Phase 2: Target line coverage for {file_path}")
    missing_test = all_missing_line.copy()
    missing_final = []
    while len(missing_test) > 0:
        print(f'line code ----------{extract_line(python_code, missing_test[0])}----------------------')
        # print(f'line code real {line_code(python_code)}------------')
        lineno = missing_test[0]
        lineno1 = extract_line(python_code, lineno)
        filtered_code, _, filter_num_lines, _ = static_slicing.static_slicing(python_code, lineno)
        class_name, function_name = find_enclosing_def_class(python_code, lineno)
        if class_name == None:
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
        if function_name == None:
            function_name = ''
            
        print(f'class_name: {class_name}')
        print(f'function_name: {function_name}')
        print(f'-------------------TEST {lineno}---------- REMOVE -------------{filter_num_lines}-------------')
        
        response_line = client.chat.completions.create(
            model='deepseek-v3-0324',
            messages=[
            {"role": "system", "content": open('scripts/prompt/system_import.txt').read()},
            {"role": "user", "content": open('scripts/prompt/find_import.txt').read().format(code=remove_external_imports(filtered_code), import_tool=extract_external_import_lines(python_code))},
        ],
            max_tokens=1024,
        )
        print(f'--------NEED IMPORT: --------- \n {response_line.choices[0].message.content} ---------')
        import_tool1 = response_line.choices[0].message.content
        try:
            import_tool1 = parse_import_tool(import_tool1)
        except Exception as e:
            print(f"[WARNING] parse_import_tool failed: {e}. import_tool1: {import_tool1}")
            import_tool1 = []
        external_code = ''
        for import_line in import_tool1:
            # Xử lý trường hợp import_line là list
            if isinstance(import_line, list):
                import_line = import_line[0] if import_line else ""
            
            if isinstance(import_line, str):
                try:
                    _, code = get_code_from_import_line(import_line)
                    if code:
                        external_code += f"\n# ===== {import_line} =====\n" + remove_space(remove_comments_and_docstrings(code)) + "\n"
                except Exception as e:
                    print(f"[WARNING] get_code_from_import_line failed for {import_line}: {e}")
        # Đưa external_code vào đầu prompt
        # prompt = prompt_template.format(program=class_segment_code, func_name=class_name, import_tool=external_code)
        
        if external_code != '':
            prompt_line = open('scripts/prompt/template_line.txt').read().format(
                func_name=function_name, 
                import_tool=external_code,
                class_name=class_name, 
                program=code_in_line(filtered_code), 
                lineno=lineno1
            )
        else:
            prompt_line = open('scripts/prompt/template_line_no_import.txt').read().format(
                func_name=function_name, 
                class_name=class_name, 
                program=code_in_line(filtered_code), 
                lineno=lineno1
            )
        
        generate_test = testgeneration_multiround_line(client, prompt_line, system_message, install_missing=True)
        testing_data = {
            'task_num': f"{package}_{safe_file_id}_{lineno}",
            'task_title': f"Line coverage for {package}",
            'code': python_code,
            'tests': generate_test
        }
        
        test_file = output_dir / f"testing_{safe_file_id}_{lineno}.jsonl"
        write_jsonl([testing_data], str(test_file))
        
        _, missing_line_new, result_execute, run_exe = run_evolution123(
            result_execute, str(test_file), func_name=class_name, all_executed_lines=all_execution_line, line_cover=lineno,
            package_root=str(pkg_top.parent), package_name=pkg_top.name
        )
        for x in run_exe:
            if x not in all_execution_line:
                all_execution_line.add(x)
    
    # Find missing lines after Phase 1
        for x in line_code(python_code):
            if x not in all_execution_line:
                all_missing_line.append(x)
        
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
    
    # Sau khi phase 2 kết thúc, ghi coverage phase 2
    total_lines_set_phase2 = set(line_code(python_code))
    all_execution_line_set_phase2 = set(all_execution_line)
    additional_line_phase2 = set(line_code1(python_code)) - total_lines_set_phase2
    total_lines_set_phase2.update(additional_line_phase2)
    all_execution_line_set_phase2.update(additional_line_phase2)
    total_lines_phase2 = len(total_lines_set_phase2)
    covered_lines_phase2 = len(all_execution_line_set_phase2 & total_lines_set_phase2)
    coverage_percentage_phase2 = (covered_lines_phase2 / total_lines_phase2) * 100 if total_lines_phase2 > 0 else 0
    coverage_result_phase2 = {
        'file': file_path,
        'total_lines': total_lines_phase2,
        'covered_lines': covered_lines_phase2,
        'missing_lines': missing_final.copy(),
        'coverage_percentage': coverage_percentage_phase2
    }
    try:
        with open(output_dir / f"{Path(file_path).stem}_phase2_coverage.json", "w") as f:
            json.dump(coverage_result_phase2, f, indent=2)
        print(f"Saved phase 2 coverage to {output_dir / f'{Path(file_path).stem}_phase2_coverage.json'}")
    except Exception as e:
        print(f"Error writing phase 2 coverage file: {e}")

    # Phase 3: Generate with feedback for this file
    print(f"Phase 3: Generate with feedback for {file_path}")
    miss_feedback = []
    # dem = 0 
    while len(missing_final) > 0:
        lineno = missing_final[0]
        print(f'-------------------TEST {lineno}---------- FEEDBACK -------------')
        
        try:
            best, test_good, _, _ = solve(result_execute, python_code, lineno)
        except Exception as e:
            print(f"[WARNING] solve failed: {e}")
            best, test_good = None, None
        
        # Xử lý trường hợp solve trả về None
        if best is None or test_good is None:
            print(f'Line {lineno} cannot be solved with feedback')
            miss_feedback.append(lineno)
            missing_final.remove(lineno)
            continue
        
        try:
            test_run = extract_test_func(test_good, package)
        except Exception as e:
            print(f"[WARNING] extract_test_func failed: {e}")
            test_run = ''
        try:
            filtered_code, _, filter_num_lines, _ = static_slicing.static_slicing(python_code, lineno)
        except Exception as e:
            print(f"[WARNING] static_slicing failed: {e}")
            filtered_code = ''
        try:
            class_name, function_name = find_enclosing_def_class(python_code, lineno)
        except Exception as e:
            print(f"[WARNING] find_enclosing_def_class failed: {e}")
            class_name, function_name = Path(file_path).stem, Path(file_path).stem
        filtered_code = f'{filtered_code}\n{test_run}'
        if class_name == None:
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
        if function_name == None:
            function_name = ''
        prompt_line = open('scripts/prompt/feedback_line.txt').read().format(
            func_name=function_name, 
            class_name=class_name, 
            test=test_run, 
            code=code_in_line(execute_and_trace(filtered_code)), 
            code_linene=extract_line(python_code, lineno)
        )
        
        # print(f'Check first --------------- {code_in_line(execute_and_trace(filtered_code))} ---------')
        generate_test = testgeneration_feedback(client, prompt_line, install_missing=True)
        
        if len(generate_test) > 0:
            testing_data = {
                'task_num': f"{package}_{safe_file_id}_{lineno}_feedback",
                'code': python_code,
                'tests': generate_test
            }
            
            test_file = output_dir / f"feed_testing1_{package}_{safe_file_id}_{lineno}.jsonl"
            write_jsonl([testing_data], str(test_file))
            
            _, missing_line_new, result_execute, run_exe = run_evolution123(
                result_execute, str(test_file), func_name=class_name, all_executed_lines=all_execution_line, line_cover=lineno, 
                package_root=str(pkg_top.parent), package_name=pkg_top.name
            )
            for x in run_exe:
                if x not in all_execution_line:
                    all_execution_line.add(x)
            
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
    
    # Sau khi phase 3 kết thúc, ghi coverage phase 3
    total_lines_set_phase3 = set(line_code(python_code))
    all_execution_line_set_phase3 = set(all_execution_line)
    additional_line_phase3 = set(line_code1(python_code)) - total_lines_set_phase3
    total_lines_set_phase3.update(additional_line_phase3)
    all_execution_line_set_phase3.update(additional_line_phase3)
    total_lines_phase3 = len(total_lines_set_phase3)
    covered_lines_phase3 = len(all_execution_line_set_phase3 & total_lines_set_phase3)
    coverage_percentage_phase3 = (covered_lines_phase3 / total_lines_phase3) * 100 if total_lines_phase3 > 0 else 0
    coverage_result_phase3 = {
        'file': file_path,
        'total_lines': total_lines_phase3,
        'covered_lines': covered_lines_phase3,
        'missing_lines': miss_feedback.copy(),
        'coverage_percentage': coverage_percentage_phase3
    }
    try:
        with open(output_dir / f"{Path(file_path).stem}_phase3_coverage.json", "w") as f:
            json.dump(coverage_result_phase3, f, indent=2)
        print(f"Saved phase 3 coverage to {output_dir / f'{Path(file_path).stem}_phase3_coverage.json'}")
    except Exception as e:
        print(f"Error writing phase 3 coverage file: {e}")
    
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
        # if i <=2:
        #     continue
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
    
    # Check and install common dependencies first
    # check_and_install_common_dependencies()
    
    pkg = load_suite(args.suite)
    max_packages = 9
    pkg = dict(list(pkg.items())[:max_packages])
    
    for i, pkg_top in enumerate(pkg):
        if i <=5:
            continue            
        
        with open("repos_ran.txt", "a") as f:
            f.write(str(pkg_top) + "\n")
        print(f"Processing {pkg_top}")
    
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
            run_test_generation_algorithm(
                package, src, files, output, pkg_top, 
                args.config if args.config else 'default',
                install_missing=getattr(args, 'install_missing_modules', True),
                add_to_pythonpath=getattr(args, 'add_to_pythonpath', True)
            )
        else:
            print(f"Would run test generation algorithm for package {package} with output to {output}")
