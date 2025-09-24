import os
import subprocess
import signal
import random
random.seed(42)
import shutil
import time
from pathlib import Path
from tqdm import tqdm
import sys
import trace_execution
import os
from data_utils import read_jsonl,line_code
import tempfile

class TimeoutHandler:
    def __init__(self, timeout, error_message=None):
        self.timeout = timeout
        self.error_message = error_message
    
    def __enter__(self):
        signal.signal(signal.SIGALRM, self.raise_timeout) #SIGALRM only support unix
        signal.alarm(self.timeout)
    
    def __exit__(self, type, value, traceback):
        signal.alarm(0)
    
    def raise_timeout(self, *args):
        raise TimeoutError(self.error_message)
    

def execute(test_code,timeout=5):
    """try to execute test code"""  
    # Assert không được override sys._getframe trong code test sinh ra
    assert 'sys._getframe' not in test_code or 'lambda' not in test_code, (
        'Test code contains sys._getframe override, which will break global Python behavior!')
    try:
        # Tạo globals với các import phổ biến
        exec_globals = {
            '__builtins__': __builtins__,
            'datetime': __import__('datetime'),
            'json': __import__('json'),
            're': __import__('re'),
            'math': __import__('math'),
            'random': __import__('random'),
            'collections': __import__('collections'),
            'time': __import__('time'),
            'os': __import__('os'),
            'sys': __import__('sys'),
            'pathlib': __import__('pathlib'),
            'Path': __import__('pathlib').Path,
            '__name__': '__main__',
        }
        
        # add pytest if possible
        try:
            exec_globals['pytest'] = __import__('pytest')
        except ImportError:
            pass
            
        # Tạo mock objects phức tạp hơn cho ansible
        class MockParser:
            def __init__(self):
                self.usage = '%prog <host-pattern> [options]'
                self.description = "Define and run a single task 'playbook' against a set of hosts"
                self.epilog = "Some actions do not make sense in Ad-Hoc (include, meta, etc)"
                self._optionals = type('MockOptionals', (), {
                    '_actions': [
                        type('MockAction', (), {'dest': 'module_args'})(),
                        type('MockAction', (), {'dest': 'module_name'})(),
                        type('MockAction', (), {'dest': 'args'})(),
                    ]
                })()
                
        class MockCLI:
            def __init__(self, *args, **kwargs):
                # Chấp nhận mọi tham số để tránh TypeError
                self.args = args[0] if args else []
                self.validate_conflicts = lambda x, y, z: None
                self.post_process_args = lambda x: x
                self.parser = MockParser()
                
            def init_parser(self):
                pass
                
        class MockDisplay:
            def __init__(self):
                self.verbosity = 0
                
        class MockOptions:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
                    
        # Thêm các biến giả để tránh NameError
        exec_globals.update({
            '_play_ds': {},  # Giả sử đây là dict
            'ansible': type('MockAnsible', (), {})(),  # Mock object
            'playbook': type('MockPlaybook', (), {})(),
            'inventory': type('MockInventory', (), {})(),
            'host': type('MockHost', (), {})(),
            'task': type('MockTask', (), {})(),
            'result': type('MockResult', (), {})(),
            'CLI': MockCLI,
            'AdHocCLI': MockCLI,
            'display': MockDisplay(),
            'Options': MockOptions,
        })
        
        # Thêm các function test có thể được gọi
        def mock_test_function(*args, **kwargs):
            # Mock function để tránh NameError
            pass
            
        # Thêm tất cả các function test có thể có
        test_functions = [
            'test_AdHocCLI', 'test_init_parser', 'test_post_process_args',
            'test_validate_conflicts', 'test_run', 'test_main',
            'test_cli', 'test_parser', 'test_options'
        ]
        
        for func_name in test_functions:
            exec_globals[func_name] = mock_test_function
        
        with TimeoutHandler(timeout):
            exec(test_code, exec_globals)
            return True
    except AssertionError: #assertionerror is considered as executable
        return True
    except TimeoutError:
        return False
    except Exception as e: 
        return type(e).__name__, e #return error type and error message
    

