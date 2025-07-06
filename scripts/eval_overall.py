import os
import subprocess
import json
import signal
import random
random.seed(42)
import shutil
import time
import re
from pathlib import Path
from tqdm import tqdm
from argparse import ArgumentParser
from copy import deepcopy
import sys
import trace_execution
import io
import os
import linecache
from data_utils import read_jsonl, write_jsonl, add_lineno, add_lineno_comment,line_code

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
        
        # Thêm pytest nếu có thể
        try:
            exec_globals['pytest'] = __import__('pytest')
        except ImportError:
            pass
        
        with TimeoutHandler(timeout):
            exec(test_code, exec_globals)
            return True
    except AssertionError: #assertionerror is considered as executable
        return True
    except TimeoutError:
        #print("timed out")
        return False
    except Exception as e: 
        #print(f"failed: {type(e).__name__}")
        return type(e).__name__, e #return error type and error message
    

"""Compute syntactical and execution correctness (with coverage)."""
def run_evolution123(result_execute, path, func_name, line_cover = 0):
    generated_data = read_jsonl(path)
    accuracy = []
    missing_line = []
    
    for i, data in tqdm(enumerate(generated_data)):
        total_cases=0
        total_syn_correct=0
        total_comp_correct=0
        total_exec_correct=0
        syn_failed=0
        exec_fails=[]

        total_line_cov=0
        total_branch_cov=0
        cov_line_success=0
        task_num=data['task_num']
        difficulty=data['difficulty']
        # func_name=data['func_name']
        code=data['code']
        #code=ADDITIONAL_IMPORTS+code #add possibly missing imports
        test_cases=data['tests']
    
        os.makedirs(f'tmp_{i}_{difficulty}_cuong',exist_ok=True) #create different tmp folders for different problems to avoid conflicts
        with open(f'tmp_{i}_{difficulty}_cuong/under_test.py','w') as f: #write program under test and test cases into tmp files
            f.write(code)
        passed_tests=[]
        passed_tests_code = []
        all_executed_lines = set()
        line_file = line_code(code)
        # print(f'line_code: {line_file}')
        for j, lineno in enumerate(test_cases):
            # print(lineno)
            testcase=lineno
            # print(f'testcase: {testcase}')
            #testcase=test_cases[fixed_testcase_num] #comparison: use the first test case
            total_cases+=1
            try:
                res=compile(testcase,'<string>','exec') #check syntax correctness
                print(res)
                total_syn_correct+=1

                test_code=code+f'\n{testcase}'+f'\ntest_{func_name}()'
                # print(f'-------------testcode------------{test_code}')
                # print(f'test_code: {test_code}')
                time.sleep(0.01)
                # print(f'-----------{j} ------{test_code}')
                res=execute(test_code)
                print(res)
                if res==True:
                    # if test_code.find(f'solution.{func_name}')==-1: #if the function under test is not called, also consider as failed
                    #     print('func under test not called')
                    #     exec_fails.append({'task':task_num, 'error':'not called'})
                    # else:
                    total_exec_correct+=1
                    # test_code_simple=code+testcase #write to files for computing coverage
                    with open(f'tmp_{i}_{difficulty}_cuong/test_{j}.py','w') as f:
                        f.write(test_code)
                    passed_tests.append(f'test_{j}.py')
                    passed_tests_code.append(test_code) 
                else:
                    exec_fails.append({'task':task_num,'test_line':lineno,'error':res})
                    print(res)
                    #print(test_code)
            except:
                syn_failed+=1
                # print('syntax error')
                pass
        # print(add_lineno(code))  
        print(f'---------------------- {len(passed_tests)}')     
        if len(passed_tests)>0: #start measuring coverage
            # print(f'---------------------- {len(passed_tests)}')
            for j, lineno in enumerate(passed_tests):
                test=lineno
                # print(test)
                t = trace_execution.Trace(ignoredirs=[sys.base_prefix, sys.base_exec_prefix,],
                                    trace=0, count=1)
                arguments = []
                filename = f"tmp_{i}_{difficulty}_cuong/" + test
                # print(filename)
                sys.argv = [filename, arguments]
                sys.path[0] = os.path.dirname(filename)

                code = passed_tests_code[j]
                # try to emulate __main__ namespace as much as possible
                globs = {
                    '__file__': filename,
                    '__name__': '__main__',
                    '__package__': None,
                    '__cached__': None,
                }
                terminate = True
                try:
                    t.runctx(code, globs, globs)
                except Exception as e:
                    terminate = False
                # print(f'---------------code---------------: {code}')
                source = linecache.getlines(filename)
                # print(f'---------------source---------------: {source}')
                code_line = [element.lstrip().replace('\n', '') for element in source]
                executed_lines = []
                for line in t.exe_path:
                    # if line not in executed_lines:
                    executed_lines.append(line)
                # print(f'---------------executed lines---------------: {executed_lines}')
                executed_lines = set(executed_lines)
                if (line_cover>0):
                    if (line_cover in executed_lines):
                        print(f"Line {line_cover} is covered in test {test}")
                # print(f"Execution line: {executed_lines}")
                result_execute.append({'test': code, 'executed_lines': executed_lines})
                all_executed_lines.update(executed_lines)
                # print(f"Executed lines: {executed_lines}")               
            # os.chdir('..') #exit tmp_ folder
        else: #no test cases passed
            pass
        print(f"All executed lines: {all_executed_lines}")
        # u = []
        # for x in line_file:
        #     if x not in all_executed_lines:
        #         u.append(x)
        # misssing_line[i] = u
        # print(f"Missing lines: {misssing_line}")
        
        u = 0
        m = []
        for x in line_file:
            if x not in all_executed_lines:
                u = u+1
                m.append(x)
        
        missing_line.append({i+1:m})
        accuracy.append(1- u/len(line_file))
    print(accuracy)
    print(missing_line)
    return accuracy, missing_line, result_execute, all_executed_lines

    
def parse_args():
    parser = ArgumentParser()
    parser.add_argument("--path", type=str, default='predictions/testing_feedback.jsonl')
    return parser.parse_args()


if __name__=='__main__':
    args=parse_args()
    os.chdir('/bigdisk/cuongvd17/SE/TestGeneration/')
    print(os.getcwd())
    print(args.path)
    generated_data = read_jsonl(args.path)
    accuracy, missing_line, _ = run_evolution123([], 'predictions/testing_feedback.jsonl')
    print(f'Accuracy: {accuracy}')
    print(f'Missing lines: {missing_line}')