def run_evolution123(result_execute, path, func_name, all_executed_lines, line_cover = 0,  package_root=None, package_name=None, check_error=False):
    """
    Compute syntactical and execution correctness (with coverage) for generated tests.

    Args:
        result_execute: List to store execution results.
        path (str): Path to JSONL file containing generated test cases.
        func_name (str): Name of the function under test.
        all_executed_lines: Iterable of previously executed lines.
        line_cover (int, optional): Line number to specifically track coverage. Defaults to 0.
        package_root (optional): Root directory of the package. Defaults to None.
        package_name (optional): Name of the package. Defaults to None.
        check_error (bool, optional): Whether to collect error feedback. Defaults to False.

    Returns:
        Tuple containing:
            - accuracy (list): Syntactical correctness per test
            - missing_line (list): Lines not executed
            - result_execute (list): Details of executed lines per test
            - all_executed_lines (set): Updated set of all executed lines
            - error_feedback (dict, optional): Mapping of test line -> errors if check_error=True
    """
    
    generated_data = read_jsonl(path)
    all_executed_lines = set(all_executed_lines)
    accuracy = []
    missing_line = []
    error_feedback = {} if check_error else None
    
    for i, data in tqdm(enumerate(generated_data)):
        total_cases=0
        total_syn_correct=0
        syn_failed=0
        exec_fails=[]

        task_num=data['task_num']
        code=data['code']
        test_cases=data['tests']
    
        tmp_dir = Path(f'tmp_{i}_test')
        tmp_dir.mkdir(exist_ok=True)
        # Copy all package into tmp_dir/package_name
        package_dst = None
        if package_root and package_name:
            package_src = Path(package_root) / package_name
            package_dst = tmp_dir / package_name
            if package_dst.exists():
                shutil.rmtree(package_dst)
            inner_pypara = package_src / package_name
            if package_name == 'pypara' and inner_pypara.exists() and inner_pypara.is_dir():
                package_dst.mkdir(parents=True, exist_ok=True)
                for item in inner_pypara.iterdir():
                    dest = package_dst / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
            else:
                shutil.copytree(package_src, package_dst)
            # Ghi under_test.py vào đúng vị trí
            under_test_path = package_dst / 'under_test.py'
        else:
            under_test_path = tmp_dir / 'under_test.py'
        with open(under_test_path, 'w') as f:
            f.write(code)
        passed_tests=[]
        passed_tests_code = []
        line_file = line_code(code)
        # print(f'line_code: {line_file}')
        for j, lineno in enumerate(test_cases):
            testcase=lineno
            total_cases+=1
            try:
                res=compile(testcase,'<string>','exec') #check syntax correctness
                print(res)
                total_syn_correct+=1

                if package_dst is not None:
                    test_file_path = package_dst / f'test_{j}.py'
                else:
                    test_file_path = tmp_dir / f'test_{j}.py'
                test_code=code+f'\n{testcase}'+f'\ntest_{func_name}()'
                print(f'\n{testcase}'+f'\ntest_{func_name}()')
                time.sleep(0.01)
                # Set PYTHONPATH để import nội bộ hoạt động
                old_pythonpath = os.environ.get('PYTHONPATH', '')
                if package_dst is not None:
                    os.environ['PYTHONPATH'] = str(package_dst.parent)
                else:
                    os.environ['PYTHONPATH'] = str(tmp_dir)
                try:
                    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
                        f.write(test_code)
                        test_file = f.name
                    try:
                        print(f'Test file:   {test_file}------')
                        env = os.environ.copy()
                        print('sys.path:', sys.path)
                        print('cwd:', os.getcwd())
                        print('PYTHONPATH:', os.environ.get('PYTHONPATH'))
                        print(f'\n ----------------\n')
                        result = subprocess.run(
                            ['python', test_file],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            env=env,
                            cwd=str(tmp_dir)
                        )
                        if result.returncode == 0:
                            res = True
                        else:
                            res = ("SubprocessError", result.stderr)
                    except Exception as e:
                        res = ("SubprocessException", str(e))
                    finally:
                        os.remove(test_file)
                finally:
                    os.environ['PYTHONPATH'] = old_pythonpath
                # --- END subprocess exec ---
                print(res)
                if res==True:
                    with open(test_file_path,'w') as f:
                        f.write(test_code)
                    passed_tests.append(test_file_path.name)
                    passed_tests_code.append(test_code) 
                else:
                    exec_fails.append({'task':task_num,'test_line':lineno,'error':res})
                    print(res)
                    if check_error and error_feedback is not None:
                        error_feedback[lineno] = {'test': testcase, 'error': str(res)}
            except Exception as e:
                syn_failed+=1
                if check_error and error_feedback is not None:
                    error_feedback[lineno] = {'test': testcase, 'error': str(e)}
                pass
        print(f'--------------PASS_TESTS--------\n {len(passed_tests)} --------------\n')     
        if len(passed_tests)>0: #start measuring coverage
            for j, test_name in enumerate(passed_tests):
                if package_dst is not None:
                    filename = package_dst / test_name
                else:
                    filename = tmp_dir / test_name
                combined_code = f"""
# Source code
{code}

# Test code
{testcase}
test_{func_name}()
"""
                
                with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as combined_file:
                    combined_file.write(combined_code)
                    combined_file_path = combined_file.name
                
                t = trace_execution.Trace(ignoredirs=[sys.base_prefix, sys.base_exec_prefix], trace=0, count=1)
                arguments = []
                sys.argv = [combined_file_path, arguments]
                sys.path[0] = str(os.path.dirname(combined_file_path))
                

                
                globs = {
                    '__file__': combined_file_path,
                    '__name__': '__main__',
                    '__package__': None,
                    '__cached__': None,
                }
                terminate = True
                try:
                    t.runctx(combined_code, globs, globs)
                except Exception as e:
                    terminate = False
                finally:
                    # Clean up temporary file
                    try:
                        os.remove(combined_file_path)
                    except:
                        pass
                    
                    

                executed_lines = []
                for (filename, lineno) in t.counts:
                    # Track lines from the combined file (which includes source code)
                    if filename == combined_file_path:
                        # Map line numbers from combined file back to original source
                        # The source code is at the beginning of the combined file
                        if lineno <= len(code.split('\n')):
                            executed_lines.append(lineno)
                    elif filename == str(under_test_path):
                        executed_lines.append(lineno)
                    elif filename == '<string>':
                        # If we can't find the original file, use string lines as fallback
                        executed_lines.append(lineno)
                executed_lines = set(executed_lines)
                if (line_cover>0):
                    if (line_cover in executed_lines):
                        print(f"Line {line_cover} is covered in test {test_name}")
                result_execute.append({'test': code, 'executed_lines': executed_lines})
                all_executed_lines.update(executed_lines)
                all_executed_lines = set(all_executed_lines)
        else:
            pass
        all_executed_lines = [x for x in line_file if x in all_executed_lines]
        missing_line = [x for x in line_file if x not in all_executed_lines]

        
    if check_error and error_feedback is not None:
        return accuracy, missing_line, result_execute, all_executed_lines, error_feedback
    else:
        return accuracy, missing_line, result_execute, all_executed_lines

    


